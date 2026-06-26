import difflib
import re

from database.connection import get_db

MIN_SUBSTRING_LEN = 5


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text)


def _word_boundary_phrase(phrase: str, text: str) -> bool:
    if not phrase or not text:
        return False
    pattern = rf"(?:^|\s){re.escape(phrase)}(?:\s|$)"
    return bool(re.search(pattern, text))


def _score_candidate(normalized_query: str, norm: str) -> float:
    if not norm:
        return 0.0

    if norm == normalized_query:
        return 1.0

    query_tokens = normalized_query.split()
    cand_tokens = norm.split()

    if len(cand_tokens) >= 2 and all(token in query_tokens for token in cand_tokens):
        return 0.92 + min(len(cand_tokens) * 0.01, 0.07)

    if len(norm) >= MIN_SUBSTRING_LEN and _word_boundary_phrase(norm, normalized_query):
        return 0.75 + (len(norm) / max(len(normalized_query), 1)) * 0.2

    if (
        len(normalized_query) >= MIN_SUBSTRING_LEN
        and len(normalized_query) >= len(norm) * 0.85
        and _word_boundary_phrase(normalized_query, norm)
    ):
        return 0.7 + (len(normalized_query) / max(len(norm), 1)) * 0.2

    score = difflib.SequenceMatcher(None, normalized_query, norm).ratio()

    if (
        len(query_tokens) >= 2
        and len(cand_tokens) < len(query_tokens)
        and not _word_boundary_phrase(norm, normalized_query)
    ):
        score = min(score, 0.55)

    return score


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
            score = _score_candidate(normalized_query, norm)
            if score > best_score:
                best_score = score
                best_match = serial

    if best_score >= 0.58:
        return best_match
    return None


async def match_serial_best_from_text(text: str) -> dict | None:
    """Try the full string and each | / newline segment; return best match."""
    normalized = _normalize(text)
    if not normalized:
        return None

    segments = [part.strip() for part in re.split(r"[|\n]+", text) if part.strip()]
    if not segments:
        segments = [text]

    best_serial = None
    best_score = 0.0

    for segment in segments:
        serial = await match_serial(segment)
        if not serial:
            continue
        score = _score_candidate(_normalize(segment), _normalize(serial["name"]))
        if score > best_score:
            best_score = score
            best_serial = serial

    return best_serial


async def search_serials(query: str, *, limit: int = 24) -> list[dict]:
    """Return active serials ranked by match score (for web search)."""
    normalized_query = _normalize(query)
    if not normalized_query:
        return []

    db = get_db()
    serials = await db.serials.find({"active": True}).to_list(length=200)
    scored: list[tuple[float, dict]] = []

    for serial in serials:
        candidates = [serial["name"], serial["slug"].replace("-", " ")]
        candidates.extend(serial.get("aliases", []))
        best_score = 0.0
        for candidate in candidates:
            best_score = max(
                best_score, _score_candidate(normalized_query, _normalize(candidate))
            )
        if best_score >= 0.45:
            scored.append((best_score, serial))

    scored.sort(key=lambda item: (-item[0], item[1]["name"]))
    results = []
    for _, serial in scored[:limit]:
        doc = dict(serial)
        doc["episode_count"] = await db.episodes.count_documents(
            {"serial_slug": serial["slug"]}
        )
        results.append(doc)
    return results
