import requests
import os
import logging
from dotenv import load_dotenv

load_dotenv()

RC_URL = os.getenv("RC_BASE_URL", "http://localhost:3000")
RC_ADMIN_ID = os.getenv("RC_USER_ID")
RC_ADMIN_TOKEN = os.getenv("RC_AUTH_TOKEN")
RC_BOT_USERNAME = os.getenv("RC_BOT_USERNAME", "bot.ai")
RC_WEBHOOK_URL = os.getenv("RC_WEBHOOK_URL")

logger = logging.getLogger(__name__)

class RocketChatService:
    def __init__(self):
        self.headers = {
            "X-Auth-Token": RC_ADMIN_TOKEN,
            "X-User-Id": RC_ADMIN_ID
        }
        self.RC_BOT_USERNAME = RC_BOT_USERNAME
        if not RC_ADMIN_TOKEN or not RC_ADMIN_ID:
            logger.warning("RocketChat Admin Token or ID is missing in environment variables")

    def create_user(self, name, email, username, password):
        """Tạo user trên RocketChat bằng quyền Admin"""
        try:
            url = f"{RC_URL}/api/v1/users.create"
            payload = {
                "name": name,
                "email": email,
                "username": username,
                "password": password,
                "verified": True
            }
            response = requests.post(url, json=payload, headers=self.headers)
            res_json = response.json()
            if not res_json.get("success"):
                logger.warning(f"RC user creation warning: {res_json.get('error')}")
            return res_json
        except Exception as e:
            logger.error(f"Error creating RocketChat user: {e}")
            return {"success": False, "error": str(e)}

    def login_user(self, username, password):
        """Đăng nhập user để lấy auth token"""
        try:
            url = f"{RC_URL}/api/v1/login"
            payload = {"user": username, "password": password}
            response = requests.post(url, json=payload)
            return response.json()
        except Exception as e:
            logger.error(f"Error logging in RocketChat user: {e}")
            return {"success": False, "error": str(e)}

    def create_im_with_bot(self, rc_user_id, rc_auth_token):
        """Tạo phòng chat DM giữa user và Bot sử dụng token của User"""
        try:
            url = f"{RC_URL}/api/v1/im.create"
            headers = {
                "X-Auth-Token": rc_auth_token,
                "X-User-Id": rc_user_id
            }
            payload = {"username": self.RC_BOT_USERNAME}
            response = requests.post(url, json=payload, headers=headers)
            res_json = response.json()
            if res_json.get("success"):
                return res_json["room"]["_id"]
            else:
                logger.error(f"Failed to create IM: {res_json}")
                return None
        except Exception as e:
            logger.error(f"Error creating IM as user: {e}")
            return None

    def send_message_via_webhook(self, room_id, text, username=None):
        """Gửi tin nhắn bằng Incoming Webhook, ưu tiên dùng room_id (rid)"""
        if not RC_WEBHOOK_URL:
            logger.error("RC_WEBHOOK_URL is not configured")
            return False
        
        try:
            payload = {
                "text": text,
                "channel": room_id, 
                "alias": "Trợ lý AI",
                "avatar": "https://cdn-icons-png.flaticon.com/512/4712/4712035.png"
            }
            
            response = requests.post(RC_WEBHOOK_URL, json=payload)
            print(f"--- WEBHOOK LOG ---")
            print(f"Target Room: {room_id}")
            print(f"Status: {response.status_code}")
            print(f"Response Body: {response.text}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error sending webhook: {e}")
            return False

    def send_message_as_bot(self, room_id, text):
        """Gửi tin nhắn vào phòng chat bằng REST API (Backup)"""
        try:
            url = f"{RC_URL}/api/v1/chat.sendMessage"
            payload = {
                "message": {
                    "rid": room_id,
                    "msg": text
                }
            }
            response = requests.post(url, json=payload, headers=self.headers)
            return response.json()
        except Exception as e:
            logger.error(f"Error sending message as bot: {e}")
            return None

# Singleton instance
rc_service = RocketChatService()
