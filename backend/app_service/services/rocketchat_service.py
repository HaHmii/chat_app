import logging

import requests

from config import settings

logger = logging.getLogger(__name__)


class RocketChatService:
    """Rocket.Chat Omnichannel/Livechat integration."""

    def __init__(self):
        self._base_url = settings.rc_base_url

    def register_livechat_visitor(self, token: str, name: str, email: str) -> dict:
        """Register or update an Omnichannel visitor."""
        try:
            visitor_payload: dict = {"token": token, "name": name, "email": email}
            if settings.rc_livechat_department_id:
                visitor_payload["department"] = settings.rc_livechat_department_id
            response = requests.post(
                f"{self._base_url}/api/v1/livechat/visitor",
                json={"visitor": visitor_payload},
            )
            res = response.json()
            if not res.get("success"):
                logger.warning(f"RC register_livechat_visitor warning: {res.get('error')}")
            return res
        except Exception as e:
            logger.error(f"RC register_livechat_visitor error: {e}")
            return {"success": False, "error": str(e)}

    def create_livechat_room(self, visitor_token: str) -> tuple[str, str] | None:
        """Create or fetch the open Livechat room for a visitor."""
        try:
            response = requests.get(
                f"{self._base_url}/api/v1/livechat/room",
                params={"token": visitor_token},
            )
            res = response.json()
            if res.get("success"):
                room = res["room"]
                room_id = room["_id"]
                visitor_id = room.get("v", {}).get("_id", "")
                return room_id, visitor_id
            logger.error(f"RC create_livechat_room failed: {res}")
            return None
        except Exception as e:
            logger.error(f"RC create_livechat_room error: {e}")
            return None

    def ensure_bot_livechat_available(self) -> bool:
        """Set bot livechat status to available so RC can route rooms to it."""
        try:
            status_res = requests.post(
                f"{self._base_url}/api/v1/livechat/agent.status",
                json={"status": "available"},
                headers={
                    "X-Auth-Token": settings.rc_bot_auth_token,
                    "X-User-Id": settings.rc_bot_user_id,
                },
            ).json()

            if status_res.get("success"):
                logger.info("Bot livechat status set to available")
                return True

            logger.warning(f"RC agent.status failed: {status_res.get('error')}")
            return False
        except Exception as e:
            logger.error(f"RC ensure_bot_livechat_available error: {e}")
            return False


rc_service = RocketChatService()
