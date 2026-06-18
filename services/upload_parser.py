import re
from datetime import datetime

from config import TZ
from database.connection import get_db
from services.serial_matcher import match_serial, match_serial_best_from_text

MONTH_NAMES = (
    "january|february|march|april|may|june|july|august|september|october|november|december"
    "|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec"
)

DATE_PATTERNS = [
    re.compile(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})"),
    re.compile(rf"(\d{{1,2}})\s+({MONTH_NAMES})\s+(\d{{4}})", re.IGNORECASE),
]

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_episode_date(text: str) -> datetime | None:
    text = text.strip()
    if not text:
        return None

    m = DATE_PATTERNS[0].search(text)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime(year, month, day, tzinfo=TZ)
        except ValueError:
            return None

    m = DATE_PATTERNS[1].search(text)
    if m:
        day = int(m.group(1))
        month_name = m.group(2).lower()
        year = int(m.group(3))
        month = MONTHS.get(month_name)
        if month:
            try:
                return datetime(year, month, day, tzinfo=TZ)
            except ValueError:
                return None
    return None


def _extract_date(caption: str) -> tuple[str, str] | None:
    """Find the date in caption and return (serial_part, date_str)."""
    best_match = None
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(caption):
            date_str = match.group(0).strip()
            if parse_episode_date(date_str) is None:
                continue
            if best_match is None or match.start() > best_match.start():
                best_match = match

    if not best_match:
        return None

    date_str = best_match.group(0).strip()
    serial_part = caption[: best_match.start()].strip().strip("-–:|")
    serial_part = serial_part.strip()
    if not serial_part:
        serial_part = caption[best_match.end() :].strip().strip("-–:|")
    return serial_part, date_str


def _split_serial_and_date(caption: str) -> tuple[str, str] | None:
    caption = caption.strip()
    if not caption:
        return None

    if "|" in caption:
        left, right = caption.rsplit("|", 1)
        left, right = left.strip(), right.strip()
        if left and right and parse_episode_date(right):
            return left, right

    if "\n" in caption:
        left, right = caption.rsplit("\n", 1)
        left, right = left.strip(), right.strip()
        if left and right and parse_episode_date(right):
            return left, right

    return _extract_date(caption)


async def _resolve_serial(serial_query: str) -> dict | None:
    query = serial_query.strip()
    if not query:
        return None

    slug = query.lower().replace(" ", "-")
    serial = await get_db().serials.find_one({"slug": slug, "active": True})
    if serial:
        return serial

    if "|" in query or "\n" in query:
        serial = await match_serial_best_from_text(query)
        if serial:
            return serial

    return await match_serial(query)


async def parse_upload_caption(caption: str) -> tuple[dict | None, datetime | None, str]:
    if not caption or not caption.strip():
        return None, None, "Caption is empty. Use: Laughter Chef 3 | 17 June 2026"

    parts = _split_serial_and_date(caption)
    if not parts:
        return (
            None,
            None,
            "Could not parse caption. Use:\n"
            "<code>Laughter Chef 3 | 17 June 2026</code>\n"
            "or\n"
            "<code>laughter-chef-3 | 17-06-2026</code>",
        )

    serial_query, date_str = parts
    serial = await _resolve_serial(serial_query)
    if not serial:
        return (
            None,
            None,
            f"Unknown serial: <b>{serial_query}</b>\n\n"
            "Create it first with:\n"
            f"<code>/addserial {serial_query}</code>",
        )

    episode_date = parse_episode_date(date_str)
    if not episode_date:
        return (
            None,
            None,
            f"Could not parse date: <b>{date_str}</b>\n"
            "Use formats like <code>17 June 2026</code> or <code>17-06-2026</code>",
        )

    return serial, episode_date, ""
