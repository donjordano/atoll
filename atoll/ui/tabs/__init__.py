"""Tabs after Claude Code and Codex, in tab-bar order. Settings is always added last."""
from atoll.ui.tabs.activity import ActivityTab
from atoll.ui.tabs.calendar import CalendarTab
from atoll.ui.tabs.git import GitTab
from atoll.ui.tabs.pi import PiTab
from atoll.ui.tabs.prs import PRTab
from atoll.ui.tabs.tasks import TasksTab
from atoll.ui.tabs.timer import TimerTab

# MediaTab (atoll.ui.tabs.media) is off for now; add it back here to restore the media player.
TABS = [PiTab, GitTab, PRTab, TimerTab, CalendarTab, TasksTab, ActivityTab]
