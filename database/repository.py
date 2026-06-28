from datetime import date, datetime, timedelta
from typing import Any

from bson import ObjectId

from pymongo import ReturnDocument

from config import TZ
from services.settings import get_free_daily_limit, is_free_unlimited
from database.connection import get_db
from database.datetime_utils import ensure_aware, normalize_user_datetimes


def _today() -> date:
    return datetime.now(TZ).date()


async def get_or_create_user(
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> tuple[dict[str, Any], bool]:
    db = get_db()
    now = datetime.now(TZ)
    user = await db.users.find_one({"telegram_id": telegram_id})

    if user:
        fields: dict[str, Any] = {"last_active": now}
        if username is not None:
            fields["username"] = username
        if first_name is not None:
            fields["first_name"] = first_name
        await db.users.update_one(
            {"telegram_id": telegram_id},
            {"$set": fields},
        )
        if username is not None:
            user["username"] = username
        if first_name is not None:
            user["first_name"] = first_name
        user["last_active"] = now
        return normalize_user_datetimes(await _normalize_daily_usage(user)), False

    doc = {
        "telegram_id": telegram_id,
        "username": username,
        "first_name": first_name,
        "plan": "free",
        "vip_expires": None,
        "membership_tier": None,
        "daily_pass_expires": None,
        "daily_watches": 0,
        "daily_reset_date": _today().isoformat(),
        "referral_watch_credits": 0,
        "referral_count": 0,
        "referred_by": None,
        "referred_at": None,
        "notify_plan": None,
        "notify_expires": None,
        "notify_serials": [],
        "last_notify_promo_at": None,
        "admin_command_attempts": 0,
        "unlocked_episodes": [],
        "trial_episodes": [],
        "banned": False,
        "registered_at": now,
        "last_active": now,
    }
    await db.users.insert_one(doc)
    return normalize_user_datetimes(doc), True


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


def has_active_daily_pass(user: dict[str, Any]) -> bool:
    expires = ensure_aware(user.get("daily_pass_expires"))
    if not expires:
        return False
    return expires > datetime.now(TZ)


def has_unlimited_watching(user: dict[str, Any]) -> bool:
    if user.get("plan") == "vip":
        return True
    return has_active_daily_pass(user)


async def _check_vip_expiry(user: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(TZ)
    updates: dict[str, Any] = {}

    if user.get("plan") == "vip":
        expires = ensure_aware(user.get("vip_expires"))
        if expires and expires < now:
            updates["plan"] = "free"
            updates["vip_expires"] = None
            updates["membership_tier"] = None
            user["plan"] = "free"
            user["vip_expires"] = None
            user["membership_tier"] = None

    daily_expires = ensure_aware(user.get("daily_pass_expires"))
    if daily_expires and daily_expires < now:
        updates["daily_pass_expires"] = None
        user["daily_pass_expires"] = None

    notify_expires = ensure_aware(user.get("notify_expires"))
    if user.get("notify_plan") and notify_expires and notify_expires < now:
        updates["notify_plan"] = None
        updates["notify_expires"] = None
        user["notify_plan"] = None
        user["notify_expires"] = None

    if updates:
        await get_db().users.update_one(
            {"telegram_id": user["telegram_id"]},
            {"$set": updates},
        )
    return user


async def get_user(telegram_id: int) -> dict[str, Any] | None:
    user = await get_db().users.find_one({"telegram_id": telegram_id})
    if user:
        return normalize_user_datetimes(await _normalize_daily_usage(user))
    return None


async def is_banned(telegram_id: int) -> bool:
    user = await get_db().users.find_one({"telegram_id": telegram_id}, {"banned": 1})
    return bool(user and user.get("banned"))


async def record_watch(telegram_id: int, episode_id: str) -> None:
    await record_episode_view(telegram_id, episode_id, counts_toward_daily_limit=True)


async def record_episode_view(
    telegram_id: int,
    episode_id: str,
    *,
    counts_toward_daily_limit: bool = False,
) -> str | None:
    db = get_db()
    now = datetime.now(TZ)
    update: dict[str, Any] = {
        "$push": {
            "watch_history": {
                "$each": [
                    {
                        "episode_id": episode_id,
                        "watched_at": now,
                    }
                ],
                "$slice": -100,
            }
        },
    }
    consumption: str | None = None
    if counts_toward_daily_limit:
        user = await db.users.find_one({"telegram_id": telegram_id})
        if user:
            limit = await get_free_daily_limit()
            daily_used = user.get("daily_watches", 0)
            bonus = user.get("referral_watch_credits", 0)
            if is_free_unlimited(limit) or daily_used < limit:
                update["$inc"] = {"daily_watches": 1}
                consumption = "daily"
            elif bonus > 0:
                update["$inc"] = {"referral_watch_credits": -1}
                consumption = "bonus"

    await db.users.update_one({"telegram_id": telegram_id}, update)

    if ObjectId.is_valid(episode_id):
        await db.episodes.update_one(
            {"_id": ObjectId(episode_id)},
            {"$inc": {"view_count": 1}},
        )
    return consumption


async def get_total_episode_views() -> int:
    db = get_db()
    pipeline = [
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$view_count", 0]}}}}
    ]
    docs = await db.episodes.aggregate(pipeline).to_list(length=1)
    return int(docs[0]["total"]) if docs else 0


async def get_top_viewed_episodes(
    limit: int = 10, serial_slug: str | None = None
) -> list[dict[str, Any]]:
    db = get_db()
    query: dict[str, Any] = {}
    if serial_slug:
        query["serial_slug"] = serial_slug
    cursor = (
        db.episodes.find(query)
        .sort([("view_count", -1), ("date", -1), ("_id", -1)])
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def get_all_episodes_for_serial(serial_slug: str) -> list[dict[str, Any]]:
    cursor = (
        get_db()
        .episodes.find({"serial_slug": serial_slug})
        .sort([("date", -1), ("_id", -1)])
    )
    return await cursor.to_list(length=5000)


async def get_serial_episode_view_total(serial_slug: str) -> int:
    db = get_db()
    pipeline = [
        {"$match": {"serial_slug": serial_slug}},
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$view_count", 0]}}}},
    ]
    docs = await db.episodes.aggregate(pipeline).to_list(length=1)
    return int(docs[0]["total"]) if docs else 0


async def get_episode_watchers(
    episode_id: str, limit: int = 25
) -> list[dict[str, Any]]:
    db = get_db()
    cursor = db.users.find(
        {"watch_history.episode_id": episode_id},
        {"telegram_id": 1, "first_name": 1, "username": 1, "watch_history": 1},
    )
    watchers: list[dict[str, Any]] = []
    async for user in cursor:
        matches = [
            entry
            for entry in user.get("watch_history", [])
            if entry.get("episode_id") == episode_id
        ]
        if not matches:
            continue
        latest = max(
            matches,
            key=lambda entry: ensure_aware(entry.get("watched_at"))
            or datetime.min.replace(tzinfo=TZ),
        )
        watchers.append(
            {
                "telegram_id": user["telegram_id"],
                "first_name": user.get("first_name"),
                "username": user.get("username"),
                "watched_at": latest.get("watched_at"),
                "watch_count": len(matches),
            }
        )

    watchers.sort(
        key=lambda entry: ensure_aware(entry.get("watched_at"))
        or datetime.min.replace(tzinfo=TZ),
        reverse=True,
    )
    return watchers[:limit]


async def grant_vip(
    telegram_id: int, days: int = 30, *, tier: str | None = None
) -> datetime:
    now = datetime.now(TZ)
    db = get_db()
    user = await db.users.find_one({"telegram_id": telegram_id})
    base = now
    if user:
        user = normalize_user_datetimes(await _normalize_daily_usage(user))
        current_expires = ensure_aware(user.get("vip_expires"))
        if current_expires and current_expires > now:
            base = current_expires
    expires = base + timedelta(days=days)
    update_fields: dict[str, Any] = {
        "plan": "vip",
        "vip_expires": expires,
        "last_active": now,
    }
    if tier:
        update_fields["membership_tier"] = tier
    await db.users.update_one(
        {"telegram_id": telegram_id},
        {
            "$set": update_fields,
            "$setOnInsert": {
                "telegram_id": telegram_id,
                "username": None,
                "first_name": None,
                "daily_watches": 0,
                "daily_reset_date": _today().isoformat(),
                "unlocked_episodes": [],
                "daily_pass_expires": None,
                "membership_tier": tier,
                "banned": False,
                "registered_at": now,
            },
        },
        upsert=True,
    )
    return expires


async def revoke_vip(telegram_id: int) -> bool:
    db = get_db()
    result = await db.users.update_one(
        {"telegram_id": telegram_id, "plan": "vip"},
        {
            "$set": {
                "plan": "free",
                "vip_expires": None,
                "membership_tier": None,
                "last_active": datetime.now(TZ),
            }
        },
    )
    return result.modified_count > 0


async def grant_daily_pass(telegram_id: int, *, hours: int = 24) -> datetime:
    now = datetime.now(TZ)
    db = get_db()
    user = await db.users.find_one({"telegram_id": telegram_id})
    base = now
    if user:
        user = normalize_user_datetimes(await _normalize_daily_usage(user))
        current_expires = ensure_aware(user.get("daily_pass_expires"))
        if current_expires and current_expires > now:
            base = current_expires
    expires = base + timedelta(hours=hours)
    await db.users.update_one(
        {"telegram_id": telegram_id},
        {
            "$set": {"daily_pass_expires": expires, "last_active": now},
            "$setOnInsert": {
                "telegram_id": telegram_id,
                "username": None,
                "first_name": None,
                "plan": "free",
                "vip_expires": None,
                "membership_tier": None,
                "daily_watches": 0,
                "daily_reset_date": _today().isoformat(),
                "unlocked_episodes": [],
                "banned": False,
                "registered_at": now,
            },
        },
        upsert=True,
    )
    return expires


def has_active_notify_membership(user: dict[str, Any]) -> bool:
    from services.notify_membership import get_notify_plan

    plan_id = user.get("notify_plan")
    if not plan_id or not get_notify_plan(plan_id):
        return False
    expires = ensure_aware(user.get("notify_expires"))
    if not expires:
        return False
    return expires > datetime.now(TZ)


def notify_covers_serial(user: dict[str, Any], serial_slug: str) -> bool:
    from services.notify_membership import get_notify_plan

    if not has_active_notify_membership(user):
        return False
    plan = get_notify_plan(user.get("notify_plan"))
    if not plan:
        return False
    if plan.serial_limit is None:
        return True
    return serial_slug in (user.get("notify_serials") or [])


async def grant_notify_membership(
    telegram_id: int, plan_id: str, *, days: int = 30
) -> datetime:
    from services.notify_membership import get_notify_plan

    plan = get_notify_plan(plan_id)
    if not plan:
        raise ValueError(f"Unknown notify plan: {plan_id}")

    now = datetime.now(TZ)
    db = get_db()
    user = await db.users.find_one({"telegram_id": telegram_id})
    base = now
    if user:
        user = normalize_user_datetimes(await _normalize_daily_usage(user))
        current = ensure_aware(user.get("notify_expires"))
        if current and current > now and user.get("notify_plan") == plan_id:
            base = current
    expires = base + timedelta(days=days)
    update: dict[str, Any] = {
        "notify_plan": plan_id,
        "notify_expires": expires,
        "last_active": now,
    }
    if plan.serial_limit is None:
        update["notify_serials"] = []
    await db.users.update_one(
        {"telegram_id": telegram_id},
        {"$set": update},
        upsert=True,
    )
    return expires


async def revoke_notify_membership(telegram_id: int) -> bool:
    result = await get_db().users.update_one(
        {"telegram_id": telegram_id, "notify_plan": {"$ne": None}},
        {
            "$set": {
                "notify_plan": None,
                "notify_expires": None,
                "notify_serials": [],
                "last_active": datetime.now(TZ),
            }
        },
    )
    return result.modified_count > 0


async def set_notify_serials(telegram_id: int, slugs: list[str]) -> tuple[bool, str]:
    from services.notify_membership import get_notify_plan

    user = await get_user(telegram_id)
    if not user or not has_active_notify_membership(user):
        return False, "no_membership"
    plan = get_notify_plan(user.get("notify_plan"))
    if not plan or plan.serial_limit is None:
        return False, "all_serials"
    cleaned = list(dict.fromkeys(s.strip() for s in slugs if s and s.strip()))
    if len(cleaned) > plan.serial_limit:
        return False, "over_limit"
    active = await list_serials()
    valid_slugs = {s["slug"] for s in active}
    cleaned = [s for s in cleaned if s in valid_slugs]
    await get_db().users.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"notify_serials": cleaned}},
    )
    return True, "ok"


