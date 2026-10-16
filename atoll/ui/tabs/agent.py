"""Claude Code and Codex tabs: plan limits, today's tokens and a heatmap."""
import os

from gi.repository import Gtk

from atoll.agents import ICONS
from atoll.core.fmt import human, pretty_model, until
from atoll.core.tokens import FIELDS, blank, fresh
from atoll.ui.charts import HeatBlock
from atoll.ui.style import pct_markup, set_level
from atoll.ui.tabs.base import Tab
from atoll.ui.widgets import lbl, title_row

FOOTNOTE = ("Fresh tokens exclude context re-read from the cache. The estimated API "
            "equivalent uses list prices; it is not what you pay.")


class Column(Gtk.Box):
    ROWS = [("Input", "input"), ("Cache write", "cache_write"), ("Output", "output"),
            ("Cache read", "cache_read"), ("Processed", None), ("Sessions", "sessions")]

    def __init__(self, name, icon_name):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True)
        self.limits, self.mode = None, "five_hour"
        self.pack_start(title_row(icon_name, name), False, False, 2)

        seg_row = Gtk.Box(spacing=8)
        seg_row.pack_start(lbl("Plan usage", "dim"), False, False, 0)
        seg = Gtk.Box()
        seg.get_style_context().add_class("seg")
        cur = Gtk.RadioButton(label="Current", draw_indicator=False)
        wk = Gtk.RadioButton(label="Weekly", group=cur, draw_indicator=False)
        cur.connect("toggled", lambda b: self.set_mode("five_hour" if b.get_active() else "seven_day"))
        seg.pack_start(cur, False, False, 0)
        seg.pack_start(wk, False, False, 0)
        seg_row.pack_start(seg, False, False, 0)
        self.pack_start(seg_row, False, False, 4)

        self.big_pct = lbl()
        self.bar = Gtk.ProgressBar()
        self.resets = lbl(cls="dim")
        self.fresh = lbl()
        for w in (self.big_pct, self.bar, self.resets):
            self.pack_start(w, False, False, 0)
        self.pack_start(lbl("Today on this PC", "dim"), False, False, 8)
        self.pack_start(self.fresh, False, False, 0)

        grid = Gtk.Grid(row_spacing=1)
        self.cells = {}
        for i, (title, key) in enumerate(self.ROWS):
            grid.attach(lbl(title, "dim", hexpand=True), 0, i, 1, 1)
            self.cells[title] = lbl(xalign=1)
            grid.attach(self.cells[title], 1, i, 1, 1)
        self.pack_start(grid, False, False, 2)

        self.cost = lbl(wrap=True, max_width_chars=26)
        self.five = lbl()
        self.where = lbl(cls="dim", ellipsize=3)  # PANGO_ELLIPSIZE_END
        for w in (self.cost, self.five, self.where):
            self.pack_start(w, False, False, 0)

    def set_mode(self, mode):
        self.mode = mode
        self.render_limits()

    def render_limits(self):
        u = (self.limits or {}).get(self.mode) or {}
        pct = u.get("utilization")
        kind = "Current" if self.mode == "five_hour" else "Weekly"
        if pct is None:
            self.big_pct.set_markup(f"<span size='xx-large' weight='bold'>—</span>  {kind}")
            self.bar.set_fraction(0)
            self.resets.set_text("No data")
        else:
            self.big_pct.set_markup(f"<span size='xx-large' weight='bold'>{pct_markup(pct)}</span>  {kind}")
            self.bar.set_fraction(min(pct, 100) / 100)
            self.resets.set_text("Resets in " + until(u.get("resets_at")))
        set_level(self.bar, pct or 0)
        five = ((self.limits or {}).get("five_hour") or {}).get("utilization")
        self.five.set_text("—" if five is None else f"{five:.0f}% of 5-hour limit")

    def render(self, limits, today, last):
        self.limits = limits
        self.render_limits()
        t = today or blank()
        self.fresh.set_markup(f"<span size='xx-large' weight='bold'>{human(fresh(t))}</span>  fresh tokens")
        for title, key in self.ROWS:
            v = len(t["sessions"]) if key == "sessions" else t[key] if key else sum(t[f] for f in FIELDS)
            self.cells[title].set_text(str(v) if key == "sessions" else human(v))
        self.cost.set_markup(f"<b>${t['cost']:.2f}</b> estimated API equivalent today")
        self.where.set_text(f"{pretty_model(last[1])} in {os.path.basename(last[2]) or '~'}" if last else "No sessions yet")


class AgentTab(Tab):
    """A plan-limited agent: limits column, heatmap and footnote. The window feeds it through render()."""

    def __init__(self, island, agent, title, glyph, alerts=False):
        super().__init__(island)
        self.agent, self.title, self.glyph, self.icon = agent, title, glyph, ICONS[agent]
        self.set_spacing(12)
        self.set_size_request(470, -1)  # every tab gets this width
        self.last_alert = lbl("No alerts yet", "dim") if alerts else None
        if self.last_alert:
            self.pack_start(self.last_alert, False, False, 0)
        self.column = Column(title, self.icon)
        self.pack_start(self.column, False, False, 0)
        self.heat = HeatBlock(agent, spacing=12)
        self.pack_start(self.heat, False, False, 0)
        self.pack_start(lbl(FOOTNOTE, "dim", wrap=True, max_width_chars=60), False, False, 6)

    def render(self, limits, today, last):
        self.column.render(limits, today, last)
