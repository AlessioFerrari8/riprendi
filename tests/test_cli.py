import io
import json
import os
import stat
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from riprendi import cli, resume
from riprendi.state import load

UTC = timezone.utc
LIMIT = {"type": "assistant", "isApiErrorMessage": True, "error": "rate_limit", "uuid": "e1",
         "timestamp": "2026-09-23T05:53:33Z",
         "message": {"content": [{"type": "text", "text": "your session limit resets 11am (Europe/Rome)"}]}}


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.home, self.projects, self.work, self.bin = root / "home", root / "projects", root / "work", root / "bin"
        for d in (self.projects / "-work", self.work, self.bin):
            d.mkdir(parents=True)
        self.session = self.projects / "-work" / "s1.jsonl"
        self.session.write_text(json.dumps({"type": "user", "uuid": "u0", "cwd": str(self.work)}) + "\n")
        # Fake claude: appends an answer to the session, as the real one would.
        fake = self.bin / "claude"
        fake.write_text(f'#!/bin/sh\necho \'{{"type": "assistant", "uuid": "done"}}\' >> "{self.session}"\n')
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.env = mock.patch.dict(os.environ, {
            "RIPRENDI_HOME": str(self.home), "RIPRENDI_PROJECTS": str(self.projects),
            "PATH": f"{self.bin}:{os.environ['PATH']}",
        })
        self.env.start()
        self.notify = mock.patch.object(resume, "notify").start()

    def tearDown(self):
        mock.patch.stopall()
        self.tmp.cleanup()

    def run_cli(self, *args) -> str:
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(list(args))
        self.assertEqual(code, 0)
        return out.getvalue()

    def test_follow_from_the_project_folder(self):
        old = os.getcwd()
        os.chdir(self.work)
        try:
            self.assertIn("s1", self.run_cli("follow"))
        finally:
            os.chdir(old)
        self.assertIn("s1", load(self.home))

    def test_unfollow(self):
        self.run_cli("follow", "s1")
        self.run_cli("unfollow", "s1")
        self.assertEqual(load(self.home), {})

    def test_full_cycle_blocked_then_resumed_then_finished(self):
        self.run_cli("follow", "s1")
        with self.session.open("a") as f:
            f.write(json.dumps(LIMIT) + "\n")

        cli.tick(self.home, self.projects, datetime(2026, 9, 23, 8, 0, tzinfo=UTC))
        self.assertEqual(load(self.home)["s1"].status, "blocked")

        cli.tick(self.home, self.projects, datetime(2026, 9, 23, 9, 5, tzinfo=UTC))
        state = load(self.home)["s1"]
        self.assertEqual(state.status, "resuming")
        for _ in range(100):
            if not resume.is_running(state.pid):
                break
            time.sleep(0.05)

        cli.tick(self.home, self.projects, datetime(2026, 9, 23, 9, 6, tzinfo=UTC))
        self.assertEqual(load(self.home)["s1"].status, "active")
        titles = [c.args[0] for c in self.notify.call_args_list]
        self.assertEqual(titles, ["Resumed", "Finished"])

    def test_missing_claude_becomes_error_and_follow_clears_it(self):
        self.run_cli("follow", "s1")
        with self.session.open("a") as f:
            f.write(json.dumps(LIMIT) + "\n")
        with mock.patch.dict(os.environ, {"PATH": "/nonexistent"}):
            cli.tick(self.home, self.projects, datetime(2026, 9, 23, 9, 5, tzinfo=UTC))
        self.assertEqual(load(self.home)["s1"].status, "error")
        self.run_cli("follow", "s1")
        self.assertEqual(load(self.home)["s1"].status, "active")

    def test_status_lists_sessions(self):
        self.run_cli("follow", "s1")
        self.assertIn(str(self.work), self.run_cli("status"))


if __name__ == "__main__":
    unittest.main()
