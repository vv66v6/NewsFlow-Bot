"""Timezone parsing and local->UTC schedule conversion for digest config.

Conversion happens once, at configuration time, anchored to the current date; the
database stores only UTC.

Accepted: IANA ``Region/City`` names (the ``tzdata`` wheel backs these on Windows),
fixed offsets (``+8``, ``-5:30``, ``+08:00``, ``UTC+8``, ``GMT-5``), and ``utc`` / ``gmt``.
Bare region-less names ("PST", "Singapore") are rejected.
"""

import re
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_OFFSET_RE = re.compile(r"^(?:utc|gmt)?([+-])(\d{1,2})(?::(\d{2}))?$", re.IGNORECASE)


def parse_timezone(value: str) -> tzinfo | None:
    """Parse a user-supplied timezone spelling; None when unrecognized."""
    raw = value.strip()
    if not raw:
        return None
    if raw.lower() in ("utc", "gmt"):
        return UTC
    m = _OFFSET_RE.match(raw)
    if m:
        sign = 1 if m.group(1) == "+" else -1
        hours = int(m.group(2))
        minutes = int(m.group(3) or 0)
        # Real-world offsets span UTC-12 … UTC+14.
        if hours > 14 or minutes > 59 or (hours == 14 and minutes > 0):
            return None
        return timezone(sign * timedelta(hours=hours, minutes=minutes))
    if "/" not in raw:
        return None
    try:
        return ZoneInfo(raw)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return None


def local_schedule_to_utc(
    hour: int,
    weekday: int | None,
    tz: tzinfo,
    *,
    now: datetime | None = None,
) -> tuple[int, int | None]:
    """Convert a local (hour, weekday) delivery schedule to UTC.

    ``weekday`` None means daily. Weekly conversion converts the
    (weekday, hour) pair jointly because the day can shift across the
    date line — Monday 04:00 UTC+8 is Sunday 20:00 UTC. Anchored to the
    next occurrence after ``now``.
    """
    anchor = (now or datetime.now(UTC)).astimezone(tz)
    local = anchor.replace(hour=hour, minute=0, second=0, microsecond=0)
    if weekday is not None:
        local += timedelta(days=(weekday - local.weekday()) % 7)
    if local < anchor:
        local += timedelta(days=7 if weekday is not None else 1)
    utc_dt = local.astimezone(UTC)
    return utc_dt.hour, (utc_dt.weekday() if weekday is not None else None)
