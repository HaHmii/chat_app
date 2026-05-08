from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))


def vn_now() -> datetime:
    """Naive datetime in Vietnam timezone (UTC+7) for DB storage."""
    return datetime.now(VN_TZ).replace(tzinfo=None)
