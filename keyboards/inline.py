from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from config import EPISODE_UNLOCK_PRICE, EPISODES_PER_PAGE, FREE_DAILY_LIMIT, SERIALS_PER_PAGE, VIP_MONTHLY_PRICE
from database import repository as repo
from services.messages import DATE_EPISODES_PER_PAGE, format_date


def main_menu_keyboard(user: dict | None = None) -> ReplyKeyboardMarkup:
    plan_button = (
        "✅ VIP Member"
        if user and user.get("plan") == "vip"
        else "⭐ Get VIP"
    )
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🔍 Search Serial"),
                KeyboardButton(text="📚 Browse Serials"),
            ],
            [
                KeyboardButton(text="📋 My Plan"),
                KeyboardButton(text=plan_button),
            ],
            [
                KeyboardButton(text="📺 Request Episode"),
                KeyboardButton(text="💬 Support"),
            ],
        ],
        resize_keyboard=True,
    )


async def serial_catalog_keyboard(page: int) -> InlineKeyboardMarkup:
    serials, total = await repo.list_serials_catalog(page, SERIALS_PER_PAGE)
    rows: list[list[InlineKeyboardButton]] = []

    for serial in serials:
        count = serial.get("episode_count", 0)
        icon = "📺" if count > 0 else "📭"
        label = f"{icon} {serial['name']} ({count})"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"pick:{serial['slug']}",
                )
            ]
        )

    total_pages = max(1, (total + SERIALS_PER_PAGE - 1) // SERIALS_PER_PAGE)
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀ Prev", callback_data=f"cat:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="Next ▶", callback_data=f"cat:{page + 1}"))
    if nav:
        rows.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def episode_list_keyboard(
    serial_slug: str,
    page: int,
    *,
    user: dict | None = None,
    show_catalog_back: bool = False,
) -> InlineKeyboardMarkup:
    episodes, total = await repo.get_episodes(serial_slug, page, EPISODES_PER_PAGE)
    rows: list[list[InlineKeyboardButton]] = []

    for ep in episodes:
        label = format_date(ep["date"])
        ep_id = str(ep["_id"])
        if user and repo.is_episode_locked_for_user(user, ep_id):
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"🔒 {label}",
                        callback_data=f"locked:{ep_id}",
                    )
                ]
            )
        else:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"▶ {label}",
                        callback_data=f"watch:{ep_id}",
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

    if show_catalog_back:
        rows.append(
            [InlineKeyboardButton(text="📚 All Serials", callback_data="cat:0")]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def date_episodes_keyboard(
    episodes: list[dict],
    date_key: str,
    page: int,
    *,
    user: dict | None = None,
) -> InlineKeyboardMarkup:
    total_pages = max(1, (len(episodes) + DATE_EPISODES_PER_PAGE - 1) // DATE_EPISODES_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    start = page * DATE_EPISODES_PER_PAGE
    page_episodes = episodes[start : start + DATE_EPISODES_PER_PAGE]

    rows: list[list[InlineKeyboardButton]] = []
    for ep in page_episodes:
        ep_id = str(ep["_id"])
        name = ep.get("serial_name", "Serial")
        if user and repo.is_episode_locked_for_user(user, ep_id):
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"🔒 {name}",
                        callback_data=f"locked:{ep_id}",
                    )
                ]
            )
        else:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"▶ {name}",
                        callback_data=f"watch:{ep_id}",
                    )
                ]
            )

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="◀ Prev",
                callback_data=f"datefind:{date_key}:{page - 1}",
            )
        )
    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton(
                text="Next ▶",
                callback_data=f"datefind:{date_key}:{page + 1}",
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


def vip_keyboard(user: dict | None = None) -> InlineKeyboardMarkup:
    if user and user.get("plan") == "vip":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ You are a VIP Member", callback_data="vip:status")],
                [InlineKeyboardButton(text="📋 My Plan", callback_data="plan")],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"⭐ Subscribe · ₹{VIP_MONTHLY_PRICE}/mo", callback_data="pay:vip")],
            [InlineKeyboardButton(text="📋 My Plan", callback_data="plan")],
        ]
    )


def plan_keyboard(user: dict | None = None) -> InlineKeyboardMarkup | None:
    if user and user.get("plan") == "vip":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ You are a VIP Member", callback_data="vip:status")],
            ]
        )
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
            [InlineKeyboardButton(text="🗑 Manage Episodes", callback_data="admin:deleps")],
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


ADMIN_EPISODES_PER_PAGE = 8


async def admin_episodes_keyboard(
    serial_slug: str, page: int
) -> InlineKeyboardMarkup:
    episodes, total = await repo.get_episodes(serial_slug, page, ADMIN_EPISODES_PER_PAGE)
    rows: list[list[InlineKeyboardButton]] = []

    for ep in episodes:
        label = format_date(ep["date"])
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🗑 {label}",
                    callback_data=f"admin:delep:{str(ep['_id'])}:{page}",
                )
            ]
        )

    total_pages = max(1, (total + ADMIN_EPISODES_PER_PAGE - 1) // ADMIN_EPISODES_PER_PAGE)
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="◀ Prev",
                callback_data=f"admin:epslist:{serial_slug}:{page - 1}",
            )
        )
    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton(
                text="Next ▶",
                callback_data=f"admin:epslist:{serial_slug}:{page + 1}",
            )
        )
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="🛠 Admin Menu", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_delete_episode_confirm_keyboard(episode_id: str, serial_slug: str, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Yes, delete",
                    callback_data=f"admin:delepok:{episode_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data=f"admin:epslist:{serial_slug}:{page}",
                ),
            ]
        ]
    )
