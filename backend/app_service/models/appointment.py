import enum
from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey, Enum, CheckConstraint
from sqlalchemy.sql import func
from database import Base

class AppointmentStatus(str, enum.Enum):
    pending = "pending"
    counter_proposed = "counter_proposed"
    confirmed = "confirmed"
    cancelled = "cancelled"
    done = "done"
    expired = "expired"

class AppointmentCancelledBy(str, enum.Enum):
    guest = "guest"
    owner = "owner"
    system = "system"

class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True)
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)
    guest_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    proposed_time = Column(DateTime, nullable=False)
    counter_proposed_time = Column(DateTime, nullable=True)
    confirmed_time = Column(DateTime, nullable=True)
    note = Column(Text, nullable=True)
    status = Column(
        Enum(AppointmentStatus, name="appointment_status"),
        default=AppointmentStatus.pending,
        nullable=False,
    )
    cancelled_by = Column(
        Enum(AppointmentCancelledBy, name="appointment_cancelled_by"),
        nullable=True,
    )
    cancel_reason = Column(Text, nullable=True)
    rating = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("guest_id <> owner_id", name="appointments_no_self_booking"),
        CheckConstraint(
            "rating IS NULL OR (rating >= 1 AND rating <= 5)",
            name="appointments_rating_range",
        ),
    )
