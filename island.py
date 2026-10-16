#!/usr/bin/env python3
"""Claude Code / Codex usage 'dynamic island' for GNOME/X11. Hover to expand, click the pill to refresh."""
import json, os, sys, threading, time, urllib.error
from datetime import date, datetime, timedelta, timezone

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

import tabs
import usage_stats as us
from tabs import lbl

POLL_SECONDS = 120
HEAT_WEEKS = 26
HEAT_COLORS = ["#1c1c1e", "#0b3d75", "#0a5fc2", "#1f7ff0", "#5aaeff"]
ALERT_FILE = os.path.expanduser("~/.cache/claude-island/alert")  # written by Claude Code hooks
LIMITS_CACHE = os.path.expanduser("~/.local/share/claude-island/limits.json")
FETCH_EVERY, BACKOFF = 90, 300

CSS = b"""
window { background: transparent; }
#pill { background: #000; border-radius: 22px; padding: 8px 18px; }
#pill.open { border-radius: 26px; padding: 14px 22px 18px; }
label { color: #fff; font-family: sans; font-size: 10.5pt; }
.dim { color: #8e8e93; font-size: 9.5pt; }
.title { font-weight: bold; }
.seg { background: #1c1c1e; border-radius: 10px; padding: 2px; }
.seg button { background: none; border: none; box-shadow: none; border-radius: 8px; padding: 2px 10px; min-height: 0; }
.seg button label { color: #8e8e93; font-size: 9.5pt; }
.seg button:checked { background: #3a3a3c; }
.seg button:checked label { color: #fff; }
progressbar trough { min-height: 6px; border-radius: 3px; background: #2c2c2e; border: none; }
progressbar progress { min-height: 6px; border-radius: 3px; border: none; }
.ok progress { background: #0a84ff; }
.warn progress { background: #ffd60a; }
.bad progress { background: #ff453a; }
.tabbar button { background: none; border: none; box-shadow: none; border-radius: 10px; padding: 4px 7px; min-height: 0; min-width: 0; }
.tabbar button label, .icon label, .icon { font-family: "JetBrainsMono Nerd Font"; font-size: 13pt; color: #8e8e93; }
.tabbar button:checked { background: #2c2c2e; }
.tabbar button:checked label, .tabbar button:hover label { color: #fff; }
.tabtitle { font-weight: bold; font-size: 12pt; }
.big { font-size: 15pt; font-weight: bold; }
.huge { font-size: 40pt; font-weight: bold; }
.mono { font-family: "JetBrainsMono Nerd Font"; font-size: 9pt; color: #d1d1d6; }
.btn { background: #2c2c2e; border: none; box-shadow: none; border-radius: 8px; padding: 4px 12px; min-height: 0; }
.btn:hover { background: #3a3a3c; }
.flat { background: none; border: none; box-shadow: none; padding: 2px 4px; min-height: 0; }
.flat:hover { background: #1c1c1e; }
.flat.icon label { font-size: 16pt; color: #fff; }
entry { background: #1c1c1e; color: #fff; border: none; border-radius: 8px; box-shadow: none; padding: 6px 10px; caret-color: #fff; }
calendar { background: #000; color: #fff; border: none; padding: 4px; }
calendar:selected { background: #0a84ff; color: #fff; border-radius: 6px; }
calendar.header, calendar.button { background: #000; color: #8e8e93; border: none; }
calendar:indeterminate { color: #48484a; }
check { background: #1c1c1e; border: 1px solid #48484a; border-radius: 4px; }
check:checked { background: #0a84ff; border-color: #0a84ff; }
switch { background: #3a3a3c; border: none; }
switch:checked { background: #30d158; }
switch slider { background: #fff; border: none; }
"""


