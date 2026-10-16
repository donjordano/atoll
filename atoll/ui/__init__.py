"""GTK 3 user interface: the window, its tabs and shared widgets."""
import gi

for _ns, _v in (("Gtk", "3.0"), ("Gdk", "3.0"), ("GdkPixbuf", "2.0")):  # before any gi.repository import below
    gi.require_version(_ns, _v)
