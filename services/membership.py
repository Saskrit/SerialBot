"""Membership catalog — shared by Telegram bot and public website."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PlanKind = Literal["free", "episode_unlock", "daily_pass", "vip"]


@dataclass(frozen=True)
class MembershipPlan:
    id: str
    name: str
    price_inr: int | None
    price_label: str
    validity: str
    kind: PlanKind
    benefits: tuple[str, ...]
    badge: str | None = None
    recommended: bool = False
    vip_days: int | None = None
    daily_pass_hours: int | None = None
    short_label: str | None = None

    @property
    def display_label(self) -> str:
        if self.short_label:
            return self.short_label
        if self.price_inr is not None:
            return f"{self.name} – ₹{self.price_inr}"
        return self.name


FREE_TOMORROW = MembershipPlan(
    id="free_tomorrow",
    name="Continue Free Tomorrow",
    price_inr=None,
    price_label="Free",
    validity="Resets at midnight UTC",
    kind="free",
    benefits=(
        "Your daily limit resets tomorrow",
        "No payment required",
    ),
    short_label="Continue Free Tomorrow",
)

EPISODE_PASS = MembershipPlan(
    id="episode_pass",
    name="Episode Pass",
    price_inr=10,
    price_label="₹10",
    validity="Permanent for this episode",
    kind="episode_unlock",
    benefits=(
        "Unlock one selected episode",
        "No subscription required",
        "Permanent access to purchased episode",
        "Available after daily limit",
    ),
    short_label="Unlock This Episode – ₹10",
)

DAILY_PASS = MembershipPlan(
    id="daily_pass",
    name="Daily Unlimited Pass",
    price_inr=19,
    price_label="₹19",
    validity="24 hours from purchase",
    kind="daily_pass",
    benefits=(
        "Unlimited episodes for 24 hours",
        "Access to all serials",
        "No daily restrictions",
        "Perfect for binge watching",
    ),
    daily_pass_hours=24,
    short_label="Daily Unlimited Pass – ₹19",
)

WEEKLY_VIP = MembershipPlan(
    id="weekly_vip",
    name="Weekly VIP",
    price_inr=39,
    price_label="₹39",
    validity="7 days",
    kind="vip",
    benefits=(
        "Unlimited episodes",
        "Full serial archive",
        "Early episode uploads",
        "Priority support",
        "No advertisements",
        "Seven-day validity",
    ),
    vip_days=7,
    short_label="Weekly VIP – ₹39",
)

MONTHLY_VIP = MembershipPlan(
    id="monthly_vip",
    name="Monthly VIP",
    price_inr=99,
    price_label="₹99",
    validity="30 days",
    kind="vip",
    benefits=(
        "Unlimited daily watching",
        "Complete episode archive",
        "No daily limits",
        "Early episode releases",
        "Request old episodes",
        "Priority support",
        "No advertisements",
        "Exclusive VIP announcements",
        "Thirty-day validity",
    ),
    badge="Recommended",
    recommended=True,
    vip_days=30,
    short_label="Monthly VIP – ₹99",
)

QUARTERLY_VIP = MembershipPlan(
    id="quarterly_vip",
    name="Quarterly VIP",
    price_inr=249,
    price_label="₹249",
    validity="90 days",
    kind="vip",
    benefits=(
        "All Monthly VIP features",
        "90-day validity",
        "Lower monthly cost",
        "Priority feature access",
    ),
    badge="Best Value",
    vip_days=90,
    short_label="Quarterly VIP – ₹249",
)

ANNUAL_VIP = MembershipPlan(
    id="annual_vip",
    name="Annual VIP",
    price_inr=799,
    price_label="₹799",
    validity="12 months",
    kind="vip",
    benefits=(
        "Unlimited viewing",
        "Complete archive access",
        "Highest priority support",
        "Exclusive member rewards",
        "Twelve-month validity",
        "Best value plan",
    ),
    badge="Maximum Savings",
    vip_days=365,
    short_label="Annual VIP – ₹799",
)

FREE_TIER = MembershipPlan(
    id="free",
    name="Free Tier",
    price_inr=0,
    price_label="Free",
    validity="Daily limit",
    kind="free",
    benefits=(
        "Browse and search all serials",
        "Limited daily episodes",
        "Refer friends for bonus watches",
        "Episode Pass available",
    ),
)

REFERRAL_PLAN = MembershipPlan(
    id="referral",
    name="Refer & Watch",
    price_inr=None,
    price_label="+5 watches",
    validity="Per successful invite",
    kind="free",
    benefits=(
        "Unique referral link for every user",
        "You and your friend each get 5 bonus watches",
        "Each user can only be referred once",
        "Bonus watches used after daily limit",
    ),
)

VIP_PRIVILEGES: tuple[str, ...] = (
    "No daily watch limits",
    "Full episode archive access",
    "Request older episodes",
    "Early uploads when available",
    "Faster support responses",
    "Exclusive member announcements",
)

UPGRADE_PLANS: tuple[MembershipPlan, ...] = (
    FREE_TOMORROW,
    EPISODE_PASS,
    DAILY_PASS,
    WEEKLY_VIP,
    MONTHLY_VIP,
    QUARTERLY_VIP,
    ANNUAL_VIP,
)

PAID_PLANS: tuple[MembershipPlan, ...] = (
    EPISODE_PASS,
    DAILY_PASS,
    WEEKLY_VIP,
    MONTHLY_VIP,
    QUARTERLY_VIP,
    ANNUAL_VIP,
)

CATALOG_PLANS: tuple[MembershipPlan, ...] = (
    FREE_TIER,
    EPISODE_PASS,
    DAILY_PASS,
    WEEKLY_VIP,
    MONTHLY_VIP,
    QUARTERLY_VIP,
    ANNUAL_VIP,
    REFERRAL_PLAN,
)

_PLANS_BY_ID: dict[str, MembershipPlan] = {
    p.id: p
    for p in (
        FREE_TOMORROW,
        EPISODE_PASS,
        DAILY_PASS,
        WEEKLY_VIP,
        MONTHLY_VIP,
        QUARTERLY_VIP,
        ANNUAL_VIP,
        FREE_TIER,
        REFERRAL_PLAN,
    )
}


def get_plan(plan_id: str) -> MembershipPlan | None:
    return _PLANS_BY_ID.get(plan_id)


def format_inr(amount: int) -> str:
    return f"₹{amount}"


def plan_button_text(plan: MembershipPlan) -> str:
    if plan.id == "free_tomorrow":
        return "⏳ Continue Free Tomorrow"
    if plan.badge == "Recommended":
        return f"⭐ {plan.short_label} ({plan.badge})"
    if plan.badge == "Best Value":
        return f"💎 {plan.short_label} ({plan.badge})"
    if plan.badge == "Maximum Savings":
        return f"🏆 {plan.short_label} ({plan.badge})"
    if plan.id == "episode_pass":
        return f"🔓 {plan.short_label}"
    return plan.short_label or plan.name
