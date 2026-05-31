from sqlalchemy.orm import Session
from models.property import Property, PropertyType, PropertyCategory, PropertyStatus
from models.user import User, UserRole
from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timedelta
import logging
import httpx

logger = logging.getLogger(__name__)

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_NOMINATIM_HEADERS = {"User-Agent": "BDSHanoiChatbot/1.0 (contact: admin@bds-hanoi.vn)"}


def _geocode_address(address: str) -> str | None:
    """Trả về chuỗi 'lat, lng' từ địa chỉ, hoặc None nếu không tìm được."""
    try:
        resp = httpx.get(
            _NOMINATIM_URL,
            params={
                "q": f"{address}, Hà Nội, Việt Nam",
                "format": "json",
                "limit": 1,
                "countrycodes": "VN",
                "accept-language": "vi",
            },
            headers=_NOMINATIM_HEADERS,
            timeout=8.0,
        )
        results = resp.json()
        if results:
            lat = float(results[0]["lat"])
            lng = float(results[0]["lon"])
            logger.info(f"[Geocode] {address!r} → {lat:.6f}, {lng:.6f}")
            return f"{lat:.6f}, {lng:.6f}"
        logger.warning(f"[Geocode] no result for {address!r}")
    except Exception as e:
        logger.warning(f"[Geocode] error for {address!r}: {e}")
    return None


class PropertyReview(BaseModel):
    action: str  # 'approved' | 'rejected'
    rejection_reason: Optional[str] = None

class PropertyUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=10, max_length=500)
    description: Optional[str] = None
    type: Optional[PropertyType] = None
    category: Optional[PropertyCategory] = None
    address: Optional[str] = Field(None, min_length=5)
    district_id: Optional[int] = None
    ward: Optional[str] = None
    street: Optional[str] = None
    price: Optional[float] = Field(None, gt=0)
    price_unit: Optional[str] = None
    area: Optional[float] = Field(None, gt=0)
    bedrooms: Optional[int] = Field(None, ge=0)
    bathrooms: Optional[int] = Field(None, ge=0)
    direction: Optional[str] = None

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

class PropertyService:
    def create_property(self, db: Session, prop_in: PropertyCreate, current_user: User):
        """
        Logic tạo tin đăng bất động sản
        """
        try:
            if current_user.role not in [UserRole.owner, UserRole.staff, UserRole.admin]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Bạn không có quyền đăng tin. Vui lòng nâng cấp tài khoản lên Chủ nhà."
                )

            gps = _geocode_address(prop_in.address)

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
                gps=gps
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

    def get_my_properties(self, db: Session, current_user: User) -> list:
        return (
            db.query(Property)
            .filter(Property.owner_id == current_user.id)
            .order_by(Property.created_at.desc())
            .all()
        )

    def update_property(self, db: Session, property_id: int, update_in: PropertyUpdate, current_user: User) -> Property:
        prop = db.query(Property).filter(Property.id == property_id).first()
        if not prop:
            raise HTTPException(status_code=404, detail="Không tìm thấy tin đăng")
        if prop.owner_id != current_user.id and current_user.role != UserRole.admin:
            raise HTTPException(status_code=403, detail="Bạn không có quyền chỉnh sửa tin này")

        update_data = update_in.model_dump(exclude_unset=True)
        needs_geocode = 'address' in update_data

        for field, value in update_data.items():
            setattr(prop, field, value)

        if needs_geocode:
            prop.gps = _geocode_address(prop.address)

        prop.status = PropertyStatus.pending
        prop.rejection_reason = None

        try:
            db.commit()
            db.refresh(prop)
            logger.info(f"User {current_user.username} updated property {property_id}")
            return prop
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating property {property_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Lỗi hệ thống khi cập nhật tin")

    def delete_property(self, db: Session, property_id: int, current_user: User) -> None:
        prop = db.query(Property).filter(Property.id == property_id).first()
        if not prop:
            raise HTTPException(status_code=404, detail="Không tìm thấy tin đăng")
        if prop.owner_id != current_user.id and current_user.role != UserRole.admin:
            raise HTTPException(status_code=403, detail="Bạn không có quyền xóa tin này")

        try:
            db.delete(prop)
            db.commit()
            logger.info(f"User {current_user.username} deleted property {property_id}")
        except Exception as e:
            db.rollback()
            logger.error(f"Error deleting property {property_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Lỗi hệ thống khi xóa tin")

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
