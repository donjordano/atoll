"""Island tabs besides Usage: Pi/OpenRouter, media, git, PRs, focus timer, calendar, tasks, activity, settings."""
import glob, json, os, subprocess, threading, time, urllib.request
from datetime import date, timedelta

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GdkPixbuf, Gio, GLib

import usage_stats as us

DATA = os.path.expanduser("~/.local/share/claude-island")
TASKS_FILE = DATA + "/tasks.json"
AGENTS_FILE = DATA + "/agents.json"
AGENTS = [("claude", "Claude Code"), ("codex", "Codex"), ("pi", "Pi · OpenRouter")]
AUTOSTART = os.path.expanduser("~/.config/autostart/claude-island.desktop")
AWAKE_CHOICES = [("Off", 0), ("1h", 3600), ("4h", 4 * 3600), ("8h", 8 * 3600), ("∞", None)]


LEVEL_COLORS = {"ok": "#30d158", "warn": "#ff9f0a", "bad": "#ff453a"}  # green ≤50%, orange ≤80%, red above


def level(pct):
    return "ok" if pct <= 50 else "warn" if pct <= 80 else "bad"


def pct_markup(pct):
    return f"<span foreground='{LEVEL_COLORS[level(pct)]}'>{pct:.0f}%</span>"


def lbl(text="", cls=None, xalign=0, **kw):
    l = Gtk.Label(label=text, xalign=xalign, **kw)
    for c in (cls or "").split():
        l.get_style_context().add_class(c)
    return l


def button(text, cb, cls="btn", *args):
    b = Gtk.Button(label=text)
    b.get_style_context().add_class(cls)
    b.connect("clicked", lambda _b: cb(*args))
    return b


def bg(work, done):
    """Run work() off the GTK thread, then done(result or exception) on it."""
    def run():
        try:
            r = work()
        except Exception as e:  # handed to done() so the tab can show it
            r = e
        GLib.idle_add(lambda: done(r) and False)
    threading.Thread(target=run, daemon=True).start()


def clear(box):
    for c in box.get_children():
        box.remove(c)


def load_agents(path=AGENTS_FILE):
    """{agent: shown?}; agents missing from the file default to on."""
    try:
        with open(path) as f:
            saved = json.load(f)
    except (OSError, ValueError):
        saved = {}
    return {a: bool(saved.get(a, True)) for a, _ in AGENTS}


