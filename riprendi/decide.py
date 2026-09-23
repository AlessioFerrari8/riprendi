"""What to do with a followed session, given its last event. No side effects."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .limits import FALLBACK_DELAY, is_limit_event, resume_at
from .state import Tracked

# Stop after this many resumes that end on the limit again: that is what a monthly
# spending limit looks like, and it does not reset at a clock time.
MAX_ATTEMPTS = 3

ACTIVE = "active"
BLOCKED = "blocked"
RESUMING = "resuming"
STOPPED = "stopped: too many attempts"
ERROR = "error"


@dataclass
class Decision:
    kind: Literal["nothing", "wait", "resume", "stop"]
    at: datetime | None = None


def decide(t: Tracked, event: dict | None, now: datetime, running: bool) -> Decision:
    """Update `t` and say what to do. `running`: a resume we started is still going."""
    if t.status == ERROR or running:
        return Decision("nothing")

    if event is None or not is_limit_event(event):
        # The session is working (or someone resumed it by hand): reset everything.
        t.status, t.attempts, t.error_uuid, t.next_at = ACTIVE, 0, None, None
        return Decision("nothing")

    uuid = event.get("uuid")
    if t.status == STOPPED and uuid == t.error_uuid:
        return Decision("nothing")

    at = resume_at(event)
    if t.status == RESUMING:
        # The resume ended and the session is on the limit again: that counts as an attempt.
        t.attempts += 1
        if uuid == t.error_uuid:
            # It wrote nothing: wait instead of relaunching straight away.
            at = now + FALLBACK_DELAY
    t.error_uuid = uuid

    if t.attempts >= MAX_ATTEMPTS:
        t.status, t.next_at = STOPPED, None
        return Decision("stop")

    if t.next_at and t.status == BLOCKED:
        # A wait already decided (e.g. half an hour after an empty resume) is never shortened.
        at = max(at, datetime.fromisoformat(t.next_at))
    t.next_at = at.isoformat()
    if now < at:
        t.status = BLOCKED
        return Decision("wait", at)
    return Decision("resume", at)
