import logging

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from core.config import settings
from tools.legal_query import LegalQueryTool

logger = logging.getLogger(__name__)

_REWRITE_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Bạn là chuyên gia pháp luật BĐS Việt Nam.\n"
     "Chuyển câu hỏi của người dùng thành một cụm từ tìm kiếm pháp lý NGẮN GỌN, CHÍNH XÁC.\n"
     "Chỉ trả về cụm từ tìm kiếm, KHÔNG giải thích, KHÔNG đánh số, KHÔNG thêm gì khác.\n"
     "Dùng thuật ngữ trong Luật Đất đai 2024, Luật Nhà ở 2023, Luật KDBĐS 2023.\n\n"
     "Tham khảo ánh xạ:\n"
     "sổ hồng → Giấy chứng nhận quyền sở hữu nhà ở và quyền sử dụng đất ở\n"
     "sổ đỏ → Giấy chứng nhận quyền sử dụng đất\n"
     "hợp đồng mua bán nhà/đất → hợp đồng chuyển nhượng quyền sử dụng đất điều kiện giao dịch\n"
     "sang tên → thủ tục chuyển nhượng đăng ký biến động quyền sử dụng đất\n"
     "kinh doanh BĐS → điều kiện kinh doanh bất động sản tổ chức cá nhân"),
    ("human", "{query}"),
])

_GENERATE_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Bạn là chuyên gia pháp lý BĐS Việt Nam. Trả lời TRỰC TIẾP và CỤ THỂ vào câu hỏi.\n\n"
     "Yêu cầu bắt buộc:\n"
     "1. Trích dẫn điều/khoản cụ thể (VD: 'Theo Điều 45, Khoản 2, Luật Đất đai 2024...') "
     "rồi giải thích NỘI DUNG quy định đó.\n"
     "2. KHÔNG chỉ nêu tên luật — phải giải thích luật đó quy định CỤ THỂ như thế nào.\n"
     "3. Nếu câu hỏi dùng từ thông thường (sổ hồng, sổ đỏ, hợp đồng mua bán...), "
     "hãy giải thích tên pháp lý tương đương rồi trả lời.\n"
     "4. KHÔNG bịa thêm thông tin ngoài văn bản được cung cấp.\n"
     "5. Nếu văn bản không đủ thông tin, chỉ nói thẳng là không tìm thấy thông tin liên quan.\n"
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
