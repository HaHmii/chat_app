import json
import logging

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError

from core.config import settings
from pattern.utils import RECURSION_LIMIT, build_property_mapping, extract_final_output, extract_tool_chain
from prompts.shared import PROPERTY_DETAIL_RULES
from tools.property_detail import PropertyDetailTool, property_detail_tool

logger = logging.getLogger(__name__)


def _format_property_list(property_list: list[int], property_list_details: list[dict]) -> str:
    lines = []
    for i, pid in enumerate(property_list):
        detail = property_list_details[i] if i < len(property_list_details) else {}
        title = detail.get("title") or f"ID {pid}"
        price = detail.get("price_display", "")
        area = detail.get("area", "")
        district = detail.get("district", "")
        meta = " | ".join(filter(None, [price, f"{area}m²" if area else "", district]))
        line = f"• Căn {i + 1}: {title}"
        if meta:
            line += f" ({meta})"
        lines.append(line)
    return "\n".join(lines)


# ─── Chain mode prompts ────────────────────────────────────────────────────────

_SLOT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Xác định BĐS người dùng muốn xem chi tiết. Trả về JSON thuần (không markdown).\n"
     'Template: {"property_id": null, "ordinal": null}\n'
     "=== DANH SÁCH BĐS HIỆN TẠI (NGUỒN DUY NHẤT để xác định property) ===\n"
     "{property_list}\n"
     "Quy tắc:\n"
     "- property_id: số nguyên nếu người dùng nêu rõ ID, null nếu không.\n"
     "- ordinal: số thứ tự (1, 2, 3...) khi người dùng nói:\n"
     "  'căn số N' / 'cái thứ N' / 'căn N' → N\n"
     "  'căn đầu tiên' / 'cái đầu' / 'cái đó' / 'đó' (danh sách 1 căn) → 1\n"
     "  null nếu không xác định được.\n"
     "Lịch sử (chỉ để hiểu ngữ cảnh): {history}"),
    ("human", "{user_message}"),
])

_MAIN_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Bạn là tư vấn viên BĐS tại Hà Nội.\n"
     + PROPERTY_DETAIL_RULES + "\n"
     "Thông tin chi tiết BĐS:\n{detail_result}\n\n"
     "Lịch sử: {history}"),
    ("human", "{user_message}"),
])


# ─── Agent mode prompt ─────────────────────────────────────────────────────────

def _build_agent_prompt(property_mapping: str, history: str) -> str:
    return (
        "Bạn là chuyên viên tra cứu thông tin chi tiết BĐS.\n"
        "Tra bảng danh sách căn để lấy đúng property_id rồi gọi tool property_detail NGAY.\n"
        "Nếu căn không có trong danh sách hoặc chưa có kết quả tìm kiếm: gọi với property_id=0.\n\n"
        + property_mapping + "\n"
        + PROPERTY_DETAIL_RULES
        + f"\nLịch sử hội thoại:\n{history}"
    )


# ─── Chain mode implementation ─────────────────────────────────────────────────

