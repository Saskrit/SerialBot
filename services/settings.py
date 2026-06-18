from config import FREE_DAILY_LIMIT as DEFAULT_FREE_DAILY_LIMIT
from database.connection import get_db

SETTINGS_ID = "bot_settings"


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
