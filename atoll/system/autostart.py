"""Start at login, and moving data over from older names and layouts."""
import os

from atoll import paths


def autostart_entry(launcher=paths.LAUNCHER):
    return ("[Desktop Entry]\nType=Application\nName=Atoll\n"
            f"Exec=python3 {launcher}\n"
            "X-GNOME-Autostart-enabled=true\n")


def write_autostart():
    os.makedirs(os.path.dirname(paths.AUTOSTART), exist_ok=True)
    with open(paths.AUTOSTART, "w") as f:
        f.write(autostart_entry())


def remove_autostart():
    if os.path.exists(paths.AUTOSTART):
        os.remove(paths.AUTOSTART)


def migrate_old_layout():
    """One-time moves: the claude-island name's folders and login entry, and login entries for the old island.py."""
    for old, new in ((paths.HOME + "/.local/share/claude-island", paths.DATA),
                     (paths.HOME + "/.cache/claude-island", paths.CACHE)):
        if os.path.isdir(old) and not os.path.exists(new):
            os.rename(old, new)
    old = paths.HOME + "/.config/autostart/claude-island.desktop"
    if os.path.exists(old):
        write_autostart()
        os.remove(old)
    try:
        with open(paths.AUTOSTART) as f:
            stale = "island.py" in f.read()  # written before the code moved into the atoll package
    except OSError:
        stale = False
    if stale:
        write_autostart()
