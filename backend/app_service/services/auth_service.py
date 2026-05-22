from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext
from models.user import UserRole, User
import logging
from services.rocketchat_service import rc_service
from sqlalchemy.orm import Session
from config import settings

logger = logging.getLogger(__name__)

# --- 1. PYDANTIC SCHEMAS ---
class UserCreate(BaseModel):
    full_name: str
    username: str
    email: EmailStr
    password: str
    phone_number: str = Field(..., min_length=9, max_length=15)

class UserResponse(BaseModel):
    id: int
    full_name: str
    username: str
    email: Optional[EmailStr]
    role: UserRole
    is_active: bool
    rc_user_id: Optional[str] = None
    rc_auth_token: Optional[str] = None
    rc_room_id: Optional[str] = None

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    role: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    rc_user_id: Optional[str] = None
    rc_auth_token: Optional[str] = None
    rc_room_id: Optional[str] = None
    rc_visitor_token: Optional[str] = None

# --- 2. BẢO MẬT & JWT LOGIC ---
SECRET_KEY = settings.secret_key
ALGORITHM = settings.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# --- 3. ROCKETCHAT INTEGRATION LOGIC ---
def sync_rocketchat_user(db: Session, user: User, password: str):
    """Đảm bảo user có tài khoản RC, token và Livechat room với bot.

    Flow Omnichannel:
      1. Tạo RC user (dùng cho DDP auth trong Flutter)
      2. Login lấy authToken
      3. Đăng ký Livechat visitor với token = username (duy nhất, ổn định)
      4. Tạo/lấy Livechat room cho visitor đó
    """
    try:
        # 1. Tạo RC user nếu chưa có (vẫn cần cho Flutter DDP auth)
        if not user.rc_user_id:
            logger.info(f"Creating RocketChat user for {user.username}")
            rc_user_res = rc_service.create_user(
                name=user.full_name,
                email=user.email,
                username=user.username,
                password=password,
            )
            if rc_user_res.get("success"):
                user.rc_user_id = rc_user_res["user"]["_id"]
                db.commit()
            else:
                logger.error(f"Failed to create RC user: {rc_user_res}")

        # 2. Login lấy authToken mới nhất (cần cho Flutter DDP login)
        logger.info(f"Logging in RocketChat user {user.username}")
        rc_login_res = rc_service.login_user(user.username, password)
        if rc_login_res.get("status") == "success":
            user.rc_auth_token = rc_login_res["data"]["authToken"]
            user.rc_user_id = rc_login_res["data"]["userId"]
            db.commit()
        else:
            logger.error(f"Failed to login RC user: {rc_login_res}")

        # 3. Đăng ký Livechat visitor (token = username — cố định, không đổi)
        visitor_token = user.username
        rc_service.register_livechat_visitor(
            token=visitor_token,
            name=user.full_name,
            email=user.email or "",
        )
        user.rc_visitor_token = visitor_token
        db.commit()

        # 4. Tạo/lấy Livechat room — gọi mỗi lần login để tự động tạo mới
        #    khi room cũ đã bị đóng (RC reuse nếu còn mở, tạo mới nếu đã đóng)
        logger.info(f"Getting/creating Livechat room for visitor {visitor_token!r}")
        result = rc_service.create_livechat_room(visitor_token)
        if result:
            room_id, _ = result
            user.rc_room_id = room_id
            db.commit()
            # 5. Đảm bảo bot online → RC routing tự assign bot vào room
            rc_service.ensure_bot_livechat_available()
        else:
            logger.error(f"Failed to get/create livechat room for {user.username}")

    except Exception as e:
        logger.error(f"sync_rocketchat_user exception: {e}", exc_info=True)

    return user
