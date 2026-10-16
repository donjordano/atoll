"""The island window: the pill, dragging, the tab bar, alerts and data refresh."""
import os, threading, time
from datetime import date, datetime

from gi.repository import Gdk, GLib, Gtk

from atoll import paths
from atoll.agents import AGENTS, ICONS, claude, codex, load_enabled, pi
from atoll.core.alerts import describe_alert
from atoll.core.fmt import human
from atoll.core.heat import heat_window
from atoll.core.history import ORDER, update_history
from atoll.core.net import FETCH_EVERY, backoff_seconds
from atoll.core.tokens import blank, fresh
from atoll.storage import read_json, write_json
from atoll.ui.style import pct_markup
from atoll.ui.tabs import TABS
from atoll.ui.tabs.agent import AgentTab
from atoll.ui.tabs.settings import SettingsTab
from atoll.ui.widgets import icon, lbl

POLL_SECONDS = 120
DRAG_THRESHOLD = 4  # px of movement before a press counts as a drag, not a click


def clamp_position(x, y, w, h, gx, gy, gw, gh):
    """Top-left (x, y) moved the least amount that keeps a w×h window inside the area."""
    return max(gx, min(x, gx + gw - w)), max(gy, min(y, gy + gh - h))


class Island(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.POPUP)  # no decorations, no taskbar entry, above others
        self.set_title("Atoll")
        self.set_visual(self.get_screen().get_rgba_visual())
        self.set_app_paintable(True)
        self.claude_limits = self.error = None
        self.state = self.history = self.alert = self.project_cwd = self.kb_grab = None
        self.alert_mtime = self.next_fetch = 0
        self.refreshing = False  # one refresh at a time: they share the scanners and the history file
        cached, age = claude.load_cached_usage()  # last good numbers: shown at once, and a restart within FETCH_EVERY skips the API
        if cached:
            self.claude_limits = cached
            self.next_fetch = time.monotonic() + max(0, FETCH_EVERY - age)

        self.pill = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, name="pill")
        self.compact = lbl("Claude …", xalign=0.5)
        self.pill_icons = {a: icon(ICONS[a], 15) for a, _ in AGENTS}
        try:  # the agent the pill shows: the last agent tab you opened
            with open(paths.PILL_FILE) as f:
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
        pos = read_json(paths.POSITION_FILE)
        self.anchor = tuple(pos) if isinstance(pos, list) and len(pos) == 2 else None  # None: top center of the primary monitor
        self.pill.pack_start(click, False, False, 0)

        self.agents = load_enabled()
        self.claude_tab = AgentTab(self, "claude", "Claude Code", "✻", alerts=True)
        self.codex_tab = AgentTab(self, "codex", "Codex", "◎")
        self.last_alert = self.claude_tab.last_alert
        self.tabs = [self.claude_tab, self.codex_tab] + [cls(self) for cls in TABS] + [SettingsTab(self)]
        self.by_agent = {t.agent: t for t in self.tabs if t.agent}
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
            b.set_no_show_all(not self.agents.get(t.agent, True))  # hidden agents stay hidden
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
            agent = tab.agent
            if agent and agent != self.pill_agent:  # non-agent tabs (git, timer…) keep the current one
                self.pill_agent = agent
                try:
                    with open(paths.PILL_FILE, "w") as f:
                        f.write(agent)
                except OSError:
                    pass
                self.render_compact()
            GLib.timeout_add(150, lambda: self.resize(1, 1) and False)  # shrink to the new tab's height

    def set_agent(self, agent, on):
        """Show or hide an agent's tab; called from Settings and at startup."""
        self.agents[agent] = on
        for t, b in self.tab_buttons.items():
            if t.agent == agent:
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
            mtime = os.stat(paths.ALERT_FILE).st_mtime
        except OSError:
            return True
        if mtime != self.alert_mtime:
            self.alert_mtime = mtime
            a = read_json(paths.ALERT_FILE)
            d = describe_alert(a) if isinstance(a, dict) else None
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
        write_json(paths.POSITION_FILE, self.anchor)

    def reset_position(self):
        self.anchor = None
        try:
            os.remove(paths.POSITION_FILE)
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
        if self.refreshing:
            return True
        self.refreshing = True

        def work():
            if self.agents["claude"] and time.monotonic() >= self.next_fetch:  # the usage endpoint rate-limits (429); local data refreshes freely
                try:
                    self.claude_limits, self.error = claude.fetch_usage(), None
                    self.next_fetch = time.monotonic() + FETCH_EVERY
                    claude.save_cached_usage(self.claude_limits)
                except Exception as e:  # network down, token expired, 429: keep last data, back off
                    self.error = str(e)[:60]
                    self.next_fetch = time.monotonic() + backoff_seconds(e)
            try:
                state = (claude.stats(), codex.stats(), pi.stats())
                self.history = update_history(state[0][0], state[1][0], state[2][0])
                lasts = [l for l in (state[0][1], state[1][1]) if l]
                self.project_cwd = max(lasts)[2] if lasts else None
            except Exception as e:  # a malformed log must not kill the island
                self.error, state = f"log scan: {e}"[:60], self.state
            GLib.idle_add(self.apply, state)
        threading.Thread(target=work, daemon=True).start()
        return True

    def apply(self, state):
        self.refreshing = False
        self.state = state
        self.render()
        return False

    def agent_summary(self, agent):
        """Pill markup for one agent."""
        pct = lambda w: "—" if w.get("utilization") is None else pct_markup(w["utilization"])
        limits = lambda l: f"5h {pct(l['five_hour'])}   7d {pct(l['seven_day'])}"  # shape checked by normalize_usage / plan_limits
        if agent == "claude":
            if self.claude_limits:
                return limits(self.claude_limits) + ("  ⚠" if self.error else "")
            return "offline, retrying" if self.error else "loading…"
        if not self.state:
            return "loading…"
        if agent == "codex":
            xl = codex.plan_limits(self.state[1][2])
            return limits(xl) if xl else "no data"
        t = self.state[2][0].get(date.today().isoformat()) or blank()  # pi: no plan limits, show today
        return f"{human(fresh(t))} tok   ${t['cost']:.2f}"

    def render_compact(self):
        esc = GLib.markup_escape_text
        order = [self.pill_agent] + [a for a, _ in AGENTS]
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
        self.claude_tab.render(cl, c_days.get(t), c_last)
        self.codex_tab.render(codex.plan_limits(x_lim), x_days.get(t), x_last)

        start, days = heat_window(today)
        for i, agent in enumerate(ORDER):
            vals = [((self.history or {}).get(k, []) + [0] * len(ORDER))[i] for k in days]
            self.by_agent[agent].heat.update(vals, start)
        return True
