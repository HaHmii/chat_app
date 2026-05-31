import logging

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError

from core.config import settings
from pattern.utils import RECURSION_LIMIT, extract_final_output, extract_tool_chain
from prompts.shared import LEGAL_RESPONSE_RULES, LEGAL_TERM_MAPPING
from tools.legal_query import LegalQueryTool

logger = logging.getLogger(__name__)

# ─── Chain mode prompts ────────────────────────────────────────────────────────

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


# ─── Agent mode prompt ─────────────────────────────────────────────────────────

def _build_agent_prompt(history: str) -> str:
    return (
        "Bạn là chuyên viên pháp lý BĐS Hà Nội.\n"
        "Bước 1 — quy đổi thuật ngữ sang pháp lý trước khi gọi tool:\n"
        + LEGAL_TERM_MAPPING + "\n"
        "Bước 2 — gọi tool legal_query với câu hỏi đã quy đổi.\n"
        "Bước 3 — trả lời theo quy tắc:\n"
        + LEGAL_RESPONSE_RULES
        + f"\nLịch sử hội thoại:\n{history}"
    )


# ─── Chain mode implementation ─────────────────────────────────────────────────

class _LegalChain:
    def __init__(self):
        self._llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.1,
        )
        self._tool = LegalQueryTool()
        self._rewrite_chain = _REWRITE_PROMPT | self._llm | StrOutputParser()
        self._generate_chain = _GENERATE_PROMPT | self._llm | StrOutputParser()

    async def run(self, user_message: str, history: str) -> dict:
        rewritten = (await self._rewrite_chain.ainvoke({"query": user_message})).strip()
        logger.info(f"[Rewrite] {user_message!r} → {rewritten!r}")

        legal_context = self._tool._run(rewritten)
        logger.info(f"[Retrieve] {len(legal_context)} chars retrieved")

        response = await self._generate_chain.ainvoke({
            "legal_context": legal_context,
            "history": history,
            "user_message": user_message,
        })

        return {
            "response": response,
            "retrieved_context": legal_context,
            "tool_chain": ["LegalQueryTool"],
            "agent_chain": ["QueryRewriter", "LegalQueryTool", "Generator"],
            "tool_calls_count": 2,
            "raw_items": [],
            "should_escalate": False,
        }


_chain = _LegalChain()


# ─── Agent mode implementation ─────────────────────────────────────────────────

async def _run_agent(
    user_message: str,
    history: str,
    extracted_slots: dict,
    user_token: str | None,
    agent_llm: ChatOpenAI,
) -> dict:
    graph = create_agent(
        model=agent_llm,
        tools=[LegalQueryTool()],
        system_prompt=_build_agent_prompt(history),
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
        logger.warning(f"[legal_query_agent] max_iterations: {user_message!r}")
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
        logger.error(f"[legal_query_agent] error: {e}")
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
    if agent_llm is not None:
        return await _run_agent(user_message, history, extracted_slots or {}, user_token, agent_llm)
    return await _chain.run(user_message, history)
