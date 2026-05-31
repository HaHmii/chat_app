import json
import logging
import re
import unicodedata
from datetime import datetime, timedelta

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError

from core.config import settings
from core.utils import VN_TZ
from pattern.tools import AppointmentHandoffTool
from pattern.utils import (
    RECURSION_LIMIT,
    build_property_mapping,
    build_week_calendar,
    extract_final_output,
    extract_tool_chain,
)
from prompts.shared import APPOINTMENT_BOOKING_RULES, APPOINTMENT_TIME_RULES, ESCALATION_RULES, ROLE_GUARD_APPOINTMENT
from tools.appointment import AppointmentTool

logger = logging.getLogger(__name__)

# ─── Confirmation helpers ─────────────────────────────────────────────────────

_VN_BASE_MAP = str.maketrans({
    "đ": "d", "ă": "a", "â": "a",
    "ê": "e", "ô": "o", "ơ": "o", "ư": "u",
})


def _normalize_text(text: str) -> str:
    nfd = unicodedata.normalize("NFD", text.lower())
    stripped = "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", stripped.translate(_VN_BASE_MAP)).strip()


_CONFIRM_EXACT = {
    "dung", "dung roi", "dong y", "xac nhan", "ok", "okay", "oke", "chot",
    "yes", "vang", "duoc", "u", "uh", "um",
}
_CONFIRM_PHRASES = (
    "dat lich di", "dat lich cho toi di", "tien hanh dat lich", "cu dat lich",
)
_DENY_TOKENS = frozenset({"khong", "chua", "huy", "thoi", "bo"})


def _is_confirmation(text: str) -> bool:
    normalized = _normalize_text(text)
    if _DENY_TOKENS & set(normalized.split()):
        return False
    if normalized in _CONFIRM_EXACT:
        return True
    return any(re.search(rf"\b{re.escape(phrase)}\b", normalized) for phrase in _CONFIRM_PHRASES)


# ─── Chain mode prompts ────────────────────────────────────────────────────────

_SLOT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Trích xuất thông tin đặt/xem/hủy lịch hẹn. Trả JSON thuần (không markdown).\n"
     'Template: {{"action":null,"property_id":null,"proposed_time":null,"note":null,"appointment_id":null}}\n'
     "=== DANH SÁCH BĐS HIỆN TẠI (NGUỒN DUY NHẤT để xác định property_id) ===\n"
     "{property_list}\n"
     "=== TUYỆT ĐỐI không dùng BĐS từ lịch sử hội thoại ===\n"
     "Quy tắc:\n"
     "- action: 'book' | 'list' | 'cancel' | null\n"
     "- property_id: CHỈ lấy từ danh sách BĐS HIỆN TẠI bên trên:\n"
     "  • 'căn số N' / 'căn thứ N' / 'cái thứ N' → ID của Căn N trong danh sách\n"
     "  • 'đó', 'đúng', 'ok', xác nhận khi chỉ 1 căn → ID của Căn 1\n"
     "  • Không rõ → null\n"
     "- proposed_time: ISO 8601 bắt buộc có múi giờ +07:00, hôm nay là {today}\n"
     "  '5h chiều' → {today}T17:00:00+07:00\n"
     "  '9h sáng' → {today}T09:00:00+07:00\n"
     "  'ngày mai 10h' → ngày mai T10:00:00+07:00\n"
     + APPOINTMENT_TIME_RULES +
     "- appointment_id: ID lịch hẹn khi hủy\n"
     "- note: ghi chú nếu có\n"
     "Hội thoại (chỉ để hiểu ngữ cảnh, KHÔNG dùng để lấy property_id):\n{history}"),
    ("human", "{user_message}"),
])

_MAIN_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Bạn là trợ lý đặt lịch xem nhà. Hỗ trợ đặt lịch, xem lịch, huỷ lịch.\n"
     "Vai trò người dùng hiện tại: {user_role}.\n"
     + ROLE_GUARD_APPOINTMENT + "\n"
     + ESCALATION_RULES + "\n"
     + APPOINTMENT_BOOKING_RULES + "\n"
     "Kết quả thao tác:\n{tool_result}\n\n"
     "Lịch sử: {history}"),
    ("human", "{user_message}"),
])


# ─── Agent mode prompt ─────────────────────────────────────────────────────────

def _build_agent_prompt(
    property_mapping: str,
    today: str,
    tomorrow: str,
    week_calendar: str,
    history: str,
    user_role: str = "unknown",
) -> str:
    return (
        "Bạn là trợ lý đặt/xem/hủy lịch hẹn xem nhà.\n"
        f"Vai trò người dùng: {user_role}.\n"
        + ROLE_GUARD_APPOINTMENT + "\n"
        + ESCALATION_RULES + "\n"
        "GỌI TOOL NGAY — không tự trả lời mà không qua tool.\n\n"
        + property_mapping + "\n"
        f"Hôm nay: {today}. Lịch tuần (tra ngay, không tự tính):\n{week_calendar}\n\n"
        + APPOINTMENT_TIME_RULES
        + f"  Ví dụ: '9h sáng mai' → {tomorrow}T09:00:00+07:00\n\n"
        "Quy tắc:\n"
        "- action='book': điền property_id và proposed_time nếu có (None nếu chưa biết).\n"
        "  Tool báo thiếu gì → hỏi thêm → gọi lại tool khi đủ.\n"
        "- action='list': gọi ngay.\n"
        "- action='cancel': gọi list trước → xác nhận với người dùng → gọi cancel.\n"
        f"\nLịch sử hội thoại:\n{history}"
    )


# ─── Chain mode implementation ─────────────────────────────────────────────────

