import json
import logging
import unicodedata
from datetime import datetime
import re

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from core.config import settings
from core.utils import VN_TZ
from tools.appointment import AppointmentTool

logger = logging.getLogger(__name__)

# NFD decomposition strips tonal marks (category Mn); only base-letter variants remain.
_VN_BASE_MAP = str.maketrans({
    "đ": "d", "ă": "a", "â": "a",
    "ê": "e", "ô": "o", "ơ": "o", "ư": "u",
})

def _normalize_text(text: str) -> str:
    nfd = unicodedata.normalize("NFD", text.lower())
    stripped = "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", stripped.translate(_VN_BASE_MAP)).strip()

_CONFIRM_EXACT = {
    "dung",
    "dung roi",
    "dong y",
    "xac nhan",
    "ok",
    "okay",
    "oke",
    "chot",
    "yes",
    "vang",
    "duoc",
    "u",
    "uh",
    "um",
}

_CONFIRM_PHRASES = (
    "dat lich di",
    "dat lich cho toi",
    "tien hanh dat lich",
    "cu dat lich",
)

_DENY_TOKENS = frozenset({"khong", "chua", "huy", "thoi", "bo"})

def _is_confirmation(text: str) -> bool:
    normalized = _normalize_text(text)
    if _DENY_TOKENS & set(normalized.split()):
        return False
    if normalized in _CONFIRM_EXACT:
        return True
    return any(re.search(rf"\b{re.escape(phrase)}\b", normalized) for phrase in _CONFIRM_PHRASES)

_SLOT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Trích xuất thông tin đặt/xem/hủy lịch hẹn. Trả JSON thuần (không markdown).\n"
     'Template: {{"action":null,"property_id":null,"proposed_time":null,"note":null,"appointment_id":null}}\n'
     "Danh sách BĐS theo thứ tự từ lần tìm kiếm gần nhất (index bắt đầu từ 1): {property_list}\n"
     "Quy tắc:\n"
     "- action: 'book' | 'list' | 'cancel' | null\n"
     "- Nếu tin nhắn hiện tại là xác nhận như 'đúng', 'ok', 'xác nhận' sau khi bot vừa hỏi xác nhận đặt lịch, action='book' và dùng lại property_id/proposed_time từ lượt đặt lịch ngay trước đó trong hội thoại.\n"
     "- property_id: xác định từ:\n"
     "  • 'căn số N' / 'căn thứ N' / 'cái thứ N' → property_list[N-1]\n"
     "  • 'đó', 'đúng', 'ok', xác nhận khi chỉ 1 căn → property_list[0]\n"
     "  • ID trực tiếp ('ID 49') → dùng số đó\n"
     "  • Không rõ → null\n"
     "- proposed_time: ISO 8601, hôm nay là {today}\n"
     "  '5h chiều' → {today}T17:00:00 | '9h sáng' → {today}T09:00:00 | 'ngày mai Xh' → ngày mai TX:00:00\n"
     "- appointment_id: ID lịch hẹn khi hủy\n"
     "- note: ghi chú nếu có\n"
     "Hội thoại:\n{history}"),
    ("human", "{user_message}"),
])

_MAIN_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Bạn là trợ lý đặt lịch xem nhà. Hỗ trợ đặt lịch, xem lịch, huỷ lịch.\n"
     "Nếu thiếu thông tin hãy hỏi thêm. Xác nhận lại với người dùng trước khi đặt.\n"
     "Kết quả thao tác:\n{tool_result}\n\n"
     "Lịch sử: {history}"),
    ("human", "{user_message}"),
])


class AppointmentChain:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.3,
        )
        self.tool = AppointmentTool()
        self._slot_chain = _SLOT_PROMPT | self.llm | StrOutputParser()
        self._chain = _MAIN_PROMPT | self.llm | StrOutputParser()

    async def run(
        self,
        user_message: str,
        history: str = "",
        extracted_slots: dict | None = None,
        user_token: str | None = None,
    ) -> dict:
        extracted_slots = extracted_slots or {}

        # Step 1: Extract appointment slots from current message + history
        today = datetime.now(VN_TZ).strftime("%Y-%m-%d")
        property_list = extracted_slots.get("property_list") or []
        pending_appointment = extracted_slots.get("pending_appointment") or {}
        apt_slots: dict = {}

        if pending_appointment and _is_confirmation(user_message):
            apt_slots = {**pending_appointment, "action": "book"}
            print(f"APT_SLOTS: {apt_slots} | pending=confirmed | user_token={'ok' if user_token else 'none'}")

            tool_result = self.tool._run(
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
            })
            return {
                "response": response,
                "retrieved_context": tool_result,
                "agent_chain": ["AppointmentChain", "AppointmentTool"],
                "tool_calls_count": 1,
                "appointment_slots": {},
                "clear_pending_appointment": tool_result.startswith("Đặt lịch thành công"),
            }

        try:
            raw_json = await self._slot_chain.ainvoke({
                "user_message": user_message,
                "history": history,
                "today": today,
                "property_list": property_list if property_list else "(chưa có)",
            })
            parsed = json.loads(raw_json.strip())
            apt_slots = {k: v for k, v in parsed.items() if v is not None}
        except Exception as e:
            logger.warning(f"[Appointment] slot extraction failed: {e}")

        action = apt_slots.get("action")
        print(f"APT_SLOTS: {apt_slots} | user_token={'ok' if user_token else 'none'}")

        # Step 2: If this is a confirmation and the previous turn can be recovered
        # from history, create the appointment now.
        tool_result = ""
        if (
            _is_confirmation(user_message)
            and action == "book"
            and apt_slots.get("property_id")
            and apt_slots.get("proposed_time")
        ):
            tool_result = self.tool._run(
                action="book",
                property_id=apt_slots.get("property_id"),
                proposed_time=apt_slots.get("proposed_time"),
                note=apt_slots.get("note"),
                user_token=user_token,
            )
            logger.info(f"[Appointment] recovered confirmed booking | result={tool_result[:100]!r}")
            response = await self._chain.ainvoke({
                "tool_result": tool_result,
                "history": history,
                "user_message": user_message,
            })
            return {
                "response": response,
                "retrieved_context": tool_result,
                "agent_chain": ["AppointmentChain", "AppointmentTool"],
                "tool_calls_count": 1,
                "appointment_slots": {},
                "clear_pending_appointment": tool_result.startswith("Đặt lịch thành công"),
            }

        # Step 3: Ask for confirmation before creating a new appointment.
        if action == "book" and apt_slots.get("property_id") and apt_slots.get("proposed_time"):
            response = await self._chain.ainvoke({
                "tool_result": (
                    "Đã có đủ thông tin đặt lịch nhưng chưa gọi API. "
                    "Hãy xác nhận lại căn nhà và thời gian, rồi yêu cầu người dùng trả lời đúng/ok/xác nhận."
                ),
                "history": history,
                "user_message": user_message,
            })
            return {
                "response": response,
                "retrieved_context": "",
                "agent_chain": ["AppointmentChain"],
                "tool_calls_count": 0,
                "appointment_slots": apt_slots,
                "pending_appointment": apt_slots,
            }

        if action:
            tool_result = self.tool._run(
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

        # Step 3: Generate response
        response = await self._chain.ainvoke({
            "tool_result": tool_result,
            "history": history,
            "user_message": user_message,
        })

        return {
            "response": response,
            "retrieved_context": tool_result,
            "agent_chain": ["AppointmentChain", "AppointmentTool"],
            "tool_calls_count": 1 if action else 0,
            "appointment_slots": apt_slots,
        }


appointment_chain = AppointmentChain()
