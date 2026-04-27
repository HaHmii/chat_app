import enum
from sqlalchemy import (
    Column, Integer, String, Text, Numeric, DateTime,
    ForeignKey, Enum, CheckConstraint, Index
)
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR
from sqlalchemy.orm import relationship
from database import Base

class PropertyType(str, enum.Enum):
    sell = 'sell'
    rent = 'rent'

class PropertyCategory(str, enum.Enum):
    apartment = 'apartment'
    house = 'house'
    land = 'land'
    villa = 'villa'
    townhouse = 'townhouse'
    shophouse = 'shophouse'
    office = 'office'

class PropertyStatus(str, enum.Enum):
    pending = 'pending'
    approved = 'approved'
    rejected = 'rejected'
    hidden = 'hidden'
    sold = 'sold'

class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    district_id = Column(Integer, ForeignKey("districts.id", ondelete="RESTRICT"), nullable=False)

    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    type = Column(Enum(PropertyType, name="property_type"), nullable=False)
    category = Column(Enum(PropertyCategory, name="property_category"), nullable=False)
    status = Column(Enum(PropertyStatus, name="property_status"), default=PropertyStatus.pending, nullable=False)

    address = Column(String(500), nullable=False)
    ward = Column(String(150), nullable=True)
    street = Column(String(150), nullable=True)
    gps = Column(String(100), nullable=True)
    
    # Giữ nguyên Numeric cho price và area
    price = Column(Numeric(18, 0), nullable=False)
    price_unit = Column(Text, nullable=True) # Lưu đơn vị giá: Triệu, Tỷ, Triệu/tháng...
    area = Column(Numeric(10, 2), nullable=False)

    bedrooms = Column(Integer, nullable=True)
    bathrooms = Column(Integer, nullable=True)
    direction = Column(String(20), nullable=True)
    legal_status = Column(String(100), nullable=True)
    amenities = Column(ARRAY(Text), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    expires_at = Column(DateTime, nullable=False)
    view_count = Column(Integer, default=0, nullable=False)
    search_vector = Column(TSVECTOR, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint('price > 0', name='properties_price_positive'),
        CheckConstraint('area > 0', name='properties_area_positive'),
    )
    images = relationship("PropertyImage", back_populates="property", cascade="all, delete-orphan")

class PropertyImage(Base):
    __tablename__ = "property_images"

    id = Column(Integer, primary_key=True)
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)
    url = Column(Text, nullable=False)
    caption = Column(String(255), nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    uploaded_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index('ux_only_one_thumbnail', 'property_id', unique=True, postgresql_where=(sort_order == 0)),
    )

    property = relationship("Property", back_populates="images")
