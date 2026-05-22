import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Body, FastAPI, Header, HTTPException, Request

from chains.router import router_chain
from core.config import settings
from handoff.agent import handoff_agent
from core.database import AsyncSessionLocal, engine
from models import ChatLog  # also registers ConversationSession via models/__init__.py
from models.base import Base
from models.schemas import EvalRequest, EvalResponse, LivechatWebhookPayload, ResolveRequest, RocketChatWebhookPayload
from services.rocketchat_service import rc_service
from services.session import (
    de_escalate_session,
    escalate_session,
    extract_and_merge_slots,
    get_or_create_session,
    save_session,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_room_locks: dict[str, asyncio.Lock] = {}

def _get_room_lock(room_id: str) -> asyncio.Lock:
    if room_id not in _room_locks:
        _room_locks[room_id] = asyncio.Lock()
    return _room_locks[room_id]


def _sanitize_pg(text: str | None) -> str | None:
    """Strip null bytes PostgreSQL rejects in text columns."""
    if not text:
        return text
    return text.replace('\x00', '')


def _compact_property(p: dict) -> dict:
    district = p.get("district") or {}
    return {
        "id": p.get("id"),
        "title": p.get("title", ""),
        "price_display": p.get("price_display", ""),
        "area": p.get("area", ""),
        "district": district.get("name", "") if isinstance(district, dict) else "",
    }


def _compact_for_rc(p: dict) -> dict:
    """Compact property cho PROPS JSON nhúng vào RC message — bỏ images/gps/created_at để tránh vượt Message_MaxAllowedSize."""
    district = p.get("district") or {}
    return {
        "id": p.get("id"),
        "title": p.get("title", ""),
        "price_display": p.get("price_display", ""),
        "area": p.get("area", ""),
        "address": p.get("address", ""),
        "thumbnail_url": p.get("thumbnail_url", ""),
        "type": p.get("type", ""),
        "category": p.get("category", ""),
        "bedrooms": p.get("bedrooms"),
        "bathrooms": p.get("bathrooms"),
        "district": district.get("name", "") if isinstance(district, dict) else "",
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info(f"AI Service started | mode={settings.ai_mode} | model={settings.openai_model}")
    yield
    logger.info("AI Service shutting down")


app = FastAPI(
    title="AI Service - BDS Ha Noi",
    description="LangChain Router Agent cho hệ thống tư vấn bất động sản Hà Nội",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
def health_check():
    return {"status": "ok", "mode": settings.ai_mode, "model": settings.openai_model}


async def _handle_message(room_id: str, user_name: str, text: str) -> None:
    """Xử lý một tin nhắn từ user — dùng chung cho cả outgoing webhook và livechat webhook."""
    async with _get_room_lock(room_id):
        try:
            async with AsyncSessionLocal() as db:
                session_data, history = await get_or_create_session(
                    db, room_id, settings.ai_mode, rc_username=user_name,
                )

            if session_data["is_escalated"]:
                logger.info(f"[Session] room {room_id} is escalated — bot silent, human in control")
                await rc_service.send_message_as_bot(
                    room_id,
                    "Nhân viên hỗ trợ đang tiếp nhận yêu cầu của bạn. Vui lòng chờ trong giây lát!",
                )
                return

            history_text = history.format_for_prompt()
            extracted_slots = session_data.get("extracted_slots") or {}
            user_token = session_data.get("user_token")

            # --- Run pipeline based on AI_MODE ---
            if settings.ai_mode == "handoff":
                result = await handoff_agent.run(
                    text,
                    history=history_text,
                    extracted_slots=extracted_slots,
                    user_token=user_token,
                )
            else:
                result = await router_chain.run(
                    text,
                    history=history_text,
                    extracted_slots=extracted_slots,
                    user_token=user_token,
                    last_intent=session_data.get("last_intent"),
                )
            bot_text = result["response"]
            raw_items: list = result.get("raw_items", [])

            # --- Human-in-the-loop: xử lý escalation ---
            if result.get("should_escalate"):
                escalation_reason = (
                    "max_iterations"
                    if "MAX_ITERATIONS_REACHED" in result.get("agent_chain", [])
                    else "user_request"
                )
                async with AsyncSessionLocal() as db:
                    await escalate_session(db, session_data["id"], reason=escalation_reason)
                if settings.rc_support_department_id:
                    await rc_service.forward_to_department(room_id, settings.rc_support_department_id)
                logger.info(f"[Escalate] room={room_id} user={user_name} reason={escalation_reason}")

            # --- Build message for Rocket.Chat ---
            if raw_items:
                props_json = json.dumps([_compact_for_rc(p) for p in raw_items], ensure_ascii=False, default=str)
                full_message = f"{bot_text}\n\n<!--PROPS:{props_json}-->"
            else:
                full_message = bot_text

            # --- Update session + save chat log ---
            history.add_user_message(text)
            history.add_ai_message(bot_text)
            if result.get("detected_intent") == "find_property":
                merged_slots = result.get("extracted_slots") or {}
                if result.get("raw_items"):
                    merged_slots["property_list"] = [p.get("id") for p in result["raw_items"]]
                    merged_slots["property_list_details"] = [_compact_property(p) for p in result["raw_items"]]
                elif extracted_slots.get("property_list"):
                    merged_slots["property_list"] = extracted_slots["property_list"]
            elif result.get("detected_intent") == "post_property":
                # Giữ nguyên các slots hiện có, chỉ cập nhật pending_post_property
                # Không chạy find_property slot extractor để tránh nhiễu
                merged_slots = dict(extracted_slots)
                if result.get("pending_post_property"):
                    merged_slots["pending_post_property"] = result["pending_post_property"]
                if result.get("clear_pending_post_property"):
                    merged_slots.pop("pending_post_property", None)
            else:
                merged_slots = await extract_and_merge_slots(text, history_text, extracted_slots)
                if result.get("pending_appointment"):
                    merged_slots["pending_appointment"] = result["pending_appointment"]
                if result.get("clear_pending_appointment"):
                    merged_slots.pop("pending_appointment", None)
                if result.get("raw_items"):
                    merged_slots["property_list"] = [p.get("id") for p in result["raw_items"]]
                    merged_slots["property_list_details"] = [_compact_property(p) for p in result["raw_items"]]

            async with AsyncSessionLocal() as db:
                await save_session(
                    db, session_data["id"], history, merged_slots, result.get("detected_intent"),
                )
                db.add(ChatLog(
                    session_id=session_data["id"],
                    user_message=text,
                    pipeline=settings.ai_mode,
                    detected_intent=result.get("detected_intent"),
                    confidence_score=result.get("confidence_score"),
                    agent_chain=result.get("agent_chain", []),
                    bot_response=_sanitize_pg(bot_text),
                    retrieved_context=_sanitize_pg(result.get("retrieved_context")),
                    latency_ms=result.get("latency_ms"),
                ))
                await db.commit()

            print("\n" + "=" * 60)
            print(f"USER    [{user_name}]: {text}")
            print(f"INTENT  : {result.get('detected_intent')} ({result.get('confidence_score') or 0:.2f})")
            print(f"CHAIN   : {' → '.join(result.get('agent_chain', []))}")
            print(f"HISTORY : {session_data['turn_count']} turn(s) | slots={merged_slots}")
            print(f"BOT     : {bot_text}")
            if raw_items:
                print(f"CARDS   : {len(raw_items)} BĐS | IDs: {[p.get('id') for p in raw_items]}")
            print(f"LATENCY : {result.get('latency_ms')} ms")
            print("=" * 60 + "\n")

            await rc_service.send_message_as_bot(room_id, full_message)

        except Exception:
            logger.exception(f"[Webhook] error processing message from {user_name!r}: {text!r}")


@app.post("/webhooks/rocketchat/outgoing")
async def rocketchat_outgoing_webhook(
    payload: RocketChatWebhookPayload, background_tasks: BackgroundTasks
):
    """Outgoing webhook (DM rooms) — giữ để tương thích ngược."""
    if payload.user_id == settings.rc_bot_user_id:
        return {"status": "ignored"}
    if not payload.text.strip():
        return {"status": "ignored"}

    logger.info(f"[Outgoing] [{payload.user_name}] room={payload.channel_id} | text={payload.text!r}")
    background_tasks.add_task(_handle_message, payload.channel_id, payload.user_name, payload.text)
    return {"status": "success"}


@app.post("/webhooks/rocketchat/livechat")
async def rocketchat_livechat_webhook(
    request: Request,
    payload: LivechatWebhookPayload,
    background_tasks: BackgroundTasks,
    x_rocketchat_livechat_token: str = Header(default=""),
):
    """RC Omnichannel Webhook — nhận tin nhắn từ Livechat visitor.

    Cấu hình tại: RC Admin → Omnichannel → Webhooks → URL = /webhooks/rocketchat/livechat
    Bật sự kiện: Visitor messages (KHÔNG bật Agent messages để tránh vòng lặp).
    Secret Token: RC gửi qua header X-Rocketchat-Livechat-Token.
    """
    # Verify secret token nếu đã cấu hình trong .env
    if settings.rc_livechat_secret:
        if x_rocketchat_livechat_token != settings.rc_livechat_secret:
            logger.warning("[Livechat] invalid secret token — request rejected")
            raise HTTPException(status_code=403, detail="Invalid livechat secret token")

    raw_body = await request.body()

    first_msg = payload.messages[0] if payload.messages else {}
    room_id: str = payload.room.get("_id", "") or first_msg.get("rid", "")
    visitor_token: str = payload.visitor.get("token", "")
    text: str = first_msg.get("msg", "")

    # RC gửi "LivechatSession" khi agent đóng conversation — dùng để auto de-escalate
    if payload.type == "LivechatSession":
        closed_at = payload.room.get("closedAt") or payload.room.get("closed_at")
        served_by = payload.room.get("servedBy") or {}
        staff_username: str | None = served_by.get("username") or None
        if room_id and closed_at:
            async with AsyncSessionLocal() as db:
                success = await de_escalate_session(db, room_id, staff_id=staff_username)
            if success:
                logger.info(f"[Livechat] room {room_id} closed by agent={staff_username!r} — session de-escalated")
            else:
                logger.info(f"[Livechat] room {room_id} closed but no escalated session found")
        return {"status": "ok", "type": "LivechatSession"}

    if payload.type != "Message":
        return {"status": "ignored", "type": payload.type}

    sender = payload.messages[0].get("u", {}) if payload.messages else {}
    sender_id: str = sender.get("_id", "")
    sender_username: str = sender.get("username", "")
    visitor_id: str = payload.visitor.get("_id", "")

    # Bỏ qua tin nhắn của bot
    if sender_id == settings.rc_bot_user_id:
        return {"status": "ignored"}

    is_agent_message = bool(sender_id) and sender_id != visitor_id

    # Agent gõ "!bot" → chuyển lại quyền điều khiển cho AI
    if is_agent_message and text.strip() == "!bot" and room_id:
        async with AsyncSessionLocal() as db:
            success = await de_escalate_session(db, room_id, staff_id=sender_username)
        if success:
            await rc_service.send_message_as_bot(
                room_id,
                "Nhân viên đã hoàn tất hỗ trợ. Tôi (trợ lý AI) đã sẵn sàng tiếp tục hỗ trợ bạn!",
            )
            logger.info(f"[Livechat] agent {sender_username!r} triggered !bot — room={room_id} de-escalated")
        return {"status": "ok"}

    # Bỏ qua mọi tin nhắn agent khác (không phải !bot)
    if is_agent_message:
        return {"status": "ignored"}

    if not room_id or not visitor_token or not text.strip():
        logger.warning(f"[Livechat] ignored — missing fields: room={room_id!r} visitor={visitor_token!r} text={text!r}")
        return {"status": "ignored"}

    logger.info(f"[Livechat] dispatching → visitor={visitor_token!r} room={room_id} text={text!r}")
    background_tasks.add_task(_handle_message, room_id, visitor_token, text)
    return {"status": "success"}


@app.post("/webhooks/session/{room_id}/resolve")
async def resolve_escalated_session(
    room_id: str,
    x_internal_key: str = Header(default=""),
    body: ResolveRequest = Body(default_factory=ResolveRequest),
):
    """Nhân viên gọi endpoint này sau khi hỗ trợ xong — AI sẽ tiếp quản trở lại.

    Body (tuỳ chọn): {"staff_id": "rc_username_of_staff"}
    """
    if x_internal_key != settings.internal_api_key:
        raise HTTPException(status_code=403, detail="Invalid internal API key")

    async with AsyncSessionLocal() as db:
        success = await de_escalate_session(db, room_id, staff_id=body.staff_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"Session not found for room_id={room_id!r}")

    await rc_service.send_message_as_bot(
        room_id,
        "Cảm ơn bạn đã liên hệ! Nhân viên đã hoàn tất hỗ trợ. "
        "Tôi (trợ lý AI) đã sẵn sàng tiếp tục hỗ trợ bạn nhé!",
    )
    logger.info(f"[Resolve] session de-escalated room={room_id} by staff={body.staff_id!r}")
    return {"status": "ok", "room_id": room_id, "resolved_by": body.staff_id}


@app.post("/eval", response_model=EvalResponse)
async def eval_pipeline(request: EvalRequest):
    """Endpoint đánh giá pipeline AI - dùng cho testing và benchmarking."""
    start = time.monotonic()

    reply = f"[eval placeholder] pipeline={request.pipeline} | input={request.user_message}"
    latency = int((time.monotonic() - start) * 1000)

    return EvalResponse(
        response=reply,
        detected_intent=None,
        confidence_score=None,
        agent_chain=[request.pipeline],
        retrieved_context=None,
        latency_ms=latency,
        llm_tokens_used=None,
        eval_expected_intent=request.expected_intent,
        eval_expected_keywords=request.expected_keywords,
        eval_expected_slots=request.expected_slots,
        eval_is_multi_turn=request.is_multi_turn,
    )
