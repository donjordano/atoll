"""Local token stats from Claude Code and Codex session logs, plus plan-usage fetchers."""
import glob, json, os, urllib.request
from datetime import datetime, timezone

HOME = os.path.expanduser("~")
CLAUDE_GLOB = HOME + "/.claude/projects/**/*.jsonl"
CODEX_GLOB = HOME + "/.codex/sessions/**/*.jsonl"

# USD list prices per 1M tokens: (input, output, cache read). Cache writes: 1.25x input (5m), 2x (1h).
# shortcut: hardcoded from the Anthropic table cached 2026-10-06 and a third-party GPT-6.1-Sol quote; update when prices change.
PRICES = {
    "claude-fable-5-1": (10, 50, 0.25), "claude-fable-5": (10, 50, 1.0),
    "claude-opus-5-5": (4, 20, 0.20), "claude-opus-5": (5, 25, 0.50),
    "claude-opus-4-8": (5, 25, 0.50), "claude-opus-4-7": (5, 25, 0.50), "claude-opus-4-6": (5, 25, 0.50),
    "claude-sonnet-5-5": (2, 10, 0.20), "claude-sonnet-5": (2, 10, 0.20), "claude-sonnet-4-6": (3, 15, 0.30),
    "claude-haiku-5-5": (0.10, 0.50, 0.01), "claude-haiku-4-5": (1, 5, 0.10),
    "gpt-6.1-sol": (2, 10, 0.20),  # cache-read rate assumed at 0.1x input
}
FIELDS = ("input", "cache_write", "output", "cache_read")


def price_for(model):
    for k, p in PRICES.items():  # prefix match handles dated ids like claude-haiku-4-5-20251001
        if model and model.startswith(k) and not model.startswith(k + "-5"):
            return p
    return None


