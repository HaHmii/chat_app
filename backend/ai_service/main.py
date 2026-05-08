import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI

from chains.router import router_chain
from core.config import settings
from core.database import AsyncSessionLocal, engine
from models import ChatLog  # also registers ConversationSession via models/__init__.py
from models.base import Base
from models.schemas import EvalRequest, EvalResponse, RocketChatWebhookPayload
from services.rocketchat_service import rc_service
from services.session import extract_and_merge_slots, get_or_create_session, save_session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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


@app.post("/webhooks/rocketchat/outgoing")
async def rocketchat_webhook(payload: RocketChatWebhookPayload, background_tasks: BackgroundTasks):
    """Nhận outgoing webhook từ Rocket.Chat, xử lý qua RouterChain, trả lời bot."""
    if payload.user_id == settings.rocketchat_bot_user_id:
        return {"status": "ignored"}

    if not payload.text.strip():
        return {"status": "ignored"}

    logger.info(f"[{payload.user_name}] room={payload.channel_id} | text={payload.text!r}")

    async def _process_and_reply():
        try:
            # --- GUARD 3: Load session, check escalation ---
            async with AsyncSessionLocal() as db:
                session_data, history = await get_or_create_session(
                    db, payload.channel_id, settings.ai_mode,
                    rc_username=payload.user_name,
                )

            if session_data["is_escalated"]:
                logger.info(f"[Session] room {payload.channel_id} is escalated — skipping")
                return

            history_text = history.format_for_prompt()
            extracted_slots = session_data.get("extracted_slots") or {}
            user_token = session_data.get("user_token")

            # --- Run RouterChain with session context ---
            result = await router_chain.run(
                payload.text,
                history=history_text,
                extracted_slots=extracted_slots,
                user_token=user_token,
                last_intent=session_data.get("last_intent"),
            )
            text = result["response"]
            raw_items: list = result.get("raw_items", [])

            # --- Build message for Rocket.Chat ---
            if raw_items:
                props_json = json.dumps(raw_items, ensure_ascii=False, default=str)
                full_message = f"{text}\n\n<!--PROPS:{props_json}-->"
            else:
                full_message = text

            # --- Update session + save chat log ---
            history.add_user_message(payload.text)
            history.add_ai_message(text)
            if result.get("detected_intent") == "find_property":
                merged_slots = result.get("extracted_slots") or {}
                if result.get("raw_items"):
                    merged_slots["property_list"] = [p.get("id") for p in result["raw_items"]]
                elif extracted_slots.get("property_list"):
                    merged_slots["property_list"] = extracted_slots["property_list"]
            else:
                merged_slots = await extract_and_merge_slots(payload.text, history_text, extracted_slots)
                if result.get("pending_appointment"):
                    merged_slots["pending_appointment"] = result["pending_appointment"]
                if result.get("clear_pending_appointment"):
                    merged_slots.pop("pending_appointment", None)

            async with AsyncSessionLocal() as db:
                await save_session(
                    db,
                    session_data["id"],
                    history,
                    merged_slots,
                    result.get("detected_intent"),
                )
                db.add(ChatLog(
                    session_id=session_data["id"],
                    user_message=payload.text,
                    pipeline="router",
                    detected_intent=result.get("detected_intent"),
                    confidence_score=result.get("confidence_score"),
                    agent_chain=result.get("agent_chain", []),
                    bot_response=text,
                    retrieved_context=result.get("retrieved_context"),
                    latency_ms=result.get("latency_ms"),
                ))
                await db.commit()

            # --- Terminal debug ---
            print("\n" + "=" * 60)
            print(f"USER    [{payload.user_name}]: {payload.text}")
            print(f"INTENT  : {result.get('detected_intent')} ({result.get('confidence_score', 0):.2f})")
            print(f"CHAIN   : {' → '.join(result.get('agent_chain', []))}")
            print(f"HISTORY : {session_data['turn_count']} turn(s) | slots={merged_slots}")
            print(f"BOT     : {text}")
            if raw_items:
                ids = [p.get("id") for p in raw_items]
                print(f"CARDS   : {len(raw_items)} BĐS | IDs: {ids}")
            print(f"LATENCY : {result.get('latency_ms')} ms")
            print("=" * 60 + "\n")

            await rc_service.send_message_as_bot(payload.channel_id, full_message)

        except Exception:
            logger.exception(f"[Webhook] error processing message from {payload.user_name!r}: {payload.text!r}")

    background_tasks.add_task(_process_and_reply)
    return {"status": "success"}


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
