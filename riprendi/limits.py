"""Detect a usage limit in Claude Code session logs and work out when it resets."""

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Resume a little after the reset: the time in the message is rounded.
RESUME_DELAY = timedelta(minutes=2)
# When the text does not say when, try again every half hour.
FALLBACK_DELAY = timedelta(minutes=30)

# "resets 11am (Europe/Rome)", "resets 3:30pm", "resets 15:00 (Europe/Rome)"
_RESET = re.compile(
    r"resets\s+(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ampm>am|pm)?(?:\s*\((?P<tz>[^)]+)\))?",
    re.IGNORECASE,
)


def is_limit_event(event: dict) -> bool:
    """The synthetic message Claude Code writes when the API answers with a usage limit."""
    return (
        event.get("type") == "assistant"
        and event.get("isApiErrorMessage") is True
        and event.get("error") == "rate_limit"
    )


def limit_text(event: dict) -> str:
    content = (event.get("message") or {}).get("content") or []
    if isinstance(content, str):
        return content
    return " ".join(part.get("text", "") for part in content if isinstance(part, dict))


def event_time(event: dict) -> datetime:
    return datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")).astimezone(timezone.utc)


def parse_reset(text: str, after: datetime) -> datetime | None:
    """The first moment after `after` at the clock time in the text, or None if it cannot be read."""
    match = _RESET.search(text)
    if not match:
        return None
    hour = int(match["h"])
    minute = int(match["m"] or 0)
    ampm = (match["ampm"] or "").lower()
    if ampm:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if ampm == "pm" else 0)
    if hour > 23 or minute > 59:
        return None
    try:
        zone = ZoneInfo(match["tz"].strip()) if match["tz"] else datetime.now().astimezone().tzinfo
    except (ZoneInfoNotFoundError, ValueError):
        return None

    local_after = after.astimezone(zone)
    candidate = local_after.replace(hour=hour, minute=minute, second=0, microsecond=0)
    # A time that has already passed means tomorrow, not this morning.
    if candidate <= local_after:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def resume_at(event: dict) -> datetime:
    """When to resume a session stopped on this error."""
    at = event_time(event)
    reset = parse_reset(limit_text(event), at)
    return reset + RESUME_DELAY if reset else at + FALLBACK_DELAY