def local_day(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().date().isoformat()


def blank():
    return {f: 0 for f in FIELDS} | {"cost": 0.0, "sessions": set()}


def add(day_stats, tok, cost, session):
    for f in FIELDS:
        day_stats[f] += tok[f]
    day_stats["cost"] += cost
    day_stats["sessions"].add(session)


def parse_claude_file(path):
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


def parse_codex_file(path):
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


claude_scanner = Scanner(CLAUDE_GLOB, parse_claude_file)
codex_scanner = Scanner(CODEX_GLOB, parse_codex_file)


def claude_stats():
    msgs, last = {}, None
    for m, l in claude_scanner.scan():
        msgs.update(m)
        if l:
            last = max(last or l, l)
    days = {}
    for day, tok, cost, session in msgs.values():
        add(days.setdefault(day, blank()), tok, cost, session)
    return days, last


def codex_stats():
    days, last, limits = {}, None, None
    for d, l, lim in codex_scanner.scan():
        for day, s in d.items():
            t = days.setdefault(day, blank())
            for f in FIELDS:
                t[f] += s[f]
            t["cost"] += s["cost"]
            t["sessions"] |= s["sessions"]
        if l:
            last = max(last or l, l)
        if lim:
            limits = max(limits or lim, lim, key=lambda x: x[0])
    return days, last, limits


def codex_limits(limits, now=None):
    """Codex rate limits from its last logged event, in the Claude API's shape."""
    if not limits:
        return None
    now = now or datetime.now(timezone.utc).timestamp()
    out = {}
    for src, dst in (("primary", "five_hour"), ("secondary", "seven_day")):
        w = limits[1].get(src) or {}
        reset = w.get("resets_at") or 0
        # shortcut: a window whose reset time has passed is shown as 0%; usage from other machines is not seen until Codex logs again here.
        out[dst] = {"utilization": w.get("used_percent", 0) if reset > now else 0,
                    "resets_at": datetime.fromtimestamp(reset, timezone.utc).isoformat() if reset > now else None}
    return out


def fetch_claude_usage():
    with open(HOME + "/.claude/.credentials.json") as f:
        token = json.load(f)["claudeAiOauth"]["accessToken"]  # re-read: Claude Code refreshes it
    req = urllib.request.Request("https://api.anthropic.com/api/oauth/usage", headers={
        "Authorization": "Bearer " + token, "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": "claude-code-island"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def fresh(s):
    return s["input"] + s["cache_write"] + s["output"]


HISTORY = HOME + "/.local/share/claude-island/daily.json"


def merge_history(stored, claude_days, codex_days):
    """Per-day [claude, codex] fresh tokens; keeps the max so days survive log pruning."""
    out = dict(stored)
    for i, days in enumerate((claude_days, codex_days)):
        for day, s in days.items():
            row = list(out.get(day, [0, 0]))
            row[i] = max(row[i], fresh(s))
            out[day] = row
    return out


def update_history(claude_days, codex_days, path=HISTORY):
    try:
        with open(path) as f:
            stored = json.load(f)
    except (OSError, ValueError):
        stored = {}
    merged = merge_history(stored, claude_days, codex_days)
    if merged != stored:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "w") as f:
            json.dump(merged, f)
        os.replace(path + ".tmp", path)  # atomic: a crash never leaves half a file
    return merged


def parse_git(porcelain):
    """Parse `git status --porcelain=v2 --branch` output."""
    out = {"branch": "?", "ahead": None, "behind": None, "changed": 0, "files": []}
    path_field = {"1": 8, "2": 9, "u": 10, "?": 1, "!": 1}  # index of the path in each v2 record type
    for line in porcelain.splitlines():
        if line.startswith("# branch.head "):
            out["branch"] = line.split(" ", 2)[2]
        elif line.startswith("# branch.ab "):
            a, b = line.split()[2:4]
            out["ahead"], out["behind"] = int(a), -int(b)
        elif line and not line.startswith("#"):
            out["changed"] += 1
            n = path_field.get(line[0], 1)
            out["files"].append(line.split(" ", n)[n].split("\t")[0])
    return out


def git_status(path):
    import subprocess
    try:
        r = subprocess.run(["git", "-C", path, "status", "--porcelain=v2", "--branch"],
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return parse_git(r.stdout) if r.returncode == 0 else None


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


if __name__ == "__main__":
    import tempfile
    assert price_for("claude-haiku-4-5-20251001") == (1, 5, 0.10)
    assert price_for("claude-opus-5-5") == (4, 20, 0.20) and price_for("claude-opus-5") == (5, 25, 0.50)
    assert price_for("mystery") is None
    assert human(375500) == "376k" and human(2_310_000) == "2.31M" and human(80500) == "80.5k" and human(3) == "3"
    assert pretty_model("claude-opus-5-5") == "Opus 5.5" and pretty_model("claude-haiku-4-5-20251001") == "Haiku 4.5"
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as t:
        line = {"type": "assistant", "timestamp": "2026-01-01T12:00:00Z", "sessionId": "s", "cwd": "/x/proj",
                "message": {"id": "m1", "model": "claude-opus-5-5", "usage": {
                    "input_tokens": 1_000_000, "output_tokens": 0, "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0}}}
        t.write(json.dumps(line) + "\n" + json.dumps(line) + "\n")  # duplicate streaming line
    msgs, last = parse_claude_file(t.name)
    assert len(msgs) == 1 and abs(msgs["m1"][2] - 4.0) < 1e-9 and last[2] == "/x/proj"
    with open(t.name, "w") as f:
        tc = lambda total, inp: {"timestamp": "2026-01-01T12:00:00Z", "type": "event_msg", "payload": {
            "type": "token_count", "info": {"total_token_usage": {"total_tokens": total},
            "last_token_usage": {"input_tokens": inp, "cached_input_tokens": 100, "output_tokens": 10}}}}
        for e in ({"timestamp": "2026-01-01T11:00:00Z", "type": "turn_context", "payload": {"model": "gpt-6.1-sol", "cwd": "/y"}},
                  tc(500, 300), tc(500, 300), tc(900, 400)):
            f.write(json.dumps(e) + "\n")
    days, last, _ = parse_codex_file(t.name)
    (s,) = days.values()
    assert (s["input"], s["cache_read"], s["output"]) == (500, 200, 20), s  # repeated event counted once
    os.unlink(t.name)
    lim = (0, {"primary": {"used_percent": 40, "resets_at": 2000}, "secondary": {"used_percent": 9, "resets_at": 500}})
    out = codex_limits(lim, now=1000)
    assert out["five_hour"]["utilization"] == 40 and out["seven_day"] == {"utilization": 0, "resets_at": None}
    day = lambda n: {"input": n, "cache_write": 0, "output": 0, "cache_read": 99}
    h = merge_history({"d1": [500, 7]}, {"d1": day(100), "d2": day(30)}, {"d2": day(4)})
    assert h == {"d1": [500, 7], "d2": [30, 4]}, h  # pruned/lower day keeps stored max
    g = parse_git("# branch.oid abc\n# branch.head main\n# branch.ab +2 -1\n"
                  "1 .M N... 100644 100644 100644 h1 h2 src/my file.py\n"
                  "2 R. N... 100644 100644 100644 h1 h2 R100 new.py\told.py\n? notes.txt\n")
    assert g == {"branch": "main", "ahead": 2, "behind": 1, "changed": 3,
                 "files": ["src/my file.py", "new.py", "notes.txt"]}, g
    assert parse_git("# branch.head (detached)\n")["ahead"] is None
    print("ok")
