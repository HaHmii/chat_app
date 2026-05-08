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


async def _fetch_user_token(rc_username: str) -> str | None:
    """Lấy JWT của user từ app_service bằng RC username."""
    try:
        resp = httpx.post(
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
        session = ConversationSession(
            rocketchat_room_id=room_id,
            pipeline=pipeline,
            user_id=rc_username,
            user_token=user_token,
            messages=[],
            extracted_slots={},
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
                await db.commit()
                logger.info(f"[Session] refreshed user token id={session.id} user={rc_username}")

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
