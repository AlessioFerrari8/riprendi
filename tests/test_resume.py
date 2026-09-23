import os
import stat
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from riprendi import resume
from riprendi.state import Tracked


class Resume(unittest.TestCase):
    def test_the_command_is_exactly_the_agreed_one(self):
        self.assertEqual(resume.build_command("abc"), [
            "claude", "--resume", "abc", "-p",
            "Il limite di utilizzo si e' sbloccato: continua da dove eri rimasto. Se il lavoro era finito, dillo e fermati.",
            "--permission-mode", "auto",
        ])
        self.assertNotIn("bypassPermissions", resume.build_command("abc"))

    def test_start_runs_in_the_session_folder_and_logs_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bin_dir, work, logs = tmp / "bin", tmp / "work", tmp / "logs"
            bin_dir.mkdir(); work.mkdir()
            fake = bin_dir / "claude"
            fake.write_text('#!/bin/sh\npwd\necho "$@"\n')
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            with mock.patch.dict(os.environ, {"PATH": f"{bin_dir}:{os.environ['PATH']}"}):
                pid = resume.start(Tracked("abc", "/p/abc.jsonl", str(work)), logs)
            for _ in range(50):
                if not resume.is_running(pid):
                    break
                time.sleep(0.05)
            log = next(logs.glob("abc-*.log")).read_text()
            self.assertIn(str(work), log)
            self.assertIn("--resume abc", log)

    def test_missing_claude_raises(self):
        # Review Focus 5: il chiamante lo trasforma in stato "errore".
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"PATH": tmp}):
                with self.assertRaises(FileNotFoundError):
                    resume.start(Tracked("abc", "/p", tmp), Path(tmp) / "logs")

    def test_is_running(self):
        self.assertTrue(resume.is_running(os.getpid()))
        self.assertFalse(resume.is_running(None))
        self.assertFalse(resume.is_running(2 ** 22 + 12345))

    def test_notify_never_raises(self):
        with mock.patch.dict(os.environ, {"PATH": "/nonexistent"}):
            resume.notify("titolo", "corpo")


if __name__ == "__main__":
    unittest.main()