def save_agents(agents, path=AGENTS_FILE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w") as f:
        json.dump(agents, f)
    os.replace(path + ".tmp", path)


class Tab(Gtk.Box):
    title, glyph, agent = "", "", None

    def __init__(self, island):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.island = island

    def on_show(self):
        pass

    def pill(self):
        return ""


# ─── Pi + OpenRouter ────────────────────────────────────────────────────────

def grid(rows):
    """Two-column dim-label / right-aligned value grid; returns (grid, {title: value label})."""
    g, cells = Gtk.Grid(row_spacing=1), {}
    for i, title in enumerate(rows):
        g.attach(lbl(title, "dim", hexpand=True), 0, i, 1, 1)
        cells[title] = lbl(xalign=1)
        g.attach(cells[title], 1, i, 1, 1)
    return g, cells


def top_models(models, n=3):
    return sorted(models.items(), key=lambda kv: -kv[1])[:n]


class PiTab(Tab):
    title, glyph, agent = "Pi · OpenRouter", "π", "pi"
    PI_ROWS = ["Input", "Cache write", "Output", "Cache read", "Requests", "Sessions"]
    OR_ROWS = ["Today", "This week", "This month", "All time"]

    def __init__(self, island):
        super().__init__(island)
        cols = Gtk.Box(spacing=28, homogeneous=True)
        self.pack_start(cols, False, False, 0)
        pi = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        orr = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        cols.pack_start(pi, True, True, 0)
        cols.pack_start(orr, True, True, 0)

        pi.pack_start(lbl("π  Pi", "title"), False, False, 2)
        pi.pack_start(lbl("Today on this PC", "dim"), False, False, 4)
        self.fresh = lbl()
        pi.pack_start(self.fresh, False, False, 0)
        g, self.pi_cells = grid(self.PI_ROWS)
        pi.pack_start(g, False, False, 2)
        self.cost, self.week = lbl(), lbl(cls="dim")
        self.where = lbl(cls="dim", ellipsize=3)
        for w in (self.cost, self.week, self.where):
            pi.pack_start(w, False, False, 0)
        pi.pack_start(lbl("Models today", "dim"), False, False, 6)
        self.models = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        pi.pack_start(self.models, False, False, 0)

        orr.pack_start(lbl("◇  OpenRouter", "title"), False, False, 2)
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

    def on_show(self):
        self.render_pi()
        if time.monotonic() - self.fetched < 60:
            return
        self.fetched = time.monotonic()
        bg(us.fetch_openrouter_key, self.render_or)

    def render_pi(self):
        days, models, last = us.pi_stats()
        today = date.today()
        t = days.get(today.isoformat()) or us.blank()
        self.fresh.set_markup(f"<span size='xx-large' weight='bold'>{us.human(us.fresh(t))}</span>  fresh tokens")
        reqs = sum(models.get(today.isoformat(), {}).values())
        vals = {"Input": t["input"], "Cache write": t["cache_write"], "Output": t["output"],
                "Cache read": t["cache_read"], "Requests": reqs, "Sessions": len(t["sessions"])}
        for k, v in vals.items():
            self.pi_cells[k].set_text(us.human(v))
        self.cost.set_markup(f"<b>${t['cost']:.2f}</b> billed today")
        week = [days.get((today - timedelta(i)).isoformat()) or us.blank() for i in range(7)]
        self.week.set_text(f"7 days: {us.human(sum(map(us.fresh, week)))} tokens · ${sum(d['cost'] for d in week):.2f}")
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
        for bar, frac in ((self.limit_bar, self.limit_bar.get_fraction()), (self.free_bar, self.free_bar.get_fraction())):
            ctx = bar.get_style_context()
            for c in ("ok", "warn", "bad"):
                ctx.remove_class(c)
            ctx.add_class(level(frac * 100))


# ─── Media ──────────────────────────────────────────────────────────────────

MPRIS_PATH, PLAYER = "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player"


def pick_player(players):
    """[(bus_name, status)] -> the playing one, else the first; None if empty."""
    return next((n for n, s in players if s == "Playing"), players[0][0] if players else None)


class MediaTab(Tab):
    title, glyph = "Media", ""

    def __init__(self, island):
        super().__init__(island)
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        self.player, self.art_url, self.art_cache = None, None, {}
        row = Gtk.Box(spacing=14)
        self.art = Gtk.Image()
        self.art.set_size_request(72, 72)
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=1)  # 1 = START
        self.song = lbl("No media playing", "title", ellipsize=3)
        self.artist = lbl(cls="dim", ellipsize=3)
        self.app = lbl(cls="dim", ellipsize=3)
        for w in (self.song, self.artist, self.app):
            info.pack_start(w, False, False, 0)
        row.pack_start(self.art, False, False, 0)
        row.pack_start(info, True, True, 0)
        self.pack_start(row, False, False, 0)
        self.progress = Gtk.ProgressBar()
        self.progress.get_style_context().add_class("ok")
        self.pack_start(self.progress, False, False, 0)
        ctrl = Gtk.Box(spacing=18, halign=3)  # 3 = CENTER
        self.play = button("", self.control, "flat icon", "PlayPause")
        for w in (button("", self.control, "flat icon", "Previous"), self.play,
                  button("", self.control, "flat icon", "Next")):
            ctrl.pack_start(w, False, False, 0)
        self.pack_start(ctrl, False, False, 0)
        GLib.timeout_add_seconds(2, self.poll)

    def call(self, name, iface, method, args=None, rtype=None):
        return self.bus.call_sync(name, MPRIS_PATH, iface, method, args, rtype,
                                  Gio.DBusCallFlags.NONE, 300, None)  # 300 ms: a hung player must not freeze the island

    def poll(self):
        if self.get_mapped():
            self.on_show()
        return True

    def on_show(self):
        try:
            names = self.bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                                       "ListNames", None, GLib.VariantType("(as)"),
                                       Gio.DBusCallFlags.NONE, 300, None).unpack()[0]
            props = {}
            for n in (n for n in names if n.startswith("org.mpris.MediaPlayer2.")):
                try:
                    props[n] = self.call(n, "org.freedesktop.DBus.Properties", "GetAll",
                                         GLib.Variant("(s)", (PLAYER,)), GLib.VariantType("(a{sv})")).unpack()[0]
                except GLib.Error:
                    pass  # player vanished between ListNames and GetAll
        except GLib.Error:
            props = {}
        self.player = pick_player([(n, p.get("PlaybackStatus")) for n, p in props.items()])
        if not self.player:
            self.song.set_text("No media playing")
            self.artist.set_text("Start Spotify, a browser video, or any MPRIS player")
            self.app.set_text("")
            self.art.clear()
            self.progress.set_fraction(0)
            return
        p = props[self.player]
        md = p.get("Metadata", {})
        self.song.set_text(md.get("xesam:title") or "Unknown title")
        self.artist.set_text(", ".join(md.get("xesam:artist") or []) or md.get("xesam:album", ""))
        self.app.set_text(self.player.split(".")[3].capitalize())
        self.play.set_label("" if p.get("PlaybackStatus") == "Playing" else "")
        length = md.get("mpris:length") or 0
        self.progress.set_fraction(min(1, (p.get("Position") or 0) / length) if length else 0)
        self.set_art(md.get("mpris:artUrl"))

    def set_art(self, url):
        if url == self.art_url:
            return
        self.art_url = url
        if not url:
            self.art.clear()
        elif url in self.art_cache:
            self.art.set_from_pixbuf(self.art_cache[url])
        else:
            def load():
                if url.startswith("file://"):
                    return GdkPixbuf.Pixbuf.new_from_file_at_scale(GLib.filename_from_uri(url)[0], 72, 72, True)
                with urllib.request.urlopen(url, timeout=5) as r:
                    loader = GdkPixbuf.PixbufLoader()
                    loader.write(r.read())
                    loader.close()
                    return loader.get_pixbuf().scale_simple(72, 72, GdkPixbuf.InterpType.BILINEAR)

            def done(pix):
                if isinstance(pix, GdkPixbuf.Pixbuf):
                    self.art_cache[url] = pix
                    if self.art_url == url:
                        self.art.set_from_pixbuf(pix)
            bg(load, done)

    def control(self, method):
        if self.player:
            try:
                self.call(self.player, PLAYER, method)
            except GLib.Error:
                pass  # e.g. Next unsupported by this player
            GLib.timeout_add(250, lambda: self.on_show() and False)


