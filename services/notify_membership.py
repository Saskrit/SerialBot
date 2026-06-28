"""Episode alert (notification) membership — monthly plans for upload notifications."""

from __future__ import annotations

from dataclasses import dataclass

from config import PAYMENT_CONTACT_USERNAME


@dataclass(frozen=True)
class NotifyMembershipPlan:
    id: str
    name: str
    price_inr: int
    price_label: str
    serial_limit: int | None  # None = all serials
    validity: str = "30 days"
    benefits: tuple[str, ...] = ()


NOTIFY_10 = NotifyMembershipPlan(
    id="notify_10",
    name="Alert Plan · 10 Serials",
    price_inr=50,
    price_label="₹50/month",
    serial_limit=10,
    benefits=(
        "Pick up to 10 serials",
        "Telegram alert on every new upload",
        "Manage picks in bot → Episode Alerts",
    ),
)

NOTIFY_20 = NotifyMembershipPlan(
    id="notify_20",
    name="Alert Plan · 20 Serials",
    price_inr=100,
    price_label="₹100/month",
    serial_limit=20,
    benefits=(
        "Pick up to 20 serials",
        "Telegram alert on every new upload",
        "Manage picks in bot → Episode Alerts",
    ),
)

NOTIFY_ALL = NotifyMembershipPlan(
    id="notify_all",
    name="Alert Plan · All Serials",
    price_inr=150,
    price_label="₹150/month",
    serial_limit=None,
    benefits=(
        "All serials in the catalog",
        "Telegram alert on every new upload",
        "No serial selection needed",
    ),
)

NOTIFY_PLANS: tuple[NotifyMembershipPlan, ...] = (NOTIFY_10, NOTIFY_20, NOTIFY_ALL)

NOTIFY_PLANS_BY_ID: dict[str, NotifyMembershipPlan] = {p.id: p for p in NOTIFY_PLANS}

NOTIFY_MEMBERSHIP_DAYS = 30


def get_notify_plan(plan_id: str | None) -> NotifyMembershipPlan | None:
    if not plan_id:
        return None
    return NOTIFY_PLANS_BY_ID.get(plan_id)


def notify_serial_limit(plan_id: str | None) -> int | None:
    plan = get_notify_plan(plan_id)
    if not plan:
        return None
    return plan.serial_limit


def build_notify_promo_text(*, payment_contact: str | None = None) -> str:
    contact = payment_contact or f"@{PAYMENT_CONTACT_USERNAME}"
    lines = [
        "🔔 <b>Episode Alert Membership</b>",
        "",
        "Get notified when new episodes are uploaded for the serials you care about.",
        "",
        f"• <b>10 serials</b> — ₹50/month",
        f"• <b>20 serials</b> — ₹100/month",
        f"• <b>All serials</b> — ₹150/month",
        "",
        f"Contact <b>{contact}</b> on Telegram to subscribe.",
        "",
        "Open the bot menu → <b>🔔 Episode Alerts</b> to pick your serials after payment.",
    ]
    return "\n".join(lines)


def build_notify_status_text(user: dict) -> str:
    from database.datetime_utils import ensure_aware
    from datetime import datetime

    from config import TZ
    from services.messages import format_date, format_datetime
    from services.payment_contact import payment_contact_label

    plan_id = user.get("notify_plan")
    plan = get_notify_plan(plan_id)
    expires = ensure_aware(user.get("notify_expires"))
    now = datetime.now(TZ)
    selected = user.get("notify_serials") or []

    lines = ["🔔 <b>Episode Alert Membership</b>", ""]

    if plan and expires and expires > now:
        limit = plan.serial_limit
        lines.extend(
            [
                f"Plan: <b>{plan.name}</b> ({plan.price_label})",
                f"Valid until: <b>{format_datetime(expires)}</b>",
            ]
        )
        if limit is None:
            lines.append("Coverage: <b>All serials</b>")
        else:
            lines.append(
                f"Selected: <b>{len(selected)}/{limit}</b> serial(s)"
            )
            if selected:
                lines.append("")
                lines.append("<b>Your serials:</b>")
                for slug in selected[:15]:
                    lines.append(f"• {slug}")
                if len(selected) > 15:
                    lines.append(f"… +{len(selected) - 15} more")
    else:
        lines.extend(
            [
                "Status: <b>Not subscribed</b>",
                "",
                "Choose a monthly plan:",
                "• 10 serials — ₹50",
                "• 20 serials — ₹100",
                "• All serials — ₹150",
                "",
                f"Contact {payment_contact_label()} for payment.",
            ]
        )
    return "\n".join(lines)
