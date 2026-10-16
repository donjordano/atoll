"""Per-day token counters and the cached log scanner every agent uses."""
import glob, os
from datetime import datetime

FIELDS = ("input", "cache_write", "output", "cache_read")


def local_day(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().date().isoformat()


def blank():
    return {f: 0 for f in FIELDS} | {"cost": 0.0, "sessions": set()}


def add(day_stats, tok, cost, session):
    for f in FIELDS:
        day_stats[f] += tok[f]
    day_stats["cost"] += cost
    day_stats["sessions"].add(session)


def merge_into(days, d):
    """Add one file's {day: stats} into days."""
    for day, s in d.items():
        t = days.setdefault(day, blank())
        for f in FIELDS:
            t[f] += s[f]
        t["cost"] += s["cost"]
        t["sessions"] |= s["sessions"]


def fresh(s):
    return s["input"] + s["cache_write"] + s["output"]


class Scanner:
    """Re-parses only files whose size or mtime changed."""

    def __init__(self, pattern, parser):
        self.pattern, self.parser, self.cache = pattern, parser, {}

    def scan(self):
        seen = {}
        for path in glob.glob(self.pattern, recursive=True):
            try:
                st = os.stat(path)
            except OSError:
                continue
            key = (st.st_size, st.st_mtime)
            hit = self.cache.get(path)
            seen[path] = hit if hit and hit[0] == key else (key, self.parser(path))
        self.cache = seen
        return [v[1] for v in seen.values()]
