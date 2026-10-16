"""Pull requests tab: your open PRs and reviews waiting on you, via the GitHub CLI."""
import time

from gi.repository import Gtk

from atoll.system.github import search_prs
from atoll.ui.tabs.base import Tab
from atoll.ui.widgets import bg, clear, lbl


class PRTab(Tab):
    title, glyph = "Pull requests", ""

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

        bg(search_prs, self.show)

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
