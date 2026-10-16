"""Regenerate docs/pill.png and docs/panels.png from your own data, with project names replaced.

Run from the repo root on an X11 desktop: python3 docs/screenshot.py  (needs ImageMagick's `montage`)
Reads plan limits from Atoll's cache instead of calling the API. Check the images before committing.
"""
import os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import cairo
from atoll.ui import style, window  # noqa: E402  (atoll.ui pins the GTK 3 versions first)
from atoll.agents import claude, codex, pi  # noqa: E402
from gi.repository import Gtk, GLib  # noqa: E402

OUT = os.path.join(ROOT, "docs") + "/"
claude.fetch_usage = lambda: claude.load_cached_usage()[0]  # no API call
claude.save_cached_usage = lambda d: None
anon = lambda last: last and (last[0], last[1], "/home/you/atoll")
for mod in (claude, codex, pi):
    f = mod.stats
    mod.stats = lambda f=f: tuple(anon(x) if isinstance(x, tuple) and len(x) == 3 and isinstance(x[0], str) else x
                                  for x in f())
window.Island.recenter = lambda self: None  # stay put while capturing

style.install()
w = window.Island()
w.move(-3000, -3000)
w.pill_agent = "claude"
buttons = list(w.tab_buttons.values())

def shot(name, then, tries=40):
    """Capture once the window's size has stopped changing (the panel slides open and resizes per tab)."""
    w.check_resize()
    while Gtk.events_pending():
        Gtk.main_iteration()
    a = w.get_allocation()
    if tries and (a.height, a.width) != getattr(shot, "last", None):
        shot.last = (a.height, a.width)
        GLib.timeout_add(200, lambda: shot(name, then, tries - 1) and False)
        return
    shot.last = None
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, a.width, a.height)
    w.draw(cairo.Context(s))
    s.write_to_png(OUT + name)
    print(name, a.width, a.height)
    then()


steps = [  # (action, image to save after it); each starts only when the previous capture is written
    (lambda: None, "pill.png"),
    (w.open_panel, "claude.png"),
    (lambda: buttons[1].set_active(True), "codex.png"),
    (lambda: buttons[2].set_active(True), "pi.png"),
]


def run_next():
    if not steps:
        Gtk.main_quit()
        return
    action, name = steps.pop(0)
    action()
    GLib.timeout_add(1500, lambda: shot(name, run_next) and False)  # let data load and tabs fetch


GLib.timeout_add(1500, lambda: run_next() and False)
Gtk.main()
subprocess.run(["montage", "-background", "none", "-tile", "3x1", "-geometry", "+16+0", "-gravity", "north",
                *(OUT + n for n in ("claude.png", "codex.png", "pi.png")), OUT + "panels.png"], check=True)
for n in ("claude.png", "codex.png", "pi.png"):
    os.remove(OUT + n)
