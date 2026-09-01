"""Safe filesystem components for gateway-derived identifiers (IA-260901-HP-03)."""

from __future__ import annotations

import hashlib
import re
import unicodedata

_WINDOWS_RESERVED = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})

_UNSAFE_PATH_RE = re.compile(r"(?:\.\.)|[/\\:\x00-\x1f]")


def safe_path_component(value: str, *, max_len: int = 128) -> str:
    raw = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not raw:
        raise ValueError("path_component_empty")
    if _UNSAFE_PATH_RE.search(raw):
        raise ValueError("path_component_unsafe")
    candidate = raw[:max_len]
    stem = candidate.rstrip(". ").upper()
    if stem in _WINDOWS_RESERVED:
        raise ValueError("path_component_reserved")
    return candidate


def safe_path_component_or_digest(value: str, *, prefix: str = "id", max_len: int = 128) -> str:
    try:
        return safe_path_component(value, max_len=max_len)
    except ValueError:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
        return f"{prefix}-{digest}"
