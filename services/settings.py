from config import FREE_DAILY_LIMIT as DEFAULT_FREE_DAILY_LIMIT
from database.connection import get_db
from services.trial_duration import format_trial_ttl, parse_trial_duration

SETTINGS_ID = "bot_settings"
DEFAULT_TRIAL_EPISODE_TTL_SECONDS = 0


def is_free_unlimited(limit: int) -> bool:
    return limit <= 0


def format_free_limit_label(limit: int) -> str:
    if is_free_unlimited(limit):
        return "Free for all (unlimited)"
    if limit == 1:
        return "1 episode per day"
    return f"{limit} episodes per day"


async def get_free_daily_limit() -> int:
    doc = await get_db().settings.find_one({"_id": SETTINGS_ID})
    if doc is not None and "free_daily_limit" in doc:
        return int(doc["free_daily_limit"])
    return DEFAULT_FREE_DAILY_LIMIT


async def set_free_daily_limit(limit: int) -> int:
    if limit < 0:
        limit = 0
    await get_db().settings.update_one(
        {"_id": SETTINGS_ID},
        {"$set": {"free_daily_limit": limit}},
        upsert=True,
    )
    return limit


async def get_trial_episode_ttl_seconds() -> int:
    doc = await get_db().settings.find_one({"_id": SETTINGS_ID})
    if doc is not None and "trial_episode_ttl_seconds" in doc:
        return max(0, int(doc["trial_episode_ttl_seconds"]))
    return DEFAULT_TRIAL_EPISODE_TTL_SECONDS


async def set_trial_episode_ttl_seconds(seconds: int) -> int:
    seconds = max(0, int(seconds))
    await get_db().settings.update_one(
        {"_id": SETTINGS_ID},
        {"$set": {"trial_episode_ttl_seconds": seconds}},
        upsert=True,
    )
    return seconds


def format_trial_ttl_label(seconds: int) -> str:
    if seconds <= 0:
        return "Off (episodes stay in chat)"
    return format_trial_ttl(seconds)


def parse_trial_ttl_setting(text: str) -> int | None:
    return parse_trial_duration(text)
