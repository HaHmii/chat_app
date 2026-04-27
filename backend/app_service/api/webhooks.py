import logging
from fastapi import APIRouter, Request

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
logger = logging.getLogger(__name__)

@router.post("/rocketchat/outgoing")
async def rocketchat_outgoing(request: Request):
    """
    Nhận outgoing webhook từ Rocket.Chat.
    Xử lý AI được chuyển sang ai_service — endpoint này chỉ còn dùng để xác nhận
    kết nối hoặc làm fallback khi ai_service chưa sẵn sàng.
    """
    data = await request.json()
    logger.info(f"Received RC webhook (forwarded to ai_service): {data}")
    return {"status": "success"}
