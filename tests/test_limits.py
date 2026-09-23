import unittest
from datetime import datetime, timedelta, timezone

from riprendi.limits import (
    FALLBACK_DELAY, RESUME_DELAY, event_time, is_limit_event, limit_text, parse_reset, resume_at,
)

# Il record vero del 2026-09-23, accorciato ai campi che contano.
REAL = {
    "type": "assistant",
    "isApiErrorMessage": True,
    "error": "rate_limit",
    "uuid": "u1",
    "timestamp": "2026-09-23T05:53:33.564Z",
    "message": {"content": [{"type": "text", "text": "You've hit your monthly spend limit · raise it at claude.ai/settings/usage?from=cc_cli_limit_message · your session limit resets 11am (Europe/Rome)"}]},
}
UTC = timezone.utc


class LimitDetection(unittest.TestCase):
    def test_the_real_record_is_a_limit(self):
        self.assertTrue(is_limit_event(REAL))
        self.assertIn("resets 11am", limit_text(REAL))

    def test_a_normal_answer_is_not(self):
        self.assertFalse(is_limit_event({"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}}))

    def test_another_api_error_is_not(self):
        self.assertFalse(is_limit_event({**REAL, "error": "overloaded"}))

    def test_a_user_line_is_not(self):
        self.assertFalse(is_limit_event({**REAL, "type": "user"}))

    def test_event_time_is_aware_utc(self):
        self.assertEqual(event_time(REAL), datetime(2026, 9, 23, 5, 53, 33, 564000, tzinfo=UTC))


class ResetParsing(unittest.TestCase):
    after = datetime(2026, 9, 23, 5, 53, tzinfo=UTC)  # 07:53 a Roma

    def test_hour_with_zone(self):
        self.assertEqual(parse_reset("resets 11am (Europe/Rome)", self.after), datetime(2026, 9, 23, 9, 0, tzinfo=UTC))

    def test_hour_and_minutes_pm(self):
        self.assertEqual(parse_reset("resets 3:30pm (Europe/Rome)", self.after), datetime(2026, 9, 23, 13, 30, tzinfo=UTC))

    def test_24h_clock_in_the_given_zone(self):
        self.assertEqual(parse_reset("resets 15:00 (Europe/Rome)", self.after), datetime(2026, 9, 23, 13, 0, tzinfo=UTC))

    def test_12am_is_midnight(self):
        self.assertEqual(parse_reset("resets 12am (Europe/Rome)", self.after), datetime(2026, 9, 23, 22, 0, tzinfo=UTC))

    def test_already_past_means_tomorrow(self):
        # Review Focus 2: letto alle 11:30 di Roma, "11am" e' domani, non stamattina.
        later = datetime(2026, 9, 23, 9, 30, tzinfo=UTC)
        self.assertEqual(parse_reset("resets 11am (Europe/Rome)", later), datetime(2026, 9, 24, 9, 0, tzinfo=UTC))

    def test_unknown_text(self):
        self.assertIsNone(parse_reset("try again later", self.after))
        self.assertIsNone(parse_reset("resets 11am (Mars/Olympus)", self.after))


class ResumeTime(unittest.TestCase):
    def test_two_minutes_after_the_reset(self):
        self.assertEqual(resume_at(REAL), datetime(2026, 9, 23, 9, 0, tzinfo=UTC) + RESUME_DELAY)

    def test_fallback_thirty_minutes_after_the_error(self):
        event = {**REAL, "message": {"content": [{"type": "text", "text": "limit reached"}]}}
        self.assertEqual(resume_at(event), event_time(event) + FALLBACK_DELAY)


if __name__ == "__main__":
    unittest.main()
