import logging
import time
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from chains.appointment import _is_confirmation, appointment_chain
from chains.default import default_chain
from chains.find_property import find_property_chain
from chains.legal_faq import legal_chain
from chains.market_analysis import market_analysis_chain
from chains.post_property import post_property_chain
from chains.property_detail import property_detail_chain
from core.config import settings
from memory.history_summarizer import history_summarizer

logger = logging.getLogger(__name__)

_POST_PROPERTY_KEYWORDS = (
    "đăng tin",
    "dang tin",
    "rao bán",
    "rao ban",
    "muốn đăng",
    "muon dang",
    "tôi đăng",
    "toi dang",
    "muốn rao",
    "muon rao",
    "đăng bất động sản",
    "dang bat dong san",
    "đăng nhà",
    "dang nha",
    "bán nhà",
    "ban nha",
    "cho thuê nhà của",
    "cho thue nha cua",
)

_FIND_PROPERTY_KEYWORDS = (
    "tìm",
    "tim",
    "kiếm",
    "kiem",
    "nhà",
    "nha",
    "căn",
    "can",
    "bất động sản",
    "bat dong san",
    "chung cư",
    "chung cu",
)

_APPOINTMENT_KEYWORDS = (
    "đặt lịch",
    "dat lich",
    "hẹn",
    "hen",
    "xem nhà",
    "xem nha",
    "lịch hẹn",
    "lich hen",
)

# Nếu câu hỏi chứa các cụm từ này thì KHÔNG phải find_property — để LLM phân loại
_MARKET_ANALYSIS_KEYWORDS = (
    "giá trung bình",
    "trung bình giá",
    "giá thị trường",
    "thị trường",
    "định giá",
    "ước tính giá",
    "so sánh giá",
    "giá/m2",
    "giá m2",
)

# Nếu câu hỏi chứa các cụm từ này thì KHÔNG phải continuation — để LLM phân loại property_detail
_PROPERTY_DETAIL_SIGNALS = (
    "chi tiết",
    "thông tin chi tiết",
    "chi tiết hơn",
    "thông tin thêm",
    "thêm thông tin",
    "xem chi tiết",
)


def _looks_like_post_property(text: str) -> bool:
    lowered = text.lower()
    return any(k in lowered for k in _POST_PROPERTY_KEYWORDS)


_CONTINUATION_SIGNALS = (
    "cái đó", "cái này", "cái kia", "căn đó", "căn này",
    "nó", "của nó", "cái đầu tiên", "cái thứ",
    "thêm nữa", "còn nữa", "tiếp theo", "cho xem thêm",
    "giá bao nhiêu", "bao nhiêu tiền", "chi tiết hơn", "thông tin thêm",
    "như vậy", "vậy thì", "vậy còn", "còn cái",
    "oke", "ok", "được rồi", "đồng ý", "xác nhận",
)

# Intent nào được phép tái dùng qua continuation (loại trừ unknown/escalate)
_REUSABLE_INTENTS = frozenset(
    {"find_property", "book_appointment", "check_appointment", "market_analysis", "general_faq", "post_property", "property_detail"}
)

# Tin nhắn ≤ N từ + có continuation signal → coi là follow-up
_CONTINUATION_MAX_WORDS = 10


def _is_continuation_message(message: str) -> bool:
    """True nếu message là follow-up ngắn của lượt trước.

    Trả về False nếu message chứa từ khoá chuyển chủ đề (appointment/market/property_detail).
    """
    lowered = message.lower().strip()
    # Không coi là continuation nếu message chứa keyword đặt lịch hoặc phân tích thị trường
    if any(k in lowered for k in _APPOINTMENT_KEYWORDS):
        return False
    if any(k in lowered for k in _MARKET_ANALYSIS_KEYWORDS):
        return False
    # Không coi là continuation nếu là yêu cầu xem chi tiết BĐS — để LLM phân loại đúng
    if any(k in lowered for k in _PROPERTY_DETAIL_SIGNALS):
        return False
    words = lowered.split()
    if len(words) <= 3:
        return True
    if len(words) <= _CONTINUATION_MAX_WORDS and any(sig in lowered for sig in _CONTINUATION_SIGNALS):
        return True
    return False


def _looks_like_property_search(text: str) -> bool:
    lowered = text.lower()
    has_find = any(k in lowered for k in _FIND_PROPERTY_KEYWORDS)
    has_appointment = any(k in lowered for k in _APPOINTMENT_KEYWORDS)
    has_market = any(k in lowered for k in _MARKET_ANALYSIS_KEYWORDS)
    has_post = _looks_like_post_property(text)
    return has_find and not has_appointment and not has_market and not has_post


