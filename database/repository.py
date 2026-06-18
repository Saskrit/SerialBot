from datetime import date, datetime, timedelta
from typing import Any

from bson import ObjectId

from config import FREE_DAILY_LIMIT, TZ
from database.connection import get_db


def _today() -> date:
    return datetime.now(TZ).date()


async def get_or_create_user(
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> dict[str, Any]:
    db = get_db()
    now = datetime.now(TZ)
    user = await db.users.find_one({"telegram_id": telegram_id})

    if user:
        await db.users.update_one(
            {"telegram_id": telegram_id},
            {
                "$set": {
                    "username": username,
                    "first_name": first_name,
                    "last_active": now,
                }
            },
        )
        user["username"] = username
        user["first_name"] = first_name
        user["last_active"] = now
        return await _normalize_daily_usage(user)

    doc = {
        "telegram_id": telegram_id,
        "username": username,
        "first_name": first_name,
        "plan": "free",
        "vip_expires": None,
        "daily_watches": 0,
        "daily_reset_date": _today().isoformat(),
        "unlocked_episodes": [],
        "banned": False,
        "registered_at": now,
        "last_active": now,
    }
    await db.users.insert_one(doc)
    return doc


async def _normalize_daily_usage(user: dict[str, Any]) -> dict[str, Any]:
    today = _today().isoformat()
    if user.get("daily_reset_date") != today:
        db = get_db()
        await db.users.update_one(
            {"telegram_id": user["telegram_id"]},
            {"$set": {"daily_watches": 0, "daily_reset_date": today}},
        )
        user["daily_watches"] = 0
        user["daily_reset_date"] = today
    return await _check_vip_expiry(user)


async def _check_vip_expiry(user: dict[str, Any]) -> dict[str, Any]:
    if user.get("plan") != "vip":
        return user

    expires = user.get("vip_expires")
    if expires and expires < datetime.now(TZ):
        db = get_db()
        await db.users.update_one(
            {"telegram_id": user["telegram_id"]},
            {"$set": {"plan": "free", "vip_expires": None}},
        )
        user["plan"] = "free"
        user["vip_expires"] = None
    return user


async def get_user(telegram_id: int) -> dict[str, Any] | None:
    user = await get_db().users.find_one({"telegram_id": telegram_id})
    if user:
        return await _normalize_daily_usage(user)
    return None


async def is_banned(telegram_id: int) -> bool:
    user = await get_db().users.find_one({"telegram_id": telegram_id}, {"banned": 1})
    return bool(user and user.get("banned"))


async def record_watch(telegram_id: int, episode_id: str) -> None:
    await get_db().users.update_one(
        {"telegram_id": telegram_id},
        {
            "$inc": {"daily_watches": 1},
            "$push": {
                "watch_history": {
                    "$each": [
                        {
                            "episode_id": episode_id,
                            "watched_at": datetime.now(TZ),
                        }
                    ],
                    "$slice": -100,
                }
            },
        },
    )


async def grant_vip(telegram_id: int, days: int = 30) -> datetime:
    now = datetime.now(TZ)
    user = await get_user(telegram_id)
    base = now
    if user and user.get("vip_expires") and user["vip_expires"] > now:
        base = user["vip_expires"]
    expires = base + timedelta(days=days)
    await get_db().users.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"plan": "vip", "vip_expires": expires}},
    )
    return expires


async def grant_episode_unlock(telegram_id: int, episode_id: str) -> None:
    await get_db().users.update_one(
        {"telegram_id": telegram_id},
        {"$addToSet": {"unlocked_episodes": episode_id}},
    )


async def has_episode_unlock(user: dict[str, Any], episode_id: str) -> bool:
    return episode_id in user.get("unlocked_episodes", [])


async def can_watch_episode(user: dict[str, Any], episode_id: str) -> tuple[bool, str]:
    if user.get("banned"):
        return False, "Your account has been suspended. Contact support."

    if user.get("plan") == "vip":
        return True, ""

    if await has_episode_unlock(user, episode_id):
        return True, ""

    if user.get("daily_watches", 0) >= FREE_DAILY_LIMIT:
        return False, "daily_limit"

    return True, ""


async def get_user_stats() -> dict[str, int]:
    db = get_db()
    total = await db.users.count_documents({})
    vip = await db.users.count_documents({"plan": "vip"})
    banned = await db.users.count_documents({"banned": True})
    today_start = datetime.combine(_today(), datetime.min.time()).replace(tzinfo=TZ)
    active_today = await db.users.count_documents({"last_active": {"$gte": today_start}})
    return {
        "total": total,
        "vip": vip,
        "banned": banned,
        "active_today": active_today,
    }


async def set_banned(telegram_id: int, banned: bool) -> bool:
    result = await get_db().users.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"banned": banned}},
    )
    return result.matched_count > 0


async def delete_user(telegram_id: int) -> bool:
    result = await get_db().users.delete_one({"telegram_id": telegram_id})
    return result.deleted_count > 0


