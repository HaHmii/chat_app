import json
import logging
import re
import unicodedata

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError

from core.config import settings
from pattern.tools import LocationSearchHandoffTool, PropertySearchHandoffTool
from pattern.utils import RECURSION_LIMIT, extract_final_output, extract_tool_chain
from prompts.shared import PROPERTY_LISTING_RULES
from tools.property_search import PropertySearchTool

logger = logging.getLogger(__name__)

SEARCH_SLOT_KEYS = {
    "district", "min_price", "max_price", "min_area",
    "property_type", "bedrooms", "category", "location_landmark", "radius_km",
}

_PAGE_SIZE = 5

_SHOW_MORE_KEYWORDS = (
    "tìm thêm", "tim them", "căn khác", "can khac", "xem thêm", "xem them",
    "thêm nữa", "them nua", "tiếp theo", "tiep theo", "còn căn nào", "con can nao",
    "còn nhà nào", "con nha nao", "còn nữa", "con nua",
    "những căn khác", "nhà khác", "cho xem thêm",
)


def _is_show_more_request(message: str) -> bool:
    lowered = message.lower()
    return any(k in lowered for k in _SHOW_MORE_KEYWORDS)


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


_BUDGET_MAX_RE = re.compile(
    r"\b(?:ngan sach|budget|toi da|khong qua|duoi)\s*(?:khoang\s*)?(\d+(?:[\.,]\d+)?)"
)


def _parse_number(value: str) -> int | float:
    parsed = float(value.replace(",", "."))
    return int(parsed) if parsed.is_integer() else parsed


def _apply_deterministic_slot_overrides(message: str, slots: dict) -> dict:
    normalized = _strip_accents(message).lower()
    budget_match = _BUDGET_MAX_RE.search(normalized)
    if not budget_match:
        return slots
    corrected = dict(slots)
    max_price = _parse_number(budget_match.group(1))
    corrected["max_price"] = max_price
    if corrected.get("min_price") == max_price:
        corrected.pop("min_price", None)
    return corrected


# ─── Chain mode prompts ────────────────────────────────────────────────────────

_SLOT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Trích xuất bộ lọc tìm kiếm BĐS Hà Nội. Trả về JSON thuần (không markdown, không giải thích).\n"
     'Template: {{"district":null,"min_price":null,"max_price":null,"min_area":null,"property_type":null,"bedrooms":null,"category":null,"location_landmark":null,"radius_km":null}}\n'
     "Quy tắc:\n"
     "- location_landmark: tên địa điểm/mốc địa lý khi người dùng nói 'gần X', 'cạnh X', 'khu vực X' "
     "(ví dụ: 'Hồ Tây', 'ĐHBK', 'Big C Thăng Long', 'Vincom Bà Triệu'). null nếu không đề cập.\n"
     "- radius_km: bán kính tìm kiếm (km) khi có location_landmark, mặc định 3.0 nếu không nói rõ, null nếu không có location_landmark\n"
     "- district: tên quận/huyện (Cầu Giấy, Ba Đình...) hoặc null — điền khi người dùng đề cập quận, kể cả khi đã có location_landmark\n"
     "- min_price/max_price: dùng số thô lưu trong DB:\n"
     "    3 triệu/tháng → 3 | 1.5 tỷ → 1.5 | 500 triệu → 500\n"
     "  'giá X' hoặc 'khoảng X': max_price=X\n"
     "  'từ X đến Y': min_price=X, max_price=Y\n"
     "  'trên X' hoặc 'tối thiểu X': min_price=X\n"
     "  'ngân sách X' hoặc 'tối đa X': max_price=X\n"
     "  Ví dụ bắt buộc về giá:\n"
     "    'ngân sách 5 tỷ' -> max_price=5, min_price=null\n"
     "    'từ 3 tỷ đến 5 tỷ' -> min_price=3, max_price=5\n"
     "    'trên 2 tỷ' -> min_price=2, max_price=null\n"
     "    'diện tích từ 50m2 trở lên, ngân sách 5 tỷ' -> min_area=50, max_price=5, min_price=null\n"
     "- property_type: suy ra từ đơn vị giá nếu không nói rõ:\n"
     "    giá triệu/tháng hoặc cho thuê → rent\n"
     "    giá tỷ hoặc triệu (bán) hoặc mua → sell\n"
     "    null nếu không rõ\n"
     "- bedrooms: số phòng ngủ nguyên hoặc null\n"
     "- category: căn hộ|nhà nguyên căn|đất nền|biệt thự|nhà phố|nhà phố thương mại|văn phòng hoặc null\n"
     "  -> apartment|house|land|villa|townhouse|shophouse|office|null\n"
     "- min_area: diện tích tối thiểu m² hoặc null"),
    ("human", "{user_message}"),
])

