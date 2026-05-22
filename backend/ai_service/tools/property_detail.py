import logging
from typing import ClassVar, Type

import httpx
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from core.config import settings

logger = logging.getLogger(__name__)

_CATEGORY_DISPLAY: dict[str, str] = {
    "apartment": "Căn hộ chung cư",
    "house": "Nhà riêng",
    "land": "Đất nền",
    "villa": "Biệt thự",
    "townhouse": "Nhà phố",
    "shophouse": "Shophouse",
    "office": "Văn phòng",
}


class PropertyDetailInput(BaseModel):
    property_id: int


class PropertyDetailTool(BaseTool):
    name: str = "property_detail"
    description: str = (
        "Lấy thông tin chi tiết của một BĐS cụ thể theo ID. "
        "Dùng khi người dùng hỏi chi tiết về một căn nhà đã được liệt kê."
    )
    args_schema: ClassVar[Type[BaseModel]] = PropertyDetailInput

    def _fetch(self, property_id: int) -> dict:
        resp = httpx.get(
            f"{settings.web_service_url}/properties/{property_id}",
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _format(data: dict) -> str:
        category_raw = data.get("category") or ""
        category = _CATEGORY_DISPLAY.get(category_raw, category_raw)

        amenities = data.get("amenities") or []
        amenities_str = ", ".join(amenities) if amenities else "Không có thông tin"

        images = data.get("images") or []
        image_count = len(images)

        lines = [
            f"### {data.get('title', 'N/A')}",
            f"- Loại hình: {category}",
            f"- Giá: {_build_price_display(data)}",
            f"- Diện tích: {data.get('area', 'N/A')} m²",
        ]

        if data.get("bedrooms") is not None:
            lines.append(f"- Số phòng ngủ: {data['bedrooms']}")
        if data.get("bathrooms") is not None:
            lines.append(f"- Số phòng vệ sinh: {data['bathrooms']}")
        if data.get("direction"):
            lines.append(f"- Hướng nhà: {data['direction']}")
        if data.get("legal_status"):
            lines.append(f"- Pháp lý: {data['legal_status']}")

        lines += [
            f"- Địa chỉ: {_build_address(data)}",
            f"- Tiện ích: {amenities_str}",
        ]

        if data.get("description"):
            lines.append(f"- Mô tả: {data['description']}")

        if data.get("owner_name"):
            lines.append(f"- Chủ nhà: {data['owner_name']}")
        if data.get("owner_phone"):
            lines.append(f"- Liên hệ: {data['owner_phone']}")

        if image_count:
            lines.append(f"- Hình ảnh: {image_count} ảnh")

        return "\n".join(lines)

    def _run(self, property_id: int) -> str:
        try:
            data = self._fetch(property_id)
            return self._format(data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return f"Không tìm thấy BĐS với ID {property_id}."
            logger.error(f"PropertyDetailTool HTTP error: {e}")
            return f"Lỗi khi lấy thông tin BĐS: {e.response.status_code}"
        except httpx.TimeoutException:
            return "Lỗi: Không kết nối được hệ thống. Vui lòng thử lại."
        except Exception as e:
            logger.error(f"PropertyDetailTool error: {e}")
            return f"Lỗi khi lấy thông tin BĐS: {str(e)}"

    def fetch_raw(self, property_id: int) -> tuple[str, dict]:
        """Trả về (text_cho_llm, raw_data). Dùng trong chain."""
        try:
            data = self._fetch(property_id)
            return self._format(data), data
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                msg = f"Không tìm thấy BĐS với ID {property_id}."
            else:
                msg = f"Lỗi khi lấy thông tin BĐS: {e.response.status_code}"
            logger.error(f"PropertyDetailTool fetch_raw HTTP error: {e}")
            return msg, {}
        except httpx.TimeoutException:
            return "Lỗi: Không kết nối được hệ thống. Vui lòng thử lại.", {}
        except Exception as e:
            logger.error(f"PropertyDetailTool fetch_raw error: {e}")
            return f"Lỗi khi lấy thông tin BĐS: {str(e)}", {}

    async def _arun(self, property_id: int) -> str:
        return self._run(property_id)


def _build_price_display(data: dict) -> str:
    price = data.get("price")
    unit = data.get("price_unit") or ""
    if price is None:
        return "N/A"
    return f"{price:,.0f} {unit}".strip()


def _build_address(data: dict) -> str:
    parts = [data.get("street"), data.get("ward"), data.get("address")]
    non_empty = [p for p in parts if p]
    return ", ".join(non_empty) if non_empty else "N/A"


property_detail_tool = PropertyDetailTool()
