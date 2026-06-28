from aiogram.types import CallbackQuery, Message

from config import PAYMENT_CONTACT_USERNAME
from services.membership import MembershipPlan, get_plan
from services.notify_membership import get_notify_plan


def payment_contact_url() -> str:
    return f"https://t.me/{PAYMENT_CONTACT_USERNAME}"


def payment_contact_label() -> str:
    return f"@{PAYMENT_CONTACT_USERNAME}"


def build_plan_payment_text(
    plan: MembershipPlan,
    *,
    telegram_id: int | None = None,
    episode_id: str | None = None,
) -> str:
    lines = [
        "💳 <b>Payment & Membership</b>",
        "",
        f"<b>{plan.name}</b> · {plan.price_label}",
        f"Validity: {plan.validity}",
        "",
        "<b>Benefits</b>",
    ]
    for benefit in plan.benefits[:5]:
        lines.append(f"• {benefit}")
    if len(plan.benefits) > 5:
        lines.append(f"• +{len(plan.benefits) - 5} more")

    lines.extend(
        [
            "",
            f"To complete your purchase, contact <b>{payment_contact_label()}</b> on Telegram.",
            f"Mention plan: <b>{plan.name}</b> ({plan.price_label})",
        ]
    )
    if episode_id and plan.kind == "episode_unlock":
        lines.append(f"Episode ID: <code>{episode_id}</code>")
    if telegram_id is not None:
        lines.extend(
            [
                "",
                f"Your Telegram ID: <code>{telegram_id}</code>",
                "<i>Share this ID when you message them.</i>",
            ]
        )
    return "\n".join(lines)


def build_payment_contact_text(
    *,
    purpose: str = "membership",
    telegram_id: int | None = None,
    plan_id: str | None = None,
    episode_id: str | None = None,
) -> str:
    if plan_id:
        plan = get_plan(plan_id)
        if plan:
            return build_plan_payment_text(
                plan, telegram_id=telegram_id, episode_id=episode_id
            )
        notify_plan = get_notify_plan(plan_id)
        if notify_plan:
            lines = [
                "💳 <b>Episode Alert Membership</b>",
                "",
                f"<b>{notify_plan.name}</b> · {notify_plan.price_label}",
                f"Validity: {notify_plan.validity}",
                "",
                f"Contact <b>{payment_contact_label()}</b> on Telegram to subscribe.",
            ]
            if telegram_id is not None:
                lines.extend(
                    [
                        "",
                        f"Your Telegram ID: <code>{telegram_id}</code>",
                    ]
                )
            return "\n".join(lines)

    if purpose == "unlock":
        plan = get_plan("episode_pass")
        if plan:
            return build_plan_payment_text(
                plan, telegram_id=telegram_id, episode_id=episode_id
            )

    lines = [
        "💳 <b>Payment & Membership</b>",
        "",
        f"Contact <b>{payment_contact_label()}</b> on Telegram for any plan:",
        "• Episode Pass — ₹10",
        "• Daily Unlimited Pass — ₹19",
        "• Weekly VIP — ₹39",
        "• Monthly VIP — ₹99 ⭐ Recommended",
        "• Quarterly VIP — ₹249",
        "• Annual VIP — ₹799",
        "",
        "<b>Episode Alerts (monthly)</b>",
        "• 10 serials — ₹50",
        "• 20 serials — ₹100",
        "• All serials — ₹150",
    ]
    if telegram_id is not None:
        lines.extend(
            [
                "",
                f"Your Telegram ID: <code>{telegram_id}</code>",
                "<i>Share this ID when you message them.</i>",
            ]
        )
    return "\n".join(lines)


async def send_payment_contact_message(
    message: Message,
    *,
    purpose: str = "membership",
    plan_id: str | None = None,
    episode_id: str | None = None,
) -> None:
    from keyboards.inline import payment_contact_keyboard

    await message.answer(
        build_payment_contact_text(
            purpose=purpose,
            telegram_id=message.from_user.id if message.from_user else None,
            plan_id=plan_id,
            episode_id=episode_id,
        ),
        reply_markup=payment_contact_keyboard(plan_id=plan_id),
        parse_mode="HTML",
    )


async def send_payment_contact_callback(
    callback: CallbackQuery,
    *,
    purpose: str = "membership",
    plan_id: str | None = None,
    episode_id: str | None = None,
) -> None:
    from keyboards.inline import payment_contact_keyboard

    await callback.message.answer(
        build_payment_contact_text(
            purpose=purpose,
            telegram_id=callback.from_user.id,
            plan_id=plan_id,
            episode_id=episode_id,
        ),
        reply_markup=payment_contact_keyboard(plan_id=plan_id),
        parse_mode="HTML",
    )
    await callback.answer()