async def toggle_notify_serial(telegram_id: int, serial_slug: str) -> tuple[bool, str]:
    from services.notify_membership import get_notify_plan

    user = await get_user(telegram_id)
    if not user or not has_active_notify_membership(user):
        return False, "no_membership"
    plan = get_notify_plan(user.get("notify_plan"))
    if not plan or plan.serial_limit is None:
        return False, "all_serials"
    serial = await get_serial_by_slug(serial_slug)
    if not serial:
        return False, "invalid_serial"
    current = list(user.get("notify_serials") or [])
    if serial_slug in current:
        current.remove(serial_slug)
    else:
        if len(current) >= plan.serial_limit:
            return False, "limit_reached"
        current.append(serial_slug)
    await get_db().users.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"notify_serials": current}},
    )
    return True, "ok"


async def get_notify_subscribers_for_serial(serial_slug: str) -> list[int]:
    now = datetime.now(TZ)
    db = get_db()
    cursor = db.users.find(
        {
            "banned": {"$ne": True},
            "notify_plan": {"$in": ["notify_10", "notify_20", "notify_all"]},
            "notify_expires": {"$gt": now},
            "$or": [
                {"notify_plan": "notify_all"},
                {"notify_serials": serial_slug},
            ],
        },
        {"telegram_id": 1},
    )
    return [doc["telegram_id"] async for doc in cursor]


