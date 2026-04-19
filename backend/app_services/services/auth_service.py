from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext
from models.user import UserRole, User
from dotenv import load_dotenv
import os
import logging
from services.rocketchat_service import rc_service
from sqlalchemy.orm import Session

load_dotenv()
logger = logging.getLogger(__name__)

# --- 1. PYDANTIC SCHEMAS ---
class UserCreate(BaseModel):
    full_name: str
    username: str
    email: EmailStr
    password: str
    phone_number: Optional[str] = None

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

# --- 2. BẢO MẬT & JWT LOGIC ---
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))

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
    """
    Đảm bảo user có tài khoản RocketChat, đã login lấy token và có room chat với bot.
    Dùng try-catch để không làm gián đoạn luồng chính nếu RC lỗi.
    """
    try:
        # 1. Nếu chưa có rc_user_id, tạo mới trên RC
        if not user.rc_user_id:
            logger.info(f"Creating RocketChat user for {user.username}")
            rc_user_res = rc_service.create_user(
                name=user.full_name,
                email=user.email,
                username=user.username,
                password=password
            )
            if rc_user_res.get("success"):
                user.rc_user_id = rc_user_res["user"]["_id"]
                db.commit()
            else:
                logger.error(f"Failed to create RC user: {rc_user_res}")

        # 2. Đăng nhập để lấy auth token (luôn lấy mới khi login app)
        logger.info(f"Logging in RocketChat user {user.username}")
        rc_login_res = rc_service.login_user(user.username, password)
        if rc_login_res.get("status") == "success":
            user.rc_auth_token = rc_login_res["data"]["authToken"]
            # Cập nhật lại rc_user_id nếu cần (đề phòng)
            user.rc_user_id = rc_login_res["data"]["userId"]
            db.commit()
            
            # 3. Tạo/Lấy Room ID với Bot nếu chưa có
            if not user.rc_room_id:
                logger.info(f"Creating RocketChat IM for {user.username} with bot")
                room_id = rc_service.create_im_with_bot(user.rc_user_id, user.rc_auth_token)
                if room_id:
                    user.rc_room_id = room_id
                    db.commit()
        else:
            logger.error(f"Failed to login RC user: {rc_login_res}")

    except Exception as e:
        logger.error(f"sync_rocketchat_user exception: {e}", exc_info=True)
    
    return user
