"""Tasks tab: a to-do list saved in ~/.local/share/atoll/tasks.json."""
from gi.repository import GLib, Gtk

from atoll import paths
from atoll.storage import read_json, write_json
from atoll.ui.tabs.base import Tab
from atoll.ui.widgets import button, clear, lbl


def load_tasks(path=paths.TASKS_FILE):
    return read_json(path, [])


def save_tasks(tasks, path=paths.TASKS_FILE):
    write_json(path, tasks)


class TasksTab(Tab):
    title, glyph = "Tasks", ""

    def __init__(self, island):
        super().__init__(island)
        self.tasks = load_tasks()
        self.entry = Gtk.Entry(placeholder_text="Add a task and press Enter")
        self.entry.connect("button-press-event", lambda *_: self.island.grab_keyboard(self.entry))
        self.entry.connect("activate", self.add)
        self.pack_start(self.entry, False, False, 0)
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.pack_start(self.list, False, False, 0)
        self.rebuild()

    def add(self, entry):
        text = entry.get_text().strip()
        if text:
            self.tasks.append({"text": text, "done": False})
            entry.set_text("")
            self.changed()

    def changed(self):
        save_tasks(self.tasks)
        self.rebuild()

    def rebuild(self):
        clear(self.list)
        for t in self.tasks:
            row = Gtk.Box(spacing=6)
            cb = Gtk.CheckButton(active=t["done"])
            cb.add(lbl())
            cb.get_child().set_markup(f"<s>{GLib.markup_escape_text(t['text'])}</s>" if t["done"]
                                      else GLib.markup_escape_text(t["text"]))
            cb.connect("toggled", lambda b, t=t: (t.update(done=b.get_active()), self.changed()))
            row.pack_start(cb, True, True, 0)
            row.pack_start(button("✕", lambda t=t: (self.tasks.remove(t), self.changed()), "flat"), False, False, 0)
            self.list.pack_start(row, False, False, 0)
        if not self.tasks:
            self.list.pack_start(lbl("Nothing to do", "dim"), False, False, 0)
        self.list.show_all()
