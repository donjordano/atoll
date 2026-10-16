"""Turn Claude Code hook payloads into pill alerts."""
import os


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
