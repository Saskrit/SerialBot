import re
from dataclasses import dataclass
from datetime import datetime

from config import TZ
from services.upload_parser import MONTH_NAMES, MONTHS, parse_episode_date

MONTH_DAY_PATTERNS = [
    re.compile(rf"^(\d{{1,2}})\s+({MONTH_NAMES})$", re.IGNORECASE),
    re.compile(r"^(\d{1,2})[.\-/](\d{1,2})$"),
    re.compile(rf"^({MONTH_NAMES})\s+(\d{{1,2}})$", re.IGNORECASE),
]


@dataclass(frozen=True)
class UserDateQuery:
    day: int
    month: int
    year: int | None = None


def format_user_date_label(query: UserDateQuery) -> str:
    if query.year:
        return datetime(query.year, query.month, query.day, tzinfo=TZ).strftime("%d %B %Y")
    return datetime(2000, query.month, query.day).strftime("%d %B")


def encode_date_query(query: UserDateQuery) -> str:
    if query.year:
        return f"y{query.year:04d}{query.month:02d}{query.day:02d}"
    return f"m{query.month:02d}{query.day:02d}"


def decode_date_query(key: str) -> UserDateQuery:
    if key.startswith("y") and len(key) == 9:
        return UserDateQuery(
            year=int(key[1:5]),
            month=int(key[5:7]),
            day=int(key[7:9]),
        )
    if key.startswith("m") and len(key) == 5:
        return UserDateQuery(
            month=int(key[1:3]),
            day=int(key[3:5]),
        )
    raise ValueError(f"Invalid date key: {key}")


def parse_user_date_query(text: str) -> UserDateQuery | None:
    text = text.strip()
    if not text:
        return None

    full_date = parse_episode_date(text)
    if full_date:
        return UserDateQuery(day=full_date.day, month=full_date.month, year=full_date.year)

    match = MONTH_DAY_PATTERNS[0].match(text)
    if match:
        day = int(match.group(1))
        month = MONTHS.get(match.group(2).lower())
        if month and 1 <= day <= 31:
            return UserDateQuery(day=day, month=month)

    match = MONTH_DAY_PATTERNS[1].match(text)
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        if 1 <= day <= 31 and 1 <= month <= 12:
            return UserDateQuery(day=day, month=month)

    match = MONTH_DAY_PATTERNS[2].match(text)
    if match:
        month = MONTHS.get(match.group(1).lower())
        day = int(match.group(2))
        if month and 1 <= day <= 31:
            return UserDateQuery(day=day, month=month)

    return None
