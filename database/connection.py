import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from config import MONGODB_DB, MONGODB_URI
from database.seed import refresh_serial_catalog, seed_serials

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
db: AsyncIOMotorDatabase | None = None


def get_db() -> AsyncIOMotorDatabase:
    if db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return db


async def init_db() -> AsyncIOMotorDatabase:
    global _client, db
    if not MONGODB_URI:
        raise RuntimeError("MONGODB_URI environment variable is not set.")
    _client = AsyncIOMotorClient(
        MONGODB_URI,
        serverSelectionTimeoutMS=10000,
        connectTimeoutMS=10000,
    )
    await _client.admin.command("ping")
    db = _client[MONGODB_DB]

    await db.users.create_index("telegram_id", unique=True)
    await db.serials.create_index("slug", unique=True)
    await db.episodes.create_index([("serial_slug", 1), ("date", -1)])
    await db.payments.create_index([("status", 1), ("created_at", -1)])
    await db.episode_requests.create_index([("status", 1), ("created_at", -1)])
    await db.support_tickets.create_index([("status", 1), ("created_at", -1)])

    inserted = await seed_serials(db)
    if inserted:
        logger.info("Seeded %s new serials into database", inserted)

    await refresh_serial_catalog(db)

    logger.info("Connected to MongoDB database: %s", MONGODB_DB)
    return db


async def close_db() -> None:
    global _client, db
    if _client is not None:
        _client.close()
        _client = None
        db = None
