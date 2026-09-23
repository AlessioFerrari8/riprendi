"""Lanciare la ripresa di una sessione e avvisare sul desktop."""

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from .state import Tracked

PROMPT = (
    "Il limite di utilizzo si e' sbloccato: continua da dove eri rimasto. "
    "Se il lavoro era finito, dillo e fermati."
)


def build_command(session_id: str) -> list[str]:
    # `auto`: nessuno risponde alle richieste di permesso, ma le azioni rischiose restano bloccate.
    return ["claude", "--resume", session_id, "-p", PROMPT, "--permission-mode", "auto"]


def start(t: Tracked, logs: Path) -> int:
    """Avvia la ripresa in background nella cartella della sessione e ne restituisce il pid."""
    if shutil.which("claude") is None:
        raise FileNotFoundError("claude non e' nel PATH")
    logs.mkdir(parents=True, exist_ok=True)
    log_path = logs / f"{t.session_id}-{datetime.now():%Y%m%d-%H%M%S}.log"
    with log_path.open("w") as log:
        process = subprocess.Popen(
            build_command(t.session_id),
            cwd=t.cwd,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            # Sessione propria: fermare il sorvegliante non deve interrompere il lavoro ripreso.
            start_new_session=True,
        )
    return process.pid


def is_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        # Se e' un nostro figlio va raccolto, altrimenti resterebbe zombie e sembrerebbe vivo.
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
    """Notifica sul desktop; se non si puo' (nessuna sessione grafica), pazienza."""
    try:
        subprocess.run(["notify-send", "--app-name=riprendi", title, body],
                       check=False, timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        pass
