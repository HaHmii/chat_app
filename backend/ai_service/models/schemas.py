from pydantic import BaseModel

class RocketChatWebhookPayload(BaseModel):
    channel_id: str
    user_id: str
    user_name: str
    token: str | None = None        # RC bỏ qua nếu không bật token verification
    channel_name: str | None = None # Vắng mặt trong một số DM payload
    text: str = ""                  # RC có thể gửi rỗng cho system message
    message_id: str | None = None

class EvalRequest(BaseModel):
    user_message: str
    pipeline: str = "router"
    expected_intent: str | None = None
    expected_keywords: list[str] | None = None
    expected_slots: dict | None = None
    is_multi_turn: bool = False
    turn_history: list[dict] | None = None

class EvalResponse(BaseModel):
    response: str
    detected_intent: str | None
    confidence_score: float | None
    agent_chain: list[str]
    retrieved_context: str | None
    latency_ms: int | None
    llm_tokens_used: int | None
    eval_expected_intent: str | None
    eval_expected_keywords: list[str] | None
    eval_expected_slots: dict | None
    eval_is_multi_turn: bool
