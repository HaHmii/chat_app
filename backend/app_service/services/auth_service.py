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
    role: Optional[UserRole] = UserRole.user

class UserResponse(BaseModel):
    id: int
    full_name: str
    username: str
    email: Optional[EmailStr]
    role: UserRole
    is_active: bool
    rc_room_id: Optional[str] = None

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    role: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
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

def init_livechat_room(db: Session, user: User):
    """Tạo hoặc lấy lại Livechat room cho user — gọi khi user mở màn hình chatbot.

    Đăng ký visitor nếu chưa có, sau đó tạo/reuse room còn mở.
    RC tự reuse room nếu còn open, tạo mới nếu đã đóng.
    """
    try:
        visitor_token = user.username

        # 3. Đăng ký Livechat visitor (token = username — cố định, không đổi)
        rc_service.register_livechat_visitor(
            token=visitor_token,
            name=user.full_name,
            email=user.email or "",
        )
        user.rc_visitor_token = visitor_token
        db.commit()

        # 4. Tạo/lấy Livechat room
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
        logger.error(f"init_livechat_room exception: {e}", exc_info=True)

    return user
