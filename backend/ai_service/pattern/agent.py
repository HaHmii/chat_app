import logging
import time

from langchain_community.callbacks import get_openai_callback
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from core.config import settings
from pattern.handoff_router import HandoffRouter
from pattern.utils import extract_pending_from_output
from pattern.router import _role_denied_result, _wants_escalate
from prompts.shared import DEFAULT_RESPONSE, OUT_OF_SCOPE_RESPONSE
from sub_agents import appointment, find_property, legal_query, market_analysis, post_property, property_detail
from sub_agents.appointment import _is_confirmation
from tools.appointment import AppointmentTool

logger = logging.getLogger(__name__)

_BOOKING_KEYWORDS = ("đặt lịch", "đặt hẹn", "hẹn xem", "lịch hẹn", "xem nhà")

_CONFIRM_RESPONSE_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Thông báo kết quả đặt lịch xem nhà cho người dùng. Trả lời thân thiện, ngắn gọn.\n"
     "QUAN TRỌNG: Dùng ĐÚNG tên căn và thời gian dưới đây, KHÔNG lấy từ lịch sử.\n"
     "{property_context}"
     "Kết quả từ hệ thống:\n{tool_result}\n\n"
     "Lịch sử: {history}"),
    ("human", "{user_message}"),
])

_SUBAGENT_MAP = {
    "find_property": find_property.run,
    "property_detail": property_detail.run,
    "appointment": appointment.run,
    "post_property": post_property.run,
    "market_analysis": market_analysis.run,
    "legal_query": legal_query.run,
}


