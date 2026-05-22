import logging
from typing import ClassVar, Optional, Type
import httpx
from langchain_core.tools import BaseTool
from pydantic import BaseModel
from core.config import settings

logger = logging.getLogger(__name__)

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_NOMINATIM_HEADERS = {"User-Agent": "BDSHanoiChatbot/1.0 (contact: admin@bds-hanoi.vn)"}


class PropertySearchInput(BaseModel):
    query: str = ""
    district: Optional[str] = None
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    min_area: Optional[float] = None
    property_type: Optional[str] = None
    bedrooms: Optional[int] = None
    category: Optional[str] = None
    location: Optional[str] = None   # tên địa điểm/mốc → tìm gần đây
    radius_km: float = 3.0


class PropertySearchTool(BaseTool):
    name: str = "property_search"
    description: str = (
        "Tìm kiếm nhà đất theo quận, khoảng giá, diện tích, loại hình. "
        "Khi người dùng nói 'gần X', 'cạnh X', 'khu vực X', truyền thêm location=<tên địa điểm>. "
        "Dùng khi người dùng hỏi tìm nhà, hỏi có nhà phù hợp không."
    )
    args_schema: ClassVar[Type[BaseModel]] = PropertySearchInput

    def _geocode(self, location: str) -> tuple[float, float] | None:
        """Chuyển tên địa điểm thành tọa độ (lat, lng) qua Nominatim (OpenStreetMap)."""
        try:
            resp = httpx.get(
                _NOMINATIM_URL,
                params={
                    "q": f"{location}, Hà Nội",
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
                logger.info(f"[PropertySearch] geocoded {location!r} → lat={lat:.4f} lng={lng:.4f}")
                return lat, lng
            logger.warning(f"[PropertySearch] geocode no result for {location!r}")
        except Exception as e:
            logger.error(f"[PropertySearch] geocode error: {e}")
        return None

    def _fetch(
        self,
        query: str = "",
        district: Optional[str] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        min_area: Optional[float] = None,
        property_type: Optional[str] = None,
        bedrooms: Optional[int] = None,
        category: Optional[str] = None,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        radius_km: float = 3.0,
    ) -> list:
        params: dict = {"limit": 10}

        if lat is not None and lng is not None:
            params["lat"] = lat
            params["lng"] = lng
            params["radius_km"] = radius_km
            print(f"SEARCH  : lat={lat:.4f} lng={lng:.4f} r={radius_km}km | {params}")
        else:
            if query:
                params["q"] = query
            if district:
                params["district"] = district
            print(f"SEARCH  : q={query!r} district={district!r} | {params}")

        if min_price is not None:
            params["min_price"] = min_price
        if max_price is not None:
            params["max_price"] = max_price
        if min_area is not None:
            params["min_area"] = min_area
        if property_type:
            params["property_type"] = property_type
        if bedrooms is not None:
            params["bedrooms"] = bedrooms
        if category:
            params["category"] = category

        resp = httpx.get(
            f"{settings.web_service_url}/search-properties/",
            params=params,
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        return data.get("items") or data.get("results") or []

    @staticmethod
    def _format_items(items: list, location: str | None = None) -> str:
        header = f"Tìm được {len(items)} BĐS gần '{location}':\n" if location else f"Tìm được {len(items)} tin đăng:\n"
        lines = [header]
        for i, p in enumerate(items, 1):
            dist = p.get("district") or {}
            district_name = dist.get("name", "N/A") if isinstance(dist, dict) else "N/A"
            bedrooms_str = f"{p['bedrooms']} PN | " if p.get("bedrooms") else ""
            bathrooms_str = f"{p['bathrooms']} VS | " if p.get("bathrooms") else ""
            distance_str = f" | Cách {p['distance_km']:.1f}km" if p.get("distance_km") is not None else ""
            amenities = p.get("amenities") or []
            amenities_str = f"\n   Tiện ích: {', '.join(amenities)}" if amenities else ""
            lines.append(
                f"{i}. [ID:{p.get('id')}] {p.get('title', 'N/A')}\n"
                f"   Giá: {p.get('price_display', 'N/A')} | "
                f"DT: {p.get('area', 'N/A')}m² | "
                f"{bedrooms_str}{bathrooms_str}"
                f"Quận: {district_name}{distance_str}\n"
                f"   Loại: {p.get('type_display', 'N/A')} – {p.get('category_display', 'N/A')}\n"
                f"   Địa chỉ: {p.get('address', 'N/A')}\n"
                f"   Pháp lý: {p.get('legal_status', 'N/A')}"
                f"{amenities_str}\n"
            )
        return "\n".join(lines)

    def _run(
        self,
        query: str = "",
        district: Optional[str] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        min_area: Optional[float] = None,
        property_type: Optional[str] = None,
        bedrooms: Optional[int] = None,
        category: Optional[str] = None,
        location: Optional[str] = None,
        radius_km: float = 3.0,
    ) -> str:
        lat, lng = None, None
        if location:
            coords = self._geocode(location)
            if not coords:
                return f"Không thể xác định tọa độ của '{location}'. Vui lòng thử tên địa điểm khác."
            lat, lng = coords
        try:
            items = self._fetch(
                query=query, district=district,
                min_price=min_price, max_price=max_price, min_area=min_area,
                property_type=property_type, bedrooms=bedrooms, category=category,
                lat=lat, lng=lng, radius_km=radius_km,
            )
            if not items:
                if location:
                    return f"Không tìm thấy BĐS trong bán kính {radius_km}km gần '{location}'."
                return "Không tìm thấy nhà phù hợp với yêu cầu hiện tại."
            return self._format_items(items, location=location)
        except httpx.TimeoutException:
            return "Lỗi: Không kết nối được hệ thống. Vui lòng thử lại."
        except Exception as e:
            logger.error(f"PropertySearchTool error: {e}")
            return f"Lỗi khi tìm nhà: {str(e)}"

    def search_raw(
        self,
        query: str = "",
        district: Optional[str] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        min_area: Optional[float] = None,
        property_type: Optional[str] = None,
        bedrooms: Optional[int] = None,
        category: Optional[str] = None,
        location: Optional[str] = None,
        radius_km: float = 3.0,
    ) -> tuple[str, list]:
        """Trả về (text_cho_llm, raw_items_cho_ui). Dùng trong FindPropertyChain."""
        lat, lng = None, None
        if location:
            coords = self._geocode(location)
            if not coords:
                return f"Không thể xác định tọa độ của '{location}'.", []
            lat, lng = coords
        try:
            items = self._fetch(
                query=query, district=district,
                min_price=min_price, max_price=max_price, min_area=min_area,
                property_type=property_type, bedrooms=bedrooms, category=category,
                lat=lat, lng=lng, radius_km=radius_km,
            )
            if not items:
                if location:
                    return f"Không tìm thấy BĐS trong bán kính {radius_km}km gần '{location}'.", []
                return "Không tìm thấy nhà phù hợp với yêu cầu hiện tại.", []
            return self._format_items(items, location=location), items
        except httpx.TimeoutException:
            return "Lỗi: Không kết nối được hệ thống. Vui lòng thử lại.", []
        except Exception as e:
            logger.error(f"PropertySearchTool search_raw error: {e}")
            return f"Lỗi khi tìm nhà: {str(e)}", []

    async def _arun(
        self,
        query: str = "",
        district: Optional[str] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        min_area: Optional[float] = None,
        property_type: Optional[str] = None,
        bedrooms: Optional[int] = None,
        category: Optional[str] = None,
        location: Optional[str] = None,
        radius_km: float = 3.0,
    ) -> str:
        return self._run(
            query=query, district=district,
            min_price=min_price, max_price=max_price, min_area=min_area,
            property_type=property_type, bedrooms=bedrooms, category=category,
            location=location, radius_km=radius_km,
        )
