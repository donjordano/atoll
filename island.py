#!/usr/bin/env python3
"""Atoll: a floating usage island for Claude Code, Codex and Pi on GNOME/X11. Click to expand, drag to move."""
import fcntl, json, os, sys, threading, time, urllib.error
from datetime import date, datetime, timedelta, timezone

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

import tabs
import usage_stats as us
from tabs import LEVEL_COLORS, icon, lbl, level, pct_markup, title_row

POLL_SECONDS = 120
HEAT_WEEKS = 26
HEAT_EMPTY = "#1c1c1e"
HEAT_COLORS = {"claude": ["#4d2618", "#84402a", "#c0603d", "#e88a63"],  # Claude Code orange
               "codex": ["#0b3d75", "#0a5fc2", "#1f7ff0", "#5aaeff"],
               "pi": ["#0f3d26", "#16653d", "#24a35f", "#4fd68a"]}
ALERT_FILE = us.CACHE + "/alert"  # written by Claude Code hooks
LIMITS_CACHE = us.DATA + "/limits.json"
POSITION_FILE = us.DATA + "/position.json"  # [center x, top y] once dragged
PILL_FILE = us.DATA + "/pill-agent"
DRAG_THRESHOLD = 4  # px of movement before a press counts as a drag, not a click
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
.ok progress { background: %(ok)s; }
.warn progress { background: %(warn)s; }
.bad progress { background: %(bad)s; }
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



