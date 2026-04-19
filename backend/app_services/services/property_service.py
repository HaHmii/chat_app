from sqlalchemy.orm import Session
from models.property import Property, PropertyType, PropertyCategory, PropertyStatus
from models.user import User, UserRole
from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class PropertyReview(BaseModel):
    action: str  # 'approved' | 'rejected'
    rejection_reason: Optional[str] = None

class PropertyCreate(BaseModel):
    title: str = Field(..., min_length=10, max_length=500)
    description: Optional[str] = None
    type: PropertyType
    category: PropertyCategory
    address: str = Field(..., min_length=5)
    district_id: int
    ward: Optional[str] = None
    street: Optional[str] = None
    
    # price và area giữ nguyên kiểu dữ liệu (Numeric -> float trong pydantic)
    price: float = Field(..., gt=0)
    price_unit: Optional[str] = None # Triệu, Tỷ, Triệu/tháng...
    area: float = Field(..., gt=0)
    
    bedrooms: Optional[int] = Field(None, ge=0)
    bathrooms: Optional[int] = Field(None, ge=0)
    direction: Optional[str] = None
    legal_status: Optional[str] = None
    amenities: Optional[List[str]] = []

class PropertyService:
    def create_property(self, db: Session, prop_in: PropertyCreate, current_user: User):
        """
        Logic tạo tin đăng bất động sản
        """
        try:
            # 1. Kiểm tra Role - Chỉ Owner, Staff hoặc Admin mới được đăng tin
            # (Bạn yêu cầu đính kèm authorization xác định role chủ nhà)
            if current_user.role not in [UserRole.owner, UserRole.staff, UserRole.admin]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Bạn không có quyền đăng tin. Vui lòng nâng cấp tài khoản lên Chủ nhà."
                )

            # 2. Kiểm tra tính hợp lệ bổ sung (ví dụ: hạn chế số tin đăng trong ngày)
            # ... có thể thêm logic ở đây ...

            expires_at = datetime.utcnow() + timedelta(days=30)

            new_property = Property(
                owner_id=current_user.id,
                district_id=prop_in.district_id,
                title=prop_in.title,
                description=prop_in.description,
                type=prop_in.type,
                category=prop_in.category,
                status=PropertyStatus.pending,
                address=prop_in.address,
                ward=prop_in.ward,
                street=prop_in.street,
                price=prop_in.price,
                price_unit=prop_in.price_unit,
                area=prop_in.area,
                bedrooms=prop_in.bedrooms,
                bathrooms=prop_in.bathrooms,
                direction=prop_in.direction,
                legal_status=prop_in.legal_status,
                amenities=prop_in.amenities,
                expires_at=expires_at
            )

            db.add(new_property)
            db.commit()
            db.refresh(new_property)

            logger.info(f"User {current_user.username} created property {new_property.id}")
            return new_property

        except HTTPException as he:
            raise he
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating property: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Lỗi hệ thống khi đăng tin: {str(e)}"
            )

    def get_pending_properties(self, db: Session) -> list:
        return (
            db.query(Property)
            .filter(Property.status == PropertyStatus.pending)
            .order_by(Property.created_at.desc())
            .all()
        )

    def review_property(self, db: Session, property_id: int, review: PropertyReview, current_user: User) -> Property:
        if current_user.role != UserRole.admin:
            raise HTTPException(status_code=403, detail="Chỉ Admin mới có quyền duyệt tin")

        prop = db.query(Property).filter(Property.id == property_id).first()
        if not prop:
            raise HTTPException(status_code=404, detail="Không tìm thấy tin đăng")
        if prop.status != PropertyStatus.pending:
            raise HTTPException(status_code=400, detail="Tin đăng không ở trạng thái chờ duyệt")

        if review.action == 'approved':
            prop.status = PropertyStatus.approved
        elif review.action == 'rejected':
            prop.status = PropertyStatus.rejected
            prop.rejection_reason = review.rejection_reason
        else:
            raise HTTPException(status_code=400, detail="action phải là 'approved' hoặc 'rejected'")

        db.commit()
        db.refresh(prop)
        logger.info(f"Admin {current_user.username} {review.action} property {property_id}")
        return prop

property_service = PropertyService()
