"""Che cosa fare con una sessione seguita, dato il suo ultimo evento. Nessun effetto esterno."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .limits import FALLBACK_DELAY, is_limit_event, resume_at
from .state import Tracked

# Oltre queste riprese finite di nuovo sul limite ci si ferma: e' il caso del limite
# mensile, che a un orario non si sblocca, e insistere consumerebbe solo tentativi.
MAX_ATTEMPTS = 3

STOPPED = "ferma: troppi tentativi"


@dataclass
class Decision:
    kind: Literal["nulla", "attendi", "riprendi", "ferma"]
    at: datetime | None = None


def decide(t: Tracked, event: dict | None, now: datetime, running: bool) -> Decision:
    """Aggiorna `t` e dice cosa fare. `running`: una ripresa lanciata da noi e' ancora in corso."""
    if t.status == "errore" or running:
        return Decision("nulla")

    if event is None or not is_limit_event(event):
        # La sessione lavora (o qualcuno l'ha ripresa a mano): tutto azzerato.
        t.status, t.attempts, t.error_uuid, t.next_at = "attiva", 0, None, None
        return Decision("nulla")

    uuid = event.get("uuid")
    if t.status == STOPPED and uuid == t.error_uuid:
        return Decision("nulla")

    at = resume_at(event)
    if t.status == "in ripresa":
        # La ripresa e' finita ed e' ancora fermo sul limite: conta come tentativo.
        t.attempts += 1
        if uuid == t.error_uuid:
            # Non ha scritto niente: si aspetta, invece di rilanciare subito.
            at = now + FALLBACK_DELAY
    t.error_uuid = uuid

    if t.attempts >= MAX_ATTEMPTS:
        t.status, t.next_at = STOPPED, None
        return Decision("ferma")

    if t.next_at and t.status == "bloccata":
        # Un'attesa gia' decisa (es. la mezz'ora dopo una ripresa a vuoto) non si accorcia.
        at = max(at, datetime.fromisoformat(t.next_at))
    t.next_at = at.isoformat()
    if now < at:
        t.status = "bloccata"
        return Decision("attendi", at)
    return Decision("riprendi", at)
