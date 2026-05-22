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
from prompts.shared import APPOINTMENT_BOOKING_RULES, APPOINTMENT_TIME_RULES
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
    "dat lich cho toi di",
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
     + APPOINTMENT_BOOKING_RULES + "\n"
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

        # Step 1: Check if this is a confirmation of a pending booking (stored in session).
        # This is the ONLY path that calls the booking tool for 'book' action — it requires
        # the bot to have already asked the user to confirm in the previous turn.
        pending_appointment = extracted_slots.get("pending_appointment") or {}
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
                "clear_pending_appointment": tool_result.startswith("Đặt lịch thành công"),
            }

        # Step 2: Extract appointment slots from current message + history
        today = datetime.now(VN_TZ).strftime("%Y-%m-%d")
        property_ids = extracted_slots.get("property_list") or []
        # Format as explicit mapping so the LLM cannot confuse ordinal with history data
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
        print(f"APT_SLOTS: {apt_slots} | user_token={'ok' if user_token else 'none'}")

        # Step 3: If this is a new booking request with full info, ask for confirmation.
        # Do NOT call the tool yet — save slots to session and wait for user to confirm.
        if action == "book" and apt_slots.get("property_id") and apt_slots.get("proposed_time"):
            response = await self._chain.ainvoke({
                "tool_result": (
                    "Đã có đủ thông tin đặt lịch nhưng chưa gọi API. "
                    "Hãy xác nhận lại căn nhà và thời gian với người dùng, "
                    "rồi yêu cầu họ trả lời đúng/ok/xác nhận để tiến hành đặt."
                ),
                "history": history,
                "user_message": user_message,
            })
            return {
                "response": response,
                "retrieved_context": "",
                "agent_chain": ["AppointmentChain"],
                "tool_calls_count": 0,
                "pending_appointment": apt_slots,
            }

        # Step 4: For list/cancel or incomplete info → call tool or ask for more info
        tool_result = ""
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
        }


appointment_chain = AppointmentChain()