async def get_all_user_ids() -> list[int]:
    cursor = get_db().users.find({"banned": {"$ne": True}}, {"telegram_id": 1})
    return [doc["telegram_id"] async for doc in cursor]


async def list_users(page: int, per_page: int = 15) -> tuple[list[dict[str, Any]], int]:
    db = get_db()
    total = await db.users.count_documents({})
    cursor = (
        db.users.find(
            {},
            {
                "telegram_id": 1,
                "first_name": 1,
                "username": 1,
                "plan": 1,
                "banned": 1,
                "daily_watches": 1,
                "registered_at": 1,
            },
        )
        .sort("registered_at", -1)
        .skip(page * per_page)
        .limit(per_page)
    )
    users = await cursor.to_list(length=per_page)
    return users, total


async def get_episodes(serial_slug: str, page: int, per_page: int) -> tuple[list[dict], int]:
    db = get_db()
    total = await db.episodes.count_documents({"serial_slug": serial_slug})
    cursor = (
        db.episodes.find({"serial_slug": serial_slug})
        .sort("date", -1)
        .skip(page * per_page)
        .limit(per_page)
    )
    episodes = await cursor.to_list(length=per_page)
    return episodes, total


async def get_episode(episode_id: str) -> dict[str, Any] | None:
    if not ObjectId.is_valid(episode_id):
        return None
    return await get_db().episodes.find_one({"_id": ObjectId(episode_id)})


async def create_payment(
    user_id: int,
    payment_type: str,
    amount: int,
    episode_id: str | None = None,
) -> str:
    doc = {
        "user_id": user_id,
        "type": payment_type,
        "episode_id": episode_id,
        "amount": amount,
        "status": "pending",
        "screenshot_file_id": None,
        "created_at": datetime.now(TZ),
        "reviewed_at": None,
        "reviewed_by": None,
    }
    result = await get_db().payments.insert_one(doc)
    return str(result.inserted_id)


async def get_payment(payment_id: str) -> dict[str, Any] | None:
    if not ObjectId.is_valid(payment_id):
        return None
    return await get_db().payments.find_one({"_id": ObjectId(payment_id)})


async def attach_payment_screenshot(payment_id: str, file_id: str) -> bool:
    if not ObjectId.is_valid(payment_id):
        return False
    result = await get_db().payments.update_one(
        {"_id": ObjectId(payment_id), "status": "pending"},
        {"$set": {"screenshot_file_id": file_id}},
    )
    return result.modified_count > 0


async def review_payment(
    payment_id: str,
    approved: bool,
    admin_id: int,
) -> dict[str, Any] | None:
    if not ObjectId.is_valid(payment_id):
        return None
    status = "approved" if approved else "rejected"
    payment = await get_payment(payment_id)
    if not payment or payment["status"] != "pending":
        return None

    await get_db().payments.update_one(
        {"_id": ObjectId(payment_id)},
        {
            "$set": {
                "status": status,
                "reviewed_at": datetime.now(TZ),
                "reviewed_by": admin_id,
            }
        },
    )
    payment["status"] = status
    return payment


async def get_pending_payments(limit: int = 10) -> list[dict[str, Any]]:
    cursor = (
        get_db()
        .payments.find({"status": "pending", "screenshot_file_id": {"$ne": None}})
        .sort("created_at", 1)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def create_episode_request(user_id: int, serial_name: str, episode_date: str) -> str:
    doc = {
        "user_id": user_id,
        "serial_name": serial_name,
        "episode_date": episode_date,
        "status": "open",
        "created_at": datetime.now(TZ),
    }
    result = await get_db().episode_requests.insert_one(doc)
    return str(result.inserted_id)


async def create_support_ticket(user_id: int, category: str, message: str) -> str:
    doc = {
        "user_id": user_id,
        "category": category,
        "message": message,
        "status": "open",
        "created_at": datetime.now(TZ),
        "admin_reply": None,
    }
    result = await get_db().support_tickets.insert_one(doc)
    return str(result.inserted_id)


async def add_episode(
    serial_slug: str,
    serial_name: str,
    episode_date: datetime,
    file_id: str,
    file_unique_id: str,
    message_id: int | None = None,
) -> str:
    doc = {
        "serial_slug": serial_slug,
        "serial_name": serial_name,
        "date": episode_date,
        "file_id": file_id,
        "file_unique_id": file_unique_id,
        "message_id": message_id,
        "uploaded_at": datetime.now(TZ),
    }
    result = await get_db().episodes.insert_one(doc)
    return str(result.inserted_id)


async def get_serial_by_slug(slug: str) -> dict[str, Any] | None:
    return await get_db().serials.find_one({"slug": slug})


async def list_serials() -> list[dict[str, Any]]:
    cursor = get_db().serials.find({"active": True}).sort("name", 1)
    return await cursor.to_list(length=200)
