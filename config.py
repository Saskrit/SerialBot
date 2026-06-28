import os
from datetime import timezone
from pathlib import Path

from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

BOT_TOKEN = os.getenv("BOT_TOKEN")

MONGODB_URI = os.getenv("MONGODB_URI", "")
MONGODB_DB = os.getenv("MONGODB_DB", "serialhub")

TELEGRAM_PROXY = os.getenv("TELEGRAM_PROXY")
PORT = int(os.getenv("PORT", "10000"))
RESTART_DELAY_SEC = 10

_admin_ids = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: set[int] = {
    int(x.strip()) for x in _admin_ids.split(",") if x.strip().isdigit()
}

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")
ADMIN_SESSION_SECRET = os.getenv("ADMIN_SESSION_SECRET") or ADMIN_SECRET or "change-me"

STORAGE_CHANNEL_ID = os.getenv("STORAGE_CHANNEL_ID")
STORAGE_CHANNEL_IDS_RAW = os.getenv("STORAGE_CHANNEL_IDS", "")


def _normalize_channel_id(value: str | None) -> int | None:
    if not value or not value.strip():
        return None
    raw = value.strip()
    if raw.startswith("-100"):
        return int(raw)
    if raw.startswith("100") and len(raw) > 3:
        return int("-100" + raw[3:])
    return int(raw)


def _load_storage_channel_ids() -> frozenset[int]:
    ids: set[int] = set()
    sources = [STORAGE_CHANNEL_IDS_RAW, STORAGE_CHANNEL_ID or ""]
    for source in sources:
        for part in source.replace(";", ",").split(","):
            part = part.strip()
            if not part:
                continue
            normalized = _normalize_channel_id(part)
            if normalized is not None:
                ids.add(normalized)
    return frozenset(ids)


STORAGE_CHANNEL_IDS: frozenset[int] = _load_storage_channel_ids()
STORAGE_CHANNEL_ID = next(iter(STORAGE_CHANNEL_IDS), None)


def is_storage_channel(chat_id: int) -> bool:
    return chat_id in STORAGE_CHANNEL_IDS

PAYMENT_CONTACT_USERNAME = os.getenv("PAYMENT_CONTACT_USERNAME", "godthough")

FREE_DAILY_LIMIT = 3
REFERRAL_BONUS_WATCHES = 5
EPISODE_UNLOCK_PRICE = 10
DAILY_PASS_PRICE = 19
WEEKLY_VIP_PRICE = 39
VIP_MONTHLY_PRICE = 99
QUARTERLY_VIP_PRICE = 249
ANNUAL_VIP_PRICE = 799
EPISODES_PER_PAGE = 9
SERIALS_PER_PAGE = 10
MIN_ARCHIVE_EPISODES = 20

NOTIFY_ON_NEW_EPISODE = os.getenv("NOTIFY_ON_NEW_EPISODE", "true").lower() in (
    "1",
    "true",
    "yes",
)

NOTIFY_PROMO_INTERVAL_HOURS = int(os.getenv("NOTIFY_PROMO_INTERVAL_HOURS", "3"))
NOTIFY_MEMBERSHIP_DAYS = 30

TZ = timezone.utc


def validate_config() -> None:
    missing: list[str] = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not MONGODB_URI:
        missing.append("MONGODB_URI")
    if missing:
        raise SystemExit(
            "Missing required environment variables: "
            + ", ".join(missing)
            + ". Set them in Railway → Service → Variables."
        )
    if not ADMIN_IDS:
        import logging

        logging.getLogger(__name__).warning(
            "ADMIN_IDS is not set. Admin panel will not work."
        )
    if not ADMIN_SECRET:
        import logging

        logging.getLogger(__name__).warning(
            "ADMIN_SECRET is not set. Web admin panel at /admin will be disabled."
        )
