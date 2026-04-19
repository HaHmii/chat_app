from fastapi import APIRouter, Request, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from database import get_db
from models.user import User
from services.rocketchat_service import rc_service
import logging

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
logger = logging.getLogger(__name__)

@router.post("/rocketchat/outgoing")
async def rocketchat_outgoing(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Nhận webhook từ RocketChat khi có tin nhắn mới.
    """
    try:
        data = await request.json()
        logger.info(f"Received RC Outgoing Webhook: {data}")
        room_id = data.get("channel_id") or data.get("room_id") or data.get("rid")
        rc_user_id = data.get("user_id")
        rc_user_name = data.get("user_name")
        text = data.get("text", "").strip().lower()

        if not room_id:
            logger.error(f"Outgoing Webhook missing room_id/channel_id. Payload: {data}")
            return {"status": "error", "message": "missing channel_id"}

        if rc_user_name == rc_service.RC_BOT_USERNAME:
            return {"status": "ignored"}

        user = db.query(User).filter(User.rc_user_id == rc_user_id).first()
        full_name = user.full_name if user else rc_user_name
        target_username = user.username if user else rc_user_name

        # Phản hồi đơn giản
        if any(greet in text for greet in ["xin chào", "hi", "hello"]):
            reply_text = f"Xin chào {full_name}, tôi là AI tư vấn bất động sản. Tôi có thể giúp gì cho bạn?"
            background_tasks.add_task(
                rc_service.send_message_via_webhook, 
                room_id, 
                reply_text, 
                target_username
            )

        return {"status": "success"}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"status": "error", "message": str(e)}
