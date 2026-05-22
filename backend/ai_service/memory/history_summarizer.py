import logging

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from core.config import settings

logger = logging.getLogger(__name__)

_SUMMARIZE_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Tóm tắt lịch sử hội thoại BĐS dưới 60 từ: "
     "chủ đề chính, yêu cầu/điều kiện user đã đưa ra, intent gần nhất. "
     "Chỉ trả về đoạn tóm tắt, không giải thích thêm."),
    ("human", "{history}"),
])

# Tóm tắt khi lịch sử có ít nhất N lượt trao đổi (1 lượt = human + ai)
_MIN_TURNS_TO_SUMMARIZE = 4


class HistorySummarizer:
    def __init__(self):
        self._llm = ChatOpenAI(
            model=settings.openai_summary_model,
            api_key=settings.openai_api_key,
            temperature=0,
            max_tokens=120,
        )
        self._chain = _SUMMARIZE_PROMPT | self._llm | StrOutputParser()

    async def summarize(self, history: str) -> str:
        """Tóm tắt lịch sử hội thoại dài thành ~60 từ để dùng trong classifier prompt."""
        if not history or history == "(Chưa có lịch sử)":
            return history

        turn_count = history.count("Người dùng:") + history.count("Bot:")
        if turn_count < _MIN_TURNS_TO_SUMMARIZE:
            return history

        try:
            summary = await self._chain.ainvoke({"history": history})
            logger.debug(f"[HistorySummarizer] {turn_count} turns → summary={summary!r}")
            return f"[Tóm tắt lịch sử] {summary.strip()}"
        except Exception as e:
            logger.warning(f"[HistorySummarizer] fallback to raw: {e}")
            return history


history_summarizer = HistorySummarizer()
