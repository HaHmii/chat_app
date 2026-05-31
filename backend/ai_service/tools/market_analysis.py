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

def _remove_outliers_iqr(values: list[float]) -> list[float]:
    if len(values) < 4:
        return values
    q1 = statistics.quantiles(values, n=4)[0]
    q3 = statistics.quantiles(values, n=4)[2]
    iqr = q3 - q1
    return [v for v in values if q1 - 1.5 * iqr <= v <= q3 + 1.5 * iqr]

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
        params: dict = {"limit": 100}
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

        raw_prices = [float(p["price"]) for p in items if p.get("price")]
        prices = _remove_outliers_iqr(raw_prices)

        raw_pm2 = [
            float(p["price"]) / float(p["area"])
            for p in items
            if p.get("price") and p.get("area") and float(p["area"]) > 0
        ]
        pm2_list = _remove_outliers_iqr(raw_pm2)

        areas_vals = [float(p["area"]) for p in items if p.get("area") and float(p["area"]) > 0]

        scope_parts = []
        if district:
            scope_parts.append(f"Quận {district}")
        if category:
            scope_parts.append(_CATEGORY_VN.get(category, category))
        if property_type:
            scope_parts.append("Cho thuê" if property_type == "rent" else "Bán")
        scope = " — ".join(scope_parts) if scope_parts else "Toàn Hà Nội"

        outlier_note = len(raw_prices) - len(prices)
        lines = [
            f"Phân tích thị trường BĐS: {scope} ({len(items)} tin đăng"
            + (f", loại bỏ {outlier_note} tin giá bất thường" if outlier_note > 0 else "")
            + ")\n"
        ]

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
                # Lọc các tin có diện tích tương đồng ±40% để định giá chính xác hơn
                similar_items = [
                    p for p in items
                    if p.get("price") and p.get("area")
                    and area * 0.6 <= float(p["area"]) <= area * 1.4
                ]
                similar_pm2 = _remove_outliers_iqr([
                    float(p["price"]) / float(p["area"]) for p in similar_items
                ])

                use_similar = len(similar_pm2) >= 3
                est_pm2 = statistics.mean(similar_pm2) if use_similar else avg_pm2
                est = est_pm2 * area

                # Tính range từ percentile thực, fallback về ±15% nếu ít dữ liệu
                ref = similar_pm2 if use_similar else pm2_list
                if len(ref) >= 4:
                    p25 = statistics.quantiles(ref, n=4)[0]
                    p75 = statistics.quantiles(ref, n=4)[2]
                    range_low = p25 * area
                    range_high = p75 * area
                else:
                    range_low = est * 0.85
                    range_high = est * 1.15

                lines += [""]
                if use_similar:
                    lines.append(
                        f"Định giá cho căn {area}m² "
                        f"(dựa trên {len(similar_pm2)} tin tương đồng): ~{_fmt(est)}"
                    )
                else:
                    lines.append(
                        f"Định giá cho căn {area}m² "
                        f"(ít dữ liệu tương đồng, dùng trung bình toàn phân khúc): ~{_fmt(est)}"
                    )
                lines.append(f"(Khoảng {_fmt(range_low)} – {_fmt(range_high)} tuỳ vị trí & nội thất)")

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
