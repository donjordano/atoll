import json
import os
import tempfile
import unittest

from atoll.agents import claude, codex, load_enabled, pi, save_enabled


def jsonl(lines):
    f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    f.write("".join(json.dumps(e) + "\n" for e in lines))
    f.close()
    return f.name


class Claude(unittest.TestCase):
    def test_streamed_duplicates_counted_once(self):
        line = {"type": "assistant", "timestamp": "2026-01-01T12:00:00Z", "sessionId": "s", "cwd": "/x/proj",
                "message": {"id": "m1", "model": "claude-opus-5-5", "usage": {
                    "input_tokens": 1_000_000, "output_tokens": 0, "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0}}}
        p = jsonl([line, line])
        self.addCleanup(os.unlink, p)
        msgs, last = claude.parse_file(p)
        self.assertEqual(len(msgs), 1)
        self.assertAlmostEqual(msgs["m1"][2], 4.0)  # 1M input tokens at $4/MTok
        self.assertEqual(last[2], "/x/proj")

    def test_normalize_usage(self):
        full = {"five_hour": {"utilization": 14, "resets_at": "2026-10-16T20:40:00+00:00", "used_dollars": None},
                "seven_day": {"utilization": 24.5, "resets_at": None}, "seven_day_opus": None, "extra": [1]}
        self.assertEqual(claude.normalize_usage(full), {
            "five_hour": {"utilization": 14.0, "resets_at": "2026-10-16T20:40:00+00:00"},
            "seven_day": {"utilization": 24.5, "resets_at": None}})
        none = {"utilization": None, "resets_at": None}
        self.assertEqual(claude.normalize_usage({"five_hour": None}), {"five_hour": none, "seven_day": none})
        for bad in ([], {"five_hour": 3}, {"five_hour": {"utilization": "14%"}},
                    {"seven_day": {"utilization": True}}, {"five_hour": {"utilization": 1, "resets_at": 5}}):
            with self.assertRaises(ValueError, msg=bad):
                claude.normalize_usage(bad)

    def test_bad_cache_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "limits.json")
            with open(p, "w") as f:
                json.dump({"at": "yesterday", "data": {"five_hour": 7}}, f)
            self.assertEqual(claude.load_cached_usage(p), (None, None))

    def test_usage_cache_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "limits.json")
            self.assertEqual(claude.load_cached_usage(p), (None, None))
            claude.save_cached_usage({"five_hour": {"utilization": 3, "resets_at": None}}, p)
            data, age = claude.load_cached_usage(p)
            self.assertEqual(data["five_hour"], {"utilization": 3.0, "resets_at": None})
            self.assertLess(age, 5)


class Codex(unittest.TestCase):
    def test_repeated_token_count_counted_once(self):
        tc = lambda total, inp: {"timestamp": "2026-01-01T12:00:00Z", "type": "event_msg", "payload": {
            "type": "token_count", "info": {"total_token_usage": {"total_tokens": total},
                                            "last_token_usage": {"input_tokens": inp, "cached_input_tokens": 100,
                                                                 "output_tokens": 10}}}}
        p = jsonl([{"timestamp": "2026-01-01T11:00:00Z", "type": "turn_context",
                    "payload": {"model": "gpt-6.1-sol", "cwd": "/y"}}, tc(500, 300), tc(500, 300), tc(900, 400)])
        self.addCleanup(os.unlink, p)
        days, last, _ = codex.parse_file(p)
        (s,) = days.values()
        self.assertEqual((s["input"], s["cache_read"], s["output"]), (500, 200, 20))

    def test_plan_limits_zero_after_reset(self):
        lim = (0, {"primary": {"used_percent": 40, "resets_at": 2000}, "secondary": {"used_percent": 9, "resets_at": 500}})
        out = codex.plan_limits(lim, now=1000)
        self.assertEqual(out["five_hour"]["utilization"], 40)
        self.assertEqual(out["seven_day"], {"utilization": 0, "resets_at": None})
        self.assertIsNone(codex.plan_limits(None))


class Pi(unittest.TestCase):
    def test_tokens_cost_models_and_cwd(self):
        pu = lambda model, cost: {"type": "message", "timestamp": "2026-01-01T12:00:00Z", "message": {
            "role": "assistant", "model": model, "usage": {"input": 10, "output": 5, "cacheRead": 7, "cacheWrite": 0,
                                                            "cost": {"total": cost}}}}
        p = jsonl([{"type": "session", "cwd": "/z/proj"}, pu("a/x", 0.5), pu("a/x", 0.25), pu("b/free", 0)])
        self.addCleanup(os.unlink, p)
        days, models, last = pi.parse_file(p)
        (s,) = days.values()
        self.assertEqual((s["input"], s["output"], s["cache_read"], s["cost"]), (30, 15, 21, 0.75))
        self.assertEqual(list(models.values()), [{"a/x": 2, "b/free": 1}])
        self.assertEqual(last[2], "/z/proj")

    def test_top_models(self):
        self.assertEqual(pi.top_models({"a": 1, "b": 5, "c": 3, "d": 2}, 2), [("b", 5), ("c", 3)])


class Enabled(unittest.TestCase):
    def test_new_agents_default_on(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "agents.json")
            self.assertEqual(load_enabled(p), {"claude": True, "codex": True, "pi": True})
            save_enabled({"claude": True, "codex": False}, p)
            self.assertEqual(load_enabled(p), {"claude": True, "codex": False, "pi": True})


if __name__ == "__main__":
    unittest.main()
