import logging
from typing import ClassVar, Optional, Type

import httpx
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from core.config import settings
from tools.appointment import AppointmentTool
from tools.post_property import PostPropertyTool
from tools.property_search import PropertySearchTool

logger = logging.getLogger(__name__)


class _AppointmentHandoffInput(BaseModel):
    action: str
    property_id: Optional[int] = None
    proposed_time: Optional[str] = None
    note: Optional[str] = None
    appointment_id: Optional[int] = None


class AppointmentHandoffTool(BaseTool):
    name: str = "appointment"
    description: str = (
        "Đặt lịch, xem lịch hoặc hủy lịch xem nhà. "
        "Dùng khi người dùng muốn hẹn xem nhà hoặc hỏi về lịch đã đặt."
    )
    args_schema: ClassVar[Type[BaseModel]] = _AppointmentHandoffInput
    user_token: str = ""

    def _run(
        self,
        action: str,
        property_id: Optional[int] = None,
        proposed_time: Optional[str] = None,
        note: Optional[str] = None,
        appointment_id: Optional[int] = None,
    ) -> str:
        return AppointmentTool()._run(
            action=action,
            property_id=property_id,
            proposed_time=proposed_time,
            note=note,
            appointment_id=appointment_id,
            user_token=self.user_token,
        )

    async def _arun(
        self,
        action: str,
        property_id: Optional[int] = None,
        proposed_time: Optional[str] = None,
        note: Optional[str] = None,
        appointment_id: Optional[int] = None,
    ) -> str:
        return self._run(action, property_id, proposed_time, note, appointment_id)


class PropertySearchHandoffTool(PropertySearchTool):
    raw_sink: list = Field(default_factory=list)

    @staticmethod
    def _filter_items(
        items: list,
        property_type: Optional[str],
        category: Optional[str],
    ) -> list:
        """Lọc client-side để đảm bảo items khớp với bộ lọc đã yêu cầu.
        Phòng trường hợp LLM agent không truyền đủ params cho API call."""
        result = items
        if property_type:
            result = [it for it in result if it.get("type") == property_type]
        if category:
            result = [it for it in result if it.get("category") == category]
        return result

    def _run(
        self,
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
        text, items = self.search_raw(
            district=district, min_price=min_price, max_price=max_price,
            min_area=min_area, property_type=property_type, bedrooms=bedrooms,
            category=category, location=location, radius_km=radius_km,
        )
        filtered = self._filter_items(items, property_type, category)
        if items and not filtered:
            logger.info(
                f"[PropertySearchHandoffTool] {len(items)} raw items filtered to 0 "
                f"(property_type={property_type!r}, category={category!r})"
            )
            text = "Không tìm thấy nhà phù hợp với yêu cầu hiện tại."
        self.raw_sink.clear()
        self.raw_sink.extend(filtered)
        return text

    async def _arun(self, **kwargs) -> str:
        return self._run(**kwargs)


class _LocationSearchHandoffInput(BaseModel):
    location: str
    radius_km: float = 3.0
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    property_type: Optional[str] = None
    category: Optional[str] = None
    bedrooms: Optional[int] = None
    min_area: Optional[float] = None


class LocationSearchHandoffTool(BaseTool):
    name: str = "location_search"
    description: str = (
        "Tìm BĐS gần một địa điểm, mốc địa lý hoặc khu vực cụ thể "
        "(hồ, trường học, bệnh viện, trung tâm thương mại, tên đường...). "
        "Dùng khi người dùng nói 'gần X', 'cạnh X', 'khu vực X'."
    )
    args_schema: ClassVar[Type[BaseModel]] = _LocationSearchHandoffInput
    raw_sink: list = Field(default_factory=list)

    def _run(
        self,
        location: str,
        radius_km: float = 3.0,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        property_type: Optional[str] = None,
        category: Optional[str] = None,
        bedrooms: Optional[int] = None,
        min_area: Optional[float] = None,
    ) -> str:
        text, items = PropertySearchTool().search_raw(
            location=location, radius_km=radius_km,
            min_price=min_price, max_price=max_price,
            property_type=property_type, category=category,
            bedrooms=bedrooms, min_area=min_area,
        )
        self.raw_sink.clear()
        self.raw_sink.extend(items)
        return text

    async def _arun(self, **kwargs) -> str:
        return self._run(**kwargs)


class _PostPropertyHandoffInput(BaseModel):
    title: str
    type: str
    category: str
    address: str
    district: str
    price: float
    area: float
    price_unit: Optional[str] = None
    description: Optional[str] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    direction: Optional[str] = None
    legal_status: Optional[str] = None


class PostPropertyHandoffTool(BaseTool):
    name: str = "post_property"
    description: str = (
        "Đăng tin bất động sản mới (bán hoặc cho thuê). "
        "Chỉ gọi khi đã có ĐỦ thông tin bắt buộc và người dùng đã xác nhận."
    )
    args_schema: ClassVar[Type[BaseModel]] = _PostPropertyHandoffInput
    user_token: str = ""

    @staticmethod
    def _lookup_district_id(name: str) -> Optional[int]:
        try:
            resp = httpx.get(f"{settings.web_service_url}/districts", timeout=5.0)
            resp.raise_for_status()
            name_lower = name.lower().strip()
            for d in resp.json():
                if name_lower in d["name"].lower() or d["name"].lower() in name_lower:
                    return d["id"]
        except Exception as e:
            logger.warning(f"[PostPropertyTool] district lookup failed: {e}")
        return None

    def _run(
        self,
        title: str,
        type: str,
        category: str,
        address: str,
        district: str,
        price: float,
        area: float,
        price_unit: Optional[str] = None,
        description: Optional[str] = None,
        bedrooms: Optional[int] = None,
        bathrooms: Optional[int] = None,
        direction: Optional[str] = None,
        legal_status: Optional[str] = None,
    ) -> str:
        district_id = self._lookup_district_id(district)
        if not district_id:
            return f"Không tìm thấy quận/huyện '{district}'. Vui lòng kiểm tra lại tên quận."
        return PostPropertyTool()._run(
            title=title, type=type, category=category, address=address,
            district_id=district_id, price=price, area=area,
            price_unit=price_unit, description=description,
            bedrooms=bedrooms, bathrooms=bathrooms,
            direction=direction, legal_status=legal_status,
            user_token=self.user_token,
        )

    async def _arun(self, **kwargs) -> str:
        return self._run(**kwargs)
