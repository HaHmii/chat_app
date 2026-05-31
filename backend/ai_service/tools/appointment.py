import logging
from typing import ClassVar, Optional, Type

import httpx
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from core.config import settings

logger = logging.getLogger(__name__)


class AppointmentInput(BaseModel):
    action: str  # "book" | "list" | "cancel"
    property_id: Optional[int] = None
    proposed_time: Optional[str] = None  # ISO datetime
    note: Optional[str] = None
    appointment_id: Optional[int] = None
    user_token: Optional[str] = None


class AppointmentTool(BaseTool):
    name: str = "appointment"
    description: str = (
        "Đặt lịch, xem lịch hoặc hủy lịch xem nhà. "
        "Dùng khi người dùng muốn hẹn xem nhà hoặc hỏi về lịch đã đặt."
    )
    args_schema: ClassVar[Type[BaseModel]] = AppointmentInput

    def _run(
        self,
        action: str,
        property_id: Optional[int] = None,
        proposed_time: Optional[str] = None,
        note: Optional[str] = None,
        appointment_id: Optional[int] = None,
        user_token: Optional[str] = None,
    ) -> str:
        try:
            if action in {"book", "list", "cancel"} and not user_token:
                return (
                    "Bạn cần đăng nhập tài khoản khách trước khi đặt hoặc xem lịch hẹn. "
                    "Tôi chưa lấy được phiên đăng nhập của bạn từ Rocket.Chat."
                )

            headers = {"Authorization": f"Bearer {user_token}"} if user_token else {}

            if action == "book":
                missing = []
                if not property_id:
                    missing.append("property_id (mã căn nhà)")
                if not proposed_time:
                    missing.append("proposed_time (thời gian muốn xem)")
                if missing:
                    return f"Cần cung cấp thêm: {', '.join(missing)}"

                body = {"property_id": property_id, "proposed_time": proposed_time}
                if note:
                    body["note"] = note

                resp = httpx.post(
                    f"{settings.web_service_url}/appointments/",
                    json=body,
                    headers=headers,
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json()
                appointment = data.get("data", data) if isinstance(data, dict) else {}
                return (
                    "Đặt lịch thành công!\n"
                    f"Mã lịch hẹn: #{appointment.get('id')}\n"
                    f"Thời gian: {appointment.get('proposed_time', proposed_time)}\n"
                    f"Trạng thái: {appointment.get('status', 'pending')}"
                )

            if action == "list":
                resp = httpx.get(
                    f"{settings.web_service_url}/appointments/my-appointments",
                    headers=headers,
                    timeout=10.0,
                )
                resp.raise_for_status()
                items = resp.json()
                if isinstance(items, dict):
                    items = items.get("items") or items.get("results") or []
                if not items:
                    return "Bạn chưa có lịch hẹn nào."

                lines = [f"Danh sách lịch hẹn ({len(items)} lịch):\n"]
                for apt in items:
                    lines.append(
                        f"- #{apt.get('id')} - {apt.get('proposed_time', 'N/A')} "
                        f"| Trạng thái: {apt.get('status', 'N/A')}"
                    )
                return "\n".join(lines)

            if action == "cancel":
                if not appointment_id:
                    return "Cần cung cấp thêm: appointment_id (mã lịch hẹn cần hủy)"
                resp = httpx.patch(
                    f"{settings.web_service_url}/appointments/{appointment_id}/cancel",
                    json={
                        "cancelled_by": "user",
                        "cancel_reason": note or "Người dùng yêu cầu hủy lịch",
                    },
                    headers=headers,
                    timeout=10.0,
                )
                resp.raise_for_status()
                return f"Đã hủy lịch hẹn #{appointment_id} thành công."

            return f"Hành động không hợp lệ: {action!r}. Chỉ hỗ trợ: book, list, cancel."

        except httpx.TimeoutException:
            return "Lỗi: Không kết nối được hệ thống. Vui lòng thử lại."
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code == 401:
                return (
                    "Không thể xác thực phiên đăng nhập để đặt lịch. "
                    "Vui lòng đăng nhập lại rồi thử đặt lịch lần nữa."
                )
            logger.error("AppointmentTool HTTP error: %s %s", status_code, e.response.text[:200])
            return f"Lỗi khi xử lý lịch hẹn: HTTP {status_code}"
        except Exception as e:
            logger.error("AppointmentTool error: %s", e)
            return f"Lỗi khi xử lý lịch hẹn: {str(e)}"

    async def _arun(
        self,
        action: str,
        property_id: Optional[int] = None,
        proposed_time: Optional[str] = None,
        note: Optional[str] = None,
        appointment_id: Optional[int] = None,
        user_token: Optional[str] = None,
    ) -> str:
        return self._run(
            action=action,
            property_id=property_id,
            proposed_time=proposed_time,
            note=note,
            appointment_id=appointment_id,
            user_token=user_token,
        )
