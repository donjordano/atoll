"""Short human-readable numbers, model names and durations."""
from datetime import datetime, timezone


def human(n):
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if n >= div:
            v = n / div
            return f"{v:.3g}{suf}" if v < 100 else f"{v:.0f}{suf}"
    return str(int(n))


def pretty_model(m):
    """claude-opus-5-5 -> Opus 5.5; other names unchanged."""
    if not m.startswith("claude-"):
        return m
    parts = [p for p in m.split("-")[1:] if len(p) < 8]  # drop date suffixes
    return parts[0].capitalize() + " " + ".".join(parts[1:])


def until(iso, now=None):
    """'2 h 05 min' / '3 d 4 h' until an ISO timestamp."""
    if not iso:
        return "—"
    now = now or datetime.now(timezone.utc)
    s = max(0, int((datetime.fromisoformat(iso) - now).total_seconds()))
    d, h, m = s // 86400, s % 86400 // 3600, s % 3600 // 60
    return f"{d} d {h} h" if d else f"{h} h {m:02d} min"


def fmt_clock(secs):
    secs = max(0, int(secs))
    return f"{secs // 3600}:{secs % 3600 // 60:02d}:{secs % 60:02d}" if secs >= 3600 else f"{secs // 60:02d}:{secs % 60:02d}"