async def get_users_without_notify_membership() -> list[int]:
    now = datetime.now(TZ)
    cursor = get_db().users.find(
        {
            "banned": {"$ne": True},
            "$or": [
                {"notify_plan": None},
                {"notify_plan": {"$exists": False}},
                {"notify_expires": {"$lte": now}},
                {"notify_expires": None},
            ],
        },
        {"telegram_id": 1},
    )
    return [doc["telegram_id"] async for doc in cursor]


async def mark_notify_promo_sent(telegram_id: int) -> None:
    await get_db().users.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"last_notify_promo_at": datetime.now(TZ)}},
    )


async def count_notify_subscribers() -> int:
    now = datetime.now(TZ)
    return await get_db().users.count_documents(
        {
            "banned": {"$ne": True},
            "notify_plan": {"$in": ["notify_10", "notify_20", "notify_all"]},
            "notify_expires": {"$gt": now},
        }
    )


async def grant_episode_unlock(telegram_id: int, episode_id: str) -> None:
    await get_db().users.update_one(
        {"telegram_id": telegram_id},
        {"$addToSet": {"unlocked_episodes": episode_id}},
    )


async def has_free_watch_allowance(user: dict[str, Any]) -> bool:
    if has_unlimited_watching(user):
        return True
    limit = await get_free_daily_limit()
    if is_free_unlimited(limit):
        return True
    if user.get("daily_watches", 0) < limit:
        return True
    if user.get("referral_watch_credits", 0) > 0:
        return True
    return False


