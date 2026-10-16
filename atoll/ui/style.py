"""The island's look: one CSS sheet plus the green/orange/red usage levels."""
from gi.repository import Gdk, Gtk

LEVEL_COLORS = {"ok": "#30d158", "warn": "#ff9f0a", "bad": "#ff453a"}  # green ≤50%, orange ≤80%, red above

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


def level(pct):
    return "ok" if pct <= 50 else "warn" if pct <= 80 else "bad"


def pct_markup(pct):
    return f"<span foreground='{LEVEL_COLORS[level(pct)]}'>{pct:.0f}%</span>"


def set_level(widget, pct):
    """Color a progress bar by usage level."""
    ctx = widget.get_style_context()
    for c in LEVEL_COLORS:
        ctx.remove_class(c)
    ctx.add_class(level(pct))


def install():
    prov = Gtk.CssProvider()
    prov.load_from_data((CSS.decode() % LEVEL_COLORS).encode())
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
