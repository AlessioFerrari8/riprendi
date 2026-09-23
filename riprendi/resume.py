"""Start the resume of a session and send desktop notifications."""

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from .state import Tracked

PROMPT = (
    "The usage limit has reset: continue from where you left off. "
    "If the work was already finished, say so and stop."
)


def build_command(session_id: str) -> list[str]:
    # `auto`: nobody is there to answer permission prompts, but risky actions stay blocked.
    return ["claude", "--resume", session_id, "-p", PROMPT, "--permission-mode", "auto"]


def start(t: Tracked, logs: Path) -> int:
    """Start the resume in the background, in the session's folder, and return its pid."""
    if shutil.which("claude") is None:
        raise FileNotFoundError("claude is not on PATH")
    logs.mkdir(parents=True, exist_ok=True)
    log_path = logs / f"{t.session_id}-{datetime.now():%Y%m%d-%H%M%S}.log"
    with log_path.open("w") as log:
        process = subprocess.Popen(
            build_command(t.session_id),
            cwd=t.cwd,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            # Own session: stopping the watcher must not kill the resumed work.
            start_new_session=True,
        )
    return process.pid


def is_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        # If it is our child it must be reaped, or it stays a zombie and looks alive.
        done, _ = os.waitpid(pid, os.WNOHANG)
        return done == 0
    except ChildProcessError:
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def notify(title: str, body: str) -> None:
    """Desktop notification; if that is not possible (no graphical session), never mind."""
    try:
        subprocess.run(["notify-send", "--app-name=riprendi", title, body],
                       check=False, timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        pass