async def apply_referral(
    new_user_id: int, referrer_id: int, *, bonus_watches: int
) -> tuple[bool, str, int | None]:
    if new_user_id == referrer_id:
        return False, "self_referral", None

    db = get_db()
    referrer = await db.users.find_one({"telegram_id": referrer_id})
    if not referrer:
        return False, "referrer_not_found", None

    now = datetime.now(TZ)
    referred = await db.users.find_one_and_update(
        {
            "telegram_id": new_user_id,
            "$or": [{"referred_by": None}, {"referred_by": {"$exists": False}}],
        },
        {"$set": {"referred_by": referrer_id, "referred_at": now}},
        return_document=ReturnDocument.AFTER,
    )
    if not referred:
        return False, "already_referred", None

    await db.users.update_one(
        {"telegram_id": referrer_id},
        {
            "$inc": {
                "referral_watch_credits": bonus_watches,
                "referral_count": 1,
            }
        },
    )
    await db.users.update_one(
        {"telegram_id": new_user_id},
        {"$inc": {"referral_watch_credits": bonus_watches}},
    )
    updated_referrer = await db.users.find_one({"telegram_id": referrer_id})
    credits = updated_referrer.get("referral_watch_credits", 0) if updated_referrer else bonus_watches
    return True, "ok", credits