_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Bạn là tư vấn viên BĐS tại Hà Nội.\n"
     + PROPERTY_LISTING_RULES + "\n"
     "Kết quả tìm kiếm (NGUỒN DUY NHẤT được dùng để liệt kê BĐS):\n{search_result}\n\n"
     "Lịch sử hội thoại (chỉ dùng để hiểu ngữ cảnh, KHÔNG dùng để lấy BĐS):\n{history}"),
    ("human", "{user_message}"),
])


# ─── Agent mode prompt ─────────────────────────────────────────────────────────

def _build_agent_prompt(history: str) -> str:
    return (
        "Bạn là chuyên viên tìm kiếm BĐS Hà Nội.\n"
        "Gọi tool NGAY với thông tin đã có — không hỏi thêm trước khi tìm.\n"
        "- property_search: tìm theo bộ lọc (quận, giá, diện tích, loại hình...)\n"
        "- location_search: tìm gần địa danh cụ thể ('gần X', 'cạnh X', 'khu vực X')\n\n"
        "Quy tắc trích xuất tham số tool (BẮT BUỘC tuân theo):\n"
        "- property_type: 'mua'/'bán'/giá tỷ → 'sell' | 'thuê'/giá triệu/tháng → 'rent'\n"
        "  LUÔN truyền property_type nếu người dùng đề cập mua/thuê.\n"
        "- category: LUÔN truyền nếu người dùng nói loại hình cụ thể:\n"
        "    căn hộ/chung cư → 'apartment'\n"
        "    nhà riêng/nhà nguyên căn → 'house'\n"
        "    đất nền/đất → 'land'\n"
        "    biệt thự → 'villa'\n"
        "    nhà phố → 'townhouse'\n"
        "    nhà phố thương mại/shophouse → 'shophouse'\n"
        "    văn phòng → 'office'\n"
        "- max_price: ngân sách/tối đa/không quá/dưới → truyền số (đơn vị triệu hoặc tỷ như DB).\n"
        "- min_area: 'từ Xm² trở lên'/'ít nhất Xm²' → truyền X.\n"
        "- district: tên quận/huyện người dùng đề cập.\n\n"
        + PROPERTY_LISTING_RULES
        + f"\nLịch sử hội thoại:\n{history}"
    )


# ─── Chain mode implementation ─────────────────────────────────────────────────

class _FindPropertyChain:
    def __init__(self):
        self._llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0,
        )
        self._property_tool = PropertySearchTool()
        self._slot_chain = _SLOT_PROMPT | self._llm | StrOutputParser()
        self._chain = _PROMPT | self._llm | StrOutputParser()

    async def run(
        self,
        user_message: str,
        history: str,
        extracted_slots: dict,
    ) -> dict:
        pending: list | None = extracted_slots.get("property_pending")

        if _is_show_more_request(user_message) and pending is not None:
            session_slots = {k: v for k, v in extracted_slots.items() if k in SEARCH_SLOT_KEYS and v is not None}
            if not pending:
                logger.info("[FindProperty] show_more requested but pending is empty")
                return {
                    "response": (
                        "Đã hiển thị tất cả kết quả phù hợp với yêu cầu của bạn. "
                        "Bạn muốn tìm với điều kiện khác không?"
                    ),
                    "retrieved_context": None,
                    "tool_chain": [],
                    "agent_chain": ["FindPropertyChain"],
                    "tool_calls_count": 0,
                    "raw_items": [],
                    "total_items_found": 0,
                    "should_escalate": False,
                    "extracted_slots": {**session_slots, "property_pending": []},
                }

            batch = pending[:_PAGE_SIZE]
            remaining = pending[_PAGE_SIZE:]
            _landmark = session_slots.get("location_landmark")
            search_result = PropertySearchTool._format_items(batch, location=_landmark)
            logger.info(f"[FindProperty] show_more | batch={len(batch)} remaining={len(remaining)}")

            response = await self._chain.ainvoke({
                "search_result": search_result,
                "history": history,
                "user_message": user_message,
            })
            return {
                "response": response,
                "retrieved_context": search_result,
                "tool_chain": [],
                "agent_chain": ["FindPropertyChain", "PendingBuffer"],
                "tool_calls_count": 0,
                "raw_items": batch,
                "total_items_found": len(batch) + len(remaining),
                "should_escalate": False,
                "extracted_slots": {**session_slots, "property_pending": remaining},
            }

        current_slots: dict = {}
        try:
            raw_json = await self._slot_chain.ainvoke({"user_message": user_message})
            parsed = json.loads(raw_json.strip())
            current_slots = {
                k: v for k, v in parsed.items()
                if k in SEARCH_SLOT_KEYS and v is not None
            }
            current_slots = _apply_deterministic_slot_overrides(user_message, current_slots)
        except Exception as e:
            logger.warning(f"Slot extraction failed: {e}")

        session_search_slots = {
            k: v for k, v in extracted_slots.items()
            if k in SEARCH_SLOT_KEYS and v is not None
        }
        slots = {**session_search_slots, **current_slots} if current_slots else session_search_slots

        if "property_type" not in slots:
            return {
                "response": (
                    "Bạn muốn **mua** hay **thuê** bất động sản ạ? "
                    "Vui lòng cho tôi biết để tôi tìm kiếm chính xác hơn nhé!"
                ),
                "retrieved_context": None,
                "tool_chain": [],
                "agent_chain": ["FindPropertyChain"],
                "tool_calls_count": 0,
                "raw_items": [],
                "should_escalate": False,
                "extracted_slots": {**session_search_slots, **current_slots},
            }

        location_landmark = slots.pop("location_landmark", None)
        radius_km = slots.pop("radius_km", 3.0) or 3.0

        if location_landmark:
            search_result, all_items = self._property_tool.search_raw(
                location=location_landmark,
                radius_km=float(radius_km),
                **slots,
            )
            logger.info(f"[PropertySearch] landmark={location_landmark!r} r={radius_km}km | found={len(all_items)}")
            used_tool = "PropertySearchTool(nearby)"
            slots["location_landmark"] = location_landmark
            slots["radius_km"] = radius_km
        else:
            search_result, all_items = self._property_tool.search_raw(**slots)
            logger.info(f"[PropertySearch] slots={slots} | found={len(all_items)}")
            used_tool = "PropertySearchTool"

        batch = all_items[:_PAGE_SIZE]
        pending_items = all_items[_PAGE_SIZE:]
        slots["property_pending"] = pending_items

        batch_text = PropertySearchTool._format_items(batch, location=location_landmark) if batch else search_result

        response = await self._chain.ainvoke({
            "search_result": batch_text,
            "history": history,
            "user_message": user_message,
        })

        logger.info(f"[FindProperty] fresh search | show={len(batch)} pending={len(pending_items)}")

        return {
            "response": response,
            "retrieved_context": batch_text,
            "tool_chain": [used_tool],
            "agent_chain": ["FindPropertyChain", used_tool],
            "tool_calls_count": 1,
            "raw_items": batch,
            "total_items_found": len(all_items),
            "should_escalate": False,
            "extracted_slots": slots,
        }