class _PropertyDetailChain:
    def __init__(self):
        self._llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.3,
        )
        self._slot_chain = _SLOT_PROMPT | self._llm | StrOutputParser()
        self._chain = _MAIN_PROMPT | self._llm | StrOutputParser()

    async def run(
        self,
        user_message: str,
        history: str,
        extracted_slots: dict,
    ) -> dict:
        property_list: list[int] = extracted_slots.get("property_list") or []
        property_list_details: list[dict] = extracted_slots.get("property_list_details") or []

        if property_list:
            parts = []
            for i, pid in enumerate(property_list):
                detail = property_list_details[i] if i < len(property_list_details) else {}
                title = detail.get("title", "")
                parts.append(f"Căn {i + 1}: ID {pid}" + (f" — {title}" if title else ""))
            property_list_text = " | ".join(parts)
        else:
            property_list_text = "(chưa có — người dùng chưa tìm BĐS nào)"

        property_id: int | None = None
        parsed_ordinal: int | None = None
        ordinal_out_of_range = False
        try:
            raw_json = await self._slot_chain.ainvoke({
                "user_message": user_message,
                "history": history,
                "property_list": property_list_text,
            })
            parsed = json.loads(raw_json.strip())
            if parsed.get("property_id"):
                property_id = int(parsed["property_id"])
            elif parsed.get("ordinal") and property_list:
                parsed_ordinal = int(parsed["ordinal"])
                if 1 <= parsed_ordinal <= len(property_list):
                    property_id = property_list[parsed_ordinal - 1]
                else:
                    ordinal_out_of_range = True
        except Exception as e:
            logger.warning(f"[PropertyDetail] slot extraction failed: {e}")

        if property_id is None and len(property_list) == 1:
            property_id = property_list[0]
            logger.info(f"[PropertyDetail] auto-resolved single-item list → id={property_id}")

        logger.info(f"[PropertyDetail] property_id={property_id} | list={property_list}")

        if property_id is None:
            if not property_list:
                response = (
                    "Bạn chưa tìm kiếm BĐS nào. "
                    "Hãy cho tôi biết bạn đang tìm loại bất động sản nào để tôi hỗ trợ nhé!"
                )
            elif ordinal_out_of_range:
                response = (
                    f"Danh sách hiện tại chỉ có {len(property_list)} căn. "
                    f"Bạn muốn xem chi tiết căn nào?\n"
                    + _format_property_list(property_list, property_list_details)
                )
            else:
                response = (
                    "Bạn muốn xem chi tiết căn nào trong danh sách sau?\n"
                    + _format_property_list(property_list, property_list_details)
                )
            return {
                "response": response,
                "retrieved_context": None,
                "tool_chain": [],
                "agent_chain": ["PropertyDetailChain"],
                "tool_calls_count": 0,
                "raw_items": [],
                "should_escalate": False,
            }

        detail_text, _ = property_detail_tool.fetch_raw(property_id)
        logger.info(f"[PropertyDetail] fetched id={property_id} | len={len(detail_text)}")

        response = await self._chain.ainvoke({
            "detail_result": detail_text,
            "history": history,
            "user_message": user_message,
        })

        return {
            "response": response,
            "retrieved_context": detail_text,
            "tool_chain": ["PropertyDetailTool"],
            "agent_chain": ["PropertyDetailChain", "PropertyDetailTool"],
            "tool_calls_count": 1,
            "raw_items": [],
            "should_escalate": False,
        }


_chain = _PropertyDetailChain()


# ─── Agent mode implementation ─────────────────────────────────────────────────

async def _run_agent(
    user_message: str,
    history: str,
    extracted_slots: dict,
    user_token: str | None,
    agent_llm: ChatOpenAI,
) -> dict:
    property_mapping = build_property_mapping(
        extracted_slots.get("property_list") or [],
        extracted_slots.get("property_list_details") or [],
    )
    graph = create_agent(
        model=agent_llm,
        tools=[PropertyDetailTool()],
        system_prompt=_build_agent_prompt(property_mapping, history),
    )
    try:
        state = await graph.ainvoke(
            {"messages": [HumanMessage(content=user_message)]},
            config={"recursion_limit": RECURSION_LIMIT},
        )
        msgs = state.get("messages", [])
        tool_chain = extract_tool_chain(msgs)
        return {
            "response": extract_final_output(msgs),
            "retrieved_context": None,
            "tool_chain": tool_chain,
            "agent_chain": [],
            "tool_calls_count": len(tool_chain),
            "raw_items": [],
            "should_escalate": False,
        }
    except GraphRecursionError:
        logger.warning(f"[property_detail_agent] max_iterations: {user_message!r}")
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
        logger.error(f"[property_detail_agent] error: {e}")
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
