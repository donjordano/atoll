"""Pi: tokens, billed cost and models from local session logs; spend from OpenRouter."""
import json, os, urllib.request

from atoll import paths
from atoll.core.tokens import Scanner, add, blank, local_day, merge_into

LOGS = paths.HOME + "/.pi/agent/sessions/**/*.jsonl"
AUTH = paths.HOME + "/.pi/agent/auth.json"


def parse_file(path):
    """({day: stats}, {day: {model: requests}}, last (ts, model, cwd)). Cost is what the provider billed."""
    days, models, last, cwd = {}, {}, None, ""
    with open(path, errors="replace") as f:
        for line in f:
            if '"usage"' not in line and '"session"' not in line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") == "session":
                cwd = e.get("cwd", cwd)
                continue
            m = e.get("message") or {}
            u = m.get("usage")
            if e.get("type") != "message" or m.get("role") != "assistant" or not u:
                continue
            tok = {"input": u.get("input", 0), "cache_write": u.get("cacheWrite", 0),
                   "output": u.get("output", 0), "cache_read": u.get("cacheRead", 0)}
            day, model = local_day(e["timestamp"]), m.get("model", "")
            add(days.setdefault(day, blank()), tok, (u.get("cost") or {}).get("total", 0), path)
            models.setdefault(day, {})[model] = models.get(day, {}).get(model, 0) + 1
            last = max(last or ("",), (e["timestamp"], model, cwd))
    return days, models, last


scanner = Scanner(LOGS, parse_file)


def stats():
    """({day: stats}, {day: {model: requests}}, last (ts, model, cwd))."""
    days, models, last = {}, {}, None
    for d, ms, l in scanner.scan():
        merge_into(days, d)
        for day, counts in ms.items():
            for m, n in counts.items():
                models.setdefault(day, {})[m] = models.get(day, {}).get(m, 0) + n
        if l:
            last = max(last or l, l)
    return days, models, last


def top_models(models, n=3):
    return sorted(models.items(), key=lambda kv: -kv[1])[:n]


def fetch_openrouter_key():
    """OpenRouter's /key info (spend, limits, free-model quota) for the key Pi uses."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        with open(AUTH) as f:
            key = json.load(f)["openrouter"]["key"]
    req = urllib.request.Request("https://openrouter.ai/api/v1/key", headers={"Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)["data"]
