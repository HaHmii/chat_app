import logging
from typing import ClassVar, List, Optional, Type

import httpx
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from core.config import settings

logger = logging.getLogger(__name__)


class PostPropertyInput(BaseModel):
    title: str
    type: str          # sell | rent
    category: str      # apartment | house | land | villa | townhouse | shophouse | office
    address: str
    district_id: int
    price: float
    area: float
    price_unit: Optional[str] = None
    description: Optional[str] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    direction: Optional[str] = None
    legal_status: Optional[str] = None
    amenities: Optional[List[str]] = []
    user_token: Optional[str] = None


class PostPropertyTool(BaseTool):
    name: str = "post_property"
    description: str = (
        "Đăng tin bất động sản mới lên hệ thống. "
        "Dùng khi chủ nhà muốn đăng tin bán hoặc cho thuê bất động sản."
    )
    args_schema: ClassVar[Type[BaseModel]] = PostPropertyInput

    def _run(
        self,
        title: str,
        type: str,
        category: str,
        address: str,
        district_id: int,
        price: float,
        area: float,
        price_unit: Optional[str] = None,
        description: Optional[str] = None,
        bedrooms: Optional[int] = None,
        bathrooms: Optional[int] = None,
        direction: Optional[str] = None,
        legal_status: Optional[str] = None,
        amenities: Optional[List[str]] = None,
        user_token: Optional[str] = None,
    ) -> str:
        if not user_token:
            return "Bạn cần đăng nhập để đăng tin bất động sản."

        payload: dict = {
            "title": title,
            "type": type,
            "category": category,
            "address": address,
            "district_id": district_id,
            "price": price,
            "area": area,
        }
        if price_unit:
            payload["price_unit"] = price_unit
        if description:
            payload["description"] = description
        if bedrooms is not None:
            payload["bedrooms"] = bedrooms
        if bathrooms is not None:
            payload["bathrooms"] = bathrooms
        if direction:
            payload["direction"] = direction
        if legal_status:
            payload["legal_status"] = legal_status
        if amenities:
            payload["amenities"] = amenities

        try:
            resp = httpx.post(
                f"{settings.web_service_url}/properties/create",
                json=payload,
                headers={"Authorization": f"Bearer {user_token}"},
                timeout=10.0,
            )
            if resp.status_code == 201:
                data = resp.json()
                prop_id = data.get("id", "N/A")
                return (
                    f"Đăng tin thành công! Tin đăng đang chờ admin duyệt.\n"
                    f"Mã tin: #{prop_id} | Tiêu đề: {data.get('title', title)}"
                )
            if resp.status_code == 403:
                return (
                    "Tài khoản của bạn chưa có quyền đăng tin. "
                    "Vui lòng nâng cấp lên tài khoản Chủ nhà để sử dụng tính năng này."
                )
            if resp.status_code == 401:
                return "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại."
            detail = resp.json().get("detail", "Lỗi không xác định")
            return f"Đăng tin thất bại: {detail}"
        except httpx.TimeoutException:
            return "Lỗi: Không kết nối được hệ thống. Vui lòng thử lại sau."
        except Exception as e:
            logger.error(f"PostPropertyTool error: {e}")
            return f"Lỗi khi đăng tin: {str(e)}"

    async def _arun(self, **kwargs) -> str:
        return self._run(**kwargs)
