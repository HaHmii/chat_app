import logging
import re
import time
from datetime import datetime, timedelta
from typing import ClassVar, Optional, Type

import httpx
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError
from pydantic import BaseModel, Field

from chains.appointment import _is_confirmation
from core.config import settings
from core.utils import VN_TZ
from prompts.shared import (
    APPOINTMENT_BOOKING_RULES,
    APPOINTMENT_TIME_RULES,
    LEGAL_RESPONSE_RULES,
    LEGAL_TERM_MAPPING,
    MARKET_ANALYSIS_RESPONSE_RULES,
    POST_PROPERTY_RULES,
    PROPERTY_LISTING_RULES,
)
from tools.appointment import AppointmentTool
from tools.legal_query import LegalQueryTool
from tools.market_analysis import MarketAnalysisTool
from tools.post_property import PostPropertyTool
from tools.property_detail import PropertyDetailTool
from tools.property_search import PropertySearchTool

logger = logging.getLogger(__name__)

_MAX_ITERATIONS = 5
_RECURSION_LIMIT = _MAX_ITERATIONS * 2 + 1

_WEEKDAY_VN = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
_BOOKING_KEYWORDS = ("đặt lịch", "đặt hẹn", "hẹn xem", "lịch hẹn", "xem nhà")

_ISO_TIME_RE = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+07:00')
_CAN_SO_RE = re.compile(r'căn\s+số\s+(\d+)', re.IGNORECASE)

_CONFIRM_RESPONSE_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Thông báo kết quả đặt lịch xem nhà cho người dùng. Trả lời thân thiện, ngắn gọn.\n"
     "QUAN TRỌNG: Dùng ĐÚNG tên căn và thời gian dưới đây, KHÔNG lấy từ lịch sử.\n"
     "{property_context}"
     "Kết quả từ hệ thống:\n{tool_result}\n\n"
     "Lịch sử: {history}"),
    ("human", "{user_message}"),
])


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _build_week_calendar(now: datetime) -> str:
    today_wd = now.weekday()
    lines = []
    for i, name in enumerate(_WEEKDAY_VN):
        days_ahead = (i - today_wd) % 7
        label = (
            now.strftime("%Y-%m-%d") + " (hôm nay)"
            if days_ahead == 0
            else (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        )
        lines.append(f"  {name}: {label}")
    return "\n".join(lines)


def _extract_pending_from_output(
    output: str, property_list: list, property_details: list
) -> dict:
    times = _ISO_TIME_RE.findall(output)
    proposed_time = times[0] if times else None

    property_id = None
    property_title = ""
    can_matches = _CAN_SO_RE.findall(output)
    if can_matches:
        idx = int(can_matches[0]) - 1
        if 0 <= idx < len(property_list):
            property_id = property_list[idx]
            if idx < len(property_details):
                property_title = property_details[idx].get("title", "")
    elif len(property_list) == 1:
        property_id = property_list[0]
        property_title = property_details[0].get("title", "") if property_details else ""

    return {
        "property_id": property_id,
        "proposed_time": proposed_time,
        "property_title": property_title,
    }


def _extract_tool_chain(messages: list) -> list[str]:
    chain = []
    for msg in messages:
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                if name:
                    chain.append(name)
    return chain


def _extract_final_output(messages: list) -> str:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            content = msg.content
            return content if isinstance(content, str) else str(content)
    return ""


# ─── Tool wrappers ────────────────────────────────────────────────────────────

class _AppointmentHandoffInput(BaseModel):
    action: str
    property_id: Optional[int] = None
    proposed_time: Optional[str] = None
    note: Optional[str] = None
    appointment_id: Optional[int] = None


class _AppointmentHandoffTool(BaseTool):
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


class _PropertySearchHandoffTool(PropertySearchTool):
    raw_sink: list = Field(default_factory=list)

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
        text, items = self.search_raw(
            query=query,
            district=district,
            min_price=min_price,
            max_price=max_price,
            min_area=min_area,
            property_type=property_type,
            bedrooms=bedrooms,
            category=category,
        )
        self.raw_sink.clear()
        self.raw_sink.extend(items)
        return text


class _LocationSearchHandoffInput(BaseModel):
    location: str
    radius_km: float = 3.0
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    property_type: Optional[str] = None
    category: Optional[str] = None
    bedrooms: Optional[int] = None
    min_area: Optional[float] = None


class _LocationSearchHandoffTool(BaseTool):
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
            location=location,
            radius_km=radius_km,
            min_price=min_price,
            max_price=max_price,
            property_type=property_type,
            category=category,
            bedrooms=bedrooms,
            min_area=min_area,
        )
        self.raw_sink.clear()
        self.raw_sink.extend(items)
        return text

    async def _arun(
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
        return self._run(
            location=location, radius_km=radius_km,
            min_price=min_price, max_price=max_price,
            property_type=property_type, category=category,
            bedrooms=bedrooms, min_area=min_area,
        )


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


class _PostPropertyHandoffTool(BaseTool):
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
            logger.warning(f"[HandoffAgent] district lookup failed: {e}")
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
            title=title,
            type=type,
            category=category,
            address=address,
            district_id=district_id,
            price=price,
            area=area,
            price_unit=price_unit,
            description=description,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            direction=direction,
            legal_status=legal_status,
            user_token=self.user_token,
        )

    async def _arun(self, **kwargs) -> str:
        return self._run(**kwargs)


