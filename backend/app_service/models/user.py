import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Enum
from sqlalchemy.sql import func
from database import Base

class UserRole(str, enum.Enum):
    admin = 'admin'
    staff = 'staff'
    owner = 'owner'
    user = 'user'

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(255), nullable=False)
    username = Column(String(100), unique=True, nullable=False, index=True)
    phone_number = Column(String(15), nullable=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    password_hash = Column(Text, nullable=False)
    role = Column(Enum(UserRole, name="user_role"), default=UserRole.user, nullable=False)
    avatar_url = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    rc_room_id = Column(String(100), unique=True, nullable=True)
    # Livechat visitor token — dùng khi room type = livechat (omnichannel)
    rc_visitor_token = Column(String(200), nullable=True)
    
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