def until(iso, now=None):
    """'2 h 05 min' / '3 d 4 h' until an ISO timestamp."""
    if not iso:
        return "—"
    now = now or datetime.now(timezone.utc)
    s = max(0, int((datetime.fromisoformat(iso) - now).total_seconds()))
    d, h, m = s // 86400, s % 86400 // 3600, s % 3600 // 60
    return f"{d} d {h} h" if d else f"{h} h {m:02d} min"


def level(pct):
    return "ok" if pct < 60 else "warn" if pct < 85 else "bad"


def heat_levels(values):
    """Map each day's value to 0..4 by quartile of the non-zero days."""
    nz = sorted(v for v in values if v > 0)
    if not nz:
        return [0] * len(values)
    q = [nz[max(0, len(nz) * i // 4 - 1)] for i in (1, 2, 3)]
    return [0 if v <= 0 else 1 + sum(v > t for t in q) for v in values]


def describe_alert(a):
    """Hook payload -> (text, color, seconds to show) or None to clear."""
    ev, folder = a.get("hook_event_name"), os.path.basename(a.get("cwd") or "") or "Claude"
    if ev == "Stop":
        return f"{folder} · finished", "#30d158", 12
    if ev == "Notification":
        what = {"permission_prompt": "needs permission", "idle_prompt": "waiting for input"}.get(
            a.get("notification_type")) or a.get("message") or "needs attention"
        return f"{folder} · {what}", "#ff9f0a", 600
    return None  # UserPromptSubmit: you are back at the keyboard


def backoff_seconds(err):
    """Honor Retry-After on 429s, never retrying sooner than BACKOFF."""
    if isinstance(err, urllib.error.HTTPError) and err.headers:
        try:
            return max(BACKOFF, int(err.headers.get("Retry-After") or 0))
        except ValueError:
            pass
    return BACKOFF


def save_limits(data):
    try:
        os.makedirs(os.path.dirname(LIMITS_CACHE), exist_ok=True)
        with open(LIMITS_CACHE + ".tmp", "w") as f:
            json.dump({"at": time.time(), "data": data}, f)
        os.replace(LIMITS_CACHE + ".tmp", LIMITS_CACHE)
    except OSError:
        pass  # cache is a convenience; the live numbers still show



class Column(Gtk.Box):
    ROWS = [("Input", "input"), ("Cache write", "cache_write"), ("Output", "output"),
            ("Cache read", "cache_read"), ("Processed", None), ("Sessions", "sessions")]

    def __init__(self, name, glyph):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True)
        self.limits, self.mode = None, "five_hour"
        self.pack_start(lbl(f"{glyph}  {name}", "title"), False, False, 2)

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
            self.big_pct.set_markup(f"<span size='xx-large' weight='bold'>{pct:.0f}%</span>  {kind}")
            self.bar.set_fraction(min(pct, 100) / 100)
            self.resets.set_text("Resets in " + until(u.get("resets_at")))
        ctx = self.bar.get_style_context()
        for c in ("ok", "warn", "bad"):
            ctx.remove_class(c)
        ctx.add_class(level(pct or 0))
        five = ((self.limits or {}).get("five_hour") or {}).get("utilization")
        self.five.set_text("—" if five is None else f"{five:.0f}% of 5-hour limit")

    def render(self, limits, today, last):
        self.limits = limits
        self.render_limits()
        t = today or us.blank()
        self.fresh.set_markup(f"<span size='xx-large' weight='bold'>{us.human(us.fresh(t))}</span>  fresh tokens")
        for title, key in self.ROWS:
            v = len(t["sessions"]) if key == "sessions" else t[key] if key else sum(t[f] for f in us.FIELDS)
            self.cells[title].set_text(str(v) if key == "sessions" else us.human(v))
        self.cost.set_markup(f"<b>${t['cost']:.2f}</b> estimated API equivalent today")
        self.where.set_text(f"{us.pretty_model(last[1])} in {os.path.basename(last[2]) or '~'}" if last else "No sessions yet")


class Heatmap(Gtk.DrawingArea):
    CELL, GAP = 13, 4

    def __init__(self):
        super().__init__()
        self.levels = []
        self.set_size_request(HEAT_WEEKS * (self.CELL + self.GAP), 7 * (self.CELL + self.GAP))
        self.connect("draw", self.on_draw)

    def on_draw(self, _w, cr):
        step = self.CELL + self.GAP
        for i, lv in enumerate(self.levels):  # i = 0 is the Monday HEAT_WEEKS-1 weeks ago
            c = Gdk.RGBA()
            c.parse(HEAT_COLORS[lv])
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


class Island(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.POPUP)  # no decorations, no taskbar entry, above others
        self.set_visual(self.get_screen().get_rgba_visual())
        self.set_app_paintable(True)
        self.claude_limits = self.error = None
        self.state = self.history = self.alert = self.project_cwd = self.kb_grab = None
        self.alert_mtime = self.next_fetch = 0
        try:  # last good numbers: shown at once, and a restart within FETCH_EVERY skips the API
            with open(LIMITS_CACHE) as f:
                c = json.load(f)
            self.claude_limits = c["data"]
            self.next_fetch = time.monotonic() + max(0, FETCH_EVERY - (time.time() - c["at"]))
        except (OSError, ValueError, KeyError):
            pass

        self.pill = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, name="pill")
        self.compact = lbl("Claude …", xalign=0.5)
        click = Gtk.EventBox()  # only the pill text refreshes on click, not the whole panel
        click.add(self.compact)
        click.connect("button-press-event", lambda *_: self.refresh())
        self.pill.pack_start(click, False, False, 0)

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        panel.set_size_request(470, -1)  # every tab gets the Usage tab's width
        self.last_alert = lbl("No alerts yet", "dim")
        panel.pack_start(self.last_alert, False, False, 0)
        cols = Gtk.Box(spacing=28, homogeneous=True)
        self.claude_col, self.codex_col = Column("Claude Code", "✻"), Column("Codex", "◎")
        cols.pack_start(self.claude_col, True, True, 0)
        cols.pack_start(self.codex_col, True, True, 0)
        panel.pack_start(cols, False, False, 0)

        self.heat = Heatmap()
        panel.pack_start(self.heat, False, False, 4)
        legend = Gtk.Box(spacing=4)
        self.active = lbl(cls="dim", hexpand=True)
        legend.pack_start(self.active, True, True, 0)
        legend.pack_start(lbl("Less", "dim"), False, False, 4)
        for color in HEAT_COLORS[1:]:
            sw = lbl()
            sw.set_markup(f"<span foreground='{color}'>■</span>")
            legend.pack_start(sw, False, False, 0)
        legend.pack_start(lbl("More", "dim"), False, False, 4)
        panel.pack_start(legend, False, False, 0)
        panel.pack_start(lbl("Fresh tokens exclude context re-read from the cache. The estimated API "
                             "equivalent uses list prices; it is not what you pay.", "dim",
                             wrap=True, max_width_chars=60), False, False, 6)

        self.tabs = [panel] + [cls(self) for cls in tabs.TABS] + [tabs.SettingsTab(self)]
        panel.title, panel.glyph, panel.on_show, panel.pill = "Usage", "✻", lambda: None, lambda: ""
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=120,
                               vhomogeneous=False, interpolate_size=True)
        bar = Gtk.Box(spacing=2)
        bar.get_style_context().add_class("tabbar")
        self.tab_title = lbl("Usage", "tabtitle")
        first = None
        for i, t in enumerate(self.tabs):
            self.stack.add_named(t, t.title)
            b = Gtk.RadioButton(label=t.glyph, draw_indicator=False, group=first, tooltip_text=t.title)
            first = first or b
            b.connect("toggled", self.on_tab, t)
            if t is self.tabs[-1]:  # the gear sits at the far right, after the title
                bar.pack_start(self.tab_title, True, True, 10)
            bar.pack_start(b, False, False, 0)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        body.pack_start(bar, False, False, 0)
        body.pack_start(self.stack, False, False, 0)

        self.revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
                                     transition_duration=200)
        self.revealer.add(body)
        self.pill.pack_start(self.revealer, False, False, 0)

        events = Gtk.EventBox()
        events.add(self.pill)
        events.connect("enter-notify-event", self.on_enter)
        events.connect("leave-notify-event", self.on_leave)
        self.add(events)

        self.connect("size-allocate", lambda *_: self.recenter())
        self.show_all()
        self.revealer.hide()
        self.refresh()
        GLib.timeout_add_seconds(POLL_SECONDS, self.refresh)
        GLib.timeout_add_seconds(30, self.render)  # keep countdowns fresh between polls
        GLib.timeout_add(1000, self.poll_alert)

    def on_tab(self, btn, tab):
        if btn.get_active():
            self.stack.set_visible_child(tab)
            self.tab_title.set_text(tab.title)
            tab.on_show()
            GLib.timeout_add(150, lambda: self.resize(1, 1) and False)  # shrink to the new tab's height

    def notify(self, text, color, seconds):
        self.alert = (text, color, time.time() + seconds)
        self.last_alert.set_text(f"Last alert: {text} · {datetime.now():%H:%M}")
        self.render_compact()

    def grab_keyboard(self, widget):
        """A popup window gets no keyboard focus from the window manager; grab it while typing."""
        if not self.kb_grab:
            seat = Gdk.Display.get_default().get_default_seat()
            ok = seat.grab(self.get_window(), Gdk.SeatCapabilities.KEYBOARD, True, None, None, None, None)
            self.kb_grab = seat if ok == Gdk.GrabStatus.SUCCESS else None
        widget.grab_focus()
        return False

    def poll_alert(self):
        try:
            mtime = os.stat(ALERT_FILE).st_mtime
        except OSError:
            return True
        if mtime != self.alert_mtime:
            self.alert_mtime = mtime
            try:
                with open(ALERT_FILE) as f:
                    d = describe_alert(json.load(f))
            except (OSError, ValueError):
                d = None
            self.alert = d and (d[0], d[1], mtime + d[2])
            if d:
                self.last_alert.set_text(f"Last alert: {d[0]} · {datetime.fromtimestamp(mtime):%H:%M}")
            self.render_compact()
        elif self.alert and time.time() > self.alert[2]:
            self.alert = None
            self.render_compact()
        return True

    def on_enter(self, *_):
        self.alert = None  # hovering means you've seen it
        self.refresh()
        self.stack.get_visible_child().on_show()
        self.pill.get_style_context().add_class("open")
        self.revealer.show()
        self.revealer.set_reveal_child(True)

    def on_leave(self, _w, ev):
        if ev.detail != Gdk.NotifyType.INFERIOR:  # ignore moving onto child widgets
            self.revealer.set_reveal_child(False)
            GLib.timeout_add(220, self.collapse)  # after the slide finishes

    def collapse(self):
        if not self.revealer.get_reveal_child():
            self.revealer.hide()  # hidden child takes no width, so the pill shrinks
            if self.kb_grab:
                self.kb_grab.ungrab()
                self.kb_grab = None
            self.pill.get_style_context().remove_class("open")
            self.resize(1, 1)
        return False

    def recenter(self):
        geo = Gdk.Display.get_default().get_primary_monitor().get_workarea()  # below the GNOME top bar
        w, _ = self.get_size()
        self.move(geo.x + (geo.width - w) // 2, geo.y + 6)

    def refresh(self):
        def work():
            if time.monotonic() >= self.next_fetch:  # the usage endpoint rate-limits (429); local data refreshes freely
                try:
                    self.claude_limits, self.error = us.fetch_claude_usage(), None
                    self.next_fetch = time.monotonic() + FETCH_EVERY
                    save_limits(self.claude_limits)
                except Exception as e:  # network down, token expired, 429: keep last data, back off
                    self.error = str(e)[:60]
                    self.next_fetch = time.monotonic() + backoff_seconds(e)
            try:
                state = (us.claude_stats(), us.codex_stats())
                self.history = us.update_history(state[0][0], state[1][0])
                lasts = [l for l in (state[0][1], state[1][1]) if l]
                self.project_cwd = max(lasts)[2] if lasts else None
            except Exception as e:  # a malformed log must not kill the island
                self.error, state = f"log scan: {e}"[:60], self.state
            GLib.idle_add(self.apply, state)
        threading.Thread(target=work, daemon=True).start()
        return True

    def apply(self, state):
        self.state = state
        self.render()
        return False

    def render_compact(self):
        esc = GLib.markup_escape_text
        cl = self.claude_limits
        if self.alert:
            msg = self.alert[0] if len(self.alert[0]) <= 48 else self.alert[0][:47] + "…"  # ellipsized labels collapse in a shrink-to-fit popup
            text = f"<span foreground='{self.alert[1]}'>●</span>  {esc(msg)}"
        elif cl:
            text = f"✻  5h {cl['five_hour']['utilization']:.0f}%   7d {cl['seven_day']['utilization']:.0f}%"
            text += "  ⚠" if self.error else ""
        else:
            text = esc("Claude · " + ("offline, retrying" if self.error else "loading…"))
        for t in self.tabs:  # timer / awake countdowns
            if t.pill():
                text += "   " + esc(t.pill())
        self.compact.set_markup(text)
        self.compact.set_tooltip_text(self.error)  # full error on hover, not in the pill

    def render(self):
        today = date.today()
        cl = self.claude_limits
        self.render_compact()
        if not self.state:
            return True
        (c_days, c_last), (x_days, x_last, x_lim) = self.state
        t = today.isoformat()
        self.claude_col.render(cl, c_days.get(t), c_last)
        self.codex_col.render(us.codex_limits(x_lim), x_days.get(t), x_last)

        start = today - timedelta(days=today.weekday() + 7 * (HEAT_WEEKS - 1))
        days = [(start + timedelta(i)).isoformat() for i in range((today - start).days + 1)]
        vals = [sum((self.history or {}).get(k, [0, 0])) for k in days]
        self.heat.levels = heat_levels(vals)
        self.heat.queue_draw()
        self.active.set_text(f"{sum(v > 0 for v in vals)} active days, shaded by fresh tokens")
        return True


def self_test():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert until("2026-01-01T02:05:30+00:00", now) == "2 h 05 min"
    assert until("2026-01-04T04:00:00+00:00", now) == "3 d 4 h"
    assert until("2025-12-31T00:00:00+00:00", now) == "0 h 00 min"
    assert until(None) == "—"
    assert [level(p) for p in (0, 59, 60, 85, 100)] == ["ok", "ok", "warn", "bad", "bad"]
    assert heat_levels([0, 0]) == [0, 0]
    assert heat_levels([0, 1, 2, 3, 4]) == [0, 1, 2, 3, 4]
    assert describe_alert({"hook_event_name": "Stop", "cwd": "/a/proj"})[0] == "proj · finished"
    assert describe_alert({"hook_event_name": "Notification", "cwd": "/a/p",
                           "notification_type": "permission_prompt"})[0] == "p · needs permission"
    assert describe_alert({"hook_event_name": "Notification", "message": "Hi"})[0] == "Claude · Hi"
    assert describe_alert({"hook_event_name": "UserPromptSubmit"}) is None
    import email.message
    h = email.message.Message()
    h["Retry-After"] = "900"
    assert backoff_seconds(urllib.error.HTTPError("u", 429, "Too Many", h, None)) == 900
    assert backoff_seconds(OSError("down")) == BACKOFF
    print("ok")


if __name__ == "__main__":
    if "--test" in sys.argv:
        self_test()
        sys.exit()
    prov = Gtk.CssProvider()
    prov.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov,
                                             Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    Island()
    Gtk.main()
