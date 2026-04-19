from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm
from database import get_db
from models.user import User
from services import auth_service
import logging

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)

@router.post("/register", response_model=auth_service.UserResponse)
def register(user_in: auth_service.UserCreate, db: Session = Depends(get_db)):
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
        password_hash=hashed_password
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        # 3. Đồng bộ với RocketChat (Tạo user, login, tạo room)
        new_user = auth_service.sync_rocketchat_user(db, new_user, user_in.password)
        
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

    # 2. Đồng bộ/Cập nhật RocketChat session
    user = auth_service.sync_rocketchat_user(db, user, form_data.password)

    # 3. Sinh JWT token của hệ thống
    access_token = auth_service.create_access_token(
        data={"sub": str(user.id), "role": user.role.value}
    )

    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "role": user.role.value,
        "full_name": user.full_name,
        "email": user.email,
        "rc_user_id": user.rc_user_id,
        "rc_auth_token": user.rc_auth_token,
        "rc_room_id": user.rc_room_id
    }
