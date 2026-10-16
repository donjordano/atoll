"""Claude Code: plan limits from Anthropic's usage endpoint, tokens from local session logs."""
import json, time, urllib.request

from atoll import paths
from atoll.core.pricing import price_for
from atoll.core.tokens import Scanner, add, blank, local_day
from atoll.storage import read_json, write_json

LOGS = paths.HOME + "/.claude/projects/**/*.jsonl"
CREDENTIALS = paths.HOME + "/.claude/.credentials.json"


def parse_file(path):
    """{msg_id: (day, tokens, cost, session)} plus the last (ts, model, cwd) seen."""
    msgs, last = {}, None
    with open(path, errors="replace") as f:
        for line in f:
            if '"assistant"' not in line:
                continue
            try:
                e = json.loads(line)
                m = e["message"]
                u = m["usage"]
            except (ValueError, KeyError, TypeError):
                continue
            model = m.get("model", "")
            if e.get("type") != "assistant" or model.startswith("<"):
                continue
            cc = u.get("cache_creation") or {}
            w1h = cc.get("ephemeral_1h_input_tokens", 0)
            cw = u.get("cache_creation_input_tokens", 0)
            tok = {"input": u.get("input_tokens", 0), "cache_write": cw,
                   "output": u.get("output_tokens", 0), "cache_read": u.get("cache_read_input_tokens", 0)}
            p = price_for(model)
            cost = 0.0 if not p else (tok["input"] * p[0] + (cw - w1h) * 1.25 * p[0] + w1h * 2 * p[0]
                                      + tok["output"] * p[1] + tok["cache_read"] * p[2]) / 1e6
            # Streaming writes one line per content block with the same usage; key by message id.
            msgs[m.get("id") or e.get("uuid")] = (local_day(e["timestamp"]), tok, cost, e.get("sessionId", path))
            last = max(last or ("",), (e["timestamp"], model, e.get("cwd", "")))
    return msgs, last


scanner = Scanner(LOGS, parse_file)


def stats():
    """({day: stats}, last (ts, model, cwd))."""
    msgs, last = {}, None
    for m, l in scanner.scan():
        msgs.update(m)
        if l:
            last = max(last or l, l)
    days = {}
    for day, tok, cost, session in msgs.values():
        add(days.setdefault(day, blank()), tok, cost, session)
    return days, last


def fetch_usage():
    """Plan limits: {"five_hour": {"utilization", "resets_at"}, "seven_day": {...}}."""
    with open(CREDENTIALS) as f:
        token = json.load(f)["claudeAiOauth"]["accessToken"]  # re-read: Claude Code refreshes it
    req = urllib.request.Request("https://api.anthropic.com/api/oauth/usage", headers={
        "Authorization": "Bearer " + token, "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": "atoll"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def load_cached_usage(path=paths.LIMITS_CACHE):
    """(last good limits, seconds since they were fetched), or (None, None)."""
    c = read_json(path) or {}
    return (c["data"], time.time() - c["at"]) if "data" in c and "at" in c else (None, None)


def save_cached_usage(data, path=paths.LIMITS_CACHE):
    try:
        write_json(path, {"at": time.time(), "data": data})
    except OSError:
        pass  # cache is a convenience; the live numbers still show
