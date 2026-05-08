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
from core.config import settings

logger = logging.getLogger(__name__)

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


def _looks_like_property_search(text: str) -> bool:
    lowered = text.lower()
    has_find = any(k in lowered for k in _FIND_PROPERTY_KEYWORDS)
    has_appointment = any(k in lowered for k in _APPOINTMENT_KEYWORDS)
    return has_find and not has_appointment


class IntentClassification(BaseModel):
    intent: str = Field(
        description="find_property|book_appointment|check_appointment|general_faq|escalate|unknown"
    )
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


_parser = PydanticOutputParser(pydantic_object=IntentClassification)

_CLASSIFIER_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Bạn là bộ phân loại ý định chatbot BĐS Hà Nội.\n"
     "Phân loại câu hỏi vào đúng 1 nhóm:\n"
     "- find_property:     tìm nhà, hỏi có nhà phù hợp không\n"
     "- book_appointment:  đặt lịch xem nhà\n"
     "- check_appointment: hỏi lịch đã đặt, trạng thái lịch hẹn\n"
     "- general_faq:       pháp lý, sổ đỏ, sổ hồng, thủ tục mua bán\n"
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
        if _looks_like_property_search(user_message):
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
        else:
            try:
                classification: IntentClassification = await self._classifier_chain.ainvoke({
                    "user_message": user_message,
                    "history": history,
                })
                intent = classification.intent
                confidence = classification.confidence
                logger.info(f"[Router] intent={intent} confidence={confidence:.2f} | {classification.reasoning!r}")
            except Exception as e:
                logger.error(f"[Router] classification error: {e}")

        print(f"INTENT  : {intent} (confidence={confidence:.2f})")

        # Step 2: Route to destination chain
        if intent == "find_property":
            result = await find_property_chain.run(user_message, history, extracted_slots)
        elif intent in ("book_appointment", "check_appointment"):
            result = await appointment_chain.run(user_message, history, extracted_slots=extracted_slots, user_token=user_token)
        elif intent == "general_faq":
            result = await legal_chain.run(user_message, history)
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
        }


router_chain = RouterChain()
