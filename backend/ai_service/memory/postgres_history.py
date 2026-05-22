from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from core.config import settings

class PostgresChatMessageHistory(BaseChatMessageHistory):
    WINDOW_SIZE: int = settings.memory_window_size

    def __init__(self, session_id: int):
        self.session_id = session_id
        self._messages: list[BaseMessage] = []

    @property
    def messages(self) -> list[BaseMessage]:
        return list(self._messages)

    def load(self, raw_messages: list[dict]) -> None:
        self._messages = []
        _role_map = {
            "human": HumanMessage,
            "ai": AIMessage,
            "system": SystemMessage,
        }
        for m in raw_messages:
            cls = _role_map.get(m.get("role", ""))
            if cls:
                self._messages.append(cls(content=m.get("content", "")))
        self._trim_window()

    def add_messages(self, messages: list[BaseMessage]) -> None:
        self._messages.extend(messages)
        self._trim_window()

    def add_user_message(self, msg: str) -> None:
        self._messages.append(HumanMessage(content=msg))
        self._trim_window()

    def add_ai_message(self, msg: str) -> None:
        self._messages.append(AIMessage(content=msg))
        self._trim_window()

    def add_system_message(self, msg: str) -> None:
        self._messages.append(SystemMessage(content=msg))
        self._trim_window()

    def _trim_window(self) -> None:
        if len(self._messages) > self.WINDOW_SIZE:
            self._messages = self._messages[-self.WINDOW_SIZE:]

    def to_json(self) -> list[dict]:
        _cls_role = {
            HumanMessage: "human",
            AIMessage: "ai",
            SystemMessage: "system",
        }
        return [
            {"role": _cls_role.get(type(m), "unknown"), "content": m.content}
            for m in self._messages
        ]

    def format_for_prompt(self) -> str:
        if not self._messages:
            return "(Chưa có lịch sử)"
        tail = self._messages[-10:]
        _labels = {HumanMessage: "Người dùng", AIMessage: "Bot", SystemMessage: "[Hệ thống]"}
        return "\n".join(
            f"{_labels.get(type(m), '?')}: {m.content}" for m in tail
        )

    def clear(self) -> None:
        self._messages = []
