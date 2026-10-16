"""Activity tab: CPU and memory graphs, load average, and Keep Awake."""
import os

from gi.repository import GLib, Gtk

from atoll.system.awake import CHOICES, Awake
from atoll.system.sysinfo import cpu_percent, mem_percent, read_cpu
from atoll.ui.charts import Spark
from atoll.ui.tabs.base import Tab
from atoll.ui.widgets import lbl


class ActivityTab(Tab):
    title, glyph = "Activity", ""

    def __init__(self, island):
        super().__init__(island)
        self.awake = Awake()
        self.prev = read_cpu()
        self.rows = {}
        for key, color in (("CPU", "#0a84ff"), ("Memory", "#30d158")):
            head = Gtk.Box()
            head.pack_start(lbl(key, "title"), True, True, 0)
            val = lbl(xalign=1)
            head.pack_start(val, False, False, 0)
            spark = Spark(color)
            self.pack_start(head, False, False, 0)
            self.pack_start(spark, False, False, 0)
            self.rows[key] = (val, spark)
        self.load = lbl(cls="dim")
        self.pack_start(self.load, False, False, 0)

        awake = Gtk.Box(spacing=8)
        awake.pack_start(lbl("☕ Keep awake", "title"), True, True, 0)
        seg = Gtk.Box()
        seg.get_style_context().add_class("seg")
        self.awake_btns = []
        for name, secs in CHOICES:
            b = Gtk.RadioButton(label=name, draw_indicator=False,
                                group=self.awake_btns[0] if self.awake_btns else None)
            b.connect("toggled", self.on_awake, secs)
            seg.pack_start(b, False, False, 0)
            self.awake_btns.append(b)
        awake.pack_start(seg, False, False, 0)
        self.pack_start(awake, False, False, 8)
        self.pack_start(lbl("Blocks sleep, idle suspend and lid-close suspend so agents keep running. "
                            "Ends when the island quits, or below 10% battery.", "dim",
                            wrap=True, max_width_chars=60), False, False, 0)
        GLib.timeout_add(2000, self.sample)

    def on_awake(self, btn, secs):
        if not btn.get_active():
            return
        try:
            self.awake.start(secs) if secs != 0 else self.awake.stop()
        except GLib.Error as e:  # e.g. polkit refused the inhibitor
            self.island.error = "awake: " + e.message[:50]
            self.awake_btns[0].set_active(True)
        self.island.render_compact()

    def sample(self):
        cur = read_cpu()
        cpu, (mem, total_gb) = cpu_percent(self.prev, cur), mem_percent()
        self.prev = cur
        for key, v, text in (("CPU", cpu, f"{cpu:.0f}%"), ("Memory", mem, f"{mem:.0f}% of {total_gb:.0f} GB")):
            val, spark = self.rows[key]
            spark.vals = (spark.vals + [v])[-60:]
            val.set_text(text)
            if self.get_mapped():
                spark.queue_draw()
        l1, l5, l15 = os.getloadavg()
        self.load.set_text(f"Load {l1:.2f} · {l5:.2f} · {l15:.2f}   ({os.cpu_count()} cores)")
        if self.awake.expired():
            self.awake_btns[0].set_active(True)  # toggled handler releases the lock
        return True

    def pill(self):
        return self.awake.label()
