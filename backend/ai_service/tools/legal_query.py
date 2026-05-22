import logging
import re
from typing import ClassVar
from langchain_core.tools import BaseTool
from core.config import settings
from llama_index.indices.managed.llama_cloud import LlamaCloudIndex

logger = logging.getLogger(__name__)

# Null bytes (\x00) và control chars gây lỗi PostgreSQL UTF-8; giữ lại tab/newline/carriage-return.
_CONTROL_CHAR_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

def _clean_node_text(text: str) -> str:
    return _CONTROL_CHAR_RE.sub('', text).strip()

class LegalQueryTool(BaseTool):
    name: str = "legal_query"
    description: str = (
        "Tra cứu pháp luật BĐS từ Luật Đất đai 2024, Luật Nhà ở 2023, "
        "Luật Kinh doanh BĐS 2023. Input phải là thuật ngữ pháp lý chính xác."
    )
    RELEVANCE_THRESHOLD: ClassVar[float] = 0.7

    def _run(self, query: str) -> str:
        try:
            index = LlamaCloudIndex(
                name=settings.llamacloud_index_id,
                api_key=settings.llamacloud_api_key,
                project_name="estate",
            )
            retriever = index.as_retriever(similarity_top_k=5)
            nodes = retriever.retrieve(query)

            relevant = [n for n in nodes if (n.score or 0) >= self.RELEVANCE_THRESHOLD]
            if not relevant:
                logger.info(f"[LegalQuery] no nodes above threshold {self.RELEVANCE_THRESHOLD} for {query!r}")
                return (
                    "Không tìm thấy thông tin trong văn bản pháp luật. "
                    "Bạn nên tham khảo luật sư hoặc cơ quan chức năng."
                )

            parts = []
            for node in relevant:
                file_name = node.metadata.get("file_name", "văn bản pháp luật")
                cleaned = _clean_node_text(node.text)
                if cleaned:
                    parts.append(f"--- Trích từ: {file_name} ---\n{cleaned}\n")

            if not parts:
                return "Không tìm thấy nội dung hợp lệ trong văn bản pháp luật."

            return "\n".join(parts)

        except Exception as e:
            logger.error(f"LegalQueryTool error: {e}")
            return f"Lỗi khi tra cứu văn bản pháp luật: {str(e)}"

    async def _arun(self, query: str) -> str:
        return self._run(query)
