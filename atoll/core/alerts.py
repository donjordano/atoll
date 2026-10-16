"""Turn Claude Code hook payloads into pill alerts, and check that the hooks are set up."""
import os

HOOK_EVENTS = ("Notification", "Stop", "UserPromptSubmit")


def describe_alert(a):
    """Hook payload -> (text, color, seconds to show) or None to clear."""
    ev, folder = a.get("hook_event_name"), os.path.basename(a.get("cwd") or "") or "Claude"
    if ev == "Stop":
        return f"{folder} · finished", "#30d158", 12
    if ev == "Notification":
        what = {"permission_prompt": "needs permission", "idle_prompt": "waiting for input"}.get(
            a.get("notification_type")) or a.get("message") or "needs attention"
        return f"{folder} · {what}", "#ff9f0a", 600
    return None  # UserPromptSubmit: you are back at the keyboard


def alert_hooks(settings):
    """Which of HOOK_EVENTS have a command hook writing to ~/.cache/atoll in a parsed settings.json."""
    hooks = settings.get("hooks") if isinstance(settings, dict) else None
    found = set()
    for event in HOOK_EVENTS:
        groups = (hooks or {}).get(event) if isinstance(hooks, dict) else None
        for group in groups if isinstance(groups, list) else []:
            for h in (group.get("hooks") if isinstance(group, dict) else None) or []:
                if isinstance(h, dict) and h.get("type") == "command" and "/.cache/atoll" in str(h.get("command", "")):
                    found.add(event)
    return found
