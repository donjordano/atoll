"""Small widget helpers every tab uses."""
import threading

from gi.repository import GdkPixbuf, GLib, Gtk

from atoll import paths


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


def icon(name, size=16):
    """Gtk.Image of atoll/icons/<name>.svg, or None if the file is missing."""
    try:
        return Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_size(f"{paths.ICONS}/{name}.svg", size, size))
    except GLib.Error:
        return None


def title_row(icon_name, text):
    """Bold section title with the agent's logo in front."""
    row = Gtk.Box(spacing=8)
    img = icon(icon_name)
    if img:
        row.pack_start(img, False, False, 0)
    row.pack_start(lbl(text, "title"), False, False, 0)
    return row


def grid(rows):
    """Two-column dim-label / right-aligned value grid; returns (grid, {title: value label})."""
    g, cells = Gtk.Grid(row_spacing=1), {}
    for i, title in enumerate(rows):
        g.attach(lbl(title, "dim", hexpand=True), 0, i, 1, 1)
        cells[title] = lbl(xalign=1)
        g.attach(cells[title], 1, i, 1, 1)
    return g, cells
