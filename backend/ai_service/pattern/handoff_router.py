import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from sub_agents.appointment import _is_confirmation

logger = logging.getLogger(__name__)

VALID_INTENTS = frozenset({
    "find_property", "property_detail", "appointment",
    "post_property", "market_analysis", "legal_query",
    "default", "fallback",
})

_SYSTEM = """Bạn là bộ phân loại ý định cho chatbot bất động sản Hà Nội.
Phân loại tin nhắn người dùng vào ĐÚNG MỘT nhãn:

- find_property:    tìm BĐS theo tiêu chí (quận, giá, diện tích, loại hình, gần địa danh)
- property_detail:  hỏi thông tin chi tiết về một căn đã được liệt kê (căn số X, xem chi tiết, thêm thông tin...)
- appointment:      đặt/xem/hủy lịch hẹn xem nhà — KỂ CẢ khi đề cập "căn số X" kèm thời gian hẹn
- post_property:    chủ nhà đăng tin bán/cho thuê BĐS của mình — bao gồm CẢ các lượt thu thập thông tin
- market_analysis:  giá thị trường, định giá, so sánh giá, xu hướng đầu tư
- legal_query:      câu hỏi pháp lý (sổ đỏ, thủ tục, thuế, hợp đồng, sang tên...)
- default:          chào hỏi, giới thiệu bản thân
- fallback:         câu hỏi ngoài phạm vi BĐS (thời tiết, ẩm thực, thể thao...)

Lưu ý:
- Nếu lịch sử cho thấy đang trong luồng đăng tin → tiếp tục post_property
- "đặt lịch xem căn số X vào ngày Y" → appointment (không phải property_detail)
- "xác nhận / ok / đồng ý" trong ngữ cảnh đặt lịch → appointment
- Hà Nội là phạm vi hỗ trợ; tỉnh/thành khác → fallback

Trả về JSON hợp lệ: {"intent": "<label>"}"""


class HandoffRouter:
    def __init__(self, llm: ChatOpenAI):
        self._llm = llm

    async def route(
        self,
        user_message: str,
        history: str,
        extracted_slots: dict,
        last_intent: str | None = None,
    ) -> str:
        msg_lower = user_message.lower()

        # Guard: duy trì luồng post_property khi đang thu thập thông tin
        if last_intent == "post_property" or extracted_slots.get("pending_post_property"):
            has_break = any(k in msg_lower for k in (
                "tìm nhà", "tìm căn", "thuê nhà", "mua nhà", "tìm bất động sản",
                "đặt lịch", "hẹn xem", "lịch hẹn",
                "giá thị trường", "định giá", "giá trung bình",
            ))
            if not has_break:
                logger.info("[HandoffRouter] post_property continuation guard")
                return "post_property"

        # Guard: xác nhận trong ngữ cảnh đặt lịch
        if last_intent == "appointment" and _is_confirmation(user_message):
            logger.info("[HandoffRouter] appointment confirmation guard")
            return "appointment"

        # LLM classification
        context_parts = []
        if last_intent:
            context_parts.append(f"Ý định lượt trước: {last_intent}")
        if extracted_slots.get("pending_appointment"):
            context_parts.append("Đang trong luồng đặt lịch.")

        prompt = f"Lịch sử:\n{history}\n\nTin nhắn: {user_message}"
        if context_parts:
            prompt += "\n\nBối cảnh: " + " | ".join(context_parts)

        response = await self._llm.ainvoke([
            SystemMessage(content=_SYSTEM),
            HumanMessage(content=prompt),
        ])

        try:
            data = json.loads(response.content)
            intent = data.get("intent", "fallback")
            if intent not in VALID_INTENTS:
                intent = "fallback"
        except Exception:
            content = response.content.strip()
            intent = next((lb for lb in VALID_INTENTS if lb in content), "fallback")

        logger.info(f"[HandoffRouter] intent={intent!r} | {user_message!r}")
        return intent
