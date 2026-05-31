from prompts.shared import DEFAULT_RESPONSE


class DefaultChain:
    async def run(self, user_message: str, history: str = "") -> dict:
        return {
            "response": DEFAULT_RESPONSE,
            "retrieved_context": None,
            "tool_chain": [],
            "agent_chain": ["DefaultChain"],
            "tool_calls_count": 0,
            "raw_items": [],
            "should_escalate": False,
        }


default_chain = DefaultChain()
