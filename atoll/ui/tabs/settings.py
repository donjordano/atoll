"""Settings tab: agent switches, start at login, alert-hook status, refresh, reset position, quit."""
import os

from gi.repository import Gtk

from atoll import paths
from atoll.agents import AGENTS, save_enabled
from atoll.core.alerts import HOOK_EVENTS, alert_hooks
from atoll.storage import read_json
from atoll.system.autostart import remove_autostart, write_autostart
from atoll.ui.tabs.base import Tab
from atoll.ui.widgets import button, lbl


class SettingsTab(Tab):
    title, glyph = "Settings", ""

    def __init__(self, island):
        super().__init__(island)
        self.pack_start(lbl("Agents", "dim"), False, False, 0)
        for agent, name in AGENTS:
            row = Gtk.Box()
            row.pack_start(lbl(name), True, True, 0)
            sw = Gtk.Switch(active=island.agents[agent], valign=3)
            sw.connect("notify::active", self.on_agent, agent)
            row.pack_start(sw, False, False, 0)
            self.pack_start(row, False, False, 0)
        self.pack_start(lbl("General", "dim"), False, False, 6)
        row = Gtk.Box()
        row.pack_start(lbl("Start at login"), True, True, 0)
        self.autostart = Gtk.Switch(active=os.path.exists(paths.AUTOSTART), valign=3)
        self.autostart.connect("notify::active", self.on_autostart)
        row.pack_start(self.autostart, False, False, 0)
        self.pack_start(row, False, False, 0)
        self.hooks = lbl(cls="dim", wrap=True, max_width_chars=60)
        self.pack_start(self.hooks, False, False, 0)
        btns = Gtk.Box(spacing=8)
        btns.pack_start(button("Refresh now", self.island.refresh), False, False, 0)
        btns.pack_start(button("Reset position", self.island.reset_position), False, False, 0)
        btns.pack_start(button("Quit island", Gtk.main_quit), False, False, 0)
        self.pack_start(btns, False, False, 6)

    def on_show(self):
        missing = [e for e in HOOK_EVENTS if e not in alert_hooks(read_json(paths.CLAUDE_SETTINGS))]
        if not missing:
            self.hooks.set_text("Claude Code alerts: connected (Notification, Stop and UserPromptSubmit hooks)")
        elif len(missing) == len(HOOK_EVENTS):
            self.hooks.set_text("Claude Code alerts: not connected. Add the Atoll hooks to ~/.claude/settings.json.")
        else:
            self.hooks.set_text(f"Claude Code alerts: partly connected; missing the {', '.join(missing)} hook.")

    def on_agent(self, sw, _p, agent):
        self.island.set_agent(agent, sw.get_active())
        save_enabled(self.island.agents)

    def on_autostart(self, sw, _p):
        write_autostart() if sw.get_active() else remove_autostart()
