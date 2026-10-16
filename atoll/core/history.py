"""Atoll's own daily totals, so heatmap days survive the agents pruning their logs."""
from atoll import paths
from atoll.core.tokens import fresh
from atoll.storage import read_json, write_json

ORDER = ("claude", "codex", "pi")  # slot of each agent in a history row


def merge_history(stored, *agent_days):
    """Per-day [claude, codex, pi] fresh tokens; keeps the max so days survive log pruning."""
    out = dict(stored)
    for i, days in enumerate(agent_days):
        for day, s in days.items():
            row = list(out.get(day, []))
            row += [0] * (len(agent_days) - len(row))  # rows saved before Pi have 2 slots
            row[i] = max(row[i], fresh(s))
            out[day] = row
    return out


def update_history(*agent_days, path=paths.HISTORY):
    stored = read_json(path, {})
    merged = merge_history(stored, *agent_days)
    if merged != stored:
        write_json(path, merged)
    return merged
