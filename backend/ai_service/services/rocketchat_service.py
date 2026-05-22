import logging

import httpx

from core.config import settings

logger = logging.getLogger(__name__)


class RocketChatService:
    """Gửi tin nhắn từ bot qua Incoming Webhook."""

    def __init__(self):
        self._webhook_url = settings.rc_webhook_url

    async def send_message_as_bot(self, room_id: str, text: str) -> bool:
        """Gửi tin nhắn vào room (DM hoặc Livechat) bằng REST API của bot.

        Dùng chat.sendMessage thay vì incoming webhook để hỗ trợ cả DM lẫn
        Livechat room — incoming webhook chỉ hoạt động với channel thường.
        """
        headers = {
            "X-Auth-Token": settings.rc_auth_token,
            "X-User-Id": settings.rc_bot_user_id,
            "Content-Type": "application/json",
        }
        payload = {"message": {"rid": room_id, "msg": text}}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{settings.rc_url}/api/v1/chat.sendMessage",
                    json=payload,
                    headers=headers,
                    timeout=10.0,
                )
            if response.status_code != 200:
                logger.error(f"RC sendMessage failed: {response.status_code} | {response.text[:120]}")
                return False
            return True
        except Exception as e:
            logger.error(f"RC send_message_as_bot error: {e}")
            return False

    async def notify_support(
        self,
        user_room_id: str,
        username: str,
        reason: str,
        turn_count: int,
    ) -> bool:
        """Gửi alert vào chính room của user để nhân viên thấy khi mở Omnichannel inbox."""
        reason_label = {
            "user_request": "Người dùng yêu cầu hỗ trợ trực tiếp",
            "max_iterations": "Bot đạt giới hạn vòng lặp (yêu cầu quá phức tạp)",
            "error": "Lỗi hệ thống trong quá trình xử lý",
        }.get(reason, reason)

        text = (
            f"*[Yêu cầu hỗ trợ trực tiếp]*\n"
            f"Người dùng: `{username}` | Số lượt hội thoại: {turn_count}\n"
            f"Lý do: {reason_label}\n"
            f"Nhân viên vui lòng tiếp nhận hội thoại này."
        )

        return await self.send_message_as_bot(user_room_id, text)

    async def forward_to_department(self, room_id: str, department_id: str) -> bool:
        """Forward livechat room đến department để agent tiếp nhận."""
        headers = {
            "X-Auth-Token": settings.rc_auth_token,
            "X-User-Id": settings.rc_bot_user_id,
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{settings.rc_url}/api/v1/livechat/room.forward",
                    json={"roomId": room_id, "departmentId": department_id},
                    headers=headers,
                    timeout=10.0,
                )
            if response.status_code != 200:
                logger.error(f"RC room.forward failed: {response.status_code} | {response.text[:120]}")
                return False
            logger.info(f"[RC] room={room_id} forwarded to department={department_id}")
            return True
        except Exception as e:
            logger.error(f"RC forward_to_department error: {e}")
            return False


rc_service = RocketChatService()
