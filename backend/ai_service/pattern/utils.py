import re
from datetime import datetime, timedelta

from langchain_core.messages import AIMessage

_MAX_ITERATIONS = 5
RECURSION_LIMIT = _MAX_ITERATIONS * 2 + 1

_WEEKDAY_VN = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]

_ISO_TIME_RE = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+07:00')
_CAN_SO_RE = re.compile(r'căn\s+số\s+(\d+)', re.IGNORECASE)


def build_week_calendar(now: datetime) -> str:
    today_wd = now.weekday()
    lines = []
    for i, name in enumerate(_WEEKDAY_VN):
        days_ahead = (i - today_wd) % 7
        label = (
            now.strftime("%Y-%m-%d") + " (hôm nay)"
            if days_ahead == 0
            else (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        )
        lines.append(f"  {name}: {label}")
    return "\n".join(lines)


def build_property_mapping(property_list: list, property_details: list) -> str:
    if not property_list:
        return "Chưa có kết quả tìm kiếm trong phiên này.\n"
    lines = []
    for i, pid in enumerate(property_list):
        detail = property_details[i] if i < len(property_details) else {}
        title = detail.get("title", "")
        price = detail.get("price_display", "")
        area = detail.get("area", "")
        district = detail.get("district", "")
        meta = " | ".join(filter(None, [title, price, f"{area}m²" if area else "", district]))
        lines.append(
            f"  Căn số {i + 1}: property_id={pid}" + (f" — {meta}" if meta else "")
        )
    return (
        "Danh sách căn nhà từ kết quả tìm kiếm gần nhất (NGUỒN DUY NHẤT để xác định property_id):\n"
        + "\n".join(lines) + "\n"
        "Khi người dùng nói 'căn số X', 'căn thứ X', 'căn đầu tiên', 'căn cuối'..., "
        "tra bảng trên để lấy đúng property_id.\n"
    )


def extract_pending_from_output(
    output: str, property_list: list, property_details: list
) -> dict:
    times = _ISO_TIME_RE.findall(output)
    proposed_time = times[0] if times else None

    property_id = None
    property_title = ""
    can_matches = _CAN_SO_RE.findall(output)
    if can_matches:
        idx = int(can_matches[0]) - 1
        if 0 <= idx < len(property_list):
            property_id = property_list[idx]
            if idx < len(property_details):
                property_title = property_details[idx].get("title", "")
    elif len(property_list) == 1:
        property_id = property_list[0]
        property_title = property_details[0].get("title", "") if property_details else ""

    return {
        "property_id": property_id,
        "proposed_time": proposed_time,
        "property_title": property_title,
    }


def extract_tool_chain(messages: list) -> list[str]:
    chain = []
    for msg in messages:
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                if name:
                    chain.append(name)
    return chain


def extract_final_output(messages: list) -> str:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            content = msg.content
            return content if isinstance(content, str) else str(content)
    return ""
