"""Start Atoll: one instance per user, data moved from older layouts, then the window."""
import fcntl, os, sys

from atoll import paths


def main():
    os.makedirs(os.path.dirname(paths.LOCK), exist_ok=True)
    lock = open(paths.LOCK, "w")  # held for the process lifetime
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit("atoll is already running")

    from atoll.system.autostart import migrate_old_layout
    migrate_old_layout()

    from atoll.ui import style  # after the lock, so a second launch exits without loading GTK
    from atoll.ui.window import Island  # atoll.ui pins GTK 3 before anything imports it
    from gi.repository import GLib, Gtk
    GLib.set_prgname("atoll")  # window class, so GNOME groups it under the Atoll launcher
    style.install()
    Island()
    Gtk.main()
