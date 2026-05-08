import logging
from typing import ClassVar, Optional, Type

import httpx
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from core.config import settings

logger = logging.getLogger(__name__)


class PropertySearchInput(BaseModel):
    query: str
    district: Optional[str] = None
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    min_area: Optional[float] = None
    property_type: Optional[str] = None
    bedrooms: Optional[int] = None
    category: Optional[str] = None


class PropertySearchTool(BaseTool):
    name: str = "property_search"
    description: str = (
        "Tìm kiếm nhà đất theo quận, khoảng giá, diện tích, loại hình. "
        "Dùng khi người dùng hỏi tìm nhà, hỏi có nhà phù hợp không."
    )
    args_schema: ClassVar[Type[BaseModel]] = PropertySearchInput

    def _fetch(
        self,
        query: str,
        district: Optional[str] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        min_area: Optional[float] = None,
        property_type: Optional[str] = None,
        bedrooms: Optional[int] = None,
        category: Optional[str] = None,
    ) -> list:
        """Gọi API, trả về danh sách raw items."""
        params: dict = {"limit": 10}
        if district:
            params["district"] = district
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

        print(f"SEARCH  : {params}")

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
    def _format_items(items: list) -> str:
        lines = [f"Tìm được {len(items)} tin đăng:\n"]
        for i, p in enumerate(items, 1):
            dist = p.get("district") or {}
            district_name = dist.get("name", "N/A") if isinstance(dist, dict) else "N/A"
            bedrooms_str = f"{p['bedrooms']} PN | " if p.get("bedrooms") else ""
            bathrooms_str = f"{p['bathrooms']} VS | " if p.get("bathrooms") else ""
            amenities = p.get("amenities") or []
            amenities_str = f"\n   Tiện ích: {', '.join(amenities)}" if amenities else ""
            lines.append(
                f"{i}. [ID:{p.get('id')}] {p.get('title', 'N/A')}\n"
                f"   Giá: {p.get('price_display', 'N/A')} | "
                f"DT: {p.get('area', 'N/A')}m² | "
                f"{bedrooms_str}{bathrooms_str}"
                f"Quận: {district_name}\n"
                f"   Loại: {p.get('type_display','N/A')} – {p.get('category_display','N/A')}\n"
                f"   Địa chỉ: {p.get('address', 'N/A')}\n"
                f"   Pháp lý: {p.get('legal_status', 'N/A')}"
                f"{amenities_str}\n"
            )
        return "\n".join(lines)

    def _run(
        self,
        query: str,
        district: Optional[str] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        min_area: Optional[float] = None,
        property_type: Optional[str] = None,
        bedrooms: Optional[int] = None,
        category: Optional[str] = None,
    ) -> str:
        try:
            items = self._fetch(query=query, district=district, min_price=min_price,
                                max_price=max_price, min_area=min_area,
                                property_type=property_type, bedrooms=bedrooms,
                                category=category)
            if not items:
                return "Không tìm thấy nhà phù hợp với yêu cầu hiện tại."
            return self._format_items(items)
        except httpx.TimeoutException:
            return "Lỗi: Không kết nối được hệ thống. Vui lòng thử lại."
        except Exception as e:
            logger.error(f"PropertySearchTool error: {e}")
            return f"Lỗi khi tìm nhà: {str(e)}"

    def search_raw(
        self,
        query: str,
        district: Optional[str] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        min_area: Optional[float] = None,
        property_type: Optional[str] = None,
        bedrooms: Optional[int] = None,
        category: Optional[str] = None,
    ) -> tuple[str, list]:
        """Trả về (text_cho_llm, raw_items_cho_ui). Dùng trong FindPropertyChain."""
        try:
            items = self._fetch(query=query, district=district, min_price=min_price,
                                max_price=max_price, min_area=min_area,
                                property_type=property_type, bedrooms=bedrooms,
                                category=category)
            if not items:
                return "Không tìm thấy nhà phù hợp với yêu cầu hiện tại.", []
            return self._format_items(items), items
        except httpx.TimeoutException:
            return "Lỗi: Không kết nối được hệ thống. Vui lòng thử lại.", []
        except Exception as e:
            logger.error(f"PropertySearchTool search_raw error: {e}")
            return f"Lỗi khi tìm nhà: {str(e)}", []

    async def _arun(
        self,
        query: str,
        district: Optional[str] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        min_area: Optional[float] = None,
        property_type: Optional[str] = None,
        bedrooms: Optional[int] = None,
        category: Optional[str] = None,
    ) -> str:
        return self._run(
            query=query,
            district=district,
            min_price=min_price,
            max_price=max_price,
            min_area=min_area,
            property_type=property_type,
            bedrooms=bedrooms,
            category=category,
        )
