from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session
from database import get_db
from models.district import District
from models.property import Property, PropertyCategory, PropertyStatus, PropertyType

router = APIRouter(prefix="/search-properties", tags=["AI Search"])

_CATEGORY_DISPLAY = {
    "apartment": "Chung cư",
    "house": "Nhà riêng",
    "land": "Đất nền",
    "villa": "Biệt thự",
    "townhouse": "Nhà phố",
    "shophouse": "Shophouse",
    "office": "Văn phòng",
}

_TYPE_DISPLAY = {
    "sell": "Bán",
    "rent": "Cho thuê",
}

_DIRECTION_DISPLAY = {
    "N": "Bắc", "S": "Nam", "E": "Đông", "W": "Tây",
    "NE": "Đông Bắc", "NW": "Tây Bắc", "SE": "Đông Nam", "SW": "Tây Nam",
}


def _format_price(price: float, price_unit: Optional[str]) -> str:
    if price_unit:
        p = int(price) if price == int(price) else price
        return f"{p:,} {price_unit}".replace(",", ".")
    if price >= 1_000_000_000:
        val = price / 1_000_000_000
        return f"{val:.1f} Tỷ".rstrip("0").rstrip(".")
    if price >= 1_000_000:
        return f"{price / 1_000_000:.0f} Triệu"
    return f"{price:,.0f} VNĐ"

@router.get("/", response_model=dict)
def search_properties(
    q: Optional[str] = Query(None, description="Từ khoá tìm kiếm (tiêu đề, mô tả, địa chỉ)"),
    district: Optional[str] = Query(None, description="Tên quận/huyện"),
    property_type: Optional[str] = Query(None, description="Loại: sell | rent"),
    category: Optional[str] = Query(None, description="Phân loại: apartment, house, land, villa..."),
    min_price: Optional[float] = Query(None, ge=0, description="Giá tối thiểu"),
    max_price: Optional[float] = Query(None, ge=0, description="Giá tối đa"),
    min_area: Optional[float] = Query(None, ge=0, description="Diện tích tối thiểu (m²)"),
    bedrooms: Optional[int] = Query(None, ge=0, description="Số phòng ngủ tối thiểu"),
    limit: int = Query(5, ge=1, le=20, description="Số kết quả trả về"),
    status: Optional[str] = Query(None, include_in_schema=False),  # ignored, always approved
    db: Session = Depends(get_db),
):
    """
    Tìm kiếm BĐS cho AI agent. Trả về dữ liệu đầy đủ để render card.
    Luôn lọc status=approved bất kể tham số truyền vào.
    """
    query = db.query(Property).filter(Property.status == PropertyStatus.approved)

    # --- Full-text / ILIKE search ---
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            or_(
                Property.title.ilike(pattern),
                Property.description.ilike(pattern),
                Property.address.ilike(pattern),
            )
        )

    # --- District lookup by name hoặc short_name ---
    if district:
        dist_row = (
            db.query(District)
            .filter(
                or_(
                    District.name.ilike(f"%{district}%"),
                    District.short_name.ilike(f"%{district}%"),
                )
            )
            .first()
        )
        if dist_row:
            query = query.filter(Property.district_id == dist_row.id)

    # --- Type ---
    if property_type:
        try:
            query = query.filter(Property.type == PropertyType(property_type))
        except ValueError:
            pass

    # --- Category ---
    if category:
        try:
            query = query.filter(Property.category == PropertyCategory(category))
        except ValueError:
            pass

    # --- Price ---
    if min_price is not None:
        query = query.filter(Property.price >= min_price)
    if max_price is not None:
        query = query.filter(Property.price <= max_price)

    # --- Area ---
    if min_area is not None:
        query = query.filter(Property.area >= min_area)

    # --- Bedrooms (>=) ---
    if bedrooms is not None:
        query = query.filter(Property.bedrooms >= bedrooms)

    props = query.order_by(Property.created_at.desc()).limit(limit).all()

    # --- Build district cache để tránh N+1 queries ---
    district_ids = {p.district_id for p in props}
    districts = {
        d.id: d
        for d in db.query(District).filter(District.id.in_(district_ids)).all()
    }

    items = []
    for p in props:
        dist_obj = districts.get(p.district_id)
        sorted_imgs = sorted(p.images, key=lambda x: x.sort_order) if p.images else []
        thumbnail = sorted_imgs[0].url if sorted_imgs else None
        image_urls = [img.url for img in sorted_imgs[:5]]

        price_val = float(p.price)
        direction_raw = p.direction or ""
        direction_display = _DIRECTION_DISPLAY.get(direction_raw.upper(), direction_raw) if direction_raw else None

        items.append({
            "id": p.id,
            "title": p.title,
            # --- Giá ---
            "price": price_val,
            "price_unit": p.price_unit,
            "price_display": _format_price(price_val, p.price_unit),
            # --- Diện tích ---
            "area": float(p.area),
            # --- Vị trí ---
            "address": p.address,
            "ward": p.ward,
            "district": {
                "id": dist_obj.id,
                "name": dist_obj.name,
                "short_name": dist_obj.short_name,
            } if dist_obj else None,
            # --- Loại hình ---
            "type": p.type.value,
            "type_display": _TYPE_DISPLAY.get(p.type.value, p.type.value),
            "category": p.category.value,
            "category_display": _CATEGORY_DISPLAY.get(p.category.value, p.category.value),
            # --- Chi tiết căn ---
            "bedrooms": p.bedrooms,
            "bathrooms": p.bathrooms,
            "direction": direction_raw,
            "direction_display": direction_display,
            "legal_status": p.legal_status,
            "amenities": p.amenities or [],
            # --- Ảnh ---
            "thumbnail_url": thumbnail,
            "images": image_urls,
            # --- Meta ---
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "view_count": p.view_count,
        })

    return {"items": items, "total": len(items)}