class _AppointmentChain:
    def __init__(self):
        self._llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.3,
        )
        self._tool = AppointmentTool()
        self._slot_chain = _SLOT_PROMPT | self._llm | StrOutputParser()
        self._chain = _MAIN_PROMPT | self._llm | StrOutputParser()

    async def run(
        self,
        user_message: str,
        history: str,
        extracted_slots: dict,
        user_token: str | None,
    ) -> dict:
        user_role = extracted_slots.get("user_role") or "chưa đăng nhập"
        pending_appointment = extracted_slots.get("pending_appointment") or {}
        if pending_appointment and _is_confirmation(user_message):
            apt_slots = {**pending_appointment, "action": "book"}
            tool_result = self._tool._run(
                action="book",
                property_id=apt_slots.get("property_id"),
                proposed_time=apt_slots.get("proposed_time"),
                note=apt_slots.get("note"),
                user_token=user_token,
            )
            logger.info(f"[Appointment] confirmed booking | result={tool_result[:100]!r}")
            response = await self._chain.ainvoke({
                "tool_result": tool_result,
                "history": history,
                "user_message": user_message,
                "user_role": user_role,
            })
            return {
                "response": response,
                "retrieved_context": tool_result,
                "tool_chain": ["AppointmentTool"],
                "agent_chain": ["AppointmentChain", "AppointmentTool"],
                "tool_calls_count": 1,
                "raw_items": [],
                "should_escalate": False,
                "clear_pending_appointment": tool_result.startswith("Đặt lịch thành công"),
            }

        today = datetime.now(VN_TZ).strftime("%Y-%m-%d")
        property_ids = extracted_slots.get("property_list") or []
        if property_ids:
            property_list_text = " | ".join(
                f"Căn {i + 1}: ID {pid}" for i, pid in enumerate(property_ids)
            )
        else:
            property_list_text = "(chưa có — người dùng chưa tìm BĐS nào)"

        apt_slots: dict = {}
        try:
            raw_json = await self._slot_chain.ainvoke({
                "user_message": user_message,
                "history": history,
                "today": today,
                "property_list": property_list_text,
            })
            parsed = json.loads(raw_json.strip())
            apt_slots = {k: v for k, v in parsed.items() if v is not None}
        except Exception as e:
            logger.warning(f"[Appointment] slot extraction failed: {e}")

        action = apt_slots.get("action")

        if action == "book" and apt_slots.get("property_id") and apt_slots.get("proposed_time"):
            response = await self._chain.ainvoke({
                "tool_result": (
                    "Đã có đủ thông tin đặt lịch nhưng chưa gọi API. "
                    "Hãy xác nhận lại căn nhà và thời gian với người dùng, "
                    "rồi yêu cầu họ trả lời đúng/ok/xác nhận để tiến hành đặt."
                ),
                "history": history,
                "user_message": user_message,
                "user_role": user_role,
            })
            return {
                "response": response,
                "retrieved_context": "",
                "tool_chain": [],
                "agent_chain": ["AppointmentChain"],
                "tool_calls_count": 0,
                "raw_items": [],
                "should_escalate": False,
                "pending_appointment": apt_slots,
            }

        tool_result = ""
        if action == "cancel" and not apt_slots.get("appointment_id"):
            # Always list first so the LLM can show options or tell user there's nothing to cancel
            tool_result = self._tool._run(action="list", user_token=user_token)
            logger.info(f"[Appointment] cancel→list first | result={tool_result[:100]!r}")
        elif action:
            tool_result = self._tool._run(
                action=action,
                property_id=apt_slots.get("property_id"),
                proposed_time=apt_slots.get("proposed_time"),
                note=apt_slots.get("note"),
                appointment_id=apt_slots.get("appointment_id"),
                user_token=user_token,
            )
            logger.info(f"[Appointment] action={action!r} | result={tool_result[:100]!r}")
        else:
            logger.info("[Appointment] no action extracted — asking user for more info")

        response = await self._chain.ainvoke({
            "tool_result": tool_result,
            "history": history,
            "user_message": user_message,
            "user_role": user_role,
        })

        tool_was_called = bool(tool_result)
        return {
            "response": response,
            "retrieved_context": tool_result,
            "tool_chain": ["AppointmentTool"] if tool_was_called else [],
            "agent_chain": ["AppointmentChain", "AppointmentTool"] if tool_was_called else ["AppointmentChain"],
            "tool_calls_count": 1 if tool_was_called else 0,
            "raw_items": [],
            "should_escalate": False,
        }


_chain = _AppointmentChain()


# ─── Agent mode implementation ─────────────────────────────────────────────────

async def _run_agent(
    user_message: str,
    history: str,
    extracted_slots: dict,
    user_token: str | None,
    agent_llm: ChatOpenAI,
) -> dict:
    now = datetime.now(VN_TZ)
    today = now.strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    week_calendar = build_week_calendar(now)
    property_mapping = build_property_mapping(
        extracted_slots.get("property_list") or [],
        extracted_slots.get("property_list_details") or [],
    )
    user_role = extracted_slots.get("user_role") or "chưa đăng nhập"

    appointment_tool = AppointmentHandoffTool(user_token=user_token or "")
    graph = create_agent(
        model=agent_llm,
        tools=[appointment_tool],
        system_prompt=_build_agent_prompt(property_mapping, today, tomorrow, week_calendar, history, user_role),
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
        logger.warning(f"[appointment_agent] max_iterations: {user_message!r}")
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
        logger.error(f"[appointment_agent] error: {e}")
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
    return await _chain.run(user_message, history, slots, user_token)