# ─── Git ────────────────────────────────────────────────────────────────────

class GitTab(Tab):
    title, glyph = "Git", ""

    def __init__(self, island):
        super().__init__(island)
        self.head = lbl(cls="big")
        self.sub = lbl(cls="dim", ellipsize=3)
        self.files = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.commits = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for w in (self.head, self.sub, lbl("Changes", "dim"), self.files, lbl("Recent commits", "dim"), self.commits):
            self.pack_start(w, False, False, 0)

    def on_show(self):
        cwd = self.island.project_cwd
        if not cwd:
            self.head.set_text("No project yet")
            return

        def work():
            st = us.git_status(cwd)
            log = subprocess.run(["git", "-C", cwd, "log", "-6", "--format=%h  %s  · %cr"],
                                 capture_output=True, text=True, timeout=5).stdout if st else ""
            return st, log
        bg(work, lambda r: self.show(cwd, r))

    def show(self, cwd, r):
        name = os.path.basename(cwd)
        clear(self.files)
        clear(self.commits)
        if isinstance(r, Exception) or not r[0]:
            self.head.set_text(name)
            self.sub.set_text("Not a git repository" if not isinstance(r, Exception) else str(r)[:60])
        else:
            g, log = r
            self.head.set_text(f"⎇ {g['branch']}")
            sync = "no upstream" if g["ahead"] is None else f"↑{g['ahead']} ↓{g['behind']}"
            self.sub.set_text(f"{name} · {g['changed']} changed · {sync}")
            for f in g["files"][:8] or ["Working tree clean"]:
                self.files.pack_start(lbl(f, "mono", ellipsize=3), False, False, 0)
            if len(g["files"]) > 8:
                self.files.pack_start(lbl(f"…and {len(g['files']) - 8} more", "dim"), False, False, 0)
            for line in log.splitlines():
                self.commits.pack_start(lbl(line, "mono", ellipsize=3), False, False, 0)
        self.show_all()


