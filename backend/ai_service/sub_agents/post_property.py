import json
import logging
from typing import Optional

import httpx
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError

from core.config import settings
from pattern.tools import PostPropertyHandoffTool
from pattern.utils import RECURSION_LIMIT, extract_final_output, extract_tool_chain
from prompts.shared import ESCALATION_RULES, POST_PROPERTY_REQUIRED, POST_PROPERTY_RULES, ROLE_GUARD_POST_PROPERTY
from sub_agents.appointment import _is_confirmation, _normalize_text
from tools.post_property import PostPropertyTool

logger = logging.getLogger(__name__)

_DENY_WORDS = frozenset({"không", "khong", "chưa", "chua", "hủy", "huy", "thôi", "thoi"})
_RESUME_TOKENS = ("tiếp tục", "tiep tuc", "giữ nguyên", "giu nguyen", "dùng lại", "dung lai")
_NEW_TOKENS = (
    "tạo mới", "tao moi", "làm lại", "lam lai", "nhập lại", "nhap lai",
    "đăng mới", "dang moi", "tin mới", "tin moi",
)


def _is_denial(text: str) -> bool:
    normalized = _normalize_text(text)
    tokens = set(normalized.split())
    deny_words = {"khong", "chua", "huy", "thoi", "bo"}
    deny_phrases = (
        "tam dung",
        "dung viec dang tin",
        "huy dang tin",
        "bo qua",
        "thoi khong dang",
        "khong dang nua",
    )
    return bool(deny_words & tokens) or any(k in normalized for k in deny_phrases)


def _is_resume_intent(text: str) -> bool:
    lowered = text.lower()
    return any(k in lowered for k in _RESUME_TOKENS) or _is_confirmation(text)


def _is_new_intent(text: str) -> bool:
    lowered = text.lower()
    return any(k in lowered for k in _NEW_TOKENS)


_POST_CONFIRM_PHRASES = (
    "xac thuc dang tin",
    "xac nhan dang tin",
    "xac nhan dang",
    "dong y dang tin",
    "dong y dang",
    "tien hanh dang tin",
    "dang tin di",
    "gui dang tin",
    "chot dang tin",
)


def _is_post_confirmation(text: str) -> bool:
    normalized = _normalize_text(text)
    return _is_confirmation(text) or any(k in normalized for k in _POST_CONFIRM_PHRASES)


_REQUIRED_FIELDS = {"title", "type", "category", "address", "district_id", "price", "area"}

_FIELD_LABELS = {
    "title": "tiêu đề tin đăng (ít nhất 10 ký tự, mô tả ngắn gọn căn nhà)",
    "type": "loại giao dịch (bán hay cho thuê?)",
    "category": "loại bất động sản (chung cư, nhà riêng, đất nền, biệt thự, nhà liền kề, shophouse, văn phòng)",
    "address": "địa chỉ cụ thể (số nhà, tên đường, phường/xã)",
    "district_id": "quận/huyện",
    "price": "giá bán hoặc giá thuê (kèm đơn vị: triệu, tỷ, triệu/tháng)",
    "area": "diện tích (m²)",
}

# ─── Chain mode prompts ────────────────────────────────────────────────────────

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
     "Vai trò người dùng hiện tại: {user_role}.\n"
     + ROLE_GUARD_POST_PROPERTY + "\n"
     + ESCALATION_RULES + "\n"
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


# ─── Agent mode prompt ─────────────────────────────────────────────────────────

def _build_agent_prompt(history: str, user_role: str = "unknown") -> str:
    return (
        "Bạn là trợ lý hỗ trợ người dùng đăng tin BĐS (bán hoặc cho thuê nhà của mình).\n"
        f"Vai trò người dùng: {user_role}.\n"
        + ROLE_GUARD_POST_PROPERTY + "\n"
        + ESCALATION_RULES + "\n"
        "⚠️ Thông tin BĐS người dùng cung cấp là DỮ LIỆU ĐĂNG TIN — KHÔNG tìm kiếm.\n\n"
        + POST_PROPERTY_RULES
        + f"\nLịch sử hội thoại:\n{history}"
    )