class HandoffAgent:
    def __init__(self):
        self._router_llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0,
        )
        self._agent_llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.3,
        )
        self._router = HandoffRouter(self._router_llm)
        self._confirm_chain = _CONFIRM_RESPONSE_PROMPT | self._agent_llm | StrOutputParser()

    async def _confirm_booking(
        self,
        pending: dict,
        user_message: str,
        history: str,
        user_token: str | None,
        start: float,
    ) -> dict:
        with get_openai_callback() as cb:
            tool_result = AppointmentTool()._run(
                action="book",
                property_id=pending.get("property_id"),
                proposed_time=pending.get("proposed_time"),
                note=pending.get("note"),
                user_token=user_token,
            )
            logger.info(f"[HandoffAgent] confirmed booking | {tool_result[:80]!r}")

            property_title = pending.get("property_title", "")
            property_context = (
                f"Tên căn đã đặt (dùng chính xác tên này): {property_title}\n"
                if property_title else ""
            )
            response = await self._confirm_chain.ainvoke({
                "tool_result": tool_result,
                "property_context": property_context,
                "user_message": user_message,
                "history": history,
            })

        return {
            "response": response,
            "detected_intent": "appointment",
            "confidence_score": None,
            "agent_chain": ["HandoffRouter", "appointment_agent", "appointment"],
            "retrieved_context": tool_result,
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "tool_calls_count": 1,
            "should_escalate": False,
            "raw_items": [],
            "llm_tokens_used": cb.total_tokens,
            "clear_pending_appointment": True,
        }

    async def run(
        self,
        user_message: str,
        history: str = "",
        extracted_slots: dict | None = None,
        user_token: str | None = None,
        last_intent: str | None = None,
    ) -> dict:
        start = time.perf_counter()
        extracted_slots = extracted_slots or {}

        # Handle pending appointment confirmation (bypass router)
        pending = extracted_slots.get("pending_appointment") or {}
        if (
            pending.get("property_id")
            and pending.get("proposed_time")
            and _is_confirmation(user_message)
        ):
            return await self._confirm_booking(pending, user_message, history, user_token, start)

        with get_openai_callback() as cb:
            # Step 1: HandoffRouter LLM → detect intent
            intent = await self._router.route(user_message, history, extracted_slots, last_intent)

            user_role = extracted_slots.get("user_role")

            # Step 2: Sub-agent LLM → handle with specialized tools
            subagent_run = _SUBAGENT_MAP.get(intent)
            if intent == "appointment":
                if not user_token:
                    sub_result = _role_denied_result(
                        "Bạn cần đăng nhập để sử dụng tính năng đặt/xem lịch hẹn xem nhà."
                    )
                elif user_role == "owner":
                    sub_result = _role_denied_result(
                        "Tài khoản **Chủ nhà** không thể đặt lịch xem nhà của chính mình. "
                        "Vui lòng sử dụng tài khoản **khách** (role user) để đặt lịch, "
                        "hoặc liên hệ nhân viên nếu cần hỗ trợ thêm."
                    )
                else:
                    sub_result = await appointment.run(
                        user_message=user_message, history=history,
                        extracted_slots=extracted_slots, user_token=user_token,
                        agent_llm=self._agent_llm,
                    )
            elif intent == "post_property":
                if not user_token:
                    sub_result = _role_denied_result(
                        "Bạn cần đăng nhập bằng tài khoản **Chủ nhà** để đăng tin BĐS."
                    )
                elif user_role == "user":
                    sub_result = _role_denied_result(
                        "Chỉ tài khoản **Chủ nhà** mới có thể đăng tin BĐS. "
                        "Tài khoản của bạn hiện là tài khoản khách. "
                        "Vui lòng liên hệ nhân viên để được hỗ trợ nâng cấp tài khoản."
                    )
                else:
                    sub_result = await post_property.run(
                        user_message=user_message, history=history,
                        extracted_slots=extracted_slots, user_token=user_token,
                    )
            elif subagent_run:
                kwargs = {
                    "user_message": user_message,
                    "history": history,
                    "extracted_slots": extracted_slots,
                    "user_token": user_token,
                }
                if intent not in ("post_property",):
                    kwargs["agent_llm"] = self._agent_llm
                sub_result = await subagent_run(**kwargs)
            elif intent == "default":
                sub_result = {"response": DEFAULT_RESPONSE, "tool_chain": [], "raw_items": []}
            else:
                sub_result = {"response": OUT_OF_SCOPE_RESPONSE, "tool_chain": [], "raw_items": []}

        tool_chain = sub_result.get("tool_chain", [])
        output = sub_result.get("response", "")
        raw_items = sub_result.get("raw_items", [])

        # Detect escalation signal từ LLM response (nếu chưa được set bởi sub-agent)
        if not sub_result.get("should_escalate") and _wants_escalate(output):
            sub_result["should_escalate"] = True

        # agent_chain: HandoffRouter → {intent}_agent → tool(s)
        agent_chain = ["HandoffRouter", f"{intent}_agent"] + tool_chain

        result: dict = {
            "response": output,
            "detected_intent": intent,
            "confidence_score": None,
            "agent_chain": agent_chain,
            "retrieved_context": sub_result.get("retrieved_context"),
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "tool_calls_count": len(tool_chain),
            "should_escalate": sub_result.get("should_escalate", False),
            "raw_items": raw_items,
            "total_items_found": sub_result.get("total_items_found"),
            "extracted_slots": sub_result.get("extracted_slots"),
            "llm_tokens_used": cb.total_tokens,
        }
        for key in (
            "pending_post_property",
            "clear_pending_post_property",
            "pending_appointment",
            "clear_pending_appointment",
        ):
            if key in sub_result:
                result[key] = sub_result[key]

        # Pending appointment from agent output (when tool wasn't called yet)
        has_booking_intent = any(k in user_message.lower() for k in _BOOKING_KEYWORDS)
        if has_booking_intent and "appointment" not in tool_chain:
            property_list = extracted_slots.get("property_list") or []
            property_details = extracted_slots.get("property_list_details") or []
            pending_slots = extract_pending_from_output(output, property_list, property_details)
            if pending_slots.get("property_id") and pending_slots.get("proposed_time"):
                result["pending_appointment"] = pending_slots
                logger.info(
                    f"[HandoffAgent] pending saved: pid={pending_slots['property_id']} "
                    f"time={pending_slots['proposed_time']!r}"
                )

        return result


handoff_agent = HandoffAgent()
