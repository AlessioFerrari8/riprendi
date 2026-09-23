"""riprendi: follow Claude Code sessions and resume them when their usage limit resets."""

import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import __version__, resume
from .decide import BLOCKED, RESUMING, ACTIVE, ERROR, decide
from .sessions import find_session, find_session_for_cwd, last_significant_event, session_cwd
from .state import Tracked, load, save

INTERVAL_SECONDS = 60
UNIT_NAME = "riprendi.service"


def home_dir() -> Path:
    return Path(os.environ.get("RIPRENDI_HOME", Path.home() / ".local/state/riprendi"))


def projects_dir() -> Path:
    return Path(os.environ.get("RIPRENDI_PROJECTS", Path.home() / ".claude/projects"))


def unit_path() -> Path:
    return Path.home() / ".config/systemd/user" / UNIT_NAME


def _local(iso: str | None) -> str:
    return datetime.fromisoformat(iso).astimezone().strftime("%H:%M") if iso else "?"


def tick(home: Path, projects: Path, now: datetime) -> None:
    """One pass of the watcher over every followed session."""
    tracked = load(home)
    for t in tracked.values():
        path = Path(t.path)
        if not path.is_file():
            continue
        before = t.status
        decision = decide(t, last_significant_event(path), now, running=resume.is_running(t.pid))
        folder = Path(t.cwd).name or t.cwd

        if decision.kind == "resume":
            try:
                t.pid = resume.start(t, home / "logs")
                t.status = RESUMING
                resume.notify("Resumed", f"{folder}: the session is running again")
            except OSError as error:
                t.status = ERROR
                resume.notify("riprendi: error", f"{folder}: {error}")
        elif decision.kind == "stop":
            resume.notify("Stopped", f"{folder}: hit the limit again after several attempts, over to you")
        elif before == RESUMING and t.status == ACTIVE:
            resume.notify("Finished", f"{folder}: the resumed session did its work")
        elif before == RESUMING and t.status == BLOCKED:
            resume.notify("Blocked again", f"{folder}: retrying at {_local(t.next_at)}")
    save(home, tracked)


def _follow(args) -> int:
    projects, home = projects_dir(), home_dir()
    if args.session:
        path = find_session(args.session, projects)
        found = (args.session, path) if path else None
    else:
        found = find_session_for_cwd(os.getcwd(), projects)
    if not found:
        print("No session found" + ("" if args.session else " for this folder"), file=sys.stderr)
        return 1
    session_id, path = found
    tracked = load(home)
    # Following again also brings back a session that ended in error.
    tracked[session_id] = Tracked(session_id, str(path), session_cwd(path) or os.getcwd())
    save(home, tracked)
    print(f"Following {session_id} ({tracked[session_id].cwd})")
    return 0


def _unfollow(args) -> int:
    home = home_dir()
    tracked = load(home)
    session_id = args.session
    if not session_id:
        found = find_session_for_cwd(os.getcwd(), projects_dir())
        session_id = found[0] if found else None
    if session_id not in tracked:
        print("This session is not followed", file=sys.stderr)
        return 1
    del tracked[session_id]
    save(home, tracked)
    print(f"No longer following {session_id}")
    return 0


def _status(_args) -> int:
    tracked = load(home_dir())
    if not tracked:
        print("No followed sessions. Run `riprendi follow` in the project folder.")
        return 0
    for t in tracked.values():
        status = f"blocked until {_local(t.next_at)}" if t.status == BLOCKED else t.status
        print(f"{t.session_id}  {t.cwd}  {status}  attempts: {t.attempts}")
    return 0


def _watch(args) -> int:
    while True:
        tick(home_dir(), projects_dir(), datetime.now(timezone.utc))
        if args.once:
            return 0
        time.sleep(args.interval)


UNIT = """[Unit]
Description=riprendi: resume Claude Code sessions when their usage limit resets

[Service]
ExecStart={python} -m riprendi watch
Environment=PATH={path}
{pythonpath}Restart=on-failure
RestartSec=30

[Install]
WantedBy=default.target
"""


def render_unit(python: str, claude: str, source_root: str | None) -> str:
    """The systemd unit. A service does not inherit the shell's PATH, so claude's folder goes in explicitly."""
    path = ":".join(dict.fromkeys([str(Path(claude).parent), "/usr/local/bin", "/usr/bin", "/bin"]))
    pythonpath = f"Environment=PYTHONPATH={source_root}\n" if source_root else ""
    return UNIT.format(python=python, path=path, pythonpath=pythonpath)


def _source_root() -> str | None:
    """Running from a clone rather than an installed package: the service needs PYTHONPATH."""
    package = Path(__file__).resolve().parent
    return None if "site-packages" in package.parts else str(package.parent)


def _install(_args) -> int:
    claude = shutil.which("claude")
    if not claude:
        print("claude is not on PATH: install Claude Code first", file=sys.stderr)
        return 1
    if not shutil.which("systemctl"):
        print("systemctl not found: riprendi needs systemd user services", file=sys.stderr)
        return 1
    unit = unit_path()
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text(render_unit(sys.executable, claude, _source_root()))
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", UNIT_NAME], check=True)
    print(f"Watcher installed and running ({unit}).")
    return 0


def _uninstall(_args) -> int:
    unit = unit_path()
    if shutil.which("systemctl"):
        subprocess.run(["systemctl", "--user", "disable", "--now", UNIT_NAME], check=False)
    unit.unlink(missing_ok=True)
    if shutil.which("systemctl"):
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    print(f"Watcher removed. State and logs are still in {home_dir()}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="riprendi", description=__doc__)
    parser.add_argument("--version", action="version", version=f"riprendi {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("follow", help="follow this folder's latest session (or the given one)")
    p.add_argument("session", nargs="?")
    p.set_defaults(run=_follow)
    p = sub.add_parser("unfollow", help="stop following a session")
    p.add_argument("session", nargs="?")
    p.set_defaults(run=_unfollow)
    sub.add_parser("status", help="list followed sessions").set_defaults(run=_status)
    p = sub.add_parser("watch", help="the watcher loop (systemd runs it)")
    p.add_argument("--once", action="store_true", help="a single pass, then exit")
    p.add_argument("--interval", type=int, default=INTERVAL_SECONDS, help="seconds between passes")
    p.set_defaults(run=_watch)
    sub.add_parser("install", help="install and start the systemd user service").set_defaults(run=_install)
    sub.add_parser("uninstall", help="stop and remove the systemd user service").set_defaults(run=_uninstall)
    args = parser.parse_args(argv)
    return args.run(args)
