"""Git tab: branch, sync state, changes and recent commits for the project you used last."""
import os

from gi.repository import Gtk

from atoll.system.git import git_status, recent_commits
from atoll.ui.tabs.base import Tab
from atoll.ui.widgets import bg, clear, lbl


class GitTab(Tab):
    title, glyph = "Git", ""

    def __init__(self, island):
        super().__init__(island)
        self.head = lbl(cls="big")
        self.sub = lbl(cls="dim", ellipsize=3)
        self.files = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.commits = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for w in (self.head, self.sub, lbl("Changes", "dim"), self.files, lbl("Recent commits", "dim"), self.commits):
            self.pack_start(w, False, False, 0)

    def on_show(self):
        cwd = self.island.project_cwd
        if not cwd:
            self.head.set_text("No project yet")
            return

        def work():
            st = git_status(cwd)
            return st, recent_commits(cwd) if st else ""
        bg(work, lambda r: self.show(cwd, r))

    def show(self, cwd, r):
        name = os.path.basename(cwd)
        clear(self.files)
        clear(self.commits)
        if isinstance(r, Exception) or not r[0]:
            self.head.set_text(name)
            self.sub.set_text("Not a git repository" if not isinstance(r, Exception) else str(r)[:60])
        else:
            g, log = r
            self.head.set_text(f"⎇ {g['branch']}")
            sync = "no upstream" if g["ahead"] is None else f"↑{g['ahead']} ↓{g['behind']}"
            self.sub.set_text(f"{name} · {g['changed']} changed · {sync}")
            for f in g["files"][:8] or ["Working tree clean"]:
                self.files.pack_start(lbl(f, "mono", ellipsize=3), False, False, 0)
            if len(g["files"]) > 8:
                self.files.pack_start(lbl(f"…and {len(g['files']) - 8} more", "dim"), False, False, 0)
            for line in log.splitlines():
                self.commits.pack_start(lbl(line, "mono", ellipsize=3), False, False, 0)
        self.show_all()
