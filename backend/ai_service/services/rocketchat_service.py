import logging

import httpx

from core.config import settings

logger = logging.getLogger(__name__)


class RocketChatService:
    """Gửi tin nhắn từ bot qua Incoming Webhook."""

    def __init__(self):
        self._webhook_url = settings.rocketchat_webhook_url

    async def send_message_as_bot(self, room_id: str, text: str) -> bool:
        payload = {
            "channel": room_id,
            "text": text,
            "alias": "Trợ lý AI",
            "avatar": "https://cdn-icons-png.flaticon.com/512/4712/4712035.png",
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self._webhook_url, json=payload, timeout=10.0)
            if response.status_code != 200:
                logger.error(f"RC webhook failed: {response.status_code} | {response.text}")
                return False
            return True
        except Exception as e:
            logger.error(f"RC send_message_as_bot error: {e}")
            return False

rc_service = RocketChatService()