# ─── Chain mode implementation ─────────────────────────────────────────────────

class _PostPropertyChain:
    def __init__(self):
        self._llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.3,
        )
        self._tool = PostPropertyTool()
        self._slot_chain = _SLOT_PROMPT | self._llm | StrOutputParser()
        self._chain = _CONFIRM_PROMPT | self._llm | StrOutputParser()

    @staticmethod
    def _pending_state(pending: dict, awaiting_resume: bool = False) -> dict | None:
        return {**pending, "_awaiting_resume": awaiting_resume} if pending else None

    async def _lookup_district_id(self, district_name: str) -> Optional[int]:
        try:
            resp = httpx.get(f"{settings.web_service_url}/districts", timeout=5.0)
            resp.raise_for_status()
            name_lower = district_name.lower().strip()
            for d in resp.json():
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

    async def _submit_pending(
        self,
        pending: dict,
        user_message: str,
        history: str,
        user_token: str | None,
        user_role: str = "unknown",
    ) -> dict:
        api_result = self._tool._run(
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
        success = "dang tin thanh cong" in _normalize_text(api_result)
        logger.info(f"[PostProperty] submitted | success={success} | result={api_result[:80]!r}")
        response = await self._chain.ainvoke({
            "status": "done",
            "collected_info": self._format_collected(pending),
            "missing_fields": "",
            "api_result": api_result,
            "history": history,
            "user_message": user_message,
            "user_role": user_role,
        })
        return {
            "response": response,
            "retrieved_context": api_result,
            "tool_chain": ["PostPropertyTool"],
            "agent_chain": ["PostPropertyChain", "PostPropertyTool"],
            "tool_calls_count": 1,
            "raw_items": [],
            "should_escalate": False,
            "clear_pending_post_property": success,
            "pending_post_property": None if success else self._pending_state(pending),
        }

    async def run(
        self,
        user_message: str,
        history: str,
        extracted_slots: dict,
        user_token: str | None,
    ) -> dict:
        user_role = extracted_slots.get("user_role") or "chưa đăng nhập"
        pending: dict = dict(extracted_slots.get("pending_post_property") or {})
        awaiting_resume: bool = pending.pop("_awaiting_resume", False)

        # ── STATE A: đang chờ user chọn "tiếp tục hay tạo mới?" ─────────────
        if awaiting_resume:
            missing = _REQUIRED_FIELDS - set(pending.keys())
            if not missing and pending and _is_post_confirmation(user_message):
                return await self._submit_pending(pending, user_message, history, user_token, user_role)
            if _is_new_intent(user_message):
                pending = {}
            elif _is_resume_intent(user_message):
                response = await self._chain.ainvoke({
                    "status": "confirm",
                    "collected_info": self._format_collected(pending),
                    "missing_fields": "",
                    "api_result": "",
                    "history": history,
                    "user_message": user_message,
                    "user_role": user_role,
                })
                return {
                    "response": response,
                    "retrieved_context": "",
                    "tool_chain": [],
                    "agent_chain": ["PostPropertyChain"],
                    "tool_calls_count": 0,
                    "raw_items": [],
                    "should_escalate": False,
                    "pending_post_property": self._pending_state(pending),
                }
            else:
                response = (
                    f"Bạn có 1 tin đang chờ đăng:\n{self._format_collected(pending)}\n\n"
                    "Bạn muốn **tiếp tục** đăng tin này hay **tạo mới**?"
                )
                return {
                    "response": response,
                    "retrieved_context": "",
                    "tool_chain": [],
                    "agent_chain": ["PostPropertyChain"],
                    "tool_calls_count": 0,
                    "raw_items": [],
                    "should_escalate": False,
                    "pending_post_property": self._pending_state(pending, awaiting_resume=True),
                }

        missing = _REQUIRED_FIELDS - set(pending.keys())

        # ── STATE B: đủ thông tin + xác nhận → submit ────────────────────────
        if not missing and pending and _is_post_confirmation(user_message):
            return await self._submit_pending(pending, user_message, history, user_token, user_role)
            api_result = self._tool._run(
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
            success = api_result.startswith("Đăng tin thành công")
            logger.info(f"[PostProperty] submitted | success={success} | result={api_result[:80]!r}")
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
                "tool_chain": ["PostPropertyTool"],
                "agent_chain": ["PostPropertyChain", "PostPropertyTool"],
                "tool_calls_count": 1,
                "raw_items": [],
                "should_escalate": False,
                "clear_pending_post_property": success,
                "pending_post_property": None if success else self._pending_state(pending),
            }

        # ── STATE C: đủ thông tin + từ chối → lưu để dùng sau ───────────────
        if not missing and pending and _is_denial(user_message):
            return {
                "response": (
                    f"Đã lưu thông tin tin đăng. Khi muốn tiếp tục, chỉ cần nhắn **'tiếp tục'**.\n\n"
                    f"Tóm tắt đã lưu:\n{self._format_collected(pending)}"
                ),
                "retrieved_context": "",
                "tool_chain": [],
                "agent_chain": ["PostPropertyChain"],
                "tool_calls_count": 0,
                "raw_items": [],
                "should_escalate": False,
                "pending_post_property": self._pending_state(pending, awaiting_resume=True),
            }

        # ── STATE D: đủ thông tin + tin nhắn mơ hồ → hỏi tiếp tục hay mới ──
        if not missing and pending:
            response = await self._chain.ainvoke({
                "status": "confirm",
                "collected_info": self._format_collected(pending),
                "missing_fields": "",
                "api_result": "",
                "history": history,
                "user_message": user_message,
                "user_role": user_role,
            })
            return {
                "response": response,
                "retrieved_context": "",
                "tool_chain": [],
                "agent_chain": ["PostPropertyChain"],
                "tool_calls_count": 0,
                "raw_items": [],
                "should_escalate": False,
                "pending_post_property": self._pending_state(pending),
            }

        # ── STATE E: đang thu thập thông tin ─────────────────────────────────
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

        if "district" in new_slots:
            district_name = new_slots.pop("district")
            district_id = await self._lookup_district_id(district_name)
            if district_id:
                new_slots["district_id"] = district_id
                new_slots["district_name"] = district_name
            else:
                logger.warning(f"[PostProperty] district not found: {district_name!r}")

        pending.update(new_slots)
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
                "user_role": user_role,
            })
            return {
                "response": response,
                "retrieved_context": "",
                "tool_chain": [],
                "agent_chain": ["PostPropertyChain"],
                "tool_calls_count": 0,
                "raw_items": [],
                "should_escalate": False,
                "pending_post_property": self._pending_state(pending),
            }

        response = await self._chain.ainvoke({
            "status": "confirm",
            "collected_info": self._format_collected(pending),
            "missing_fields": "",
            "api_result": "",
            "history": history,
            "user_message": user_message,
            "user_role": user_role,
        })
        return {
            "response": response,
            "retrieved_context": "",
            "tool_chain": [],
            "agent_chain": ["PostPropertyChain"],
            "tool_calls_count": 0,
            "raw_items": [],
            "should_escalate": False,
            "pending_post_property": self._pending_state(pending),
        }


_chain = _PostPropertyChain()


# ─── Agent mode implementation ─────────────────────────────────────────────────

async def _run_agent(
    user_message: str,
    history: str,
    extracted_slots: dict,
    user_token: str | None,
    agent_llm: ChatOpenAI,
) -> dict:
    user_role = extracted_slots.get("user_role") or "chưa đăng nhập"
    post_property_tool = PostPropertyHandoffTool(user_token=user_token or "")
    graph = create_agent(
        model=agent_llm,
        tools=[post_property_tool],
        system_prompt=_build_agent_prompt(history, user_role),
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
        logger.warning(f"[post_property_agent] max_iterations: {user_message!r}")
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
        logger.error(f"[post_property_agent] error: {e}")
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
    return await _chain.run(user_message, history, slots, user_token)
