from datetime import datetime, timezone
import logging
from typing import Optional

from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models.appointment import Appointment, AppointmentCancelledBy, AppointmentStatus
from models.property import Property, PropertyStatus
from models.user import User, UserRole
from services.rocketchat_service import rc_service

logger = logging.getLogger(__name__)


class AppointmentCreate(BaseModel):
    property_id: int
    proposed_time: datetime
    note: Optional[str] = Field(None, max_length=2000)


class AppointmentConfirm(BaseModel):
    confirmed_time: Optional[datetime] = None


class AppointmentCounterProposal(BaseModel):
    counter_proposed_time: datetime


class AppointmentCancel(BaseModel):
    cancelled_by: AppointmentCancelledBy
    cancel_reason: str = Field(..., min_length=3, max_length=2000)


class AppointmentService:
    MAX_BOOKINGS_PER_PROPERTY = 3

    def _normalize_datetime(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _validate_future_time(self, value: datetime, field_name: str):
        normalized = self._normalize_datetime(value)
        if normalized <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{field_name} phải lớn hơn thời điểm hiện tại",
            )
        return normalized

    def _get_property_or_404(self, db: Session, property_id: int) -> Property:
        property_item = db.query(Property).filter(Property.id == property_id).first()
        if not property_item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy bất động sản",
            )
        return property_item

    def _get_appointment_or_404(self, db: Session, appointment_id: int) -> Appointment:
        appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
        if not appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy lịch hẹn",
            )
        return appointment

    def _ensure_owner_access(
        self,
        db: Session,
        appointment: Appointment,
        current_user: User,
    ) -> Property:
        if current_user.role not in [UserRole.owner, UserRole.staff, UserRole.admin]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không có quyền thao tác lịch hẹn này",
            )

        property_item = self._get_property_or_404(db, appointment.property_id)
        if current_user.role == UserRole.owner and property_item.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không có quyền thao tác lịch hẹn của căn nhà này",
            )

        return property_item

    def _send_guest_notification(self, guest: User, message: str):
        if not guest.rc_room_id:
            return
        try:
            rc_service.send_message_via_webhook(guest.rc_room_id, message)
        except Exception as e:
            logger.warning("Failed to notify guest %s: %s", guest.id, str(e))

    def create_appointment(
        self,
        db: Session,
        appointment_in: AppointmentCreate,
        current_user: User,
    ) -> Appointment:
        try:
            if current_user.role != UserRole.guest:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Chỉ tài khoản khách mới được đặt lịch hẹn",
                )

            property_item = (
                db.query(Property)
                .filter(
                    Property.id == appointment_in.property_id,
                    Property.status == PropertyStatus.approved,
                )
                .first()
            )
            if not property_item:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Không tìm thấy bất động sản hoặc tin đăng chưa được duyệt",
                )

            if property_item.owner_id == current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Bạn không thể đặt lịch với chính tin đăng của mình",
                )

            proposed_time = self._validate_future_time(
                appointment_in.proposed_time,
                "Thời gian hẹn",
            )

            booking_count = (
                db.query(Appointment)
                .filter(
                    Appointment.property_id == appointment_in.property_id,
                    Appointment.guest_id == current_user.id,
                )
                .count()
            )
            if booking_count >= self.MAX_BOOKINGS_PER_PROPERTY:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Bạn đã đạt giới hạn 3 lần đặt lịch cho căn nhà này",
                )

            new_appointment = Appointment(
                property_id=property_item.id,
                guest_id=current_user.id,
                owner_id=property_item.owner_id,
                proposed_time=proposed_time,
                note=appointment_in.note,
                status=AppointmentStatus.pending,
            )

            db.add(new_appointment)
            db.commit()
            db.refresh(new_appointment)
            return new_appointment
        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error("Error creating appointment: %s", str(e), exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Lỗi hệ thống khi đặt lịch: {str(e)}",
            )

    def get_my_appointments(self, db: Session, current_user: User):
        try:
            if current_user.role != UserRole.guest:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Chỉ tài khoản khách mới được xem lịch đã đặt",
                )

            return (
                db.query(Appointment, Property)
                .join(Property, Property.id == Appointment.property_id)
                .filter(Appointment.guest_id == current_user.id)
                .order_by(Appointment.created_at.desc())
                .all()
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error getting guest appointments: %s", str(e), exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Lỗi hệ thống khi lấy danh sách lịch hẹn: {str(e)}",
            )

    def get_property_appointments(
        self,
        db: Session,
        current_user: User,
        property_id: Optional[int] = None,
    ):
        try:
            if current_user.role not in [UserRole.owner, UserRole.staff, UserRole.admin]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Bạn không có quyền xem lịch hẹn của bất động sản",
                )

            query = (
                db.query(Appointment, Property, User)
                .join(Property, Property.id == Appointment.property_id)
                .join(User, User.id == Appointment.guest_id)
            )

            if property_id is not None:
                property_item = self._get_property_or_404(db, property_id)
                if current_user.role == UserRole.owner and property_item.owner_id != current_user.id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Bạn không có quyền xem lịch hẹn của căn nhà này",
                    )
                query = query.filter(Appointment.property_id == property_id)
            elif current_user.role == UserRole.owner:
                query = query.filter(Appointment.owner_id == current_user.id)

            return query.order_by(Appointment.created_at.desc()).all()
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error getting property appointments: %s", str(e), exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Lỗi hệ thống khi lấy lịch hẹn theo căn nhà: {str(e)}",
            )

    def confirm_appointment(
        self,
        db: Session,
        appointment_id: int,
        confirm_in: AppointmentConfirm,
        current_user: User,
    ) -> Appointment:
        try:
            appointment = self._get_appointment_or_404(db, appointment_id)
            self._ensure_owner_access(db, appointment, current_user)

            if appointment.status not in [
                AppointmentStatus.pending,
                AppointmentStatus.counter_proposed,
            ]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Chỉ có thể xác nhận lịch ở trạng thái chờ hoặc đề xuất lại",
                )

            if confirm_in.confirmed_time is not None:
                # Chủ nhà cung cấp thời gian mới → bắt buộc phải là tương lai
                appointment.confirmed_time = self._validate_future_time(
                    confirm_in.confirmed_time,
                    "Thời gian xác nhận",
                )
            else:
                # Dùng thời gian đã lưu trong DB — copy trực tiếp, không chuyển timezone
                # để đảm bảo confirmed_time và proposed_time nhất quán (cùng naive UTC)
                db_time = (
                    appointment.counter_proposed_time
                    or appointment.proposed_time
                )
                if db_time is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Lịch hẹn không có thời gian để xác nhận",
                    )
                appointment.confirmed_time = db_time
            appointment.status = AppointmentStatus.confirmed
            appointment.updated_at = datetime.utcnow()

            db.commit()
            db.refresh(appointment)
            return appointment
        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error("Error confirming appointment: %s", str(e), exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Lỗi hệ thống khi xác nhận lịch hẹn: {str(e)}",
            )

    def counter_appointment(
        self,
        db: Session,
        appointment_id: int,
        counter_in: AppointmentCounterProposal,
        current_user: User,
    ) -> Appointment:
        try:
            appointment = self._get_appointment_or_404(db, appointment_id)
            property_item = self._ensure_owner_access(db, appointment, current_user)

            if appointment.status not in [
                AppointmentStatus.pending,
                AppointmentStatus.counter_proposed,
            ]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Chỉ có thể đề xuất lại với lịch đang chờ xử lý",
                )

            appointment.counter_proposed_time = self._validate_future_time(
                counter_in.counter_proposed_time,
                "Thời gian đề xuất lại",
            )
            appointment.status = AppointmentStatus.counter_proposed
            appointment.updated_at = datetime.utcnow()

            db.commit()
            db.refresh(appointment)

            guest = db.query(User).filter(User.id == appointment.guest_id).first()
            if guest:
                display_time = appointment.counter_proposed_time.astimezone(timezone.utc).strftime(
                    "%H:%M %d/%m/%Y UTC"
                )
                self._send_guest_notification(
                    guest,
                    f"Chủ nhà đã đề xuất lại lịch xem '{property_item.title}' vào {display_time}.",
                )

            return appointment
        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error("Error counter proposing appointment: %s", str(e), exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Lỗi hệ thống khi đề xuất lại lịch hẹn: {str(e)}",
            )

    def cancel_appointment(
        self,
        db: Session,
        appointment_id: int,
        cancel_in: AppointmentCancel,
        current_user: User,
    ) -> Appointment:
        try:
            appointment = self._get_appointment_or_404(db, appointment_id)
            self._ensure_owner_access(db, appointment, current_user)

            if appointment.status in [
                AppointmentStatus.cancelled,
                AppointmentStatus.done,
                AppointmentStatus.expired,
            ]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Lịch hẹn này không thể hủy nữa",
                )

            if cancel_in.cancelled_by == AppointmentCancelledBy.guest:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Chủ nhà không thể hủy lịch với cancelled_by = guest",
                )

            appointment.status = AppointmentStatus.cancelled
            appointment.cancelled_by = cancel_in.cancelled_by
            appointment.cancel_reason = cancel_in.cancel_reason.strip()
            appointment.updated_at = datetime.utcnow()

            db.commit()
            db.refresh(appointment)
            return appointment
        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error("Error cancelling appointment: %s", str(e), exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Lỗi hệ thống khi hủy lịch hẹn: {str(e)}",
            )


appointment_service = AppointmentService()
