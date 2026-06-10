import json
import logging

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError

from core.config import settings
from pattern.utils import RECURSION_LIMIT, extract_final_output, extract_tool_chain
from prompts.shared import MARKET_ANALYSIS_RESPONSE_RULES
from tools.market_analysis import MarketAnalysisTool

logger = logging.getLogger(__name__)

# ─── Chain mode prompts ────────────────────────────────────────────────────────

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
     "Dữ liệu thị trường:\n{analysis_result}\n\n"
     "Suy luận theo thứ tự trước khi trả lời:\n"
     "Bước 1 — Xác định mức giá trung bình/m² từ dữ liệu.\n"
     "Bước 2 — Nếu người dùng hỏi diện tích cụ thể, tính tổng giá ước tính.\n"
     "Bước 3 — Nhận xét mức giá (cao/thấp/trung bình so với thị trường).\n"
     "Bước 4 — Trả lời ngắn gọn, đưa ra con số cụ thể, không nói chung chung.\n\n"
     + MARKET_ANALYSIS_RESPONSE_RULES + "\n"
     "Lịch sử hội thoại:\n{history}"),
    ("human", "{user_message}"),
])


# ─── Agent mode prompt ─────────────────────────────────────────────────────────

def _build_agent_prompt(history: str) -> str:
    return (
        "Bạn là chuyên viên phân tích thị trường BĐS Hà Nội.\n"
        "Gọi tool market_analysis ngay với thông tin đã có.\n\n"
        + MARKET_ANALYSIS_RESPONSE_RULES
        + f"\nLịch sử hội thoại:\n{history}"
    )


# ─── Chain mode implementation ─────────────────────────────────────────────────

class _MarketAnalysisChain:
    def __init__(self):
        self._llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.3,
        )
        self._tool = MarketAnalysisTool()
        self._slot_chain = _SLOT_PROMPT | self._llm | StrOutputParser()
        self._chain = _PROMPT | self._llm | StrOutputParser()

    async def run(
        self,
        user_message: str,
        history: str,
        extracted_slots: dict,
    ) -> dict:
        slots: dict = {}
        try:
            raw_json = await self._slot_chain.ainvoke({"user_message": user_message})
            parsed = json.loads(raw_json.strip())
            slots = {k: v for k, v in parsed.items() if v is not None}
        except Exception as e:
            logger.warning(f"[MarketAnalysis] slot extraction failed: {e}")

        logger.info(f"[MarketAnalysis] slots={slots}")
        analysis_result = self._tool._run(**slots)

        response = await self._chain.ainvoke({
            "analysis_result": analysis_result,
            "history": history,
            "user_message": user_message,
        })

        return {
            "response": response,
            "retrieved_context": analysis_result,
            "tool_chain": ["MarketAnalysisTool"],
            "agent_chain": ["MarketAnalysisChain", "MarketAnalysisTool"],
            "tool_calls_count": 1,
            "raw_items": [],
            "should_escalate": False,
        }


_chain = _MarketAnalysisChain()


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
        tools=[MarketAnalysisTool()],
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
        logger.warning(f"[market_analysis_agent] max_iterations: {user_message!r}")
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
        logger.error(f"[market_analysis_agent] error: {e}")
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
    return await _chain.run(user_message, history, slots)
