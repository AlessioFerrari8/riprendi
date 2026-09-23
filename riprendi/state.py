"""Followed sessions, stored in state.json."""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

STATE_FILE = "state.json"


@dataclass
class Tracked:
    session_id: str
    path: str
    cwd: str
    status: str = "active"
    attempts: int = 0
    # ISO, UTC: when the next resume is due.
    next_at: str | None = None
    # The limit error the session is stopped on: tells whether a resume produced anything.
    error_uuid: str | None = None
    pid: int | None = None


def load(home: Path) -> dict[str, Tracked]:
    try:
        raw = json.loads((home / STATE_FILE).read_text())
        return {key: Tracked(**value) for key, value in raw.items()}
    except (OSError, ValueError, TypeError):
        return {}


def save(home: Path, tracked: dict[str, Tracked]) -> None:
    home.mkdir(parents=True, exist_ok=True)
    tmp = home / (STATE_FILE + ".tmp")
    tmp.write_text(json.dumps({key: asdict(value) for key, value in tracked.items()}, indent=2))
    # Atomic replace: a half-written state file must never exist.
    os.replace(tmp, home / STATE_FILE)
