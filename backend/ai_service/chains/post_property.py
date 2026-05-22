import json
import logging
from typing import Optional

import httpx
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from chains.appointment import _is_confirmation
from core.config import settings
from prompts.shared import POST_PROPERTY_REQUIRED
from tools.post_property import PostPropertyTool

logger = logging.getLogger(__name__)

# Các trường bắt buộc để đăng tin
_REQUIRED_FIELDS = {"title", "type", "category", "address", "district_id", "price", "area"}

# Nhãn thân thiện để hỏi người dùng
_FIELD_LABELS = {
    "title": "tiêu đề tin đăng (ít nhất 10 ký tự, mô tả ngắn gọn căn nhà)",
    "type": "loại giao dịch (bán hay cho thuê?)",
    "category": "loại bất động sản (chung cư, nhà riêng, đất nền, biệt thự, nhà liền kề, shophouse, văn phòng)",
    "address": "địa chỉ cụ thể (số nhà, tên đường, phường/xã)",
    "district_id": "quận/huyện",
    "price": "giá bán hoặc giá thuê (kèm đơn vị: triệu, tỷ, triệu/tháng)",
    "area": "diện tích (m²)",
}

_SLOT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Trích xuất thông tin đăng tin BĐS từ câu của người dùng. Trả JSON thuần (không markdown).\n"
     "Template:\n"
     '{{"title":null,"type":null,"category":null,"address":null,"district":null,'
     '"price":null,"price_unit":null,"area":null,"bedrooms":null,"bathrooms":null,'
     '"direction":null,"legal_status":null,"description":null}}\n'
     "Quy tắc:\n"
     "- title: tiêu đề tin đăng (chuỗi ký tự mô tả căn nhà) hoặc null\n"
     "- type: 'sell' (bán) | 'rent' (cho thuê) | null\n"
     "- category: 'apartment'|'house'|'land'|'villa'|'townhouse'|'shophouse'|'office' | null\n"
     "- address: địa chỉ cụ thể (không bao gồm tên quận) hoặc null\n"
     "- district: tên quận/huyện (chuỗi, chưa cần ID) hoặc null\n"
     "- price: số thực (giá trị số, không kèm đơn vị) hoặc null\n"
     "- price_unit: 'Triệu' | 'Tỷ' | 'Triệu/tháng' | null\n"
     "- area: số thực (m²) hoặc null\n"
     "- bedrooms: số nguyên hoặc null\n"
     "- bathrooms: số nguyên hoặc null\n"
     "- direction: hướng nhà (Đông, Tây, Nam, Bắc, Đông-Nam...) hoặc null\n"
     "- legal_status: tình trạng pháp lý (sổ đỏ, sổ hồng, hợp đồng mua bán...) hoặc null\n"
     "- description: mô tả chi tiết về căn nhà hoặc null\n"
     "Lịch sử hội thoại:\n{history}"),
    ("human", "{user_message}"),
])

_CONFIRM_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Bạn là trợ lý hỗ trợ đăng tin BĐS.\n"
     + POST_PROPERTY_REQUIRED + "\n"
     "Trạng thái: {status}\n"
     "Thông tin đã thu thập:\n{collected_info}\n"
     "Trường còn thiếu: {missing_fields}\n"
     "Kết quả gọi API: {api_result}\n\n"
     "Hướng dẫn dựa trên trạng thái:\n"
     "- status='missing': Hỏi thêm các trường còn thiếu theo thứ tự ưu tiên. Liệt kê rõ từng mục.\n"
     "- status='confirm': Hiển thị tóm tắt thông tin và yêu cầu người dùng xác nhận (ok/đúng rồi).\n"
     "- status='done': Thông báo kết quả đăng tin dựa trên api_result.\n"
     "Trả lời bằng tiếng Việt, thân thiện và rõ ràng.\n"
     "Lịch sử hội thoại:\n{history}"),
    ("human", "{user_message}"),
])


