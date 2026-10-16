"""Keep Awake: a logind inhibitor that blocks sleep, idle suspend and lid-close suspend."""
import os, time

from gi.repository import Gio, GLib

from atoll.system.sysinfo import low_battery

CHOICES = [("Off", 0), ("1h", 3600), ("4h", 4 * 3600), ("8h", 8 * 3600), ("∞", None)]


class Awake:
    """Holds a logind sleep/idle/lid-switch inhibitor. The lock lives in an fd, so it ends with this process."""

    def __init__(self):
        self.fd, self.until = None, None

    def start(self, seconds):
        self.stop()
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
        res, fds = bus.call_with_unix_fd_list_sync(
            "org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager", "Inhibit",
            GLib.Variant("(ssss)", ("sleep:idle:handle-lid-switch", "Atoll", "Keeping agents running", "block")),
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