class IntentClassification(BaseModel):
    intent: str = Field(
        description="find_property|property_detail|book_appointment|check_appointment|market_analysis|general_faq|post_property|escalate|unknown"
    )
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


_parser = PydanticOutputParser(pydantic_object=IntentClassification)

_CLASSIFIER_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Bạn là bộ phân loại ý định chatbot BĐS Hà Nội.\n"
     "Phân loại câu hỏi vào đúng 1 nhóm:\n"
     "- find_property:     tìm nhà, hỏi có nhà phù hợp không, tìm gần địa điểm/khu vực\n"
     "- property_detail:   hỏi thông tin chi tiết về một BĐS cụ thể đã được liệt kê "
     "(ví dụ: 'căn số 1 chi tiết', 'cho biết thêm về căn đó', 'bao nhiêu phòng ngủ', 'xem chi tiết căn 2')\n"
     "- book_appointment:  đặt lịch xem nhà\n"
     "- check_appointment: hỏi lịch đã đặt, trạng thái lịch hẹn\n"
     "- market_analysis:   hỏi giá thị trường, giá trung bình, so sánh giá, định giá, ước tính giá BĐS\n"
     "- general_faq:       pháp lý, sổ đỏ, sổ hồng, thủ tục mua bán\n"
     "- post_property:     chủ nhà muốn đăng tin bán nhà, cho thuê nhà, rao bán BĐS\n"
     "- escalate:          muốn gặp nhân viên, yêu cầu hỗ trợ trực tiếp\n"
     "- unknown:           không thuộc nhóm nào trên\n"
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

        # Step 1: Classify intent
        intent = "unknown"
        confidence = 0.0
        if _looks_like_post_property(user_message):
            intent = "post_property"
            confidence = 1.0
            logger.info("[Router] keyword guard matched post property")
        elif (
            _is_confirmation(user_message)
            and extracted_slots.get("pending_post_property")
        ):
            intent = "post_property"
            confidence = 1.0
            logger.info("[Router] confirmation matched pending post property")
        elif _looks_like_property_search(user_message):
            intent = "find_property"
            confidence = 1.0
            logger.info("[Router] keyword guard matched property search")
        elif (
            _is_confirmation(user_message)
            and (extracted_slots.get("pending_appointment") or last_intent == "book_appointment")
        ):
            intent = "book_appointment"
            confidence = 1.0
            logger.info("[Router] confirmation matched pending appointment")
        elif last_intent in _REUSABLE_INTENTS and _is_continuation_message(user_message):
            intent = last_intent
            confidence = 0.9
            logger.info(f"[Router] continuation detected → reusing last_intent={last_intent!r}")
        else:
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

        # Step 2: Route to destination chain
        if intent == "post_property":
            result = await post_property_chain.run(user_message, history, extracted_slots=extracted_slots, user_token=user_token)
        elif intent == "find_property":
            result = await find_property_chain.run(user_message, history, extracted_slots)
        elif intent == "property_detail":
            result = await property_detail_chain.run(user_message, history, extracted_slots)
        elif intent in ("book_appointment", "check_appointment"):
            result = await appointment_chain.run(user_message, history, extracted_slots=extracted_slots, user_token=user_token)
        elif intent == "market_analysis":
            result = await market_analysis_chain.run(user_message, history, extracted_slots)
        elif intent == "general_faq":
            result = await legal_chain.run(user_message, history)
        elif intent == "escalate":
            result = {
                "response": (
                    "Tôi hiểu bạn muốn được hỗ trợ trực tiếp từ nhân viên tư vấn. "
                    "Đang chuyển yêu cầu của bạn đến đội ngũ hỗ trợ, "
                    "vui lòng chờ trong giây lát — nhân viên sẽ liên hệ với bạn sớm nhất có thể!"
                ),
                "agent_chain": ["EscalateHandler"],
                "should_escalate": True,
            }
        else:
            result = await default_chain.run(user_message, history)

        latency_ms = int((time.perf_counter() - start) * 1000)

        return {
            "response": result["response"],
            "detected_intent": intent,
            "confidence_score": confidence,
            "agent_chain": ["RouterChain"] + result.get("agent_chain", []),
            "retrieved_context": result.get("retrieved_context"),
            "latency_ms": latency_ms,
            "tool_calls_count": result.get("tool_calls_count", 0),
            "raw_items": result.get("raw_items", []),
            "extracted_slots": result.get("extracted_slots"),
            "appointment_slots": result.get("appointment_slots"),
            "pending_appointment": result.get("pending_appointment"),
            "clear_pending_appointment": result.get("clear_pending_appointment", False),
            "pending_post_property": result.get("pending_post_property"),
            "clear_pending_post_property": result.get("clear_pending_post_property", False),
            "should_escalate": result.get("should_escalate", False),
        }


router_chain = RouterChain()
