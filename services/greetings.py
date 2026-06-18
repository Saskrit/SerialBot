import re

GREETINGS = {
    "hi",
    "hello",
    "hey",
    "hii",
    "hiii",
    "hola",
    "sup",
    "yo",
}

GREETING_RE = re.compile(r"^(hi|hello|hey|hola|sup|yo)\b", re.IGNORECASE)


STATUS_QUERIES = {
    "status",
    "my status",
    "account status",
    "account",
    "vip status",
}


def is_status_query(text: str | None) -> bool:
    if not text:
        return False
    return text.strip().lower() in STATUS_QUERIES


def is_greeting(text: str | None) -> bool:
    if not text:
        return False
    cleaned = text.strip().lower()
    first_word = cleaned.split()[0] if cleaned else ""
    return first_word in GREETINGS or bool(GREETING_RE.match(cleaned))
