"""Drawn widgets: the activity heatmap and the CPU/memory sparkline."""
from gi.repository import Gdk, Gtk

from atoll.core.heat import WEEKS, heat_levels, month_labels
from atoll.ui.widgets import lbl

HEAT_EMPTY = "#1c1c1e"
HEAT_COLORS = {"claude": ["#4d2618", "#84402a", "#c0603d", "#e88a63"],  # Claude Code orange
               "codex": ["#0b3d75", "#0a5fc2", "#1f7ff0", "#5aaeff"],
               "pi": ["#0f3d26", "#16653d", "#24a35f", "#4fd68a"]}


class Heatmap(Gtk.DrawingArea):
    CELL, GAP, TOP = 13, 4, 16  # TOP: room for the month labels

    def __init__(self, who):
        super().__init__()
        self.who, self.levels, self.start = who, [], None
        self.set_size_request(WEEKS * (self.CELL + self.GAP), self.TOP + 7 * (self.CELL + self.GAP))
        self.connect("draw", self.on_draw)

    def on_draw(self, _w, cr):
        step = self.CELL + self.GAP
        cr.set_source_rgba(0.6, 0.6, 0.62, 1)
        cr.set_font_size(10)
        for col, name in month_labels(self.start, len(self.levels)):
            cr.move_to(col * step, 10)
            cr.show_text(name)
        cr.translate(0, self.TOP)
        for i, lv in enumerate(self.levels):  # i = 0 is the Monday WEEKS-1 weeks ago
            c = Gdk.RGBA()
            c.parse(HEAT_COLORS[self.who][lv - 1] if lv else HEAT_EMPTY)
            cr.set_source_rgba(c.red, c.green, c.blue, 1)
            x, y = (i // 7) * step, (i % 7) * step
            r = 3
            cr.new_sub_path()
            cr.arc(x + self.CELL - r, y + r, r, -1.5708, 0)
            cr.arc(x + self.CELL - r, y + self.CELL - r, r, 0, 1.5708)
            cr.arc(x + r, y + self.CELL - r, r, 1.5708, 3.1416)
            cr.arc(x + r, y + r, r, 3.1416, 4.7124)
            cr.close_path()
            cr.fill()


class HeatBlock(Gtk.Box):
    """A heatmap with its active-days count and Less/More legend."""

    def __init__(self, who, spacing):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)  # spacing: match the tab's own
        self.heat = Heatmap(who)
        self.pack_start(self.heat, False, False, 4)
        legend = Gtk.Box(spacing=4)
        self.active = lbl(cls="dim", hexpand=True)
        legend.pack_start(self.active, True, True, 0)
        sw = lbl()
        sw.set_markup(" ".join(f"<span foreground='{c}'>■</span>" for c in HEAT_COLORS[who]))
        legend.pack_start(lbl("Less", "dim"), False, False, 4)
        legend.pack_start(sw, False, False, 0)
        legend.pack_start(lbl("More", "dim"), False, False, 4)
        self.pack_start(legend, False, False, 0)

    def update(self, values, start):
        self.heat.levels, self.heat.start = heat_levels(values), start
        self.heat.queue_draw()
        self.active.set_text(f"{sum(v > 0 for v in values)} active days, shaded by fresh tokens")


class Spark(Gtk.DrawingArea):
    def __init__(self, color):
        super().__init__()
        self.vals, self.rgb = [], tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
        self.set_size_request(-1, 36)
        self.connect("draw", self.draw)

    def draw(self, w, cr):
        width, h = w.get_allocated_width(), w.get_allocated_height()
        if len(self.vals) < 2:
            return
        step = width / 59
        cr.set_source_rgba(*self.rgb, 1)
        cr.set_line_width(1.5)
        x0 = width - step * (len(self.vals) - 1)
        for i, v in enumerate(self.vals):
            cr.line_to(x0 + i * step, h - 1 - (h - 2) * v / 100)
        cr.stroke_preserve()
        cr.line_to(width, h)
        cr.line_to(x0, h)
        cr.set_source_rgba(*self.rgb, 0.15)
        cr.fill()
