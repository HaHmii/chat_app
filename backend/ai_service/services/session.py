import base64
import json
import logging
from datetime import timedelta

import httpx
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.utils import vn_now
from memory.postgres_history import PostgresChatMessageHistory
from models.conversation_session import ConversationSession

logger = logging.getLogger(__name__)

_SLOT_LLM = ChatOpenAI(
    model=settings.openai_model,
    api_key=settings.openai_api_key,
    temperature=0,
)

_SLOT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Trích xuất thông tin tìm BĐS từ câu hỏi. Trả JSON thuần (không markdown).\n"
     'Template: {{"district":null,"min_price":null,"max_price":null,"min_area":null,"property_type":null,"bedrooms":null,"category":null}}\n'
     "Chỉ bao gồm key nếu đề cập rõ ràng. Giá lưu số thô (3 triệu=3, 1.5 tỷ=1.5).\n"
     "Lịch sử: {history}"),
    ("human", "{message}"),
])

_slot_chain = _SLOT_PROMPT | _SLOT_LLM | StrOutputParser()


def _decode_jwt_role(token: str) -> str | None:
    """Decode JWT payload (không verify) để lấy claim 'role'."""
    try:
        payload_b64 = token.split('.')[1]
        payload_b64 += '=' * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload.get("role")
    except Exception:
        return None


async def _fetch_user_token(rc_username: str) -> str | None:
    """Lấy JWT của user từ app_service bằng RC username."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.web_service_url}/auth/internal/token",
                params={"rc_username": rc_username},
                headers={"x-internal-key": settings.internal_api_key},
                timeout=5.0,
            )
        if resp.status_code == 200:
            return resp.json().get("access_token")
        logger.warning(f"[Session] fetch token failed: {resp.status_code} {resp.text[:100]}")
    except Exception as e:
        logger.warning(f"[Session] fetch token error: {e}")
    return None


async def get_or_create_session(
    db: AsyncSession,
    room_id: str,
    pipeline: str,
    rc_username: str | None = None,
) -> tuple[dict, PostgresChatMessageHistory]:
    stmt = select(ConversationSession).where(
        ConversationSession.rocketchat_room_id == room_id,
        ConversationSession.pipeline == pipeline,
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if session is None:
        user_token = await _fetch_user_token(rc_username) if rc_username else None
        initial_slots: dict = {}
        if user_token:
            role = _decode_jwt_role(user_token)
            if role:
                initial_slots["user_role"] = role
        session = ConversationSession(
            rocketchat_room_id=room_id,
            pipeline=pipeline,
            rc_user=rc_username,
            user_token=user_token,
            messages=[],
            extracted_slots=initial_slots,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        logger.info(f"[Session] created id={session.id} room={room_id} user={rc_username} token={'ok' if user_token else 'none'}")
    else:
        timeout = timedelta(hours=settings.session_timeout_hours)
        if session.last_active_at and vn_now() - session.last_active_at > timeout:
            session.messages = []
            session.extracted_slots = {}
            await db.commit()
            logger.info(f"[Session] reset (expired) id={session.id}")

        if rc_username:
            user_token = await _fetch_user_token(rc_username)
            if user_token and user_token != session.user_token:
                session.user_token = user_token
                role = _decode_jwt_role(user_token)
                if role:
                    current_slots = dict(session.extracted_slots or {})
                    current_slots["user_role"] = role
                    session.extracted_slots = current_slots
                await db.commit()
                logger.info(f"[Session] refreshed user token id={session.id} user={rc_username} role={role!r}")

    history = PostgresChatMessageHistory(session_id=session.id)
    history.load(session.messages or [])

    return {
        "id": session.id,
        "is_escalated": session.is_escalated or False,
        "extracted_slots": session.extracted_slots or {},
        "last_intent": session.last_intent,
        "turn_count": session.turn_count or 0,
        "user_token": session.user_token,
    }, history


async def save_session(
    db: AsyncSession,
    session_id: int,
    history: PostgresChatMessageHistory,
    extracted_slots: dict,
    last_intent: str | None,
) -> None:
    stmt = select(ConversationSession).where(ConversationSession.id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is None:
        return

    session.messages = history.to_json()
    session.extracted_slots = extracted_slots
    session.last_intent = last_intent
    session.last_active_at = vn_now()
    session.turn_count = (session.turn_count or 0) + 1
    await db.commit()


async def escalate_session(
    db: AsyncSession,
    session_id: int,
    reason: str = "user_request",
) -> None:
    """Đánh dấu session là escalated — AI sẽ không xử lý các tin nhắn tiếp theo."""
    stmt = select(ConversationSession).where(ConversationSession.id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is None:
        return
    session.is_escalated = True
    session.escalated_at = vn_now()
    session.escalation_reason = reason
    await db.commit()
    logger.info(f"[Session] escalated id={session_id} reason={reason!r}")


async def de_escalate_session(
    db: AsyncSession,
    room_id: str,
    staff_id: str | None = None,
) -> bool:
    """Nhân viên đã xử lý xong — reset session để AI tiếp tục hỗ trợ."""
    stmt = select(ConversationSession).where(ConversationSession.rocketchat_room_id == room_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is None:
        return False
    session.is_escalated = False
    session.escalated_at = None
    session.escalation_reason = None
    session.rc_staff = staff_id
    session.messages = []
    session.extracted_slots = {}
    await db.commit()
    logger.info(f"[Session] de-escalated room={room_id} by staff={staff_id!r}")
    return True


async def extract_and_merge_slots(
    user_message: str,
    history_text: str,
    current_slots: dict,
) -> dict:
    try:
        raw_json = await _slot_chain.ainvoke({
            "message": user_message,
            "history": history_text,
        })
        parsed = json.loads(raw_json.strip())
        new_slots = {k: v for k, v in parsed.items() if v is not None}
        merged = {**current_slots, **new_slots}
        if new_slots:
            logger.info(f"[SlotMerge] new={new_slots} merged={merged}")
        return merged
    except Exception as e:
        logger.warning(f"[SlotMerge] failed: {e}")
        return dict(current_slots)
