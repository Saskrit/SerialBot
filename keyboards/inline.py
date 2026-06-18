from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from config import EPISODE_UNLOCK_PRICE, EPISODES_PER_PAGE, VIP_MONTHLY_PRICE
from database import repository as repo
from services.messages import format_date


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Search Serial")],
            [
                KeyboardButton(text="📋 My Plan"),
                KeyboardButton(text="⭐ Get VIP"),
            ],
            [
                KeyboardButton(text="📺 Request Episode"),
                KeyboardButton(text="💬 Support"),
            ],
        ],
        resize_keyboard=True,
    )


async def episode_list_keyboard(serial_slug: str, page: int) -> InlineKeyboardMarkup:
    episodes, total = await repo.get_episodes(serial_slug, page, EPISODES_PER_PAGE)
    rows: list[list[InlineKeyboardButton]] = []

    for ep in episodes:
        label = format_date(ep["date"])
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"▶ {label}",
                    callback_data=f"watch:{ep['_id']}",
                )
            ]
        )

    nav: list[InlineKeyboardButton] = []
    total_pages = max(1, (total + EPISODES_PER_PAGE - 1) // EPISODES_PER_PAGE)
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="◀ Prev",
                callback_data=f"eps:{serial_slug}:{page - 1}",
            )
        )
    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton(
                text="Next ▶",
                callback_data=f"eps:{serial_slug}:{page + 1}",
            )
        )
    if nav:
        rows.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def limit_reached_keyboard(episode_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🔓 Unlock Episode · ₹{EPISODE_UNLOCK_PRICE}",
                    callback_data=f"pay:unlock:{episode_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"⭐ VIP Monthly · ₹{VIP_MONTHLY_PRICE}",
                    callback_data="pay:vip",
                )
            ],
            [InlineKeyboardButton(text="📋 My Plan", callback_data="plan")],
        ]
    )


def payment_instructions_keyboard(payment_id: str, bot_username: str) -> InlineKeyboardMarkup:
    upload_url = f"https://t.me/{bot_username}?start=pay_{payment_id}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📸 Upload Screenshot in Bot",
                    url=upload_url,
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data=f"pay:cancel:{payment_id}",
                )
            ],
        ]
    )


def vip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"⭐ Subscribe · ₹{VIP_MONTHLY_PRICE}/mo", callback_data="pay:vip")],
            [InlineKeyboardButton(text="📋 My Plan", callback_data="plan")],
        ]
    )


def plan_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"⭐ Upgrade to VIP · ₹{VIP_MONTHLY_PRICE}", callback_data="pay:vip")],
        ]
    )


def support_categories_keyboard() -> InlineKeyboardMarkup:
    categories = [
        ("Payment Issue", "support:cat:payment"),
        ("Missing Episode", "support:cat:missing"),
        ("VIP Problem", "support:cat:vip"),
        ("Technical Issue", "support:cat:technical"),
        ("Other", "support:cat:other"),
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=cb)] for label, cb in categories
        ]
    )


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Statistics", callback_data="admin:stats")],
            [InlineKeyboardButton(text="👥 All Users", callback_data="admin:users:0")],
            [InlineKeyboardButton(text="💳 Pending Payments", callback_data="admin:payments")],
            [InlineKeyboardButton(text="📺 Episode Requests", callback_data="admin:requests")],
            [InlineKeyboardButton(text="💬 Support Tickets", callback_data="admin:support")],
            [InlineKeyboardButton(text="📢 Broadcast", callback_data="admin:broadcast")],
            [InlineKeyboardButton(text="⭐ Grant VIP", callback_data="admin:grantvip")],
            [InlineKeyboardButton(text="👤 Manage User", callback_data="admin:user")],
        ]
    )


def admin_users_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(text="◀ Prev", callback_data=f"admin:users:{page - 1}")
        )
    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton(text="Next ▶", callback_data=f"admin:users:{page + 1}")
        )
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🛠 Admin Menu", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_payment_keyboard(payment_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Approve", callback_data=f"admin:pay:ok:{payment_id}"),
                InlineKeyboardButton(text="❌ Reject", callback_data=f"admin:pay:no:{payment_id}"),
            ]
        ]
    )


def admin_user_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⭐ Grant VIP", callback_data=f"admin:vip:{telegram_id}"),
                InlineKeyboardButton(text="🚫 Ban", callback_data=f"admin:ban:{telegram_id}"),
            ],
            [
                InlineKeyboardButton(text="✅ Unban", callback_data=f"admin:unban:{telegram_id}"),
                InlineKeyboardButton(text="🗑 Delete", callback_data=f"admin:del:{telegram_id}"),
            ],
        ]
    )