async def has_episode_unlock(user: dict[str, Any], episode_id: str) -> bool:
    return episode_id in user.get("unlocked_episodes", [])


async def can_watch_episode(user: dict[str, Any], episode_id: str) -> tuple[bool, str]:
    if user.get("banned"):
        return False, "Your account has been suspended. Contact support."

    if has_unlimited_watching(user):
        return True, ""

    if episode_id in user.get("unlocked_episodes", []):
        return True, ""

    if await has_used_trial_episode(user, episode_id):
        return False, "trial_used"

    limit = await get_free_daily_limit()
    if not is_free_unlimited(limit) and not await has_free_watch_allowance(user):
        return False, "daily_limit"

    return True, ""


async def has_used_trial_episode(user: dict[str, Any], episode_id: str) -> bool:
    from services.settings import get_trial_episode_ttl_seconds

    if user.get("plan") == "vip" or has_active_daily_pass(user):
        return False
    if episode_id in user.get("unlocked_episodes", []):
        return False
    if await get_trial_episode_ttl_seconds() <= 0:
        return False
    return episode_id in user.get("trial_episodes", [])


async def mark_trial_episode_used(telegram_id: int, episode_id: str) -> None:
    await get_db().users.update_one(
        {"telegram_id": telegram_id},
        {"$addToSet": {"trial_episodes": episode_id}},
    )


async def save_trial_deletion(
    telegram_id: int,
    episode_id: str,
    message_id: int,
    delete_at: datetime,
) -> None:
    await get_db().trial_deletions.update_one(
        {
            "telegram_id": telegram_id,
            "episode_id": episode_id,
            "message_id": message_id,
        },
        {
            "$set": {
                "telegram_id": telegram_id,
                "episode_id": episode_id,
                "message_id": message_id,
                "delete_at": delete_at,
            }
        },
        upsert=True,
    )


async def remove_trial_deletion(
    telegram_id: int, episode_id: str, message_id: int
) -> None:
    await get_db().trial_deletions.delete_one(
        {
            "telegram_id": telegram_id,
            "episode_id": episode_id,
            "message_id": message_id,
        }
    )


async def get_pending_trial_deletions() -> list[dict[str, Any]]:
    cursor = get_db().trial_deletions.find({}).sort("delete_at", 1)
    return await cursor.to_list(length=5000)


async def is_episode_daily_locked(user: dict[str, Any], episode_id: str) -> bool:
    if has_unlimited_watching(user):
        return False
    if episode_id in user.get("unlocked_episodes", []):
        return False
    limit = await get_free_daily_limit()
    if is_free_unlimited(limit):
        return False
    return not await has_free_watch_allowance(user)


async def is_episode_locked_for_user(user: dict[str, Any], episode_id: str) -> bool:
    if await has_used_trial_episode(user, episode_id):
        return True
    return await is_episode_daily_locked(user, episode_id)


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


async def increment_admin_command_attempts(telegram_id: int) -> int:
    doc = await get_db().users.find_one_and_update(
        {"telegram_id": telegram_id},
        {"$inc": {"admin_command_attempts": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        return 1
    return int(doc.get("admin_command_attempts", 1))


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
                "referred_by": 1,
            },
        )
        .sort("registered_at", -1)
        .skip(page * per_page)
        .limit(per_page)
    )
    users = await cursor.to_list(length=per_page)
    return users, total


