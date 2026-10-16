import email.message
import os
import tempfile
import unittest
import urllib.error
from datetime import date, datetime, timezone

from atoll.core.alerts import describe_alert
from atoll.core.fmt import fmt_clock, human, pretty_model, until
from atoll.core.heat import heat_levels, heat_window, month_labels
from atoll.core.history import merge_history, update_history
from atoll.core.net import BACKOFF, backoff_seconds
from atoll.core.pricing import price_for
from atoll.storage import read_json, write_json


def day(n):
    return {"input": n, "cache_write": 0, "output": 0, "cache_read": 99}


class Pricing(unittest.TestCase):
    def test_prefix_and_dated_ids(self):
        self.assertEqual(price_for("claude-haiku-4-5-20251001"), (1, 5, 0.10))
        self.assertEqual(price_for("claude-opus-5-5"), (4, 20, 0.20))
        self.assertEqual(price_for("claude-opus-5"), (5, 25, 0.50))  # not shadowed by opus-5-5
        self.assertIsNone(price_for("mystery"))


class Formatting(unittest.TestCase):
    def test_human(self):
        self.assertEqual([human(n) for n in (375500, 2_310_000, 80500, 3)], ["376k", "2.31M", "80.5k", "3"])

    def test_pretty_model(self):
        self.assertEqual(pretty_model("claude-opus-5-5"), "Opus 5.5")
        self.assertEqual(pretty_model("claude-haiku-4-5-20251001"), "Haiku 4.5")
        self.assertEqual(pretty_model("gpt-6.1-sol"), "gpt-6.1-sol")

    def test_until(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(until("2026-01-01T02:05:30+00:00", now), "2 h 05 min")
        self.assertEqual(until("2026-01-04T04:00:00+00:00", now), "3 d 4 h")
        self.assertEqual(until("2025-12-31T00:00:00+00:00", now), "0 h 00 min")
        self.assertEqual(until(None), "—")

    def test_fmt_clock(self):
        self.assertEqual([fmt_clock(s) for s in (25 * 60, 59.9, -3, 90 * 60)], ["25:00", "00:59", "00:00", "1:30:00"])


class Heat(unittest.TestCase):
    def test_levels_by_quartile(self):
        self.assertEqual(heat_levels([0, 0]), [0, 0])
        self.assertEqual(heat_levels([0, 1, 2, 3, 4]), [0, 1, 2, 3, 4])

    def test_month_labels(self):
        self.assertEqual(month_labels(date(2026, 4, 27), 21), [(0, "May")])  # the week holding May 1 is May's
        self.assertEqual(month_labels(date(2026, 4, 20), 21), [(1, "May")])  # one-column Apr label dropped
        self.assertEqual(month_labels(date(2026, 4, 6), 35)[0], (0, "Apr"))

    def test_window_starts_on_monday_and_ends_today(self):
        start, days = heat_window(date(2026, 10, 16), weeks=2)  # a Friday
        self.assertEqual(start, date(2026, 10, 5))
        self.assertEqual((days[0], days[-1], len(days)), ("2026-10-05", "2026-10-16", 12))


class History(unittest.TestCase):
    def test_keeps_stored_max(self):
        h = merge_history({"d1": [500, 7]}, {"d1": day(100), "d2": day(30)}, {"d2": day(4)})
        self.assertEqual(h, {"d1": [500, 7], "d2": [30, 4]})  # pruned/lower day keeps stored max

    def test_old_rows_grow_a_pi_slot(self):
        self.assertEqual(merge_history({"d1": [500, 7]}, {}, {}, {"d1": day(9)}), {"d1": [500, 7, 9]})

    def test_update_writes_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "sub", "daily.json")
            self.assertEqual(update_history({"d1": day(5)}, {}, {}, path=p), {"d1": [5, 0, 0]})
            self.assertEqual(read_json(p), {"d1": [5, 0, 0]})


class Alerts(unittest.TestCase):
    def test_describe(self):
        self.assertEqual(describe_alert({"hook_event_name": "Stop", "cwd": "/a/proj"})[0], "proj · finished")
        self.assertEqual(describe_alert({"hook_event_name": "Notification", "cwd": "/a/p",
                                         "notification_type": "permission_prompt"})[0], "p · needs permission")
        self.assertEqual(describe_alert({"hook_event_name": "Notification", "message": "Hi"})[0], "Claude · Hi")
        self.assertIsNone(describe_alert({"hook_event_name": "UserPromptSubmit"}))

    def test_backoff_honors_retry_after(self):
        h = email.message.Message()
        h["Retry-After"] = "900"
        self.assertEqual(backoff_seconds(urllib.error.HTTPError("u", 429, "Too Many", h, None)), 900)
        self.assertEqual(backoff_seconds(OSError("down")), BACKOFF)


class Storage(unittest.TestCase):
    def test_round_trip_and_default(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a", "x.json")
            self.assertEqual(read_json(p, []), [])
            write_json(p, {"k": 1})
            self.assertEqual(read_json(p), {"k": 1})
            self.assertFalse(os.path.exists(p + ".tmp"))


if __name__ == "__main__":
    unittest.main()
