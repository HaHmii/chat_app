import logging
import time

from langchain_community.callbacks import get_openai_callback
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from core.config import settings
from memory.history_summarizer import history_summarizer
from pattern.default import default_chain
from prompts.shared import DEFAULT_RESPONSE
from sub_agents import appointment, find_property, legal_query, market_analysis, post_property, property_detail
from sub_agents.appointment import _is_confirmation

logger = logging.getLogger(__name__)

_POST_PROPERTY_KEYWORDS = (
    "đăng tin", "dang tin", "rao bán", "rao ban", "muốn đăng", "muon dang",
    "tôi đăng", "toi dang", "muốn rao", "muon rao", "đăng bất động sản",
    "dang bat dong san", "đăng nhà", "dang nha", "bán nhà", "ban nha",
    "cho thuê nhà của", "cho thue nha cua",
)

_FIND_PROPERTY_KEYWORDS = (
    "bất động sản", "bat dong san", "chung cư", "chung cu", "căn hộ", "can ho",
    "nhà đất", "nha dat", "đất nền", "dat nen", "biệt thự", "biet thu",
    "nhà phố", "nha pho", "nhà riêng", "nha rieng", "shophouse",
    "tìm nhà", "tim nha", "mua nhà", "mua nha", "thuê nhà", "thue nha",
    "tìm căn", "tim can", "mua căn", "mua can", "thuê căn", "thue can",
    "nhà cho thuê", "nha cho thue", "thuê văn phòng", "thue van phong",
    "mặt bằng cho thuê", "mat bang cho thue",
)

_APPOINTMENT_KEYWORDS = (
    "đặt lịch", "dat lich", "hẹn", "hen", "xem nhà", "xem nha",
    "lịch hẹn", "lich hen",
)

_MARKET_ANALYSIS_KEYWORDS = (
    "giá trung bình", "trung bình giá", "giá thị trường", "thị trường",
    "định giá", "ước tính giá", "so sánh giá", "giá/m2", "giá m2",
    "xu hướng", "xu huong", "tiềm năng", "tiem nang",
    "biến động", "bien dong", "có tăng không", "tăng không", "giảm không",
)

_LEGAL_PRIORITY_KEYWORDS = (
    "thủ tục", "thu tuc", "điều khoản", "dieu khoan", "thế chấp", "the chap",
    "nội quy", "noi quy", "thẩm quyền", "tham quyen", "thuế phí", "thue phi",
    "sang tên", "sang ten", "quyền sở hữu", "quyen so huu",
    "luật đất đai", "luat dat dai", "luật nhà ở", "luat nha o",
    "hợp đồng mua bán", "hop dong mua ban", "hợp đồng thuê nhà", "hop dong thue nha",
    "điều kiện mua nhà", "dieu kien mua nha", "quy định pháp luật", "quy dinh phap luat",
    "người nước ngoài có được", "nguoi nuoc ngoai co duoc",
)

_PROPERTY_DETAIL_SIGNALS = (
    "chi tiết", "thông tin chi tiết", "chi tiết hơn",
    "thông tin thêm", "thêm thông tin", "xem chi tiết",
)

_EXPLICIT_SEARCH_VERBS = (
    "tìm", "tim", "kiếm", "kiem", "tìm kiếm", "tim kiem",
    "muốn tìm", "muon tim", "cần tìm", "can tim",
    "đang tìm", "đang tim",
)

_CONTINUATION_SIGNALS = (
    "cái đó", "cái này", "cái kia", "căn đó", "căn này",
    "nó", "của nó", "cái đầu tiên", "cái thứ",
    "thêm nữa", "còn nữa", "tiếp theo", "cho xem thêm",
    "giá bao nhiêu", "bao nhiêu tiền", "chi tiết hơn", "thông tin thêm",
    "như vậy", "vậy thì", "vậy còn", "còn cái",
    "oke", "ok", "được rồi", "đồng ý", "xác nhận",
)

_REUSABLE_INTENTS = frozenset(
    {"find_property", "appointment", "market_analysis", "legal_query", "post_property", "property_detail"}
)

_ESCALATION_SIGNALS = (
    "chuyển nhân viên", "nhân viên sẽ hỗ trợ", "chuyển yêu cầu",
    "nhân viên tư vấn", "đội ngũ hỗ trợ", "liên hệ nhân viên",
    "vui lòng chờ trong giây lát", "nhân viên sẽ liên hệ",
)


def _wants_escalate(text: str) -> bool:
    lower = text.lower()
    return any(sig in lower for sig in _ESCALATION_SIGNALS)


def _role_denied_result(message: str) -> dict:
    return {
        "response": message,
        "tool_chain": [],
        "agent_chain": ["RoleGuard"],
        "tool_calls_count": 0,
        "raw_items": [],
        "should_escalate": False,
    }

_CONTINUATION_MAX_WORDS = 10


