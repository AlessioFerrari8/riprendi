import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from riprendi.decide import MAX_ATTEMPTS, decide
from riprendi.state import Tracked, load, save

UTC = timezone.utc


def limit(uuid: str, when: str = "2026-09-23T05:53:33Z") -> dict:
    return {"type": "assistant", "isApiErrorMessage": True, "error": "rate_limit", "uuid": uuid, "timestamp": when,
            "message": {"content": [{"type": "text", "text": "your session limit resets 11am (Europe/Rome)"}]}}


def tracked(**kw) -> Tracked:
    return Tracked(session_id="s1", path="/p/s1.jsonl", cwd="/work", **kw)


BEFORE = datetime(2026, 9, 23, 8, 0, tzinfo=UTC)   # 10:00 a Roma
AFTER = datetime(2026, 9, 23, 9, 5, tzinfo=UTC)    # 11:05 a Roma


class Decide(unittest.TestCase):
    def test_a_working_session_needs_nothing_and_resets_the_count(self):
        t = tracked(attempts=2, status="bloccata")
        self.assertEqual(decide(t, {"type": "assistant", "uuid": "x"}, AFTER, running=False).kind, "nulla")
        self.assertEqual((t.status, t.attempts), ("attiva", 0))

    def test_blocked_waits_until_two_minutes_after_the_reset(self):
        t = tracked()
        d = decide(t, limit("e1"), BEFORE, running=False)
        self.assertEqual(d.kind, "attendi")
        self.assertEqual(d.at, datetime(2026, 9, 23, 9, 2, tzinfo=UTC))
        self.assertEqual(t.status, "bloccata")

    def test_after_the_reset_it_resumes(self):
        t = tracked()
        self.assertEqual(decide(t, limit("e1"), AFTER, running=False).kind, "riprendi")

    def test_never_twice_while_a_resume_is_running(self):
        # Review Focus 3.
        t = tracked(status="in ripresa", error_uuid="e1")
        self.assertEqual(decide(t, limit("e1"), AFTER, running=True).kind, "nulla")

    def test_a_resume_that_hits_the_limit_again_counts_as_an_attempt(self):
        t = tracked(status="in ripresa", error_uuid="e1", attempts=0)
        decide(t, limit("e2", "2026-09-23T09:03:00Z"), AFTER, running=False)
        self.assertEqual(t.attempts, 1)
        self.assertEqual(t.error_uuid, "e2")

    def test_a_resume_that_wrote_nothing_counts_and_waits_half_an_hour(self):
        # La ripresa e' finita senza scrivere niente (rete giu', claude in errore): stesso
        # errore di prima. Senza questa regola si riprenderebbe a raffica, un giro al minuto.
        t = tracked(status="in ripresa", error_uuid="e1", attempts=0)
        d = decide(t, limit("e1"), AFTER, running=False)
        self.assertEqual(t.attempts, 1)
        self.assertEqual(d.kind, "attendi")
        self.assertEqual(d.at, datetime(2026, 9, 23, 9, 35, tzinfo=UTC))

    def test_same_error_seen_again_is_not_a_new_attempt(self):
        t = tracked(status="bloccata", error_uuid="e1", attempts=1)
        decide(t, limit("e1"), BEFORE, running=False)
        self.assertEqual(t.attempts, 1)

    def test_stops_after_three_failed_resumes(self):
        t = tracked(status="in ripresa", error_uuid="e3", attempts=MAX_ATTEMPTS - 1)
        d = decide(t, limit("e4", "2026-09-23T09:03:00Z"), AFTER, running=False)
        self.assertEqual(d.kind, "ferma")
        self.assertEqual(t.status, "ferma: troppi tentativi")
        # e resta ferma ai giri successivi, senza notificare di nuovo
        self.assertEqual(decide(t, limit("e4", "2026-09-23T09:03:00Z"), AFTER, running=False).kind, "nulla")

    def test_a_stopped_session_restarts_by_itself_if_work_resumes(self):
        t = tracked(status="ferma: troppi tentativi", attempts=MAX_ATTEMPTS)
        decide(t, {"type": "user", "uuid": "manual"}, AFTER, running=False)
        self.assertEqual((t.status, t.attempts), ("attiva", 0))

    def test_errore_status_is_sticky(self):
        t = tracked(status="errore")
        self.assertEqual(decide(t, limit("e1"), AFTER, running=False).kind, "nulla")


class State(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as home:
            data = {"s1": tracked(status="bloccata", attempts=1, error_uuid="e1", pid=42, next_at="2026-09-23T09:02:00+00:00")}
            save(Path(home), data)
            self.assertEqual(load(Path(home)), data)

    def test_missing_or_broken_state_is_empty(self):
        with tempfile.TemporaryDirectory() as home:
            self.assertEqual(load(Path(home)), {})
            (Path(home) / "state.json").write_text("{not json")
            self.assertEqual(load(Path(home)), {})


if __name__ == "__main__":
    unittest.main()
