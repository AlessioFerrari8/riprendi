import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from riprendi.sessions import find_session, find_session_for_cwd, last_significant_event, session_cwd


def write(path: Path, lines: list, tail: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(l) + "\n" for l in lines) + tail)
    return path


class Sessions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.projects = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_last_significant_event_skips_other_types(self):
        path = write(self.projects / "p" / "s1.jsonl", [
            {"type": "user", "uuid": "a", "cwd": "/w"},
            {"type": "assistant", "uuid": "b"},
            {"type": "system", "uuid": "c"},
            {"type": "summary", "uuid": "d"},
        ])
        self.assertEqual(last_significant_event(path)["uuid"], "b")

    def test_a_half_written_last_line_is_skipped(self):
        # Claude Code may be writing while we read.
        path = write(self.projects / "p" / "s1.jsonl", [{"type": "user", "uuid": "a"}], tail='{"type": "assis')
        self.assertEqual(last_significant_event(path)["uuid"], "a")

    def test_missing_or_empty_file(self):
        self.assertIsNone(last_significant_event(self.projects / "nope.jsonl"))
        self.assertIsNone(last_significant_event(write(self.projects / "p" / "e.jsonl", [])))

    def test_session_cwd(self):
        path = write(self.projects / "p" / "s1.jsonl", [{"type": "summary"}, {"type": "user", "cwd": "/work/app"}])
        self.assertEqual(session_cwd(path), "/work/app")

    def test_find_session_for_cwd_picks_the_most_recent_and_ignores_subagents(self):
        old = write(self.projects / "-work-app" / "old.jsonl", [{"type": "user", "cwd": "/work/app"}])
        new = write(self.projects / "-work-app" / "new.jsonl", [{"type": "user", "cwd": "/work/app"}])
        sub = write(self.projects / "-work-app" / "new" / "subagents" / "agent-x.jsonl", [{"type": "user", "cwd": "/work/app"}])
        other = write(self.projects / "-work-other" / "o.jsonl", [{"type": "user", "cwd": "/work/other"}])
        now = time.time()
        os.utime(old, (now - 100, now - 100))
        os.utime(new, (now - 50, now - 50))
        os.utime(sub, (now, now))
        os.utime(other, (now, now))

        self.assertEqual(find_session_for_cwd("/work/app", self.projects), ("new", new))

    def test_find_session_for_cwd_none(self):
        self.assertIsNone(find_session_for_cwd("/nowhere", self.projects))

    def test_find_session_by_id(self):
        path = write(self.projects / "-work-app" / "abc.jsonl", [{"type": "user"}])
        self.assertEqual(find_session("abc", self.projects), path)
        self.assertIsNone(find_session("zzz", self.projects))


if __name__ == "__main__":
    unittest.main()
