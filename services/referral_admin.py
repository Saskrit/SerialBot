"""Format referral relationships for admin views (web + Telegram)."""

from __future__ import annotations

from typing import Any


def user_display_name(user: dict[str, Any] | None, *, fallback_id: int | None = None) -> str:
    if not user:
        if fallback_id is not None:
            return f"Unknown user ({fallback_id})"
        return "Unknown user"
    name = user.get("first_name") or user.get("username") or "Unknown"
    username = user.get("username")
    if username:
        return f"{name} (@{username})"
    return name


def user_admin_summary(user: dict[str, Any] | None, *, fallback_id: int | None = None) -> str:
    """Plain-text summary: Name (@user) · ID 123456"""
    if not user:
        tid = fallback_id if fallback_id is not None else "?"
        return f"Unknown user · ID {tid}"
    name = user_display_name(user)
    return f"{name} · ID {user['telegram_id']}"


def format_invite_pair_text(
    referrer: dict[str, Any] | None,
    referred: dict[str, Any],
    *,
    referrer_id: int | None = None,
) -> str:
    inviter = user_admin_summary(referrer, fallback_id=referrer_id or referred.get("referred_by"))
    invitee = user_admin_summary(referred)
    return f"{inviter} invited {invitee}"


def format_invite_pair_html(
    referrer: dict[str, Any] | None,
    referred: dict[str, Any],
    *,
    referrer_id: int | None = None,
) -> str:
    rid = referrer_id or referred.get("referred_by")
    inviter_name = user_display_name(referrer, fallback_id=rid)
    invitee_name = user_display_name(referred)
    if referrer and referrer.get("telegram_id"):
        inviter = (
            f'<a href="/admin/users/{referrer["telegram_id"]}">{inviter_name}</a> '
            f'<code>{referrer["telegram_id"]}</code>'
        )
    elif rid:
        inviter = f'{inviter_name} <code>{rid}</code>'
    else:
        inviter = inviter_name
    invitee = (
        f'<a href="/admin/users/{referred["telegram_id"]}">{invitee_name}</a> '
        f'<code>{referred["telegram_id"]}</code>'
    )
    return f"{inviter} invited {invitee}"
