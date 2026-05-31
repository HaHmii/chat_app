from pydantic import BaseModel

class RocketChatWebhookPayload(BaseModel):
    channel_id: str
    user_id: str
    user_name: str
    token: str | None = None        # RC bỏ qua nếu không bật token verification
    channel_name: str | None = None # Vắng mặt trong một số DM payload
    text: str = ""                  # RC có thể gửi rỗng cho system message
    message_id: str | None = None


class LivechatWebhookPayload(BaseModel):
    """Payload từ RC Admin → Omnichannel → Webhooks.

    Chỉ fire cho Livechat room, chỉ khi visitor gửi tin (agent messages
    không trigger nếu không bật tùy chọn 'Agent messages' trong RC).
    """
    type: str = ""          # "Message" | "LivechatSession" | ...
    visitor: dict = {}      # { token, name, email, ... }
    room: dict = {}         # { _id, servedBy, ... }
    messages: list[dict] = []  # [{ msg, _id, ts, u, ... }]

class ResolveRequest(BaseModel):
    staff_id: str | None = None


class EvalRequest(BaseModel):
    user_message: str
    pipeline: str = "router"
    is_multi_turn: bool = False
    turn_history: list[dict] | None = None
    user_token: str | None = None
    last_intent: str | None = None
    extracted_slots: dict | None = None

class EvalResponse(BaseModel):
    response: str
    detected_intent: str | None
    confidence_score: float | None
    agent_chain: list[str]
    retrieved_context: str | None
    latency_ms: int | None
    llm_tokens_used: int | None
    llm_calls: int | None = None
    raw_items: list | None = None
    total_items_found: int | None = None  # tổng BĐS DB trả về (trước khi cắt batch)
    should_escalate: bool = False
    extracted_slots: dict | None = None