# ─── Pull requests ──────────────────────────────────────────────────────────

def parse_prs(text):
    return [(p["repository"]["nameWithOwner"], p["number"], p["title"], p["url"]) for p in json.loads(text or "[]")]


class PRTab(Tab):
    title, glyph = "Pull requests", ""
    QUERIES = [("Yours", "--author=@me"), ("Review requested", "--review-requested=@me")]

    def __init__(self, island):
        super().__init__(island)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.pack_start(self.body, False, False, 0)
        self.fetched = 0
        self.body.pack_start(lbl("Loading…", "dim"), False, False, 0)

    def on_show(self):
        if time.monotonic() - self.fetched < 120:  # GitHub search API is rate-limited
            return
        self.fetched = time.monotonic()

        def work():
            out = []
            for name, flag in self.QUERIES:
                r = subprocess.run(["gh", "search", "prs", flag, "--state=open", "--limit=6",
                                    "--json=repository,number,title,url"], capture_output=True, text=True, timeout=20)
                if r.returncode:
                    raise RuntimeError(r.stderr.strip()[:80] or "gh failed")
                out.append((name, parse_prs(r.stdout)))
            return out
        bg(work, self.show)

    def show(self, r):
        clear(self.body)
        if isinstance(r, Exception):
            self.fetched = 0  # retry on next open
            self.body.pack_start(lbl(f"GitHub CLI: {r}", "dim", wrap=True, max_width_chars=60), False, False, 0)
        else:
            for name, prs in r:
                self.body.pack_start(lbl(name, "dim"), False, False, 4)
                for repo, num, title, url in prs:
                    b = Gtk.Button()
                    b.get_style_context().add_class("flat")
                    row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                    row.pack_start(lbl(f"#{num}  {title}", ellipsize=3), False, False, 0)
                    row.pack_start(lbl(repo, "dim"), False, False, 0)
                    b.add(row)
                    b.connect("clicked", lambda _b, u=url: Gtk.show_uri_on_window(None, u, 0))
                    self.body.pack_start(b, False, False, 0)
                if not prs:
                    self.body.pack_start(lbl("None open", "mono"), False, False, 0)
        self.show_all()


# ─── Focus timer ────────────────────────────────────────────────────────────

def fmt_clock(secs):
    secs = max(0, int(secs))
    return f"{secs // 3600}:{secs % 3600 // 60:02d}:{secs % 60:02d}" if secs >= 3600 else f"{secs // 60:02d}:{secs % 60:02d}"


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


# ─── Calendar ───────────────────────────────────────────────────────────────

class CalendarTab(Tab):
    title, glyph = "Calendar", ""

    def __init__(self, island):
        super().__init__(island)
        self.cal = Gtk.Calendar()
        self.pack_start(self.cal, False, False, 0)
        # shortcut: no event list; this account has no online calendars. Read Evolution's calendar service if you add one.
        self.pack_start(button("Open GNOME Calendar", lambda: subprocess.Popen(["gnome-calendar"])),
                        False, False, 0)

    def on_show(self):
        t = time.localtime()
        self.cal.select_month(t.tm_mon - 1, t.tm_year)
        self.cal.select_day(t.tm_mday)


# ─── Tasks ──────────────────────────────────────────────────────────────────