async def list_referred_users(referrer_id: int) -> list[dict[str, Any]]:
    db = get_db()
    cursor = (
        db.users.find({"referred_by": referrer_id})
        .sort([("referred_at", -1), ("registered_at", -1)])
    )
    return await cursor.to_list(length=500)


async def list_referral_pairs(
    page: int, per_page: int = 20
) -> tuple[list[dict[str, Any]], int]:
    db = get_db()
    query = {"referred_by": {"$ne": None, "$exists": True}}
    total = await db.users.count_documents(query)
    cursor = (
        db.users.find(query)
        .sort([("referred_at", -1), ("registered_at", -1)])
        .skip(page * per_page)
        .limit(per_page)
    )
    referred_users = await cursor.to_list(length=per_page)
    if not referred_users:
        return [], total

    referrer_ids = list({u["referred_by"] for u in referred_users if u.get("referred_by")})
    referrers: dict[int, dict[str, Any]] = {}
    if referrer_ids:
        async for doc in db.users.find({"telegram_id": {"$in": referrer_ids}}):
            referrers[doc["telegram_id"]] = doc

    pairs: list[dict[str, Any]] = []
    for referred in referred_users:
        referrer_id = referred.get("referred_by")
        pairs.append(
            {
                "referrer": referrers.get(referrer_id),
                "referrer_id": referrer_id,
                "referred": referred,
                "referred_at": referred.get("referred_at") or referred.get("registered_at"),
            }
        )
    return pairs, total


async def count_referrals() -> int:
    return await get_db().users.count_documents(
        {"referred_by": {"$ne": None, "$exists": True}}
    )


async def get_episodes(serial_slug: str, page: int, per_page: int) -> tuple[list[dict], int]:
    db = get_db()
    total = await db.episodes.count_documents({"serial_slug": serial_slug})
    cursor = (
        db.episodes.find({"serial_slug": serial_slug})
        .sort([("date", -1), ("_id", -1)])
        .skip(page * per_page)
        .limit(per_page)
    )
    episodes = await cursor.to_list(length=per_page)
    return episodes, total


