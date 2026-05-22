import logging
import requests
from config import settings

logger = logging.getLogger(__name__)


class RocketChatService:
    """Quản lý tài khoản user trên Rocket.Chat (tạo, đăng nhập, tạo DM)."""

    def __init__(self):
        self._admin_headers = {
            "X-Auth-Token": settings.rc_auth_token,
            "X-User-Id": settings.rc_user_id,
        }
        self._bot_username = settings.rc_bot_username
        self._base_url = settings.rc_base_url

    def create_user(self, name: str, email: str, username: str, password: str) -> dict:
        """Tạo user trên Rocket.Chat bằng quyền Admin."""
        try:
            response = requests.post(
                f"{self._base_url}/api/v1/users.create",
                json={"name": name, "email": email, "username": username, "password": password, "verified": True},
                headers=self._admin_headers,
            )
            res = response.json()
            if not res.get("success"):
                logger.warning(f"RC create_user warning: {res.get('error')}")
            return res
        except Exception as e:
            logger.error(f"RC create_user error: {e}")
            return {"success": False, "error": str(e)}

    def login_user(self, username: str, password: str) -> dict:
        """Đăng nhập user để lấy auth token."""
        try:
            response = requests.post(
                f"{self._base_url}/api/v1/login",
                json={"user": username, "password": password},
            )
            return response.json()
        except Exception as e:
            logger.error(f"RC login_user error: {e}")
            return {"success": False, "error": str(e)}

    def create_im_with_bot(self, rc_user_id: str, rc_auth_token: str) -> str | None:
        """Tạo phòng DM giữa user và Bot, trả về room_id."""
        try:
            response = requests.post(
                f"{self._base_url}/api/v1/im.create",
                json={"username": self._bot_username},
                headers={"X-Auth-Token": rc_auth_token, "X-User-Id": rc_user_id},
            )
            res = response.json()
            if res.get("success"):
                return res["room"]["_id"]
            logger.error(f"RC create_im_with_bot failed: {res}")
            return None
        except Exception as e:
            logger.error(f"RC create_im_with_bot error: {e}")
            return None

    # ── Omnichannel / Livechat API ─────────────────────────────────────────────

    def register_livechat_visitor(self, token: str, name: str, email: str) -> dict:
        """Đăng ký visitor Omnichannel.

        departmentId phải truyền ở đây — RC dùng nó để route room về đúng department
        khi visitor tạo room sau đó. Không thể truyền ở /livechat/room.
        """
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
        """Tạo/lấy Livechat room cho visitor.

        Trả về (room_id, visitor_id) — cả hai cần thiết để assign agent sau đó.
        RC tự động reuse room cũ nếu đã tồn tại và chưa đóng.
        """
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
        """Set bot livechat status = available để RC routing tự assign vào room mới."""
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
