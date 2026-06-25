from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from config import EPISODE_UNLOCK_PRICE, EPISODES_PER_PAGE, SERIALS_PER_PAGE, VIP_MONTHLY_PRICE
from database import repository as repo
from services.messages import DATE_EPISODES_PER_PAGE, format_date, format_month_year

CLOSE_CALLBACK = "ui:close"
HOME_CALLBACK = "ui:home"


def close_button_row(*, include_home: bool = True) -> list[InlineKeyboardButton]:
    row: list[InlineKeyboardButton] = []
    if include_home:
        row.append(InlineKeyboardButton(text="🏠 Home", callback_data=HOME_CALLBACK))
    row.append(InlineKeyboardButton(text="❌ Close", callback_data=CLOSE_CALLBACK))
    return row


def append_ui_actions(
    rows: list[list[InlineKeyboardButton]], *, include_home: bool = True
) -> None:
    rows.append(close_button_row(include_home=include_home))


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
            [KeyboardButton(text="🎁 Refer & Watch")],
            [KeyboardButton(text="❌ Close Menu")],
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

    append_ui_actions(rows)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def episode_list_keyboard(
    serial_slug: str,
    page: int,
    *,
    year: int,
    month: int,
    user: dict | None = None,
    show_catalog_back: bool = False,
    show_month_back: bool = True,
) -> InlineKeyboardMarkup:
    episodes, total = await repo.get_episodes_by_month(
        serial_slug, year, month, page, EPISODES_PER_PAGE
    )
    yyyymm = f"{year}{month:02d}"
    rows: list[list[InlineKeyboardButton]] = []

    for ep in episodes:
        label = format_date(ep["date"])
        ep_id = str(ep["_id"])
        if user and await repo.has_used_trial_episode(user, ep_id):
            button_label = f"🔒 {label}"
            callback_data = f"trialused:{ep_id}"
        elif user and await repo.is_episode_daily_locked(user, ep_id):
            button_label = f"🔒 {label}"
            callback_data = f"locked:{ep_id}"
        else:
            button_label = f"▶ {label}"
            callback_data = f"watch:{ep_id}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=button_label,
                    callback_data=callback_data,
                )
            ]
        )

    nav: list[InlineKeyboardButton] = []
    total_pages = max(1, (total + EPISODES_PER_PAGE - 1) // EPISODES_PER_PAGE)
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="◀ Prev",
                callback_data=f"epsm:{serial_slug}:{yyyymm}:{page - 1}",
            )
        )
    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton(
                text="Next ▶",
                callback_data=f"epsm:{serial_slug}:{yyyymm}:{page + 1}",
            )
        )
    if nav:
        rows.append(nav)

    if show_month_back:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📅 Change Month",
                    callback_data=f"epsmonth:{serial_slug}",
                )
            ]
        )

    if show_catalog_back:
        rows.append(
            [InlineKeyboardButton(text="📚 All Serials", callback_data="cat:0")]
        )

    append_ui_actions(rows)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def episode_months_keyboard(
    serial_slug: str,
    months: list[dict[str, int]],
    *,
    show_catalog_back: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for month_info in months:
        label = (
            f"📅 {format_month_year(month_info['year'], month_info['month'])} "
            f"({month_info['count']})"
        )
        yyyymm = f"{month_info['year']}{month_info['month']:02d}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"epsm:{serial_slug}:{yyyymm}:0",
                )
            ]
        )

    if show_catalog_back:
        rows.append(
            [InlineKeyboardButton(text="📚 All Serials", callback_data="cat:0")]
        )

    append_ui_actions(rows)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def serial_nav_keyboard(*, show_catalog_back: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if show_catalog_back:
        rows.append(
            [InlineKeyboardButton(text="📚 All Serials", callback_data="cat:0")]
        )
    append_ui_actions(rows)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def date_episodes_keyboard(
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
        if user and await repo.has_used_trial_episode(user, ep_id):
            button_label = f"🔒 {name}"
            callback_data = f"trialused:{ep_id}"
        elif user and await repo.is_episode_daily_locked(user, ep_id):
            button_label = f"🔒 {name}"
            callback_data = f"locked:{ep_id}"
        else:
            button_label = f"▶ {name}"
            callback_data = f"watch:{ep_id}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=button_label,
                    callback_data=callback_data,
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

    append_ui_actions(rows)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def limit_reached_keyboard(episode_id: str) -> InlineKeyboardMarkup:
    rows = [
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
    append_ui_actions(rows)
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
        rows = [
            [InlineKeyboardButton(text="✅ You are a VIP Member", callback_data="vip:status")],
            [InlineKeyboardButton(text="📋 My Plan", callback_data="plan")],
        ]
    else:
        rows = [
            [InlineKeyboardButton(text=f"⭐ Subscribe · ₹{VIP_MONTHLY_PRICE}/mo", callback_data="pay:vip")],
            [InlineKeyboardButton(text="📋 My Plan", callback_data="plan")],
        ]
    append_ui_actions(rows)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plan_keyboard(user: dict | None = None) -> InlineKeyboardMarkup | None:
    if user and user.get("plan") == "vip":
        rows = [
            [InlineKeyboardButton(text="✅ You are a VIP Member", callback_data="vip:status")],
        ]
    else:
        rows = [
            [InlineKeyboardButton(text=f"⭐ Upgrade to VIP · ₹{VIP_MONTHLY_PRICE}", callback_data="pay:vip")],
            [InlineKeyboardButton(text="🎁 Refer & Watch", callback_data="refer")],
        ]
    append_ui_actions(rows)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def support_categories_keyboard() -> InlineKeyboardMarkup:
    categories = [
        ("Payment Issue", "support:cat:payment"),
        ("Missing Episode", "support:cat:missing"),
        ("VIP Problem", "support:cat:vip"),
        ("Technical Issue", "support:cat:technical"),
        ("Other", "support:cat:other"),
    ]
    rows = [[InlineKeyboardButton(text=label, callback_data=cb)] for label, cb in categories]
    append_ui_actions(rows)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def new_episode_notification_keyboard(
    serial_slug: str, episode_id: str
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="▶ Watch Now", callback_data=f"watch:{episode_id}")],
        [InlineKeyboardButton(text="📺 View Serial", callback_data=f"pick:{serial_slug}")],
    ]
    append_ui_actions(rows)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_free_limit_keyboard(current: int) -> InlineKeyboardMarkup:
    options = [0, 3, 4, 5, 6, 7, 8, 9, 10]
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for value in options:
        if value == 0:
            label = "♾ Free for all"
        else:
            label = str(value)
        if value == current:
            label = f"✓ {label}"
        row.append(
            InlineKeyboardButton(
                text=label,
                callback_data=f"admin:freelimit:{value}",
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="🛠 Admin Menu", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_trial_ttl_keyboard(current: int) -> InlineKeyboardMarkup:
    from services.settings import format_trial_ttl_label

    presets = [
        (0, "Off"),
        (10, "10 sec"),
        (30, "30 sec"),
        (60, "1 min"),
        (120, "2 min"),
        (300, "5 min"),
        (3600, "1 hr"),
        (7200, "2 hr"),
        (86400, "24 hr"),
    ]
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for seconds, short_label in presets:
        label = f"✓ {short_label}" if seconds == current else short_label
        row.append(
            InlineKeyboardButton(
                text=label,
                callback_data=f"admin:trial:{seconds}",
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="🛠 Admin Menu", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📊 Statistics", callback_data="admin:stats")],
        [InlineKeyboardButton(text="👥 All Users", callback_data="admin:users:0")],
        [InlineKeyboardButton(text="💳 Pending Payments", callback_data="admin:payments")],
        [InlineKeyboardButton(text="⚙️ Free Tier Limit", callback_data="admin:freelimit")],
        [InlineKeyboardButton(text="⏳ Trial Episode Timer", callback_data="admin:trial")],
        [InlineKeyboardButton(text="📺 Episode Requests", callback_data="admin:requests")],
        [InlineKeyboardButton(text="💬 Support Tickets", callback_data="admin:support")],
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="admin:broadcast")],
        [InlineKeyboardButton(text="⭐ Grant VIP", callback_data="admin:grantvip")],
        [InlineKeyboardButton(text="➕ Add Serial", callback_data="admin:addserial")],
        [InlineKeyboardButton(text="🗑 Delete Serial", callback_data="admin:delserial:0")],
        [InlineKeyboardButton(text="📈 Episode Views", callback_data="admin:epstats")],
        [InlineKeyboardButton(text="🗑 Manage Episodes", callback_data="admin:deleps")],
        [InlineKeyboardButton(text="👤 Manage User", callback_data="admin:user")],
    ]
    append_ui_actions(rows, include_home=False)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def admin_serials_delete_keyboard(page: int) -> InlineKeyboardMarkup:
    serials, total = await repo.list_serials_admin(page, SERIALS_PER_PAGE)
    rows: list[list[InlineKeyboardButton]] = []

    for serial in serials:
        count = serial.get("episode_count", 0)
        label = f"🗑 {serial['name']} ({count} ep)"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"admin:delser:{serial['slug']}",
                )
            ]
        )

    total_pages = max(1, (total + SERIALS_PER_PAGE - 1) // SERIALS_PER_PAGE)
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="◀ Prev", callback_data=f"admin:delserial:{page - 1}"
            )
        )
    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton(
                text="Next ▶", callback_data=f"admin:delserial:{page + 1}"
            )
        )
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="🛠 Admin Menu", callback_data="admin:menu")])
    append_ui_actions(rows, include_home=False)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_delete_serial_confirm_keyboard(serial_slug: str, page: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Yes, delete serial",
                    callback_data=f"admin:delserok:{serial_slug}",
                ),
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data=f"admin:delserial:{page}",
                ),
            ]
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
    append_ui_actions(rows, include_home=False)
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
    append_ui_actions(rows, include_home=False)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def admin_episode_stats_keyboard(
    serial_slug: str, page: int
) -> InlineKeyboardMarkup:
    episodes, total = await repo.get_episodes(serial_slug, page, ADMIN_EPISODES_PER_PAGE)
    rows: list[list[InlineKeyboardButton]] = []

    for ep in episodes:
        label = format_date(ep["date"])
        views = ep.get("view_count", 0)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"👁 {views} · {label}",
                    callback_data=f"admin:epstat:{str(ep['_id'])}:{page}",
                )
            ]
        )

    total_pages = max(1, (total + ADMIN_EPISODES_PER_PAGE - 1) // ADMIN_EPISODES_PER_PAGE)
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="◀ Prev",
                callback_data=f"admin:epstatslist:{serial_slug}:{page - 1}",
            )
        )
    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton(
                text="Next ▶",
                callback_data=f"admin:epstatslist:{serial_slug}:{page + 1}",
            )
        )
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="🛠 Admin Menu", callback_data="admin:menu")])
    append_ui_actions(rows, include_home=False)
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