class PostPropertyChain:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.3,
        )
        self.tool = PostPropertyTool()
        self._slot_chain = _SLOT_PROMPT | self.llm | StrOutputParser()
        self._chain = _CONFIRM_PROMPT | self.llm | StrOutputParser()

    async def _lookup_district_id(self, district_name: str) -> Optional[int]:
        """Gọi /districts để tìm district_id theo tên quận."""
        try:
            resp = httpx.get(f"{settings.web_service_url}/districts", timeout=5.0)
            resp.raise_for_status()
            districts = resp.json()
            name_lower = district_name.lower().strip()
            for d in districts:
                if name_lower in d["name"].lower() or d["name"].lower() in name_lower:
                    return d["id"]
        except Exception as e:
            logger.warning(f"[PostProperty] district lookup failed: {e}")
        return None

    def _format_collected(self, slots: dict) -> str:
        type_map = {"sell": "Bán", "rent": "Cho thuê"}
        category_map = {
            "apartment": "Chung cư", "house": "Nhà riêng", "land": "Đất nền",
            "villa": "Biệt thự", "townhouse": "Nhà liền kề",
            "shophouse": "Shophouse", "office": "Văn phòng",
        }
        lines = []
        if slots.get("title"):
            lines.append(f"• Tiêu đề: {slots['title']}")
        if slots.get("type"):
            lines.append(f"• Loại: {type_map.get(slots['type'], slots['type'])}")
        if slots.get("category"):
            lines.append(f"• Loại BĐS: {category_map.get(slots['category'], slots['category'])}")
        if slots.get("address"):
            lines.append(f"• Địa chỉ: {slots['address']}")
        if slots.get("district_name"):
            lines.append(f"• Quận/Huyện: {slots['district_name']}")
        if slots.get("price") is not None:
            unit = slots.get("price_unit", "")
            lines.append(f"• Giá: {slots['price']} {unit}".strip())
        if slots.get("area") is not None:
            lines.append(f"• Diện tích: {slots['area']} m²")
        if slots.get("bedrooms") is not None:
            lines.append(f"• Phòng ngủ: {slots['bedrooms']}")
        if slots.get("bathrooms") is not None:
            lines.append(f"• Phòng vệ sinh: {slots['bathrooms']}")
        if slots.get("direction"):
            lines.append(f"• Hướng nhà: {slots['direction']}")
        if slots.get("legal_status"):
            lines.append(f"• Pháp lý: {slots['legal_status']}")
        if slots.get("description"):
            lines.append(f"• Mô tả: {slots['description'][:100]}...")
        return "\n".join(lines) if lines else "(chưa có thông tin)"

    async def run(
        self,
        user_message: str,
        history: str = "",
        extracted_slots: dict | None = None,
        user_token: str | None = None,
    ) -> dict:
        extracted_slots = extracted_slots or {}
        pending: dict = dict(extracted_slots.get("pending_post_property") or {})

        # Bước 1: Nếu đã có đủ thông tin và người dùng xác nhận → đăng tin
        if pending and _is_confirmation(user_message):
            api_result = self.tool._run(
                title=pending["title"],
                type=pending["type"],
                category=pending["category"],
                address=pending["address"],
                district_id=pending["district_id"],
                price=pending["price"],
                area=pending["area"],
                price_unit=pending.get("price_unit"),
                description=pending.get("description"),
                bedrooms=pending.get("bedrooms"),
                bathrooms=pending.get("bathrooms"),
                direction=pending.get("direction"),
                legal_status=pending.get("legal_status"),
                amenities=pending.get("amenities"),
                user_token=user_token,
            )
            logger.info(f"[PostProperty] submitted | result={api_result[:80]!r}")
            response = await self._chain.ainvoke({
                "status": "done",
                "collected_info": self._format_collected(pending),
                "missing_fields": "",
                "api_result": api_result,
                "history": history,
                "user_message": user_message,
            })
            return {
                "response": response,
                "retrieved_context": api_result,
                "agent_chain": ["PostPropertyChain", "PostPropertyTool"],
                "tool_calls_count": 1,
                "clear_pending_post_property": api_result.startswith("Đăng tin thành công"),
            }

        # Bước 2: Trích xuất slot từ tin nhắn hiện tại
        new_slots: dict = {}
        try:
            raw_json = await self._slot_chain.ainvoke({
                "user_message": user_message,
                "history": history,
            })
            parsed = json.loads(raw_json.strip())
            new_slots = {k: v for k, v in parsed.items() if v is not None}
        except Exception as e:
            logger.warning(f"[PostProperty] slot extraction failed: {e}")

        # Bước 3: Tra cứu district_id nếu có tên quận mới
        if "district" in new_slots:
            district_name = new_slots.pop("district")
            district_id = await self._lookup_district_id(district_name)
            if district_id:
                new_slots["district_id"] = district_id
                new_slots["district_name"] = district_name
            else:
                logger.warning(f"[PostProperty] district not found: {district_name!r}")

        # Bước 4: Gộp slot mới vào pending (ưu tiên thông tin mới hơn)
        pending.update(new_slots)

        # Bước 5: Kiểm tra trường còn thiếu
        missing = _REQUIRED_FIELDS - set(pending.keys())
        missing_labels = [_FIELD_LABELS[f] for f in sorted(missing)]

        if missing:
            response = await self._chain.ainvoke({
                "status": "missing",
                "collected_info": self._format_collected(pending),
                "missing_fields": ", ".join(missing_labels),
                "api_result": "",
                "history": history,
                "user_message": user_message,
            })
            return {
                "response": response,
                "retrieved_context": "",
                "agent_chain": ["PostPropertyChain"],
                "tool_calls_count": 0,
                "pending_post_property": pending if pending else None,
            }

        # Bước 6: Đã đủ thông tin → yêu cầu xác nhận
        response = await self._chain.ainvoke({
            "status": "confirm",
            "collected_info": self._format_collected(pending),
            "missing_fields": "",
            "api_result": "",
            "history": history,
            "user_message": user_message,
        })
        return {
            "response": response,
            "retrieved_context": "",
            "agent_chain": ["PostPropertyChain"],
            "tool_calls_count": 0,
            "pending_post_property": pending,
        }


post_property_chain = PostPropertyChain()
