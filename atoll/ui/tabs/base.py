"""What every tab in the island provides."""
from gi.repository import Gtk


class Tab(Gtk.Box):
    """One page of the panel. agent: set on agent tabs, which Settings can hide and the pill can show."""
    title, glyph, agent, icon = "", "", None, None  # icon: name in atoll/icons, shown instead of glyph

    def __init__(self, island):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.island = island

    def on_show(self):
        """Called when the tab becomes visible or the panel opens on it."""

    def pill(self):
        """Extra text for the pill (timer, keep-awake), or ''."""
        return ""
