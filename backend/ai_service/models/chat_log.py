from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, Text
from core.utils import vn_now
from models.base import Base


class ChatLog(Base):
    __tablename__ = "chat_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, default=0, nullable=False)
    user_message = Column(Text, nullable=False)
    pipeline = Column(String(50))
    detected_intent = Column(String(50))
    confidence_score = Column(Float)
    agent_chain = Column(JSON)
    bot_response = Column(Text)
    retrieved_context = Column(Text)
    latency_ms = Column(Integer)
    created_at = Column(DateTime, default=vn_now)
