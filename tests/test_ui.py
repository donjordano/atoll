"""Widget-level checks. Needs a display (CI runs them under xvfb-run)."""
import os
import tempfile
import unittest

from atoll.ui.style import level, pct_markup
from atoll.ui.tabs.media import pick_player
from atoll.ui.tabs.tasks import load_tasks, save_tasks
from atoll.ui.widgets import icon
from atoll.ui.window import clamp_position


class Style(unittest.TestCase):
    def test_levels(self):
        self.assertEqual([level(p) for p in (0, 50, 51, 80, 81)], ["ok", "ok", "warn", "warn", "bad"])
        self.assertEqual(pct_markup(12.4), "<span foreground='#30d158'>12%</span>")


class Widgets(unittest.TestCase):
    def test_every_logo_loads(self):
        for name in ("claude-code", "codex", "pi", "openrouter"):
            self.assertIsNotNone(icon(name), name)
        self.assertIsNone(icon("nope"))


class Window(unittest.TestCase):
    def test_clamp_keeps_window_on_screen(self):
        self.assertEqual(clamp_position(50, 50, 100, 40, 0, 0, 1000, 800), (50, 50))
        self.assertEqual(clamp_position(-30, 790, 100, 40, 0, 0, 1000, 800), (0, 760))
        self.assertEqual(clamp_position(990, 10, 100, 40, 0, 20, 1000, 800), (900, 20))


class Media(unittest.TestCase):
    def test_pick_player(self):
        self.assertIsNone(pick_player([]))
        self.assertEqual(pick_player([("a", "Paused"), ("b", "Playing")]), "b")
        self.assertEqual(pick_player([("a", "Paused"), ("b", "Stopped")]), "a")


class Tasks(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "tasks.json")
            self.assertEqual(load_tasks(p), [])
            save_tasks([{"text": "a", "done": True}], p)
            self.assertEqual(load_tasks(p), [{"text": "a", "done": True}])


if __name__ == "__main__":
    unittest.main()
