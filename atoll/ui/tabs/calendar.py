"""Calendar tab: a month view and a shortcut to GNOME Calendar."""
import subprocess, time

from gi.repository import Gtk

from atoll.ui.tabs.base import Tab
from atoll.ui.widgets import button


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
