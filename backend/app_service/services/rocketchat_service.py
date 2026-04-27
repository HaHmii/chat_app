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


rc_service = RocketChatService()
