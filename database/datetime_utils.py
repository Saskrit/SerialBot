from datetime import datetime

from config import TZ


def ensure_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ)


def normalize_user_datetimes(user: dict) -> dict:
    for field in ("vip_expires", "registered_at", "last_active"):
        if user.get(field):
            user[field] = ensure_aware(user[field])
    return user
