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


def is_greeting(text: str | None) -> bool:
    if not text:
        return False
    cleaned = text.strip().lower()
    first_word = cleaned.split()[0] if cleaned else ""
    return first_word in GREETINGS or bool(GREETING_RE.match(cleaned))
