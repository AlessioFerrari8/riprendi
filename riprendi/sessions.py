"""Read Claude Code session files (~/.claude/projects/<folder>/<id>.jsonl)."""

import json
from pathlib import Path

_SIGNIFICANT = {"user", "assistant"}
_BLOCK = 256 * 1024


def _lines_from_end(path: Path):
    """The file's lines from last to first, without loading it all: sessions can weigh tens of MB."""
    with path.open("rb") as handle:
        handle.seek(0, 2)
        position = handle.tell()
        rest = b""
        while position > 0:
            size = min(_BLOCK, position)
            position -= size
            handle.seek(position)
            chunk = handle.read(size) + rest
            lines = chunk.split(b"\n")
            rest = lines.pop(0)
            for line in reversed(lines):
                yield line
        if rest:
            yield rest


def last_significant_event(path: Path) -> dict | None:
    """The last user or assistant line. A half-written line is skipped."""
    if not path.is_file():
        return None
    for raw in _lines_from_end(path):
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") in _SIGNIFICANT:
            return event
    return None


def session_cwd(path: Path) -> str | None:
    """The session's working directory, from the first line that records it."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                try:
                    event = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(event, dict) and event.get("cwd"):
                    return event["cwd"]
    except OSError:
        return None
    return None


def _top_level_sessions(projects: Path):
    # Only <folder>/<id>.jsonl: subagents live further down, in <id>/subagents/.
    return projects.glob("*/*.jsonl")


def find_session_for_cwd(cwd: str, projects: Path) -> tuple[str, Path] | None:
    """The most recently modified session working in `cwd`.

    The folder name is derived from the path by an undocumented rule, so the `cwd`
    recorded inside the file is compared instead: that is the real data.
    """
    target = str(Path(cwd).resolve())
    best: tuple[float, str, Path] | None = None
    for path in _top_level_sessions(projects):
        found = session_cwd(path)
        if not found or str(Path(found).resolve()) != target:
            continue
        mtime = path.stat().st_mtime
        if best is None or mtime > best[0]:
            best = (mtime, path.stem, path)
    return (best[1], best[2]) if best else None


def find_session(session_id: str, projects: Path) -> Path | None:
    for path in _top_level_sessions(projects):
        if path.stem == session_id:
            return path
    return None
