import re

_DURATION_RE = re.compile(
    r"^(\d+)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours)?$",
    re.IGNORECASE,
)


def parse_trial_duration(text: str) -> int | None:
    text = text.strip().lower()
    if text in {"off", "0", "disable", "disabled", "none"}:
        return 0

    match = _DURATION_RE.match(text.replace(" ", ""))
    if not match:
        match = _DURATION_RE.match(text)
    if not match:
        return None

    value = int(match.group(1))
    unit = (match.group(2) or "s").lower()

    if unit in {"s", "sec", "secs", "second", "seconds"}:
        return value
    if unit in {"m", "min", "mins", "minute", "minutes"}:
        return value * 60
    if unit in {"h", "hr", "hrs", "hour", "hours"}:
        return value * 3600
    return None


def format_trial_ttl(seconds: int) -> str:
    if seconds <= 0:
        return "Off"
    if seconds < 60:
        return f"{seconds} second(s)" if seconds != 1 else "1 second"
    if seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} minute(s)" if minutes != 1 else "1 minute"
    hours = seconds // 3600
    remainder = seconds % 3600
    if remainder == 0:
        return f"{hours} hour(s)" if hours != 1 else "1 hour"
    minutes = remainder // 60
    return f"{hours}h {minutes}m"
