import json
import logging

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from core.config import settings
from prompts.shared import PROPERTY_DETAIL_RULES
from tools.property_detail import property_detail_tool

logger = logging.getLogger(__name__)

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


class PropertyDetailChain:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.3,
        )
        self._slot_chain = _SLOT_PROMPT | self.llm | StrOutputParser()
        self._chain = _MAIN_PROMPT | self.llm | StrOutputParser()

    async def run(
        self,
        user_message: str,
        history: str = "",
        extracted_slots: dict | None = None,
    ) -> dict:
        extracted_slots = extracted_slots or {}
        property_list: list[int] = extracted_slots.get("property_list") or []

        if property_list:
            property_list_text = " | ".join(
                f"Căn {i + 1}: ID {pid}" for i, pid in enumerate(property_list)
            )
        else:
            property_list_text = "(chưa có — người dùng chưa tìm BĐS nào)"

        property_id: int | None = None
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
                ordinal = int(parsed["ordinal"])
                if 1 <= ordinal <= len(property_list):
                    property_id = property_list[ordinal - 1]
        except Exception as e:
            logger.warning(f"[PropertyDetail] slot extraction failed: {e}")

        logger.info(f"[PropertyDetail] property_id={property_id} | list={property_list}")

        if property_id is None:
            detail_result = (
                "Không xác định được BĐS cần xem chi tiết. "
                "Vui lòng cho biết căn số mấy hoặc ID cụ thể."
            )
            response = await self._chain.ainvoke({
                "detail_result": detail_result,
                "history": history,
                "user_message": user_message,
            })
            return {
                "response": response,
                "retrieved_context": None,
                "agent_chain": ["PropertyDetailChain"],
                "tool_calls_count": 0,
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
            "agent_chain": ["PropertyDetailChain", "PropertyDetailTool"],
            "tool_calls_count": 1,
        }


property_detail_chain = PropertyDetailChain()
