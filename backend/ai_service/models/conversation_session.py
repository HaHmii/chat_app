from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String

from core.utils import vn_now
from models.base import Base


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rocketchat_room_id = Column(String(100), nullable=False, index=True)
    pipeline = Column(String(50), nullable=False, default="router")
    user_id = Column(String(100))
    messages = Column(JSON, default=list)
    extracted_slots = Column(JSON, default=dict)
    last_intent = Column(String(50))
    is_escalated = Column(Boolean, default=False)
    user_token = Column(String(1024))
    last_active_at = Column(DateTime, default=vn_now)
    turn_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=vn_now)
