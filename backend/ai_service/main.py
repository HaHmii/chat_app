import logging
import time
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI

from core.config import settings
from models.schemas import EvalRequest, EvalResponse, RocketChatWebhookPayload
from services.rocketchat_service import rc_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    """Nhận outgoing webhook từ Rocket.Chat, xử lý qua AI agent, trả lời bot."""
    if payload.user_id == settings.rocketchat_bot_user_id:
        return {"status": "ignored"}

    if not payload.text.strip():
        return {"status": "ignored"}

    logger.info(f"[{payload.user_name}] room={payload.channel_id} | text={payload.text!r}")

    reply = f"Xin chào {payload.user_name}, tôi đang xử lý yêu cầu của bạn..."

    background_tasks.add_task(rc_service.send_message_as_bot, payload.channel_id, reply)
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
