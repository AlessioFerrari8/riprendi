"""Riconoscere un limite di utilizzo nei log di Claude Code e capire quando si sblocca."""

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Si riprende un po' dopo lo sblocco: l'orario del messaggio e' arrotondato all'ora.
RESUME_DELAY = timedelta(minutes=2)
# Se il testo non dice quando, si riprova ogni mezz'ora.
FALLBACK_DELAY = timedelta(minutes=30)

# "resets 11am (Europe/Rome)", "resets 3:30pm", "resets 15:00 (Europe/Rome)"
_RESET = re.compile(
    r"resets\s+(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ampm>am|pm)?(?:\s*\((?P<tz>[^)]+)\))?",
    re.IGNORECASE,
)


def is_limit_event(event: dict) -> bool:
    """Il messaggio sintetico che Claude Code scrive quando l'API risponde con un limite."""
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
    """Il primo istante dopo `after` con l'ora indicata nel testo, o None se non si capisce."""
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
    # Un orario gia' passato e' quello di domani, non di stamattina.
    if candidate <= local_after:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def resume_at(event: dict) -> datetime:
    """Quando riprendere la sessione ferma su questo errore."""
    at = event_time(event)
    reset = parse_reset(limit_text(event), at)
    return reset + RESUME_DELAY if reset else at + FALLBACK_DELAY
