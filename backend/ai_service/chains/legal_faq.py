import logging
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from core.config import settings
from prompts.shared import LEGAL_RESPONSE_RULES, LEGAL_TERM_MAPPING
from tools.legal_query import LegalQueryTool

logger = logging.getLogger(__name__)

_REWRITE_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Bạn là chuyên gia pháp luật BĐS Việt Nam.\n"
     "Chuyển câu hỏi của người dùng thành một cụm từ tìm kiếm pháp lý NGẮN GỌN, CHÍNH XÁC.\n"
     "Chỉ trả về cụm từ tìm kiếm, KHÔNG giải thích, KHÔNG đánh số, KHÔNG thêm gì khác.\n"
     + LEGAL_TERM_MAPPING),
    ("human", "{query}"),
])

_GENERATE_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Bạn là chuyên gia pháp lý BĐS Việt Nam. Trả lời TRỰC TIẾP và CỤ THỂ vào câu hỏi.\n\n"
     + LEGAL_RESPONSE_RULES + "\n"
     "Văn bản pháp luật:\n{legal_context}\n\n"
     "Lịch sử hội thoại: {history}"),
    ("human", "{user_message}"),
])


class LegalFAQChain:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.1,
        )
        self.tool = LegalQueryTool()
        self._rewrite_chain = _REWRITE_PROMPT | self.llm | StrOutputParser()
        self._generate_chain = _GENERATE_PROMPT | self.llm | StrOutputParser()

    async def run(self, user_message: str, history: str = "") -> dict:
        # Step 1: Rewrite — dịch câu hỏi sang thuật ngữ pháp lý
        rewritten = (await self._rewrite_chain.ainvoke({"query": user_message})).strip()
        logger.info(f"[Rewrite] {user_message!r} → {rewritten!r}")

        # Step 2: Retrieve — tìm kiếm trong văn bản pháp luật
        legal_context = self.tool._run(rewritten)
        logger.info(f"[Retrieve] {len(legal_context)} chars retrieved")

        # Step 3: Generate — sinh câu trả lời từ context
        response = await self._generate_chain.ainvoke({
            "legal_context": legal_context,
            "history": history,
            "user_message": user_message,
        })

        return {
            "response": response,
            "rewritten_query": rewritten,
            "retrieved_context": legal_context,
            "agent_chain": ["QueryRewriter", "LegalQueryTool", "Generator"],
            "tool_calls_count": 2,
        }


legal_chain = LegalFAQChain()
