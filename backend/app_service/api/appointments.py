from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from config import settings
from database import get_db
from models.appointment import AppointmentStatus
from models.property import Property
from models.user import User
from services.appointment_service import (
    AppointmentCancel,
    AppointmentConfirm,
    AppointmentCounterProposal,
    AppointmentCreate,
    appointment_service,
)

router = APIRouter(prefix="/appointments", tags=["Appointments"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

SECRET_KEY = settings.secret_key
ALGORITHM = settings.algorithm

def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Không thể xác thực thông tin đăng nhập",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    return user

def serialize_appointment(
    appointment,
    property_item: Property,
    user: User = None,
):
    return {
        "id": appointment.id,
        "property_id": appointment.property_id,
        "property_title": property_item.title if property_item else None,
        "user_id": appointment.user_id,
        "user_name": user.full_name if user else None,
        "user_phone": user.phone_number if user else None,
        "owner_id": appointment.owner_id,
        "proposed_time": appointment.proposed_time.isoformat()
        if appointment.proposed_time
        else None,
        "counter_proposed_time": appointment.counter_proposed_time.isoformat()
        if appointment.counter_proposed_time
        else None,
        "confirmed_time": appointment.confirmed_time.isoformat()
        if appointment.confirmed_time
        else None,
        "status": appointment.status.value
        if isinstance(appointment.status, AppointmentStatus)
        else appointment.status,
        "cancelled_by": appointment.cancelled_by.value if appointment.cancelled_by else None,
        "cancel_reason": appointment.cancel_reason,
        "created_at": appointment.created_at.isoformat() if appointment.created_at else None,
        "updated_at": appointment.updated_at.isoformat() if appointment.updated_at else None,
    }

def serialize_single_appointment(db: Session, appointment):
    property_item = db.query(Property).filter(Property.id == appointment.property_id).first()
    user = db.query(User).filter(User.id == appointment.user_id).first()
    return serialize_appointment(appointment, property_item, user)

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_appointment(
    appointment_in: AppointmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        appointment = appointment_service.create_appointment(db, appointment_in, current_user)
        return {
            "message": "Đặt lịch hẹn thành công",
            "data": serialize_single_appointment(db, appointment),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi hệ thống khi xử lý yêu cầu đặt lịch: {str(e)}",
        )

@router.get("/my-appointments", response_model=List[dict])
def get_my_appointments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        rows = appointment_service.get_my_appointments(db, current_user)
        return [serialize_appointment(appointment, property_item) for appointment, property_item in rows]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi hệ thống khi lấy lịch đã đặt: {str(e)}",
        )

@router.get("/property-appointments", response_model=List[dict])
def get_property_appointments(
    property_id: Optional[int] = Query(None, description="ID bất động sản"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        rows = appointment_service.get_property_appointments(
            db=db,
            current_user=current_user,
            property_id=property_id,
        )
        return [
            serialize_appointment(appointment, property_item, user)
            for appointment, property_item, user in rows
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi hệ thống khi lấy lịch theo căn nhà: {str(e)}",
        )

@router.patch("/{appointment_id}/confirm")
def confirm_appointment(
    appointment_id: int,
    confirm_in: AppointmentConfirm,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        appointment = appointment_service.confirm_appointment(
            db,
            appointment_id,
            confirm_in,
            current_user,
        )
        return {
            "message": "Xác nhận lịch hẹn thành công",
            "data": serialize_single_appointment(db, appointment),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi hệ thống khi xác nhận lịch hẹn: {str(e)}",
        )

@router.patch("/{appointment_id}/counter")
def counter_appointment(
    appointment_id: int,
    counter_in: AppointmentCounterProposal,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        appointment = appointment_service.counter_appointment(
            db,
            appointment_id,
            counter_in,
            current_user,
        )
        return {
            "message": "Đề xuất lại thời gian thành công",
            "data": serialize_single_appointment(db, appointment),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi hệ thống khi đề xuất lại lịch hẹn: {str(e)}",
        )

@router.patch("/{appointment_id}/cancel")
def cancel_appointment(
    appointment_id: int,
    cancel_in: AppointmentCancel,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        appointment = appointment_service.cancel_appointment(
            db,
            appointment_id,
            cancel_in,
            current_user,
        )
        return {
            "message": "Hủy lịch hẹn thành công",
            "data": serialize_single_appointment(db, appointment),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi hệ thống khi hủy lịch hẹn: {str(e)}",
        )
