"""Subscription filter rules, stored as JSON on ``Subscription.filter_rule``.

``include_*`` must hit at least once to keep an entry; any ``exclude_*`` hit drops it.
An empty rule matches everything.

Keywords are case-insensitive. A keyword of pure ASCII word characters matches on WORD
BOUNDARIES (only ASCII word chars count as boundaries); anything else — CJK, ``c++`` —
keeps substring matching. A whole field written as ``/pattern/`` is one case-insensitive
regex instead of a keyword list.

Invalid stored patterns and match timeouts both fail OPEN with a warning; matching runs
on the mrab ``regex`` engine (see REGEX_MATCH_TIMEOUT_S). The text matched is the CLEANED
title + summary + content.
"""

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import regex

logger = logging.getLogger(__name__)

# Belt against pathological patterns; generous for real filters.
MAX_REGEX_LENGTH = 256

# Wall-clock budget for ONE user-regex application. User patterns compile under the
# mrab `regex` engine (stdlib `re` cannot be interrupted) and fail OPEN on timeout,
# same as an invalid stored pattern. Keyword matching stays on escaped stdlib re.
REGEX_MATCH_TIMEOUT_S = 0.1

# Pure-ASCII "word-ish" keyword: word chars, single spaces between them.
_WORDISH_RE = re.compile(r"^[A-Za-z0-9_]+(?: [A-Za-z0-9_]+)*$")


@lru_cache(maxsize=256)
def _compiled_regex(pattern: str) -> "regex.Pattern[str] | None":
    """Compile a stored filter regex; None (fail open, logged) if invalid."""
    try:
        return regex.compile(pattern, regex.IGNORECASE)
    except regex.error as e:
        logger.warning(f"Ignoring invalid filter regex {pattern!r}: {e}")
        return None


def _regex_hit(pattern: "regex.Pattern[str]", source: str, text: str) -> bool | None:
    """Apply a user regex under the match timeout.

    Returns True/False for a completed search, None when the timeout fired —
    callers treat None as "this pattern doesn't apply" (fail open)."""
    try:
        return pattern.search(text, timeout=REGEX_MATCH_TIMEOUT_S) is not None
    except TimeoutError:
        logger.warning(
            f"Filter regex {source!r} exceeded {REGEX_MATCH_TIMEOUT_S}s "
            f"on a {len(text)}-char entry; skipping it (fail open)"
        )
        return None


@lru_cache(maxsize=1024)
def _keyword_pattern(keyword: str) -> "re.Pattern[str] | None":
    """Word-boundary pattern for word-ish ASCII keywords; None → substring.

    Boundaries are ASCII-only lookarounds, not ``\\b``: ``\\b`` treats CJK
    ideographs as word characters, which would stop ``ai`` from matching
    "AI芯片" — and unspaced CJK context is exactly where the substring
    rationale applies.
    """
    if _WORDISH_RE.match(keyword):
        escaped = re.escape(keyword)
        return re.compile(rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])", re.IGNORECASE)
    return None


def _keyword_hit(keyword: str, text: str, lowered: str) -> bool:
    pattern = _keyword_pattern(keyword)
    if pattern is not None:
        return pattern.search(text) is not None
    return keyword.lower() in lowered


@dataclass(frozen=True)
class FilterRule:
    include_keywords: tuple[str, ...] = field(default_factory=tuple)
    exclude_keywords: tuple[str, ...] = field(default_factory=tuple)
    include_regex: str | None = None
    exclude_regex: str | None = None

    def is_empty(self) -> bool:
        return not (
            self.include_keywords
            or self.exclude_keywords
            or self.include_regex
            or self.exclude_regex
        )

    def matches(self, text: str) -> bool:
        """Return True if `text` passes the filter.

        `text` is the cleaned `title + summary + content`, built by the
        caller (see module docstring for the semantics).
        """
        if not text:
            text = ""
        lowered = text.lower()

        if self.include_regex:
            pattern = _compiled_regex(self.include_regex)
            if pattern is not None and _regex_hit(pattern, self.include_regex, text) is False:
                return False
        elif self.include_keywords:
            if not any(_keyword_hit(kw, text, lowered) for kw in self.include_keywords):
                return False

        if self.exclude_regex:
            pattern = _compiled_regex(self.exclude_regex)
            if pattern is not None and _regex_hit(pattern, self.exclude_regex, text) is True:
                return False
        if self.exclude_keywords:
            if any(_keyword_hit(kw, text, lowered) for kw in self.exclude_keywords):
                return False

        return True

    @classmethod
    def from_json(cls, data: dict[str, Any] | None) -> "FilterRule":
        if not data:
            return cls()
        return cls(
            include_keywords=tuple(data.get("include_keywords") or ()),
            exclude_keywords=tuple(data.get("exclude_keywords") or ()),
            include_regex=data.get("include_regex") or None,
            exclude_regex=data.get("exclude_regex") or None,
        )

    def to_json(self) -> dict[str, Any] | None:
        """Serialize for DB storage. Empty rules round-trip to None so we
        don't persist a row cluttered with empty arrays."""
        if self.is_empty():
            return None
        data: dict[str, Any] = {
            "include_keywords": list(self.include_keywords),
            "exclude_keywords": list(self.exclude_keywords),
        }
        if self.include_regex:
            data["include_regex"] = self.include_regex
        if self.exclude_regex:
            data["exclude_regex"] = self.exclude_regex
        return data


def parse_keyword_csv(raw: str | None) -> tuple[str, ...]:
    """Parse a user-supplied comma-separated keyword string.

    Trims whitespace on each token, drops empties. `None` or `""` → empty tuple.
    """
    if not raw:
        return ()
    return tuple(kw for kw in (item.strip() for item in raw.split(",")) if kw)


def parse_filter_field(raw: str | None) -> tuple[tuple[str, ...], str | None]:
    """Parse one include/exclude field → (keywords, regex).

    A whole field written as ``/pattern/`` is a single regex (validated
    here — raises ValueError with a user-facing message); anything else
    is a comma-separated keyword list. Exactly one of the two return
    slots is populated.
    """
    if raw is None:
        return (), None
    value = raw.strip()
    if len(value) >= 2 and value.startswith("/") and value.endswith("/"):
        pattern = value[1:-1]
        if not pattern:
            raise ValueError("empty regex")
        if len(pattern) > MAX_REGEX_LENGTH:
            raise ValueError(f"regex too long (max {MAX_REGEX_LENGTH} chars)")
        try:
            # Same engine as the runtime matcher (_compiled_regex) so
            # set-time acceptance and dispatch-time behavior can't diverge.
            regex.compile(pattern, regex.IGNORECASE)
        except regex.error as e:
            raise ValueError(f"invalid regex: {e}") from None
        return (), pattern
    return parse_keyword_csv(value), None
