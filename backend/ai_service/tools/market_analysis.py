import logging
import statistics
from typing import ClassVar, Optional, Type
import httpx
from langchain_core.tools import BaseTool
from pydantic import BaseModel
from core.config import settings

logger = logging.getLogger(__name__)

_CATEGORY_VN = {
    "apartment": "Chung cư",
    "house": "Nhà riêng",
    "land": "Đất nền",
    "villa": "Biệt thự",
    "townhouse": "Nhà phố",
    "shophouse": "Shophouse",
    "office": "Văn phòng",
}

def _fmt(price: float) -> str:
    if price >= 1_000_000_000:
        val = price / 1_000_000_000
        return f"{val:.1f} Tỷ"
    if price >= 1_000_000:
        return f"{price / 1_000_000:.0f} Triệu"
    return f"{price:,.0f} VNĐ"

class MarketAnalysisInput(BaseModel):
    district: Optional[str] = None
    category: Optional[str] = None   # apartment | house | land | villa | townhouse | shophouse | office
    property_type: Optional[str] = None  # sell | rent
    area: Optional[float] = None  # m², dùng để định giá ước tính

class MarketAnalysisTool(BaseTool):
    name: str = "market_analysis"
    description: str = (
        "So sánh giá thị trường BĐS theo quận/loại hình. "
        "Nếu có diện tích (area m²), ước tính giá cho căn đó. "
        "Dùng khi người dùng hỏi 'giá thị trường', 'giá trung bình', 'định giá', 'ước tính giá'."
    )
    args_schema: ClassVar[Type[BaseModel]] = MarketAnalysisInput

    def _run(
        self,
        district: Optional[str] = None,
        category: Optional[str] = None,
        property_type: Optional[str] = None,
        area: Optional[float] = None,
    ) -> str:
        params: dict = {"limit": 20}
        if district:
            params["district"] = district
        if category:
            params["category"] = category
        if property_type:
            params["property_type"] = property_type

        try:
            resp = httpx.get(
                f"{settings.web_service_url}/search-properties/",
                params=params,
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items") or data.get("results") or []
        except httpx.TimeoutException:
            return "Lỗi: Không kết nối được hệ thống. Vui lòng thử lại."
        except Exception as e:
            logger.error(f"MarketAnalysisTool error: {e}")
            return f"Lỗi khi lấy dữ liệu thị trường: {str(e)}"

        if not items:
            scope = f"quận {district}" if district else "Hà Nội"
            return f"Không đủ dữ liệu để phân tích thị trường tại {scope}."

        prices = [float(p["price"]) for p in items if p.get("price")]
        pm2_list = [
            float(p["price"]) / float(p["area"])
            for p in items
            if p.get("price") and p.get("area") and float(p["area"]) > 0
        ]
        areas_vals = [float(p["area"]) for p in items if p.get("area") and float(p["area"]) > 0]

        scope_parts = []
        if district:
            scope_parts.append(f"Quận {district}")
        if category:
            scope_parts.append(_CATEGORY_VN.get(category, category))
        if property_type:
            scope_parts.append("Cho thuê" if property_type == "rent" else "Bán")
        scope = " — ".join(scope_parts) if scope_parts else "Toàn Hà Nội"

        lines = [f"Phân tích thị trường BĐS: {scope} ({len(items)} tin đăng)\n"]

        if prices:
            lines += [
                f"- Giá trung bình : {_fmt(statistics.mean(prices))}",
                f"- Giá thấp nhất  : {_fmt(min(prices))}",
                f"- Giá cao nhất   : {_fmt(max(prices))}",
            ]
            if len(prices) >= 3:
                lines.append(f"- Trung vị        : {_fmt(statistics.median(prices))}")

        if pm2_list:
            avg_pm2 = statistics.mean(pm2_list)
            lines.append(f"- Giá/m² trung bình: {_fmt(avg_pm2)}/m²")
            if area and area > 0:
                est = avg_pm2 * area
                lines += [
                    "",
                    f"Định giá cho căn {area}m²: ~{_fmt(est)}",
                    f"(Khoảng {_fmt(est * 0.85)} – {_fmt(est * 1.15)} tuỳ vị trí & nội thất)",
                ]

        if areas_vals:
            lines.append(f"- Diện tích trung bình: {statistics.mean(areas_vals):.0f} m²")

        return "\n".join(lines)

    async def _arun(
        self,
        district: Optional[str] = None,
        category: Optional[str] = None,
        property_type: Optional[str] = None,
        area: Optional[float] = None,
    ) -> str:
        return self._run(district=district, category=category, property_type=property_type, area=area)
