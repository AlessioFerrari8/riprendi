"""Comando `riprendi`: segue sessioni di Claude Code e le riprende quando il limite si sblocca."""

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import resume
from .decide import decide
from .sessions import find_session, find_session_for_cwd, last_significant_event, session_cwd
from .state import Tracked, load, save

INTERVAL_SECONDS = 60


def home_dir() -> Path:
    return Path(os.environ.get("RIPRENDI_HOME", Path.home() / ".local/state/riprendi"))


def projects_dir() -> Path:
    return Path(os.environ.get("RIPRENDI_PROJECTS", Path.home() / ".claude/projects"))


def _local(iso: str | None) -> str:
    return datetime.fromisoformat(iso).astimezone().strftime("%H:%M") if iso else "?"


def tick(home: Path, projects: Path, now: datetime) -> None:
    """Un giro del sorvegliante su tutte le sessioni seguite."""
    tracked = load(home)
    for t in tracked.values():
        path = Path(t.path)
        if not path.is_file():
            continue
        before = t.status
        decision = decide(t, last_significant_event(path), now, running=resume.is_running(t.pid))
        folder = Path(t.cwd).name or t.cwd

        if decision.kind == "riprendi":
            try:
                t.pid = resume.start(t, home / "logs")
                t.status = "in ripresa"
                resume.notify("Ripresa", f"{folder}: la sessione riparte")
            except (FileNotFoundError, OSError) as error:
                t.status = "errore"
                resume.notify("riprendi: errore", f"{folder}: {error}")
        elif decision.kind == "ferma":
            resume.notify("Ferma", f"{folder}: di nuovo sul limite dopo piu' tentativi, riprendi tu")
        elif before == "in ripresa" and t.status == "attiva":
            resume.notify("Finita", f"{folder}: la ripresa ha lavorato")
        elif before == "in ripresa" and t.status == "bloccata":
            resume.notify("Di nuovo bloccata", f"{folder}: riprovo alle {_local(t.next_at)}")
    save(home, tracked)


def _segui(args) -> int:
    projects, home = projects_dir(), home_dir()
    if args.session:
        path = find_session(args.session, projects)
        found = (args.session, path) if path else None
    else:
        found = find_session_for_cwd(os.getcwd(), projects)
    if not found:
        print("Nessuna sessione trovata" + ("" if args.session else " per questa cartella"), file=sys.stderr)
        return 1
    session_id, path = found
    tracked = load(home)
    # Rilanciare `segui` rimette in gioco anche una sessione finita in errore.
    tracked[session_id] = Tracked(session_id, str(path), session_cwd(path) or os.getcwd())
    save(home, tracked)
    print(f"Seguo {session_id} ({tracked[session_id].cwd})")
    return 0


def _smetti(args) -> int:
    home = home_dir()
    tracked = load(home)
    session_id = args.session
    if not session_id:
        found = find_session_for_cwd(os.getcwd(), projects_dir())
        session_id = found[0] if found else None
    if session_id not in tracked:
        print("Questa sessione non e' seguita", file=sys.stderr)
        return 1
    del tracked[session_id]
    save(home, tracked)
    print(f"Non seguo piu' {session_id}")
    return 0


def _stato(_args) -> int:
    tracked = load(home_dir())
    if not tracked:
        print("Nessuna sessione seguita. Usa `riprendi segui` nella cartella del progetto.")
        return 0
    for t in tracked.values():
        status = f"bloccata fino alle {_local(t.next_at)}" if t.status == "bloccata" else t.status
        print(f"{t.session_id}  {t.cwd}  {status}  riprese: {t.attempts}")
    return 0


def _sorveglia(args) -> int:
    while True:
        tick(home_dir(), projects_dir(), datetime.now(timezone.utc))
        if args.once:
            return 0
        time.sleep(args.intervallo)


UNIT = """[Unit]
Description=riprendi: riprende le sessioni di Claude Code quando il limite si sblocca

[Service]
ExecStart={python} -m riprendi sorveglia
WorkingDirectory={repo}
Environment=PYTHONPATH={repo}
Environment=PATH={path}
Restart=on-failure
RestartSec=30

[Install]
WantedBy=default.target
"""


def _installa(_args) -> int:
    repo = Path(__file__).resolve().parent.parent
    claude = subprocess.run(["sh", "-c", "command -v claude"], capture_output=True, text=True).stdout.strip()
    if not claude:
        print("claude non e' nel PATH: installalo prima", file=sys.stderr)
        return 1
    # Il servizio non eredita il PATH della shell: ci va la cartella di claude, esplicitamente.
    path = ":".join(dict.fromkeys([str(Path(claude).parent), "/usr/local/bin", "/usr/bin", "/bin"]))
    unit_dir = Path.home() / ".config/systemd/user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    (unit_dir / "riprendi.service").write_text(UNIT.format(python=sys.executable, repo=repo, path=path))

    launcher = Path.home() / ".local/bin/riprendi"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text(f'#!/bin/sh\nPYTHONPATH="{repo}" exec "{sys.executable}" -m riprendi "$@"\n')
    launcher.chmod(0o755)

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", "riprendi.service"], check=True)
    print(f"Servizio attivo. Comando installato in {launcher}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="riprendi", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("segui", help="segue la sessione di questa cartella (o quella indicata)")
    p.add_argument("session", nargs="?")
    p.set_defaults(run=_segui)
    p = sub.add_parser("smetti", help="smette di seguire una sessione")
    p.add_argument("session", nargs="?")
    p.set_defaults(run=_smetti)
    sub.add_parser("stato", help="elenca le sessioni seguite").set_defaults(run=_stato)
    p = sub.add_parser("sorveglia", help="il ciclo del sorvegliante (lo lancia systemd)")
    p.add_argument("--once", action="store_true")
    p.add_argument("--intervallo", type=int, default=INTERVAL_SECONDS)
    p.set_defaults(run=_sorveglia)
    sub.add_parser("installa", help="installa il servizio systemd e il comando").set_defaults(run=_installa)
    args = parser.parse_args(argv)
    return args.run(args)
