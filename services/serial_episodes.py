from aiogram.types import CallbackQuery, Message

from database import repository as repo
from keyboards.inline import episode_list_keyboard, episode_months_keyboard, serial_nav_keyboard
from services.messages import build_episode_list_text, build_episode_months_text


async def open_serial_episodes(
    target: Message | CallbackQuery,
    serial: dict,
    db_user: dict,
    *,
    show_catalog_back: bool = False,
) -> None:
    months = await repo.get_episode_months(serial["slug"])
    if not months:
        text = (
            f"📺 <b>{serial['name']}</b>\n\n"
            "No episodes uploaded yet.\n"
            "Use 📺 Request Episode to ask for one."
        )
        keyboard = serial_nav_keyboard(show_catalog_back=show_catalog_back)
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(
                text, reply_markup=keyboard, parse_mode="HTML"
            )
            await target.answer()
        else:
            await target.answer(text, reply_markup=keyboard, parse_mode="HTML")
        return

    if len(months) == 1:
        month = months[0]
        await show_serial_episodes_for_month(
            target,
            serial,
            db_user,
            month["year"],
            month["month"],
            0,
            show_catalog_back=show_catalog_back,
            show_month_back=False,
        )
        return

    await show_serial_month_picker(
        target, serial, months, show_catalog_back=show_catalog_back
    )


async def show_serial_month_picker(
    target: Message | CallbackQuery,
    serial: dict,
    months: list[dict[str, int]] | None = None,
    *,
    show_catalog_back: bool = False,
) -> None:
    if months is None:
        months = await repo.get_episode_months(serial["slug"])
    text = build_episode_months_text(serial, months)
    keyboard = episode_months_keyboard(
        serial["slug"], months, show_catalog_back=show_catalog_back
    )
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await target.answer()
    else:
        await target.answer(text, reply_markup=keyboard, parse_mode="HTML")


async def show_serial_episodes_for_month(
    target: Message | CallbackQuery,
    serial: dict,
    db_user: dict,
    year: int,
    month: int,
    page: int,
    *,
    show_catalog_back: bool = False,
    show_month_back: bool = True,
) -> None:
    text, _ = await build_episode_list_text(
        serial, page, db_user, year=year, month=month
    )
    keyboard = await episode_list_keyboard(
        serial["slug"],
        page,
        year=year,
        month=month,
        user=db_user,
        show_catalog_back=show_catalog_back,
        show_month_back=show_month_back,
    )
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await target.answer()
    else:
        await target.answer(text, reply_markup=keyboard, parse_mode="HTML")


def parse_yyyymm(value: str) -> tuple[int, int] | None:
    if len(value) != 6 or not value.isdigit():
        return None
    year, month = int(value[:4]), int(value[4:6])
    if month < 1 or month > 12:
        return None
    return year, month
