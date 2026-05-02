"""Small, dependency-free text utilities used across the codebase."""

from __future__ import annotations

import re
import unicodedata


_CAMEL_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")
_NUMBERED_PREFIX_RE = re.compile(r"^\s*\d+\s*[\.\):\-]\s*")
_MULTI_WS_RE = re.compile(r"\s+")


def slugify(text: str) -> str:
    """Lowercase, ASCII-safe, hyphen-separated identifier."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "facet"


def split_camel(text: str) -> str:
    """Insert spaces in CamelCase, e.g. 'HonestyHumility' -> 'Honesty Humility'."""
    return _CAMEL_RE.sub(" ", text)


def normalize_facet_name(raw: str) -> str:
    """Apply the canonical name-cleaning sequence used by the data pipeline."""
    s = raw.replace(" ", " ").strip()
    s = _NUMBERED_PREFIX_RE.sub("", s)        # '793. Sufi practice...' -> 'Sufi practice...'
    s = s.rstrip(":;,.")                       # 'Democratic Leadership:' -> 'Democratic Leadership'
    s = split_camel(s)                         # 'HonestyHumility' -> 'Honesty Humility'
    s = _MULTI_WS_RE.sub(" ", s).strip()
    # Title-case-ish: keep acronyms uppercase, otherwise titlecase first letter
    if s and s[0].islower():
        s = s[0].upper() + s[1:]
    return s