def month_labels(start, n_days):
    """[(column, "Jan"), ...] for each week column where a month begins, GitHub-style."""
    if not start:
        return []
    out = []
    for i in range(0, n_days, 7):
        week = [start + timedelta(i + d) for d in range(7)]
        firsts = [d for d in week if d.day == 1]
        if i == 0 or firsts:
            out.append((i // 7, (firsts or week)[0].strftime("%b")))
    if len(out) > 1 and out[1][0] - out[0][0] < 3:  # partial first month would overlap the next label
        out.pop(0)
    return out


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
    CELL, GAP, TOP = 13, 4, 16  # TOP: room for the month labels

    def __init__(self, who):
        super().__init__()
        self.who, self.levels, self.start = who, [], None
        self.set_size_request(HEAT_WEEKS * (self.CELL + self.GAP), self.TOP + 7 * (self.CELL + self.GAP))
        self.connect("draw", self.on_draw)

    def on_draw(self, _w, cr):
        step = self.CELL + self.GAP
        cr.set_source_rgba(0.6, 0.6, 0.62, 1)
        cr.set_font_size(10)
        for col, name in month_labels(self.start, len(self.levels)):
            cr.move_to(col * step, 10)
            cr.show_text(name)
        cr.translate(0, self.TOP)
        for i, lv in enumerate(self.levels):  # i = 0 is the Monday HEAT_WEEKS-1 weeks ago
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


def clamp_position(x, y, w, h, gx, gy, gw, gh):
    """Top-left (x, y) moved the least amount that keeps a w×h window inside the area."""
    return max(gx, min(x, gx + gw - w)), max(gy, min(y, gy + gh - h))


def heat_block(box, who):
    """Pack a heatmap and its legend into box; returns (heatmap, active-days label)."""
    heat = Heatmap(who)
    box.pack_start(heat, False, False, 4)
    legend = Gtk.Box(spacing=4)
    active = lbl(cls="dim", hexpand=True)
    legend.pack_start(active, True, True, 0)
    sw = lbl()
    sw.set_markup(" ".join(f"<span foreground='{c}'>■</span>" for c in HEAT_COLORS[who]))
    legend.pack_start(lbl("Less", "dim"), False, False, 4)
    legend.pack_start(sw, False, False, 0)
    legend.pack_start(lbl("More", "dim"), False, False, 4)
    box.pack_start(legend, False, False, 0)
    return heat, active


class Island(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.POPUP)  # no decorations, no taskbar entry, above others
        self.set_title("Atoll")
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
        self.pill_icons = {a: icon(a.replace("claude", "claude-code"), 15) for a in ("claude", "codex", "pi")}
        try:  # the agent the pill shows: the last agent tab you opened
            with open(PILL_FILE) as f:
                self.pill_agent = f.read().strip()
        except OSError:
            self.pill_agent = "claude"
        head = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        for img in filter(None, self.pill_icons.values()):
            head.pack_start(img, False, False, 0)
            img.set_no_show_all(True)
        head.pack_start(self.compact, False, False, 0)
        click = Gtk.EventBox()  # the pill header: click opens/closes the panel, drag moves the island
        click.add(head)
        click.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK)
        click.connect("button-press-event", self.on_press)
        click.connect("motion-notify-event", self.on_drag)
        click.connect("button-release-event", self.on_release)
        self.drag = None
        try:
            with open(POSITION_FILE) as f:
                self.anchor = tuple(json.load(f))
        except (OSError, ValueError, TypeError):
            self.anchor = None  # default: top center of the primary monitor
        self.pill.pack_start(click, False, False, 0)

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        panel.set_size_request(470, -1)  # every tab gets the Claude tab's width
        self.last_alert = lbl("No alerts yet", "dim")
        panel.pack_start(self.last_alert, False, False, 0)
        self.claude_col, self.codex_col = Column("Claude Code", "claude-code"), Column("Codex", "codex")
        panel.pack_start(self.claude_col, False, False, 0)
        codex = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        codex.pack_start(self.codex_col, False, False, 0)

        self.heats = [heat_block(panel, "claude"), heat_block(codex, "codex")]  # history order: [claude, codex, pi]
        for box in (panel, codex):
            box.pack_start(lbl("Fresh tokens exclude context re-read from the cache. The estimated API "
                             "equivalent uses list prices; it is not what you pay.", "dim",
                               wrap=True, max_width_chars=60), False, False, 6)

        for t, title, glyph, agent in ((panel, "Claude Code", "✻", "claude"), (codex, "Codex", "◎", "codex")):
            t.title, t.glyph, t.agent, t.icon, t.on_show, t.pill = title, glyph, agent, agent.replace(
                "claude", "claude-code"), lambda: None, lambda: ""
        self.agents = tabs.load_agents()
        self.tabs = [panel, codex] + [cls(self) for cls in tabs.TABS] + [tabs.SettingsTab(self)]
        self.heats.append(heat_block(next(t for t in self.tabs if getattr(t, "agent", None) == "pi"), "pi"))
        self.tab_buttons = {}
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=120,
                               vhomogeneous=False, interpolate_size=True)
        bar = Gtk.Box(spacing=2)
        bar.get_style_context().add_class("tabbar")
        self.tab_title = lbl("Claude Code", "tabtitle")
        first = None
        for i, t in enumerate(self.tabs):
            self.stack.add_named(t, t.title)
            img = t.icon and icon(t.icon)
            b = Gtk.RadioButton(draw_indicator=False, group=first, tooltip_text=t.title)
            b.add(img or Gtk.Label(label=t.glyph))
            first = first or b
            b.connect("toggled", self.on_tab, t)
            b.set_no_show_all(not self.agents.get(getattr(t, "agent", None), True))  # hidden agents stay hidden
            self.tab_buttons[t] = b
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
        events.connect("leave-notify-event", self.on_leave)
        self.add(events)

        self.connect("size-allocate", lambda *_: self.recenter())
        self.show_all()
        self.revealer.hide()
        self.resize(1, 1)  # shrink to the pill; an oversized transparent window would block clicks under it
        for a, on in self.agents.items():
            self.set_agent(a, on)
        self.refresh()
        GLib.timeout_add_seconds(POLL_SECONDS, self.refresh)
        GLib.timeout_add_seconds(30, self.render)  # keep countdowns fresh between polls
        GLib.timeout_add(1000, self.poll_alert)

    def on_tab(self, btn, tab):
        if btn.get_active():
            self.stack.set_visible_child(tab)
            self.tab_title.set_text(tab.title)
            tab.on_show()
            agent = getattr(tab, "agent", None)
            if agent and agent != self.pill_agent:  # non-agent tabs (git, timer…) keep the current one
                self.pill_agent = agent
                try:
                    with open(PILL_FILE, "w") as f:
                        f.write(agent)
                except OSError:
                    pass
                self.render_compact()
            GLib.timeout_add(150, lambda: self.resize(1, 1) and False)  # shrink to the new tab's height

    def set_agent(self, agent, on):
        """Show or hide an agent's tab; called from Settings and at startup."""
        self.agents[agent] = on
        for t, b in self.tab_buttons.items():
            if getattr(t, "agent", None) == agent:
                b.set_visible(on)
                if not on and b.get_active():  # leaving a hidden tab selected would strand it
                    next(x for x in self.tab_buttons.values() if x.get_visible()).set_active(True)
        if agent == "claude" and on:
            self.next_fetch = 0
        self.render()

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

    def open_panel(self):
        self.alert = None  # opening the panel means you've seen it
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

    def on_press(self, _w, ev):
        if ev.button == 1:
            self.drag = (ev.x_root, ev.y_root, self.anchor or self.default_anchor(), False)

    def on_drag(self, _w, ev):
        if not self.drag:
            return
        x0, y0, (ax, ay), moved = self.drag
        dx, dy = ev.x_root - x0, ev.y_root - y0
        if moved or abs(dx) + abs(dy) > DRAG_THRESHOLD:
            self.drag = (x0, y0, (ax, ay), True)
            self.anchor = (int(ax + dx), int(ay + dy))
            self.recenter()

    def on_release(self, _w, ev):
        if not self.drag or ev.button != 1:
            return
        moved, self.drag = self.drag[3], None
        if not moved:
            if self.revealer.get_reveal_child():
                self.revealer.set_reveal_child(False)
                GLib.timeout_add(220, self.collapse)
            else:
                self.open_panel()
            return
        os.makedirs(os.path.dirname(POSITION_FILE), exist_ok=True)
        with open(POSITION_FILE + ".tmp", "w") as f:
            json.dump(self.anchor, f)
        os.replace(POSITION_FILE + ".tmp", POSITION_FILE)

    def reset_position(self):
        self.anchor = None
        try:
            os.remove(POSITION_FILE)
        except OSError:
            pass
        self.recenter()

    def default_anchor(self):
        geo = Gdk.Display.get_default().get_primary_monitor().get_workarea()  # below the GNOME top bar
        return geo.x + geo.width // 2, geo.y + 6

    def recenter(self):
        """Keep the pill's top center on the anchor, clamped so the whole window stays on its monitor."""
        cx, top = self.anchor or self.default_anchor()
        w, h = self.get_size()
        geo = Gdk.Display.get_default().get_monitor_at_point(cx, top).get_workarea()
        self.move(*clamp_position(cx - w // 2, top, w, h, geo.x, geo.y, geo.width, geo.height))

    def refresh(self):
        def work():
            if self.agents["claude"] and time.monotonic() >= self.next_fetch:  # the usage endpoint rate-limits (429); local data refreshes freely
                try:
                    self.claude_limits, self.error = us.fetch_claude_usage(), None
                    self.next_fetch = time.monotonic() + FETCH_EVERY
                    save_limits(self.claude_limits)
                except Exception as e:  # network down, token expired, 429: keep last data, back off
                    self.error = str(e)[:60]
                    self.next_fetch = time.monotonic() + backoff_seconds(e)
            try:
                state = (us.claude_stats(), us.codex_stats(), us.pi_stats())
                self.history = us.update_history(state[0][0], state[1][0], state[2][0])
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

    def agent_summary(self, agent):
        """Pill markup for one agent."""
        limits = lambda l: f"5h {pct_markup(l['five_hour']['utilization'])}   7d {pct_markup(l['seven_day']['utilization'])}"
        if agent == "claude":
            if self.claude_limits:
                return limits(self.claude_limits) + ("  ⚠" if self.error else "")
            return "offline, retrying" if self.error else "loading…"
        if not self.state:
            return "loading…"
        if agent == "codex":
            xl = us.codex_limits(self.state[1][2])
            return limits(xl) if xl else "no data"
        t = self.state[2][0].get(date.today().isoformat()) or us.blank()  # pi: no plan limits, show today
        return f"{us.human(us.fresh(t))} tok   ${t['cost']:.2f}"

    def render_compact(self):
        esc = GLib.markup_escape_text
        order = [self.pill_agent] + [a for a, _ in tabs.AGENTS]
        shown = next((a for a in order if self.agents.get(a)), None)  # selected agent, or the first one still on
        if self.alert:
            msg = self.alert[0] if len(self.alert[0]) <= 48 else self.alert[0][:47] + "…"  # ellipsized labels collapse in a shrink-to-fit popup
            text, shown = f"<span foreground='{self.alert[1]}'>●</span>  {esc(msg)}", None
        else:
            text = self.agent_summary(shown) if shown else "●"
        for t in self.tabs:  # timer / awake countdowns
            if t.pill():
                text += "   " + esc(t.pill())
        self.compact.set_markup(text)
        for a, img in self.pill_icons.items():
            if img:
                img.set_visible(a == shown)
        self.compact.set_tooltip_text(self.error)  # full error on hover, not in the pill

    def render(self):
        today = date.today()
        cl = self.claude_limits
        self.render_compact()
        if not self.state:
            return True
        (c_days, c_last), (x_days, x_last, x_lim), _pi = self.state
        t = today.isoformat()
        self.claude_col.render(cl, c_days.get(t), c_last)
        self.codex_col.render(us.codex_limits(x_lim), x_days.get(t), x_last)

        start = today - timedelta(days=today.weekday() + 7 * (HEAT_WEEKS - 1))
        days = [(start + timedelta(i)).isoformat() for i in range((today - start).days + 1)]
        for i, (heat, active) in enumerate(self.heats):
            vals = [((self.history or {}).get(k, []) + [0] * 3)[i] for k in days]
            heat.levels, heat.start = heat_levels(vals), start
            heat.queue_draw()
            active.set_text(f"{sum(v > 0 for v in vals)} active days, shaded by fresh tokens")
        return True


def self_test():
    assert clamp_position(50, 50, 100, 40, 0, 0, 1000, 800) == (50, 50)
    assert clamp_position(-30, 790, 100, 40, 0, 0, 1000, 800) == (0, 760)  # pulled back on screen
    assert clamp_position(990, 10, 100, 40, 0, 20, 1000, 800) == (900, 20)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert until("2026-01-01T02:05:30+00:00", now) == "2 h 05 min"
    assert until("2026-01-04T04:00:00+00:00", now) == "3 d 4 h"
    assert until("2025-12-31T00:00:00+00:00", now) == "0 h 00 min"
    assert until(None) == "—"
    assert month_labels(date(2026, 4, 27), 21) == [(0, "May")]  # the week holding May 1 is May's
    assert month_labels(date(2026, 4, 20), 21) == [(1, "May")]  # one-column Apr label dropped
    assert month_labels(date(2026, 4, 6), 35)[0] == (0, "Apr")
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
    os.makedirs(os.path.expanduser("~/.cache"), exist_ok=True)
    lock = open(os.path.expanduser("~/.cache/atoll.lock"), "w")  # outside CACHE so migrating it can't race the lock
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit("atoll is already running")
    tabs.migrate_old_name()
    GLib.set_prgname("atoll")  # window class, so GNOME groups it under the Atoll launcher
    prov = Gtk.CssProvider()
    prov.load_from_data((CSS.decode() % LEVEL_COLORS).encode())
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov,
                                             Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    Island()
    Gtk.main()
