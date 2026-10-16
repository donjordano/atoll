"""Every file and folder Atoll reads or writes."""
import os

HOME = os.path.expanduser("~")
PACKAGE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(PACKAGE)  # source checkout or /opt/atoll
ICONS = os.path.join(PACKAGE, "icons")
LAUNCHER = os.path.join(ROOT, "bin", "atoll")

DATA = HOME + "/.local/share/atoll"  # history, limits, tasks, settings
CACHE = HOME + "/.cache/atoll"  # alert file from Claude Code hooks
LOCK = HOME + "/.cache/atoll.lock"  # outside CACHE so migrating CACHE can't race the lock

ALERT_FILE = CACHE + "/alert"  # written by Claude Code hooks
LIMITS_CACHE = DATA + "/limits.json"
POSITION_FILE = DATA + "/position.json"  # [center x, top y] once dragged
PILL_FILE = DATA + "/pill-agent"
HISTORY = DATA + "/daily.json"
TASKS_FILE = DATA + "/tasks.json"
AGENTS_FILE = DATA + "/agents.json"
AUTOSTART = HOME + "/.config/autostart/atoll.desktop"
CLAUDE_SETTINGS = HOME + "/.claude/settings.json"