def _looks_like_post_property(text: str) -> bool:
    lowered = text.lower()
    return any(k in lowered for k in _POST_PROPERTY_KEYWORDS)


def _is_explicit_search(text: str) -> bool:
    lowered = text.lower()
    return any(k in lowered for k in _EXPLICIT_SEARCH_VERBS)


def _is_continuation_message(message: str) -> bool:
    lowered = message.lower().strip()
    if any(k in lowered for k in _APPOINTMENT_KEYWORDS):
        return False
    if any(k in lowered for k in _MARKET_ANALYSIS_KEYWORDS):
        return False
    if any(k in lowered for k in _PROPERTY_DETAIL_SIGNALS):
        return False
    words = lowered.split()
    if len(words) <= 3:
        return True
    if len(words) <= _CONTINUATION_MAX_WORDS and any(sig in lowered for sig in _CONTINUATION_SIGNALS):
        return True
    return False


def _has_active_flow(extracted_slots: dict) -> bool:
    return bool(
        extracted_slots.get("pending_post_property") or
        extracted_slots.get("pending_appointment") or
        extracted_slots.get("property_list")
    )


def _looks_like_legal_query(text: str) -> bool:
    lowered = text.lower()
    return any(k in lowered for k in _LEGAL_PRIORITY_KEYWORDS)


def _looks_like_property_search(text: str) -> bool:
    lowered = text.lower()
    has_find = any(k in lowered for k in _FIND_PROPERTY_KEYWORDS)
    has_appointment = any(k in lowered for k in _APPOINTMENT_KEYWORDS)
    has_market = any(k in lowered for k in _MARKET_ANALYSIS_KEYWORDS)
    has_post = _looks_like_post_property(text)
    has_detail = any(k in lowered for k in _PROPERTY_DETAIL_SIGNALS)
    return has_find and not has_appointment and not has_market and not has_post and not has_detail


class IntentClassification(BaseModel):
    intent: str = Field(
        description="find_property|property_detail|appointment|legal_query|market_analysis|post_property|escalate|fallback"
    )
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


_parser = PydanticOutputParser(pydantic_object=IntentClassification)

_CLASSIFIER_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Bạn là bộ phân loại ý định chatbot BĐS Hà Nội.\n"
     "Phân loại câu hỏi vào đúng 1 nhóm:\n"
     "- find_property:   tìm nhà, hỏi có nhà phù hợp không, tìm gần địa điểm/khu vực\n"
     "- property_detail: hỏi thông tin chi tiết về một BĐS cụ thể đã được liệt kê\n"
     "- appointment:     đặt lịch xem nhà, hủy lịch, xem danh sách lịch hẹn, kiểm tra trạng thái lịch\n"
     "- legal_query:     pháp lý, thủ tục, quy định, thuế phí, hợp đồng, quyền sở hữu\n"
     "- market_analysis: hỏi giá thị trường, giá trung bình, so sánh giá, định giá, xu hướng\n"
     "- post_property:   chủ nhà muốn đăng tin bán nhà, cho thuê nhà, rao bán BĐS\n"
     "- escalate:        muốn gặp nhân viên, yêu cầu hỗ trợ trực tiếp\n"
     "- fallback:        không thuộc nhóm nào trên (thời tiết, nấu ăn, thể thao...)\n"
     "Lịch sử: {history}\n"
     "{format_instructions}"),
    ("human", "{user_message}"),
]).partial(format_instructions=_parser.get_format_instructions())


