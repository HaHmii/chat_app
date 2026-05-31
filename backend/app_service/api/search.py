import math
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


def _parse_gps(gps: str) -> tuple[float, float] | None:
    """Parse 'lat,lng' string to (lat, lng) floats. Returns None if invalid."""
    try:
        parts = gps.strip().split(",")
        if len(parts) == 2:
            return float(parts[0].strip()), float(parts[1].strip())
    except (ValueError, AttributeError):
        pass
    return None


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in km between two GPS coordinates."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


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


def _build_item(p: Property, dist_obj: Optional[District], distance_km: Optional[float] = None) -> dict:
    sorted_imgs = sorted(p.images, key=lambda x: x.sort_order) if p.images else []
    price_val = float(p.price)
    direction_raw = p.direction or ""
    direction_display = _DIRECTION_DISPLAY.get(direction_raw.upper(), direction_raw) if direction_raw else None

    item = {
        "id": p.id,
        "title": p.title,
        "price": price_val,
        "price_unit": p.price_unit,
        "price_display": _format_price(price_val, p.price_unit),
        "area": float(p.area),
        "address": p.address,
        "ward": p.ward,
        "district": {
            "id": dist_obj.id,
            "name": dist_obj.name,
            "short_name": dist_obj.short_name,
        } if dist_obj else None,
        "type": p.type.value,
        "type_display": _TYPE_DISPLAY.get(p.type.value, p.type.value),
        "category": p.category.value,
        "category_display": _CATEGORY_DISPLAY.get(p.category.value, p.category.value),
        "bedrooms": p.bedrooms,
        "bathrooms": p.bathrooms,
        "direction": direction_raw,
        "direction_display": direction_display,
        "thumbnail_url": sorted_imgs[0].url if sorted_imgs else None,
        "images": [img.url for img in sorted_imgs[:5]],
        "gps": p.gps,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }
    if distance_km is not None:
        item["distance_km"] = round(distance_km, 2)
    return item


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
    limit: int = Query(10, ge=1, le=20, description="Số kết quả trả về"),
    # Nearby mode — khi có lat+lng thì tìm theo bán kính thay vì full-text
    lat: Optional[float] = Query(None, description="Vĩ độ (latitude) — bật chế độ tìm gần đây"),
    lng: Optional[float] = Query(None, description="Kinh độ (longitude) — bật chế độ tìm gần đây"),
    radius_km: float = Query(3.0, ge=0.1, le=50.0, description="Bán kính tìm kiếm (km), chỉ dùng khi có lat+lng"),
    status: Optional[str] = Query(None, include_in_schema=False),  # ignored, always approved
    db: Session = Depends(get_db),
):
    """
    Tìm kiếm BĐS cho AI agent.
    - Khi có lat+lng: tìm theo bán kính (nearby mode), sắp xếp theo khoảng cách.
    - Khi không có lat+lng: tìm theo từ khoá / bộ lọc (search mode).
    Luôn lọc status=approved.
    """
    nearby_mode = lat is not None and lng is not None

    query_obj = db.query(Property).filter(Property.status == PropertyStatus.approved)

    if nearby_mode:
        query_obj = query_obj.filter(Property.gps.isnot(None))

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
            query_obj = query_obj.filter(Property.district_id == dist_row.id)

    if property_type:
        try:
            query_obj = query_obj.filter(Property.type == PropertyType(property_type))
        except ValueError:
            pass

    if category:
        try:
            query_obj = query_obj.filter(Property.category == PropertyCategory(category))
        except ValueError:
            pass

    if min_price is not None:
        query_obj = query_obj.filter(Property.price >= min_price)
    if max_price is not None:
        query_obj = query_obj.filter(Property.price <= max_price)
    if min_area is not None:
        query_obj = query_obj.filter(Property.area >= min_area)
    if bedrooms is not None:
        query_obj = query_obj.filter(Property.bedrooms >= bedrooms)

    if nearby_mode:
        props = query_obj.all()

        nearby: list[tuple] = []
        for p in props:
            coords = _parse_gps(p.gps)
            if coords:
                dist = _haversine(lat, lng, coords[0], coords[1])
                if dist <= radius_km:
                    nearby.append((p, dist))
        nearby.sort(key=lambda x: x[1])
        nearby = nearby[:limit]

        district_ids = {p.district_id for p, _ in nearby}
        districts = {
            d.id: d
            for d in db.query(District).filter(District.id.in_(district_ids)).all()
        }
        items = [_build_item(p, districts.get(p.district_id), dist) for p, dist in nearby]
    else:
        props = query_obj.order_by(Property.created_at.desc()).limit(limit).all()

        district_ids = {p.district_id for p in props}
        districts = {
            d.id: d
            for d in db.query(District).filter(District.id.in_(district_ids)).all()
        }
        items = [_build_item(p, districts.get(p.district_id)) for p in props]

    return {"items": items, "total": len(items)}
