"""Heatmap math: the day window, shading levels and month labels."""
from datetime import timedelta

WEEKS = 26


def heat_window(today, weeks=WEEKS):
    """(first Monday shown, [ISO day, ...] up to today)."""
    start = today - timedelta(days=today.weekday() + 7 * (weeks - 1))
    return start, [(start + timedelta(i)).isoformat() for i in range((today - start).days + 1)]


def heat_levels(values):
    """Map each day's value to 0..4 by quartile of the non-zero days."""
    nz = sorted(v for v in values if v > 0)
    if not nz:
        return [0] * len(values)
    q = [nz[max(0, len(nz) * i // 4 - 1)] for i in (1, 2, 3)]
    return [0 if v <= 0 else 1 + sum(v > t for t in q) for v in values]


def month_labels(start, n_days):
    """[(column, "Jan"), ...] for each week column where a month begins, GitHub-style."""
    if not start:
        return []
    out = []
    for i in range(0, n_days, 7):
        week = [start + timedelta(i + d) for d in range(7)]
        firsts = [d for d in week if d.day == 1]
        if i == 0 or firsts:
            out.append((i // 7, (firsts or week)[0].strftime("%b")))
    if len(out) > 1 and out[1][0] - out[0][0] < 3:  # partial first month would overlap the next label
        out.pop(0)
    return out
