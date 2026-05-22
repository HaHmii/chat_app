import json
import logging
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from core.config import settings
from prompts.shared import PROPERTY_LISTING_RULES
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
    "location_landmark",
    "radius_km",
}

_PAGE_SIZE = 5

_SHOW_MORE_KEYWORDS = (
    "tìm thêm", "tim them",
    "căn khác", "can khac",
    "xem thêm", "xem them",
    "thêm nữa", "them nua",
    "tiếp theo", "tiep theo",
    "còn căn nào", "con can nao",
    "còn nhà nào", "con nha nao",
    "còn nữa", "con nua",
    "những căn khác", "nhà khác",
    "cho xem thêm",
)


def _is_show_more_request(message: str) -> bool:
    lowered = message.lower()
    return any(k in lowered for k in _SHOW_MORE_KEYWORDS)

_SLOT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Trích xuất bộ lọc tìm kiếm BĐS Hà Nội. Trả về JSON thuần (không markdown, không giải thích).\n"
     'Template: {{"district":null,"min_price":null,"max_price":null,"min_area":null,"property_type":null,"bedrooms":null,"category":null,"location_landmark":null,"radius_km":null}}\n'
     "Quy tắc:\n"
     "- location_landmark: tên địa điểm/mốc địa lý khi người dùng nói 'gần X', 'cạnh X', 'khu vực X' "
     "(ví dụ: 'Hồ Tây', 'ĐHBK', 'Big C Thăng Long', 'Vincom Bà Triệu'). null nếu không đề cập.\n"
     "- radius_km: bán kính tìm kiếm (km) khi có location_landmark, mặc định 3.0 nếu không nói rõ, null nếu không có location_landmark\n"
     "- district: tên quận/huyện (Cầu Giấy, Ba Đình...) hoặc null — KHÔNG điền nếu đã có location_landmark\n"
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
     "- category: căn hộ|nhà nguyên căn|đất nền|biệt thự|nhà phố|nhà phố thương mại|văn phòng hoặc null\n"
     "  -> apartment|house|land|villa|townhouse|shophouse|office|null\n"
     "- min_area: diện tích tối thiểu m² hoặc null"),
    ("human", "{user_message}"),
])

_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Bạn là tư vấn viên BĐS tại Hà Nội.\n"
     + PROPERTY_LISTING_RULES + "\n"
     "Kết quả tìm kiếm (NGUỒN DUY NHẤT được dùng để liệt kê BĐS):\n{search_result}\n\n"
     "Lịch sử hội thoại (chỉ dùng để hiểu ngữ cảnh, KHÔNG dùng để lấy BĐS):\n{history}"),
    ("human", "{user_message}"),
])


class FindPropertyChain:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.3,
        )
        self.property_tool = PropertySearchTool()
        self._slot_chain = _SLOT_PROMPT | self.llm | StrOutputParser()
        self._chain = _PROMPT | self.llm | StrOutputParser()

    async def run(
        self,
        user_message: str,
        history: str = "",
        extracted_slots: dict | None = None,
    ) -> dict:
        extracted_slots = extracted_slots or {}

        # property_pending=None → chưa search lần nào; [] → đã search nhưng hết kết quả
        pending: list | None = extracted_slots.get("property_pending")

        # --- SHOW MORE: người dùng muốn xem thêm căn, dùng pending buffer ---
        if _is_show_more_request(user_message) and pending is not None:
            session_slots = {k: v for k, v in extracted_slots.items() if k in SEARCH_SLOT_KEYS and v is not None}

            if not pending:
                response = (
                    "Đã hiển thị tất cả kết quả phù hợp với yêu cầu của bạn. "
                    "Bạn muốn tìm với điều kiện khác không?"
                )
                logger.info("[FindProperty] show_more requested but pending is empty")
                return {
                    "response": response,
                    "retrieved_context": None,
                    "raw_items": [],
                    "extracted_slots": {**session_slots, "property_pending": []},
                    "agent_chain": ["FindPropertyChain"],
                    "tool_calls_count": 0,
                }

            batch = pending[:_PAGE_SIZE]
            remaining = pending[_PAGE_SIZE:]
            _landmark = session_slots.get("location_landmark")
            search_result = PropertySearchTool._format_items(batch, location=_landmark)
            logger.info(f"[FindProperty] show_more | batch={len(batch)} remaining={len(remaining)}")

            response = await self._chain.ainvoke({
                "search_result": search_result,
                "history": history,
                "user_message": user_message,
            })
            return {
                "response": response,
                "retrieved_context": search_result,
                "raw_items": batch,
                "extracted_slots": {**session_slots, "property_pending": remaining},
                "agent_chain": ["FindPropertyChain", "PendingBuffer"],
                "tool_calls_count": 0,
            }

        # --- FRESH SEARCH ---
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

        # Merge: session làm nền, current ghi đè từng key — giữ location_landmark từ session
        slots = {**session_search_slots, **current_slots} if current_slots else session_search_slots
        print(f"SLOTS   : session={session_search_slots} current={current_slots} search={slots}")

        # Hỏi lại nếu chưa biết mua hay thuê
        if "property_type" not in slots:
            return {
                "response": (
                    "Bạn muốn **mua** hay **thuê** bất động sản ạ? "
                    "Vui lòng cho tôi biết để tôi tìm kiếm chính xác hơn nhé!"
                ),
                "retrieved_context": None,
                "raw_items": [],
                "extracted_slots": {**session_search_slots, **current_slots},
                "agent_chain": ["FindPropertyChain"],
                "tool_calls_count": 0,
            }

        location_landmark = slots.pop("location_landmark", None)
        radius_km = slots.pop("radius_km", 3.0) or 3.0

        if location_landmark:
            filter_slots = {k: v for k, v in slots.items() if k not in ("district",)}
            search_result, all_items = self.property_tool.search_raw(
                location=location_landmark,
                radius_km=float(radius_km),
                **filter_slots,
            )
            logger.info(f"[PropertySearch] landmark={location_landmark!r} r={radius_km}km | found={len(all_items)}")
            used_tool = "PropertySearchTool(nearby)"
            slots["location_landmark"] = location_landmark
            slots["radius_km"] = radius_km
        else:
            search_result, all_items = self.property_tool.search_raw(query=user_message, **slots)
            logger.info(f"[PropertySearch] query={user_message!r} | slots={slots} | found={len(all_items)}")
            used_tool = "PropertySearchTool"

        # Chỉ hiển thị _PAGE_SIZE đầu, phần còn lại lưu vào pending buffer
        batch = all_items[:_PAGE_SIZE]
        pending_items = all_items[_PAGE_SIZE:]
        slots["property_pending"] = pending_items

        # Chỉ build LLM context từ batch đang hiển thị
        if batch:
            batch_text = PropertySearchTool._format_items(batch, location=location_landmark)
        else:
            batch_text = search_result

        response = await self._chain.ainvoke({
            "search_result": batch_text,
            "history": history,
            "user_message": user_message,
        })

        logger.info(f"[FindProperty] fresh search | show={len(batch)} pending={len(pending_items)}")

        return {
            "response": response,
            "retrieved_context": batch_text,
            "raw_items": batch,
            "extracted_slots": slots,
            "agent_chain": ["FindPropertyChain", used_tool],
            "tool_calls_count": 1,
        }


find_property_chain = FindPropertyChain()
