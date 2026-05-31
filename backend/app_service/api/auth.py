from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from jose import jwt, JWTError
from config import settings
from database import get_db
from models.user import User
from services import auth_service
import logging

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def _get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> User:
    exc = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Không thể xác thực")
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise exc
    except JWTError:
        raise exc
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise exc
    return user

@router.post("/register", response_model=auth_service.UserResponse)
def register(user_in: auth_service.UserCreate, db: Session = Depends(get_db)):
    if not user_in.phone_number or not user_in.phone_number.strip():
        raise HTTPException(status_code=400, detail="Số điện thoại là bắt buộc.")

    # 1. Kiểm tra trùng lặp trong DB Local
    user_exists = db.query(User).filter(
        (User.username == user_in.username) | (User.email == user_in.email)
    ).first()

    if user_exists:
        raise HTTPException(status_code=400, detail="Tên đăng nhập hoặc Email đã tồn tại.")

    # 2. Tạo User Local
    hashed_password = auth_service.get_password_hash(user_in.password)
    new_user = User(
        full_name=user_in.full_name,
        username=user_in.username,
        email=user_in.email,
        phone_number=user_in.phone_number,
        password_hash=hashed_password,
        role=user_in.role,
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        return new_user
    except Exception as e:
        db.rollback()
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail=f"Lỗi đăng ký: {str(e)}")

@router.post("/login", response_model=auth_service.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # 1. Kiểm tra user local
    user = db.query(User).filter(User.username == form_data.username).first()

    if not user or not auth_service.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tên đăng nhập hoặc mật khẩu không chính xác",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=400, detail="Tài khoản đã bị khóa")

    # 2. Sinh JWT token của hệ thống
    access_token = auth_service.create_access_token(
        data={"sub": str(user.id), "role": user.role.value}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role.value,
        "full_name": user.full_name,
        "email": user.email,
        "rc_room_id": user.rc_room_id,
        "rc_visitor_token": user.rc_visitor_token,
    }


@router.post("/init-chat-room")
def init_chat_room(
    current_user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    """Tạo hoặc lấy lại Livechat room. Gọi khi user mở màn hình chatbot."""
    user = auth_service.init_livechat_room(db, current_user)
    if not user.rc_room_id:
        raise HTTPException(status_code=500, detail="Không thể tạo phòng chat")
    return {
        "rc_room_id": user.rc_room_id,
        "rc_visitor_token": user.rc_visitor_token,
    }


@router.post("/internal/token")
def get_token_by_rc_username(
    rc_username: str,
    x_internal_key: str = Header(...),
    db: Session = Depends(get_db),
):
    """Internal endpoint — AI service dùng để lấy JWT cho user theo RC username."""
    if x_internal_key != settings.internal_api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal key")

    user = db.query(User).filter(User.username == rc_username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    token = auth_service.create_access_token(
        data={"sub": str(user.id), "role": user.role.value}
    )
    return {"access_token": token, "user_id": user.id}
