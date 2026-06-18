import difflib
import re

from database.connection import get_db


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text)


async def match_serial(query: str) -> dict | None:
    normalized_query = _normalize(query)
    if not normalized_query:
        return None

    serials = await get_db().serials.find({"active": True}).to_list(length=200)
    if not serials:
        return None

    best_match = None
    best_score = 0.0

    for serial in serials:
        candidates = [serial["name"], serial["slug"].replace("-", " ")]
        candidates.extend(serial.get("aliases", []))

        for candidate in candidates:
            norm = _normalize(candidate)
            if not norm:
                continue

            if norm in normalized_query or normalized_query in norm:
                return serial

            score = difflib.SequenceMatcher(None, normalized_query, norm).ratio()
            if score > best_score:
                best_score = score
                best_match = serial

    if best_score >= 0.55:
        return best_match
    return None
