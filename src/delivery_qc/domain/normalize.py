from __future__ import annotations

import re
import unicodedata


_SPACE_RE = re.compile(r"\s+")
_STATUS_SEPARATOR_RE = re.compile(r"[_\-]+")
_COUNT_RE = re.compile(
    r"(?P<count>\d+)\s*(?:pallets?|carts?|containers?|crates?|bundles?|racks?)\b",
    re.IGNORECASE,
)


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = normalized.replace("–", "-").replace("—", "-")
    return _SPACE_RE.sub(" ", normalized.strip()).casefold()


def normalize_status(value: str) -> str:
    normalized = _STATUS_SEPARATOR_RE.sub(" ", value or "")
    return normalize_text(normalized)


def status_matches(value: str, accepted_statuses: tuple[str, ...]) -> bool:
    normalized_value = normalize_status(value)
    terminal_value = normalize_status(re.split(r"\s+-\s+", value or "")[-1])
    normalized_accepted = {normalize_status(status) for status in accepted_statuses}
    return normalized_value in normalized_accepted or terminal_value in normalized_accepted


def parse_container_count(value: str) -> int | None:
    matches = [int(match.group("count")) for match in _COUNT_RE.finditer(value or "")]
    if matches:
        return sum(matches)
    stripped = (value or "").strip()
    return int(stripped) if stripped.isdigit() else None


def parse_container_names(value: str) -> tuple[str, ...]:
    parts = re.split(r"[,;|]", value or "")
    return tuple(part.strip() for part in parts if part.strip())
