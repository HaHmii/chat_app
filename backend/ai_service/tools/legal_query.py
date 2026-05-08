import logging
from typing import ClassVar

from langchain_core.tools import BaseTool

from core.config import settings
from llama_index.indices.managed.llama_cloud import LlamaCloudIndex

logger = logging.getLogger(__name__)


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

            if not nodes:
                return (
                    "Không tìm thấy thông tin trong văn bản pháp luật. "
                    "Bạn nên tham khảo luật sư hoặc cơ quan chức năng."
                )

            parts = []
            for node in nodes:
                file_name = node.metadata.get("file_name", "văn bản pháp luật")
                parts.append(f"--- Trích từ: {file_name} ---\n{node.text}\n")
            return "\n".join(parts)

        except Exception as e:
            logger.error(f"LegalQueryTool error: {e}")
            return f"Lỗi khi tra cứu văn bản pháp luật: {str(e)}"

    async def _arun(self, query: str) -> str:
        return self._run(query)