def load_tasks(path=TASKS_FILE):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def save_tasks(tasks, path=TASKS_FILE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w") as f:
        json.dump(tasks, f)
    os.replace(path + ".tmp", path)  # atomic: never a half-written task list


class TasksTab(Tab):
    title, glyph = "Tasks", ""

    def __init__(self, island):
        super().__init__(island)
        self.tasks = load_tasks()
        self.entry = Gtk.Entry(placeholder_text="Add a task and press Enter")
        self.entry.connect("button-press-event", lambda *_: self.island.grab_keyboard(self.entry))
        self.entry.connect("activate", self.add)
        self.pack_start(self.entry, False, False, 0)
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.pack_start(self.list, False, False, 0)
        self.rebuild()

    def add(self, entry):
        text = entry.get_text().strip()
        if text:
            self.tasks.append({"text": text, "done": False})
            entry.set_text("")
            self.changed()

    def changed(self):
        save_tasks(self.tasks)
        self.rebuild()

    def rebuild(self):
        clear(self.list)
        for t in self.tasks:
            row = Gtk.Box(spacing=6)
            cb = Gtk.CheckButton(active=t["done"])
            cb.add(lbl())
            cb.get_child().set_markup(f"<s>{GLib.markup_escape_text(t['text'])}</s>" if t["done"]
                                      else GLib.markup_escape_text(t["text"]))
            cb.connect("toggled", lambda b, t=t: (t.update(done=b.get_active()), self.changed()))
            row.pack_start(cb, True, True, 0)
            row.pack_start(button("✕", lambda t=t: (self.tasks.remove(t), self.changed()), "flat"), False, False, 0)
            self.list.pack_start(row, False, False, 0)
        if not self.tasks:
            self.list.pack_start(lbl("Nothing to do", "dim"), False, False, 0)
        self.list.show_all()


# ─── Activity ───────────────────────────────────────────────────────────────

def read_cpu():
    with open("/proc/stat") as f:
        v = [int(x) for x in f.readline().split()[1:]]
    return v[3] + v[4], sum(v)  # (idle + iowait, total)


def cpu_percent(prev, cur):
    total = cur[1] - prev[1]
    return 0.0 if total <= 0 else 100.0 * (1 - (cur[0] - prev[0]) / total)


def mem_percent():
    m = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":")
            m[k] = int(v.split()[0])
    return 100.0 * (1 - m["MemAvailable"] / m["MemTotal"]), m["MemTotal"] / 1048576


def low_battery():
    for bat in glob.glob("/sys/class/power_supply/BAT*"):
        try:
            with open(bat + "/status") as f, open(bat + "/capacity") as c:
                if f.read().strip() == "Discharging" and int(c.read()) < 10:
                    return True
        except (OSError, ValueError):
            pass
    return False


class Awake:
    """Holds a logind sleep/idle/lid-switch inhibitor. The lock lives in an fd, so it ends with this process."""

    def __init__(self):
        self.fd, self.until = None, None

    def start(self, seconds):
        self.stop()
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
        res, fds = bus.call_with_unix_fd_list_sync(
            "org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager", "Inhibit",
            GLib.Variant("(ssss)", ("sleep:idle:handle-lid-switch", "Claude Island", "Keeping agents running", "block")),
            GLib.VariantType("(h)"), Gio.DBusCallFlags.NONE, -1, None, None)
        self.fd = fds.get(res.unpack()[0])
        self.until = None if seconds is None else time.monotonic() + seconds

    def stop(self):
        if self.fd is not None:
            os.close(self.fd)
        self.fd = self.until = None

    def expired(self):
        return self.fd is not None and ((self.until and time.monotonic() >= self.until) or low_battery())

    def label(self):
        if self.fd is None:
            return ""
        if self.until is None:
            return "☕ ∞"
        m = max(0, int(self.until - time.monotonic())) // 60
        return f"☕ {m // 60}h {m % 60:02d}m"


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
        for name, secs in AWAKE_CHOICES:
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


# ─── Settings ───────────────────────────────────────────────────────────────

