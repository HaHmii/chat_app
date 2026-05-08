class DefaultChain:
    async def run(self, user_message: str, history: str = "") -> dict:
        return {
            "response": (
                "Xin chào! Tôi có thể hỗ trợ:\n"
                "• Tìm nhà/căn hộ theo quận, giá, diện tích\n"
                "• Đặt lịch xem nhà\n"
                "• Giải đáp pháp lý mua bán, thuê nhà\n"
                "Bạn cần hỗ trợ gì?"
            ),
            "retrieved_context": None,
            "agent_chain": ["DefaultChain"],
            "tool_calls_count": 0,
        }


default_chain = DefaultChain()
