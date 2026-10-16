"""Codex: tokens and rate limits, both read from local session logs."""
import json
from datetime import datetime, timezone

from atoll import paths
from atoll.core.pricing import price_for
from atoll.core.tokens import Scanner, add, blank, local_day, merge_into

LOGS = paths.HOME + "/.codex/sessions/**/*.jsonl"


def parse_file(path):
    """({day: stats}, last (ts, model, cwd), last rate_limits)."""
    days, last, limits = {}, None, None
    model = cwd = ""
    prev_total = None
    with open(path, errors="replace") as f:
        for line in f:
            if not any(k in line for k in ('"token_count"', '"turn_context"', '"session_meta"')):
                continue
            try:
                e = json.loads(line)
                p = e["payload"]
            except (ValueError, KeyError):
                continue
            if e.get("type") == "session_meta":
                cwd = p.get("cwd", cwd)
            elif e.get("type") == "turn_context":
                model = p.get("model", model)
                cwd = p.get("cwd", cwd)
            elif p.get("type") == "token_count":
                if p.get("rate_limits"):
                    limits = (e["timestamp"], p["rate_limits"])
                info = p.get("info") or {}
                total = (info.get("total_token_usage") or {}).get("total_tokens")
                lu = info.get("last_token_usage")
                if not lu or total == prev_total:  # Codex re-emits the same count; only count changes
                    continue
                prev_total = total
                cr, cw = lu.get("cached_input_tokens", 0), lu.get("cache_write_input_tokens", 0)
                tok = {"input": max(0, lu.get("input_tokens", 0) - cr - cw), "cache_write": cw,
                       "output": lu.get("output_tokens", 0), "cache_read": cr}
                pr = price_for(model)
                cost = 0.0 if not pr else ((tok["input"] + cw) * pr[0] + tok["output"] * pr[1] + cr * pr[2]) / 1e6
                add(days.setdefault(local_day(e["timestamp"]), blank()), tok, cost, path)
                last = (e["timestamp"], model, cwd)
    return days, last, limits


scanner = Scanner(LOGS, parse_file)


def stats():
    """({day: stats}, last (ts, model, cwd), newest logged rate_limits)."""
    days, last, limits = {}, None, None
    for d, l, lim in scanner.scan():
        merge_into(days, d)
        if l:
            last = max(last or l, l)
        if lim:
            limits = max(limits or lim, lim, key=lambda x: x[0])
    return days, last, limits


def plan_limits(logged, now=None):
    """Codex rate limits from its last logged event, in the Claude API's shape."""
    if not logged:
        return None
    now = now or datetime.now(timezone.utc).timestamp()
    out = {}
    for src, dst in (("primary", "five_hour"), ("secondary", "seven_day")):
        w = logged[1].get(src) or {}
        reset = w.get("resets_at") or 0
        # shortcut: a window whose reset time has passed is shown as 0%; usage from other machines is not seen until Codex logs again here.
        out[dst] = {"utilization": w.get("used_percent", 0) if reset > now else 0,
                    "resets_at": datetime.fromtimestamp(reset, timezone.utc).isoformat() if reset > now else None}
    return out
