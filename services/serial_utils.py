import re


def slugify_serial_name(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug.strip("-")


def parse_add_serial_input(text: str) -> tuple[str, list[str]]:
    if "|" in text:
        name_part, aliases_part = text.split("|", 1)
        aliases = [part.strip() for part in aliases_part.split(",") if part.strip()]
    else:
        name_part = text
        aliases = []
    return name_part.strip(), aliases