# ─── HandoffAgent ─────────────────────────────────────────────────────────────

class HandoffAgent:
    def __init__(self):
        self._llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.3,
        )
        self._confirm_chain = _CONFIRM_RESPONSE_PROMPT | self._llm | StrOutputParser()

    def _build_graph(
        self,
        property_tool: _PropertySearchHandoffTool,
        location_tool: _LocationSearchHandoffTool,
        appointment_tool: _AppointmentHandoffTool,
        post_property_tool: _PostPropertyHandoffTool,
        history: str,
        extracted_slots: dict,
    ):
        now = datetime.now(VN_TZ)
        today = now.strftime("%Y-%m-%d")
        tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        week_calendar = _build_week_calendar(now)

        property_list: list = extracted_slots.get("property_list") or []
        property_details: list = extracted_slots.get("property_list_details") or []
        if property_list:
            mapping_lines = []
            for i, pid in enumerate(property_list):
                detail = property_details[i] if i < len(property_details) else {}
                title = detail.get("title", "")
                price = detail.get("price_display", "")
                area = detail.get("area", "")
                district = detail.get("district", "")
                meta = " | ".join(filter(None, [title, price, f"{area}m²" if area else "", district]))
                mapping_lines.append(
                    f"  Căn số {i + 1}: property_id={pid}" + (f" — {meta}" if meta else "")
                )
            property_mapping_section = (
                "Danh sách căn nhà từ kết quả tìm kiếm gần nhất (NGUỒN DUY NHẤT để xác định property_id):\n"
                + "\n".join(mapping_lines) + "\n"
                "Khi người dùng nói 'căn số X', 'căn thứ X', 'căn đầu tiên', 'căn cuối'... "
                "hãy tra bảng trên để lấy đúng property_id và dùng tên căn khi xác nhận với người dùng.\n"
            )
        else:
            property_mapping_section = (
                "Chưa có kết quả tìm kiếm trong phiên này. "
                "Nếu người dùng đề cập 'căn số X' mà chưa tìm nhà, gọi property_search trước.\n"
            )

        system_prompt = (
            "Bạn là tư vấn viên bất động sản Hà Nội, có thể tìm nhà, xem chi tiết, đặt lịch, "
            "phân tích thị trường, tra cứu pháp lý và hỗ trợ đăng tin.\n"
            "Sử dụng các tools theo đúng hướng dẫn dưới đây.\n\n"

            "═══ 1. TÌM NHÀ THEO BỘ LỌC (tool: property_search) ═══\n"
            "- Dùng khi người dùng tìm nhà theo quận, giá, diện tích, loại hình.\n"
            "- Gọi NGAY với bất kỳ thông tin nào có: district, min_price, max_price, "
            "min_area, property_type (rent/sell), bedrooms, category.\n"
            "- KHÔNG hỏi thêm trước khi tìm.\n"
            + PROPERTY_LISTING_RULES + "\n"

            "═══ 2. TÌM NHÀ THEO VỊ TRÍ GPS (tool: location_search) ═══\n"
            "- Dùng khi người dùng nói 'gần X', 'cạnh X', 'khu vực X' với tên địa danh cụ thể.\n"
            "- location: tên địa điểm (Hồ Tây, Đại học Bách Khoa, Big C, Vincom, tên đường...).\n"
            "- radius_km: bán kính km, mặc định 3.0 nếu không nói rõ.\n"
            "- Gọi NGAY, không hỏi thêm. Thêm khoảng cách (km) sau tên quận khi trình bày.\n"
            + PROPERTY_LISTING_RULES + "\n"

            "═══ 3. XEM CHI TIẾT BĐS (tool: property_detail) ═══\n"
            "- Dùng khi người dùng hỏi thông tin chi tiết về một căn cụ thể.\n"
            "- Tra bảng danh sách căn bên dưới để lấy đúng property_id trước khi gọi tool.\n\n"

            "═══ 4. PHÂN TÍCH GIÁ THỊ TRƯỜNG (tool: market_analysis) ═══\n"
            "- Dùng khi người dùng hỏi 'giá thị trường', 'giá trung bình', "
            "'định giá', 'ước tính giá', 'so sánh giá'.\n"
            "- Tham số tuỳ chọn: district, category, property_type, area (m² để định giá).\n"
            "- Gọi ngay với thông tin có được.\n"
            + MARKET_ANALYSIS_RESPONSE_RULES + "\n"

            "═══ 5. ĐẶT/XEM/HỦY LỊCH HẸN (tool: appointment) ═══\n"
            + property_mapping_section + "\n"
            f"Hôm nay là {today} (UTC+7). Lịch tuần (tra ngay, không tự tính):\n"
            f"{week_calendar}\n\n"
            + APPOINTMENT_TIME_RULES
            + f"  Ví dụ: '9h sáng mai' → {tomorrow}T09:00:00+07:00\n\n"
            + APPOINTMENT_BOOKING_RULES + "\n"

            "═══ 6. PHÁP LÝ BĐS (tool: legal_query) ═══\n"
            "Bước A — Quy đổi thuật ngữ trước khi gọi tool:\n"
            + LEGAL_TERM_MAPPING + "\n"
            "Bước B — Sau khi nhận văn bản pháp luật từ tool:\n"
            + LEGAL_RESPONSE_RULES + "\n"

            "═══ 7. ĐĂNG TIN BĐS (tool: post_property) ═══\n"
            + POST_PROPERTY_RULES + "\n"

            f"Lịch sử hội thoại:\n{history}"
        )

        return create_agent(
            model=self._llm,
            tools=[
                property_tool,
                location_tool,
                PropertyDetailTool(),
                MarketAnalysisTool(),
                appointment_tool,
                LegalQueryTool(),
                post_property_tool,
            ],
            system_prompt=system_prompt,
        )

    async def _confirm_booking(
        self,
        pending: dict,
        user_message: str,
        history: str,
        user_token: str | None,
        start: float,
    ) -> dict:
        tool_result = AppointmentTool()._run(
            action="book",
            property_id=pending.get("property_id"),
            proposed_time=pending.get("proposed_time"),
            note=pending.get("note"),
            user_token=user_token,
        )
        logger.info(f"[HandoffAgent] confirmed booking | {tool_result[:80]!r}")

        property_title = pending.get("property_title", "")
        property_context = (
            f"Tên căn đã đặt (dùng chính xác tên này, không lấy từ lịch sử): {property_title}\n"
            if property_title else ""
        )

        response = await self._confirm_chain.ainvoke({
            "tool_result": tool_result,
            "property_context": property_context,
            "user_message": user_message,
            "history": history,
        })

        return {
            "response": response,
            "detected_intent": None,
            "confidence_score": None,
            "agent_chain": ["HandoffAgent", "appointment"],
            "retrieved_context": tool_result,
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "tool_calls_count": 1,
            "should_escalate": False,
            "raw_items": [],
            "clear_pending_appointment": True,
        }

    async def run(
        self,
        user_message: str,
        history: str = "",
        extracted_slots: dict | None = None,
        user_token: str | None = None,
    ) -> dict:
        start = time.perf_counter()
        extracted_slots = extracted_slots or {}

        pending = extracted_slots.get("pending_appointment") or {}
        if (
            pending.get("property_id")
            and pending.get("proposed_time")
            and _is_confirmation(user_message)
        ):
            return await self._confirm_booking(pending, user_message, history, user_token, start)

        property_tool = _PropertySearchHandoffTool()
        location_tool = _LocationSearchHandoffTool()
        appointment_tool = _AppointmentHandoffTool(user_token=user_token or "")
        post_property_tool = _PostPropertyHandoffTool(user_token=user_token or "")
        graph = self._build_graph(
            property_tool, location_tool, appointment_tool, post_property_tool,
            history, extracted_slots,
        )

        try:
            state = await graph.ainvoke(
                {"messages": [HumanMessage(content=user_message)]},
                config={"recursion_limit": _RECURSION_LIMIT},
            )
            messages = state.get("messages", [])
            tool_chain = _extract_tool_chain(messages)
            output = _extract_final_output(messages)
            raw_items = list(property_tool.raw_sink) or list(location_tool.raw_sink)

            result: dict = {
                "response": output,
                "detected_intent": None,
                "confidence_score": None,
                "agent_chain": ["HandoffAgent"] + tool_chain,
                "retrieved_context": None,
                "latency_ms": int((time.perf_counter() - start) * 1000),
                "tool_calls_count": len(tool_chain),
                "should_escalate": False,
                "raw_items": raw_items,
            }

            has_booking_intent = any(k in user_message.lower() for k in _BOOKING_KEYWORDS)
            if has_booking_intent and "appointment" not in tool_chain:
                property_list = extracted_slots.get("property_list") or []
                property_details = extracted_slots.get("property_list_details") or []
                pending_slots = _extract_pending_from_output(output, property_list, property_details)
                if pending_slots.get("property_id") and pending_slots.get("proposed_time"):
                    result["pending_appointment"] = pending_slots
                    logger.info(f"[HandoffAgent] pending saved: pid={pending_slots['property_id']} time={pending_slots['proposed_time']!r}")

            return result

        except GraphRecursionError:
            logger.warning(f"[HandoffAgent] max_iterations ({_MAX_ITERATIONS}) reached for: {user_message!r}")
            return {
                "response": "Yêu cầu này khá phức tạp. Để tôi chuyển đến nhân viên hỗ trợ bạn.",
                "detected_intent": None,
                "confidence_score": None,
                "agent_chain": ["HandoffAgent", "MAX_ITERATIONS_REACHED"],
                "retrieved_context": None,
                "latency_ms": int((time.perf_counter() - start) * 1000),
                "tool_calls_count": 0,
                "should_escalate": True,
                "raw_items": [],
            }

        except Exception as e:
            logger.error(f"[HandoffAgent] error: {e}")
            return {
                "response": f"Lỗi xử lý: {str(e)}",
                "detected_intent": None,
                "confidence_score": None,
                "agent_chain": ["HandoffAgent", "ERROR"],
                "retrieved_context": None,
                "latency_ms": int((time.perf_counter() - start) * 1000),
                "tool_calls_count": 0,
                "should_escalate": False,
                "raw_items": [],
            }


handoff_agent = HandoffAgent()