class RouterChain:
    def __init__(self):
        self._llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0,
        )
        self._classifier_chain = _CLASSIFIER_PROMPT | self._llm | _parser

    async def run(
        self,
        user_message: str,
        history: str = "",
        extracted_slots: dict | None = None,
        user_token: str | None = None,
        last_intent: str | None = None,
    ) -> dict:
        extracted_slots = extracted_slots or {}
        start = time.perf_counter()

        intent = "fallback"
        confidence = 0.0
        _msg_lower = user_message.lower()

        if _looks_like_legal_query(user_message):
            intent = "legal_query"
            confidence = 1.0
            logger.info("[Router] keyword guard matched legal query")
        elif _looks_like_post_property(user_message):
            intent = "post_property"
            confidence = 1.0
            logger.info("[Router] keyword guard matched post property")
        elif (
            post_property._is_post_confirmation(user_message)
            and extracted_slots.get("pending_post_property")
        ):
            intent = "post_property"
            confidence = 1.0
            logger.info("[Router] confirmation matched pending post property")
        elif (
            last_intent == "post_property"
            and not _is_explicit_search(user_message)
            and not any(k in _msg_lower for k in _APPOINTMENT_KEYWORDS)
            and not any(k in _msg_lower for k in _MARKET_ANALYSIS_KEYWORDS)
        ):
            intent = "post_property"
            confidence = 0.95
            logger.info("[Router] post_property slot-filling continuation")
        elif _looks_like_property_search(user_message):
            intent = "find_property"
            confidence = 1.0
            logger.info("[Router] keyword guard matched property search")
        elif (
            _is_confirmation(user_message)
            and (extracted_slots.get("pending_appointment") or last_intent == "appointment")
        ):
            intent = "appointment"
            confidence = 1.0
            logger.info("[Router] confirmation matched pending appointment")
        elif (
            last_intent in _REUSABLE_INTENTS
            and _is_continuation_message(user_message)
            and _has_active_flow(extracted_slots)
        ):
            intent = last_intent
            confidence = 0.9
            logger.info(f"[Router] continuation detected → reusing last_intent={last_intent!r}")

        with get_openai_callback() as cb:
            if intent == "fallback" and confidence == 0.0:
                try:
                    summarized_history = await history_summarizer.summarize(history)
                    classification: IntentClassification = await self._classifier_chain.ainvoke({
                        "user_message": user_message,
                        "history": summarized_history,
                    })
                    intent = classification.intent
                    confidence = classification.confidence
                    logger.info(f"[Router] intent={intent} confidence={confidence:.2f} | {classification.reasoning!r}")
                except Exception as e:
                    logger.error(f"[Router] classification error: {e}")

            print(f"INTENT  : {intent} (confidence={confidence:.2f})")

            user_role = extracted_slots.get("user_role")

            if intent == "appointment":
                if not user_token:
                    result = _role_denied_result(
                        "Bạn cần đăng nhập để sử dụng tính năng đặt/xem lịch hẹn xem nhà."
                    )
                elif user_role == "owner":
                    result = _role_denied_result(
                        "Tài khoản **Chủ nhà** không thể đặt lịch xem nhà của chính mình. "
                        "Vui lòng sử dụng tài khoản **khách** (role user) để đặt lịch, "
                        "hoặc liên hệ nhân viên nếu cần hỗ trợ thêm."
                    )
                else:
                    result = await appointment.run(user_message, history, extracted_slots=extracted_slots, user_token=user_token)
            elif intent == "post_property":
                if not user_token:
                    result = _role_denied_result(
                        "Bạn cần đăng nhập bằng tài khoản **Chủ nhà** để đăng tin BĐS."
                    )
                elif user_role == "user":
                    result = _role_denied_result(
                        "Chỉ tài khoản **Chủ nhà** mới có thể đăng tin BĐS. "
                        "Tài khoản của bạn hiện là tài khoản khách. "
                        "Vui lòng liên hệ nhân viên để được hỗ trợ nâng cấp tài khoản."
                    )
                else:
                    result = await post_property.run(user_message, history, extracted_slots=extracted_slots, user_token=user_token)
            elif intent == "find_property":
                result = await find_property.run(user_message, history, extracted_slots)
            elif intent == "property_detail":
                result = await property_detail.run(user_message, history, extracted_slots)
            elif intent == "market_analysis":
                result = await market_analysis.run(user_message, history, extracted_slots)
            elif intent == "legal_query":
                result = await legal_query.run(user_message, history)
            elif intent == "escalate":
                result = {
                    "response": (
                        "Tôi hiểu bạn muốn được hỗ trợ trực tiếp từ nhân viên tư vấn. "
                        "Đang chuyển yêu cầu của bạn đến đội ngũ hỗ trợ, "
                        "vui lòng chờ trong giây lát — nhân viên sẽ liên hệ với bạn sớm nhất có thể!"
                    ),
                    "agent_chain": ["EscalateHandler"],
                    "tool_chain": [],
                    "tool_calls_count": 0,
                    "raw_items": [],
                    "retrieved_context": None,
                    "should_escalate": True,
                }
            else:
                result = await default_chain.run(user_message, history)

        # Detect escalation signal từ LLM response (nếu chưa được set bởi sub-agent)
        if not result.get("should_escalate") and _wants_escalate(result.get("response", "")):
            result["should_escalate"] = True

        total_tokens: int = cb.total_tokens
        latency_ms = int((time.perf_counter() - start) * 1000)

        return {
            "response": result["response"],
            "detected_intent": intent,
            "confidence_score": confidence,
            "agent_chain": ["RouterChain"] + result.get("agent_chain", []),
            "retrieved_context": result.get("retrieved_context"),
            "latency_ms": latency_ms,
            "tool_calls_count": result.get("tool_calls_count", 0),
            "llm_tokens_used": total_tokens,
            "raw_items": result.get("raw_items", []),
            "total_items_found": result.get("total_items_found"),
            "extracted_slots": result.get("extracted_slots"),
            "appointment_slots": result.get("appointment_slots"),
            "pending_appointment": result.get("pending_appointment"),
            "clear_pending_appointment": result.get("clear_pending_appointment", False),
            "pending_post_property": result.get("pending_post_property"),
            "clear_pending_post_property": result.get("clear_pending_post_property", False),
            "should_escalate": result.get("should_escalate", False),
        }


router_chain = RouterChain()
