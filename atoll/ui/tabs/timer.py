"""Focus timer tab: 25/50/90-minute sessions with a countdown in the pill."""
import time

from gi.repository import GLib, Gtk

from atoll.core.fmt import fmt_clock
from atoll.ui.tabs.base import Tab
from atoll.ui.widgets import button, lbl


class TimerTab(Tab):
    title, glyph = "Focus", "\U000F051B"

    def __init__(self, island):
        super().__init__(island)
        self.end = self.left = None  # running: end set; paused: left set
        self.clock = lbl("25:00", "huge", xalign=0.5)
        self.pack_start(self.clock, False, False, 6)
        presets = Gtk.Box(spacing=8, halign=3)
        for m in (25, 50, 90):
            presets.pack_start(button(f"{m} min", self.start, "btn", m * 60), False, False, 0)
        self.pack_start(presets, False, False, 0)
        ctrl = Gtk.Box(spacing=8, halign=3)
        self.pause_btn = button("Pause", self.pause)
        ctrl.pack_start(self.pause_btn, False, False, 0)
        ctrl.pack_start(button("Stop", self.stop), False, False, 0)
        self.pack_start(ctrl, False, False, 0)
        GLib.timeout_add(1000, self.tick)

    def remaining(self):
        return self.end - time.monotonic() if self.end else self.left

    def start(self, secs):
        self.end, self.left = time.monotonic() + secs, None
        self.tick()

    def pause(self):
        if self.end:
            self.end, self.left = None, self.remaining()
            self.pause_btn.set_label("Resume")
        elif self.left:
            self.start(self.left)
            self.pause_btn.set_label("Pause")

    def stop(self):
        self.end = self.left = None
        self.pause_btn.set_label("Pause")
        self.clock.set_text("25:00")
        self.island.render_compact()

    def tick(self):
        r = self.remaining()
        if r is None:
            return True
        if self.end and r <= 0:
            self.stop()
            self.island.notify("Focus session done", "#30d158", 60)
            return True
        self.clock.set_text(fmt_clock(r))
        self.island.render_compact()
        return True

    def pill(self):
        r = self.remaining()
        return "" if r is None else ("⏸ " if self.left else "⏱ ") + fmt_clock(r)
