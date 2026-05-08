import json
import logging

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from core.config import settings
from tools.property_search import PropertySearchTool

logger = logging.getLogger(__name__)

SEARCH_SLOT_KEYS = {
    "district",
    "min_price",
    "max_price",
    "min_area",
    "property_type",
    "bedrooms",
    "category",
}

_SLOT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Trích xuất bộ lọc tìm kiếm BĐS Hà Nội. Trả về JSON thuần (không markdown, không giải thích).\n"
     'Template: {{"district":null,"min_price":null,"max_price":null,"min_area":null,"property_type":null,"bedrooms":null,"category":null}}\n'
     "Quy tắc:\n"
     "- district: tên quận/huyện (Cầu Giấy, Ba Đình...) hoặc null\n"
     "- min_price/max_price: dùng số thô lưu trong DB:\n"
     "    3 triệu/tháng → 3 | 1.5 tỷ → 1.5 | 500 triệu → 500\n"
     "  'giá X' hoặc 'khoảng X': max_price=X\n"
     "  'từ X đến Y': min_price=X, max_price=Y\n"
     "  'trên X' hoặc 'tối thiểu X': min_price=X\n"
     "- property_type: suy ra từ đơn vị giá nếu không nói rõ:\n"
     "    giá triệu/tháng hoặc cho thuê → rent\n"
     "    giá tỷ hoặc triệu (bán) hoặc mua → sell\n"
     "    null nếu không rõ\n"
     "- bedrooms: số phòng ngủ nguyên hoặc null\n"
     "- category: apartment|house|land|villa|townhouse|shophouse|office|null\n"
     "- min_area: diện tích tối thiểu m² hoặc null"),
    ("human", "{user_message}"),
])

_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Bạn là tư vấn viên BĐS tại Hà Nội. Dùng kết quả tìm kiếm để trả lời thân thiện, rõ ràng, đề xuất cụ thể.\n"
     "Nếu không tìm thấy nhà phù hợp, thông báo và gợi ý điều chỉnh điều kiện tìm kiếm.\n"
     "Nếu người dùng muốn đặt lịch xem nhà, hỏi thời gian mong muốn và căn số mấy.\n"
     "KHÔNG bịa thêm thông tin ngoài kết quả tìm kiếm.\n"
     "Khi liệt kê bất động sản, đánh số thứ tự rõ ràng: '1. Tên căn - Giá - Diện tích...'\n\n"
     "Kết quả tìm kiếm:\n{search_result}\n\n"
     "Lịch sử: {history}"),
    ("human", "{user_message}"),
])


class FindPropertyChain:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.3,
        )
        self.tool = PropertySearchTool()
        self._slot_chain = _SLOT_PROMPT | self.llm | StrOutputParser()
        self._chain = _PROMPT | self.llm | StrOutputParser()

    async def run(
        self,
        user_message: str,
        history: str = "",
        extracted_slots: dict | None = None,
    ) -> dict:
        extracted_slots = extracted_slots or {}

        # Step 1: Extract slots from current message, then merge with session baseline
        current_slots: dict = {}
        try:
            raw_json = await self._slot_chain.ainvoke({"user_message": user_message})
            parsed = json.loads(raw_json.strip())
            current_slots = {
                k: v
                for k, v in parsed.items()
                if k in SEARCH_SLOT_KEYS and v is not None
            }
        except Exception as e:
            logger.warning(f"Slot extraction failed: {e}")

        session_search_slots = {
            k: v
            for k, v in extracted_slots.items()
            if k in SEARCH_SLOT_KEYS and v is not None
        }

        # A new find-property message with explicit filters should not inherit stale filters
        # from the previous search. If no new filters are extracted, keep the previous search
        # context so follow-ups like "còn căn nào khác không" still work.
        slots = current_slots or session_search_slots
        print(f"SLOTS   : session={session_search_slots} current={current_slots} search={slots}")

        # Step 2: Search properties using extracted slots
        search_result, raw_items = self.tool.search_raw(query=user_message, **slots)
        logger.info(f"[PropertySearch] query={user_message!r} | slots={slots} | found={len(raw_items)}")

        # Step 3: Generate LLM response
        response = await self._chain.ainvoke({
            "search_result": search_result,
            "history": history,
            "user_message": user_message,
        })

        return {
            "response": response,
            "retrieved_context": search_result,
            "raw_items": raw_items,
            "extracted_slots": slots,
            "agent_chain": ["FindPropertyChain", "PropertySearchTool"],
            "tool_calls_count": 1,
        }


find_property_chain = FindPropertyChain()
