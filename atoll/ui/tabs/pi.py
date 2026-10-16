"""Pi · OpenRouter tab: Pi's tokens, billed cost and models, plus OpenRouter key spending."""
import os, time
from datetime import date, timedelta

from gi.repository import Gtk

from atoll.agents import pi
from atoll.agents.pi import top_models
from atoll.core.fmt import human
from atoll.core.tokens import blank, fresh
from atoll.ui.charts import HeatBlock
from atoll.ui.style import set_level
from atoll.ui.tabs.base import Tab
from atoll.ui.widgets import bg, clear, grid, lbl, title_row


class PiTab(Tab):
    title, glyph, agent, icon = "Pi · OpenRouter", "π", "pi", "pi"
    PI_ROWS = ["Input", "Cache write", "Output", "Cache read", "Requests", "Sessions"]
    OR_ROWS = ["Today", "This week", "This month", "All time"]

    def __init__(self, island):
        super().__init__(island)
        cols = Gtk.Box(spacing=28, homogeneous=True)
        self.pack_start(cols, False, False, 0)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        orr = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        cols.pack_start(col, True, True, 0)
        cols.pack_start(orr, True, True, 0)

        col.pack_start(title_row("pi", "Pi"), False, False, 2)
        col.pack_start(lbl("Today on this PC", "dim"), False, False, 4)
        self.fresh = lbl()
        col.pack_start(self.fresh, False, False, 0)
        g, self.pi_cells = grid(self.PI_ROWS)
        col.pack_start(g, False, False, 2)
        self.cost, self.week = lbl(), lbl(cls="dim")
        self.where = lbl(cls="dim", ellipsize=3)
        for w in (self.cost, self.week, self.where):
            col.pack_start(w, False, False, 0)
        col.pack_start(lbl("Models today", "dim"), False, False, 6)
        self.models = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        col.pack_start(self.models, False, False, 0)

        orr.pack_start(title_row("openrouter", "OpenRouter"), False, False, 2)
        orr.pack_start(lbl("Spend on this key", "dim"), False, False, 4)
        self.spend = lbl()
        orr.pack_start(self.spend, False, False, 0)
        g, self.or_cells = grid(self.OR_ROWS)
        orr.pack_start(g, False, False, 2)
        self.limit, self.limit_bar = lbl(), Gtk.ProgressBar()
        orr.pack_start(self.limit, False, False, 6)
        orr.pack_start(self.limit_bar, False, False, 0)
        self.free, self.free_bar = lbl(), Gtk.ProgressBar()
        orr.pack_start(lbl("Free models today", "dim"), False, False, 6)
        orr.pack_start(self.free, False, False, 0)
        orr.pack_start(self.free_bar, False, False, 0)
        self.or_err = lbl(cls="dim", wrap=True, max_width_chars=28)
        orr.pack_start(self.or_err, False, False, 0)
        self.fetched = 0
        self.heat = HeatBlock("pi", spacing=10)  # fed by the window from the shared daily history
        self.pack_start(self.heat, False, False, 0)

    def on_show(self):
        self.render_pi()
        if time.monotonic() - self.fetched < 60:
            return
        self.fetched = time.monotonic()
        bg(pi.fetch_openrouter_key, self.render_or)

    def render_pi(self):
        days, models, last = pi.stats()
        today = date.today()
        t = days.get(today.isoformat()) or blank()
        self.fresh.set_markup(f"<span size='xx-large' weight='bold'>{human(fresh(t))}</span>  fresh tokens")
        reqs = sum(models.get(today.isoformat(), {}).values())
        vals = {"Input": t["input"], "Cache write": t["cache_write"], "Output": t["output"],
                "Cache read": t["cache_read"], "Requests": reqs, "Sessions": len(t["sessions"])}
        for k, v in vals.items():
            self.pi_cells[k].set_text(human(v))
        self.cost.set_markup(f"<b>${t['cost']:.2f}</b> billed today")
        week = [days.get((today - timedelta(i)).isoformat()) or blank() for i in range(7)]
        self.week.set_text(f"7 days: {human(sum(map(fresh, week)))} tokens · ${sum(d['cost'] for d in week):.2f}")
        self.where.set_text(f"{last[1]} in {os.path.basename(last[2]) or '~'}" if last else "No Pi sessions found")
        clear(self.models)
        for m, n in top_models(models.get(today.isoformat(), {})) or [("None yet", "")]:
            row = Gtk.Box()
            row.pack_start(lbl(m, "mono", hexpand=True, ellipsize=1), True, True, 0)  # ellipsize start: keep model name
            row.pack_start(lbl(str(n), xalign=1), False, False, 0)
            self.models.pack_start(row, False, False, 0)
        self.models.show_all()

    def render_or(self, d):
        if isinstance(d, Exception):
            self.fetched = 0  # retry on next open
            self.or_err.set_text(f"OpenRouter: {d}")
            return
        self.or_err.set_text("")
        self.spend.set_markup(f"<span size='xx-large' weight='bold'>${d.get('usage_monthly', 0):.2f}</span>  this month")
        for k, f in zip(self.OR_ROWS, ("usage_daily", "usage_weekly", "usage_monthly", "usage")):
            self.or_cells[k].set_text(f"${d.get(f) or 0:.2f}")
        lim = d.get("limit")
        self.limit.set_text(f"${d.get('limit_remaining') or 0:.2f} of ${lim:.2f} limit left" if lim else "No spend limit")
        self.limit_bar.set_fraction(min(1, (lim - (d.get("limit_remaining") or 0)) / lim) if lim else 0)
        self.limit_bar.set_visible(bool(lim))
        fr = d.get("free_model_daily_requests") or {}
        used, cap = fr.get("used", 0), fr.get("limit") or 0
        self.free.set_text(f"{used} of {cap} requests" if cap else "—")
        self.free_bar.set_fraction(min(1, used / cap) if cap else 0)
        for bar in (self.limit_bar, self.free_bar):
            set_level(bar, bar.get_fraction() * 100)