async def get_episode_months(serial_slug: str) -> list[dict[str, int]]:
    db = get_db()
    pipeline = [
        {"$match": {"serial_slug": serial_slug}},
        {
            "$group": {
                "_id": {"year": {"$year": "$date"}, "month": {"$month": "$date"}},
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id.year": -1, "_id.month": -1}},
    ]
    docs = await db.episodes.aggregate(pipeline).to_list(length=120)
    return [
        {
            "year": doc["_id"]["year"],
            "month": doc["_id"]["month"],
            "count": doc["count"],
        }
        for doc in docs
    ]


async def get_episodes_by_month(
    serial_slug: str, year: int, month: int, page: int, per_page: int
) -> tuple[list[dict], int]:
    db = get_db()
    start = datetime(year, month, 1, tzinfo=TZ)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=TZ)
    else:
        end = datetime(year, month + 1, 1, tzinfo=TZ)
    query = {"serial_slug": serial_slug, "date": {"$gte": start, "$lt": end}}
    total = await db.episodes.count_documents(query)
    cursor = (
        db.episodes.find(query)
        .sort([("date", -1), ("_id", -1)])
        .skip(page * per_page)
        .limit(per_page)
    )
    episodes = await cursor.to_list(length=per_page)
    return episodes, total


async def get_episode(episode_id: str) -> dict[str, Any] | None:
    if not ObjectId.is_valid(episode_id):
        return None
    return await get_db().episodes.find_one({"_id": ObjectId(episode_id)})


async def delete_episode(episode_id: str) -> dict[str, Any] | None:
    if not ObjectId.is_valid(episode_id):
        return None
    db = get_db()
    episode = await db.episodes.find_one_and_delete({"_id": ObjectId(episode_id)})
    if episode:
        await db.users.update_many(
            {"unlocked_episodes": episode_id},
            {"$pull": {"unlocked_episodes": episode_id}},
        )
    return episode


async def delete_episode_by_serial_date(
    serial_slug: str, episode_date: datetime
) -> dict[str, Any] | None:
    db = get_db()
    episode = await db.episodes.find_one_and_delete(
        {"serial_slug": serial_slug, "date": episode_date}
    )
    if episode:
        ep_id = str(episode["_id"])
        await db.users.update_many(
            {"unlocked_episodes": ep_id},
            {"$pull": {"unlocked_episodes": ep_id}},
        )
    return episode


async def get_open_episode_requests(limit: int = 50) -> list[dict[str, Any]]:
    cursor = (
        get_db()
        .episode_requests.find({"status": "open"})
        .sort("created_at", -1)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def close_episode_request(request_id: str) -> bool:
    if not ObjectId.is_valid(request_id):
        return False
    result = await get_db().episode_requests.update_one(
        {"_id": ObjectId(request_id), "status": "open"},
        {"$set": {"status": "closed", "closed_at": datetime.now(TZ)}},
    )
    return result.modified_count > 0


async def get_open_support_tickets(limit: int = 50) -> list[dict[str, Any]]:
    cursor = (
        get_db()
        .support_tickets.find({"status": "open"})
        .sort("created_at", -1)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def reply_support_ticket(
    ticket_id: str, admin_reply: str, admin_id: int
) -> dict[str, Any] | None:
    if not ObjectId.is_valid(ticket_id):
        return None
    ticket = await get_db().support_tickets.find_one_and_update(
        {"_id": ObjectId(ticket_id), "status": "open"},
        {
            "$set": {
                "status": "closed",
                "admin_reply": admin_reply,
                "replied_by": admin_id,
                "replied_at": datetime.now(TZ),
            }
        },
        return_document=True,
    )
    return ticket


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


async def upsert_episode(
    serial_slug: str,
    serial_name: str,
    episode_date: datetime,
    file_id: str,
    file_unique_id: str,
    message_id: int | None = None,
    storage_channel_id: int | None = None,
) -> tuple[str, bool]:
    """Insert or update episode by serial + date. Returns (episode_id, created)."""
    db = get_db()
    now = datetime.now(TZ)
    payload = {
        "serial_slug": serial_slug,
        "serial_name": serial_name,
        "date": episode_date,
        "file_id": file_id,
        "file_unique_id": file_unique_id,
        "message_id": message_id,
        "storage_channel_id": storage_channel_id,
        "uploaded_at": now,
        "view_count": 0,
    }
    existing = await db.episodes.find_one(
        {"serial_slug": serial_slug, "date": episode_date}
    )
    if existing:
        await db.episodes.update_one({"_id": existing["_id"]}, {"$set": payload})
        return str(existing["_id"]), False

    result = await db.episodes.insert_one(payload)
    return str(result.inserted_id), True


async def add_episode(
    serial_slug: str,
    serial_name: str,
    episode_date: datetime,
    file_id: str,
    file_unique_id: str,
    message_id: int | None = None,
    storage_channel_id: int | None = None,
) -> str:
    ep_id, _ = await upsert_episode(
        serial_slug,
        serial_name,
        episode_date,
        file_id,
        file_unique_id,
        message_id,
        storage_channel_id,
    )
    return ep_id


async def get_serial_by_slug(slug: str) -> dict[str, Any] | None:
    return await get_db().serials.find_one({"slug": slug})


async def create_serial(
    name: str, aliases: list[str] | None = None
) -> tuple[dict[str, Any] | None, str]:
    from services.serial_utils import slugify_serial_name

    clean_name = name.strip()
    if not clean_name:
        return None, "Serial name cannot be empty."

    slug = slugify_serial_name(clean_name)
    if not slug:
        return None, "Could not generate a slug from that name."

    existing = await get_serial_by_slug(slug)
    if existing:
        return None, (
            f"Serial already exists: <b>{existing['name']}</b> "
            f"(<code>{slug}</code>)"
        )

    clean_aliases = list(
        dict.fromkeys(alias.strip() for alias in (aliases or []) if alias.strip())
    )
    doc = {
        "name": clean_name,
        "slug": slug,
        "aliases": clean_aliases,
        "active": True,
    }
    await get_db().serials.insert_one(doc)
    return doc, ""


async def update_serial(
    slug: str, name: str, aliases: list[str] | None = None
) -> tuple[dict[str, Any] | None, str]:
    db = get_db()
    serial = await db.serials.find_one({"slug": slug, "active": True})
    if not serial:
        return None, "Serial not found."

    clean_name = name.strip()
    if not clean_name:
        return None, "Serial name cannot be empty."

    clean_aliases = list(
        dict.fromkeys(alias.strip() for alias in (aliases or []) if alias.strip())
    )
    await db.serials.update_one(
        {"slug": slug},
        {"$set": {"name": clean_name, "aliases": clean_aliases}},
    )
    if clean_name != serial.get("name"):
        await db.episodes.update_many(
            {"serial_slug": slug},
            {"$set": {"serial_name": clean_name}},
        )

    updated = await db.serials.find_one({"slug": slug})
    return updated, ""


async def count_active_serials() -> int:
    return await get_db().serials.count_documents({"active": True})


async def list_serials_admin(
    page: int, per_page: int
) -> tuple[list[dict[str, Any]], int]:
    db = get_db()
    total = await db.serials.count_documents({"active": True})
    cursor = (
        db.serials.find({"active": True})
        .sort("name", 1)
        .skip(page * per_page)
        .limit(per_page)
    )
    serials = await cursor.to_list(length=per_page)
    for serial in serials:
        serial["episode_count"] = await db.episodes.count_documents(
            {"serial_slug": serial["slug"]}
        )
    return serials, total


async def delete_serial(serial_slug: str) -> tuple[dict[str, Any] | None, int]:
    db = get_db()
    serial = await db.serials.find_one({"slug": serial_slug, "active": True})
    if not serial:
        return None, 0

    ep_count = await db.episodes.count_documents({"serial_slug": serial_slug})
    if ep_count:
        cursor = db.episodes.find({"serial_slug": serial_slug}, {"_id": 1})
        async for doc in cursor:
            ep_id = str(doc["_id"])
            await db.users.update_many(
                {"unlocked_episodes": ep_id},
                {"$pull": {"unlocked_episodes": ep_id}},
            )
        await db.episodes.delete_many({"serial_slug": serial_slug})

    now = datetime.now(TZ)
    await db.serials.update_one(
        {"slug": serial_slug},
        {
            "$set": {
                "active": False,
                "deleted_at": now,
                "deleted_by_admin": True,
            }
        },
    )
    return serial, ep_count


async def list_serials() -> list[dict[str, Any]]:
    cursor = get_db().serials.find({"active": True}).sort("name", 1)
    return await cursor.to_list(length=200)


async def get_episodes_by_date_query(
    day: int, month: int, year: int | None = None
) -> list[dict[str, Any]]:
    db = get_db()
    if year:
        start = datetime(year, month, day, tzinfo=TZ)
        end = start + timedelta(days=1)
        cursor = db.episodes.find({"date": {"$gte": start, "$lt": end}})
    else:
        cursor = db.episodes.find(
            {
                "$expr": {
                    "$and": [
                        {"$eq": [{"$dayOfMonth": "$date"}, day]},
                        {"$eq": [{"$month": "$date"}, month]},
                    ]
                }
            }
        )
    return await cursor.sort("serial_name", 1).to_list(length=500)


async def list_serials_catalog(
    page: int, per_page: int
) -> tuple[list[dict[str, Any]], int]:
    db = get_db()
    total = await db.serials.count_documents({"active": True})
    cursor = (
        db.serials.find({"active": True})
        .sort("name", 1)
        .skip(page * per_page)
        .limit(per_page)
    )
    serials = await cursor.to_list(length=per_page)
    for serial in serials:
        serial["episode_count"] = await db.episodes.count_documents(
            {"serial_slug": serial["slug"]}
        )
    return serials, total