class SettingsTab(Tab):
    title, glyph = "Settings", ""

    def __init__(self, island):
        super().__init__(island)
        self.pack_start(lbl("Agents", "dim"), False, False, 0)
        for agent, name in AGENTS:
            row = Gtk.Box()
            row.pack_start(lbl(name), True, True, 0)
            sw = Gtk.Switch(active=island.agents[agent], valign=3)
            sw.connect("notify::active", self.on_agent, agent)
            row.pack_start(sw, False, False, 0)
            self.pack_start(row, False, False, 0)
        self.pack_start(lbl("General", "dim"), False, False, 6)
        row = Gtk.Box()
        row.pack_start(lbl("Start at login"), True, True, 0)
        self.autostart = Gtk.Switch(active=os.path.exists(AUTOSTART), valign=3)
        self.autostart.connect("notify::active", self.on_autostart)
        row.pack_start(self.autostart, False, False, 0)
        self.pack_start(row, False, False, 0)
        self.hooks = lbl(cls="dim", wrap=True, max_width_chars=60)
        self.pack_start(self.hooks, False, False, 0)
        btns = Gtk.Box(spacing=8)
        btns.pack_start(button("Refresh now", self.island.refresh), False, False, 0)
        btns.pack_start(button("Quit island", Gtk.main_quit), False, False, 0)
        self.pack_start(btns, False, False, 6)

    def on_show(self):
        try:
            with open(os.path.expanduser("~/.claude/settings.json")) as f:
                ok = ".cache/claude-island" in f.read()
        except OSError:
            ok = False
        self.hooks.set_text("Claude Code alerts: connected (Notification, Stop and UserPromptSubmit hooks)" if ok else
                            "Claude Code alerts: not connected. Add the island hooks to ~/.claude/settings.json.")

    def on_agent(self, sw, _p, agent):
        self.island.set_agent(agent, sw.get_active())
        save_agents(self.island.agents)

    def on_autostart(self, sw, _p):
        if sw.get_active():
            os.makedirs(os.path.dirname(AUTOSTART), exist_ok=True)
            with open(AUTOSTART, "w") as f:
                f.write("[Desktop Entry]\nType=Application\nName=Claude Usage Island\n"
                        f"Exec=python3 {os.path.abspath(os.path.join(os.path.dirname(__file__), 'island.py'))}\n"
                        "X-GNOME-Autostart-enabled=true\n")
        elif os.path.exists(AUTOSTART):
            os.remove(AUTOSTART)


# MediaTab is off for now; add it back here to restore the media player.
TABS = [PiTab, GitTab, PRTab, TimerTab, CalendarTab, TasksTab, ActivityTab]


if __name__ == "__main__":
    import tempfile
    assert [level(p) for p in (0, 50, 51, 80, 81)] == ["ok", "ok", "warn", "warn", "bad"]
    assert pct_markup(12.4) == "<span foreground='#30d158'>12%</span>"
    assert top_models({"a": 1, "b": 5, "c": 3, "d": 2}, 2) == [("b", 5), ("c", 3)]
    assert pick_player([]) is None
    assert pick_player([("a", "Paused"), ("b", "Playing")]) == "b"
    assert pick_player([("a", "Paused"), ("b", "Stopped")]) == "a"
    assert parse_prs('[{"repository":{"nameWithOwner":"o/r"},"number":5,"title":"T","url":"u"}]') == [("o/r", 5, "T", "u")]
    assert parse_prs("") == []
    assert fmt_clock(25 * 60) == "25:00" and fmt_clock(59.9) == "00:59" and fmt_clock(-3) == "00:00"
    assert fmt_clock(90 * 60) == "1:30:00"
    assert cpu_percent((100, 1000), (150, 1100)) == 50.0 and cpu_percent((1, 1), (1, 1)) == 0.0
    p = tempfile.mktemp()
    save_tasks([{"text": "a", "done": True}], p)
    assert load_tasks(p) == [{"text": "a", "done": True}] and load_tasks(p + "x") == []
    os.unlink(p)
    p = tempfile.mktemp()
    assert load_agents(p) == {"claude": True, "codex": True, "pi": True}
    save_agents({"claude": True, "codex": False}, p)
    assert load_agents(p) == {"claude": True, "codex": False, "pi": True}  # new agents default on
    os.unlink(p)
    print("ok")
