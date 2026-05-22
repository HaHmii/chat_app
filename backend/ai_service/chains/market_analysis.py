import json
import logging
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from core.config import settings
from prompts.shared import MARKET_ANALYSIS_RESPONSE_RULES
from tools.market_analysis import MarketAnalysisTool

logger = logging.getLogger(__name__)

_SLOT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Trích xuất tham số phân tích thị trường BĐS Hà Nội. Trả JSON thuần (không markdown).\n"
     'Template: {{"district":null,"category":null,"property_type":null,"area":null}}\n'
     "Quy tắc:\n"
     "- district: tên quận/huyện hoặc null\n"
     "- category: apartment|house|land|villa|townhouse|shophouse|office|null\n"
     "- property_type: sell|rent|null (suy từ ngữ cảnh nếu không nói rõ)\n"
     "- area: diện tích m² (số thực) khi người dùng muốn định giá một căn cụ thể, null nếu không đề cập"),
    ("human", "{user_message}"),
])

_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Bạn là chuyên gia phân tích thị trường BĐS Hà Nội.\n"
     + MARKET_ANALYSIS_RESPONSE_RULES + "\n"
     "Dữ liệu thị trường:\n{analysis_result}\n\n"
     "Lịch sử hội thoại:\n{history}"),
    ("human", "{user_message}"),
])


class MarketAnalysisChain:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.3,
        )
        self.tool = MarketAnalysisTool()
        self._slot_chain = _SLOT_PROMPT | self.llm | StrOutputParser()
        self._chain = _PROMPT | self.llm | StrOutputParser()

    async def run(
        self,
        user_message: str,
        history: str = "",
        extracted_slots: dict | None = None,
    ) -> dict:
        slots: dict = {}
        try:
            raw_json = await self._slot_chain.ainvoke({"user_message": user_message})
            parsed = json.loads(raw_json.strip())
            slots = {k: v for k, v in parsed.items() if v is not None}
        except Exception as e:
            logger.warning(f"[MarketAnalysis] slot extraction failed: {e}")

        logger.info(f"[MarketAnalysis] slots={slots}")
        analysis_result = self.tool._run(**slots)

        response = await self._chain.ainvoke({
            "analysis_result": analysis_result,
            "history": history,
            "user_message": user_message,
        })

        return {
            "response": response,
            "retrieved_context": analysis_result,
            "agent_chain": ["MarketAnalysisChain", "MarketAnalysisTool"],
            "tool_calls_count": 1,
        }


market_analysis_chain = MarketAnalysisChain()