_chain = _FindPropertyChain()


# ─── Agent mode implementation ─────────────────────────────────────────────────

async def _run_agent(
    user_message: str,
    history: str,
    extracted_slots: dict,
    user_token: str | None,
    agent_llm: ChatOpenAI,
) -> dict:
    property_tool = PropertySearchHandoffTool()
    location_tool = LocationSearchHandoffTool()
    graph = create_agent(
        model=agent_llm,
        tools=[property_tool, location_tool],
        system_prompt=_build_agent_prompt(history),
    )
    try:
        state = await graph.ainvoke(
            {"messages": [HumanMessage(content=user_message)]},
            config={"recursion_limit": RECURSION_LIMIT},
        )
        msgs = state.get("messages", [])
        tool_chain = extract_tool_chain(msgs)
        raw_items = list(property_tool.raw_sink) or list(location_tool.raw_sink)
        return {
            "response": extract_final_output(msgs),
            "retrieved_context": None,
            "tool_chain": tool_chain,
            "agent_chain": [],
            "tool_calls_count": len(tool_chain),
            "raw_items": raw_items,
            "total_items_found": len(raw_items),
            "should_escalate": False,
        }
    except GraphRecursionError:
        logger.warning(f"[find_property_agent] max_iterations: {user_message!r}")
        return {
            "response": "Yêu cầu này khá phức tạp. Để tôi chuyển đến nhân viên hỗ trợ bạn.",
            "retrieved_context": None,
            "tool_chain": [],
            "agent_chain": [],
            "tool_calls_count": 0,
            "raw_items": [],
            "should_escalate": True,
        }
    except Exception as e:
        logger.error(f"[find_property_agent] error: {e}")
        return {
            "response": f"Lỗi xử lý: {str(e)}",
            "retrieved_context": None,
            "tool_chain": [],
            "agent_chain": [],
            "tool_calls_count": 0,
            "raw_items": [],
            "should_escalate": False,
        }


# ─── Unified entry point ───────────────────────────────────────────────────────

async def run(
    user_message: str,
    history: str = "",
    extracted_slots: dict | None = None,
    user_token: str | None = None,
    agent_llm: ChatOpenAI | None = None,
) -> dict:
    slots = extracted_slots or {}
    if agent_llm is not None:
        return await _run_agent(user_message, history, slots, user_token, agent_llm)
    return await _chain.run(user_message, history, slots)
