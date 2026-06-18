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

STORAGE_CHANNEL_ID = os.getenv("STORAGE_CHANNEL_ID")


def _normalize_channel_id(value: str | None) -> int | None:
    if not value or not value.strip():
        return None
    raw = value.strip()
    if raw.startswith("-100"):
        return int(raw)
    if raw.startswith("100") and len(raw) > 3:
        return int("-100" + raw[3:])
    return int(raw)


if STORAGE_CHANNEL_ID:
    STORAGE_CHANNEL_ID = _normalize_channel_id(STORAGE_CHANNEL_ID)

UPI_ID = os.getenv("UPI_ID", "serialhub@upi")
PAYMENT_NAME = os.getenv("PAYMENT_NAME", "Serial Hub")

FREE_DAILY_LIMIT = 3
EPISODE_UNLOCK_PRICE = 10
VIP_MONTHLY_PRICE = 99
EPISODES_PER_PAGE = 5
MIN_ARCHIVE_EPISODES = 20

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
            + ". Set them in Render Dashboard → Environment."
        )
    if not ADMIN_IDS:
        import logging

        logging.getLogger(__name__).warning(
            "ADMIN_IDS is not set. Admin panel and payment review will not work."
        )
