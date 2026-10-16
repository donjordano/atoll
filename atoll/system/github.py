"""Open pull requests through the GitHub CLI."""
import json, subprocess

QUERIES = [("Yours", "--author=@me"), ("Review requested", "--review-requested=@me")]


def parse_prs(text):
    return [(p["repository"]["nameWithOwner"], p["number"], p["title"], p["url"]) for p in json.loads(text or "[]")]


def search_prs():
    """[(heading, [(repo, number, title, url), ...]), ...]; raises RuntimeError if gh fails."""
    out = []
    for name, flag in QUERIES:
        r = subprocess.run(["gh", "search", "prs", flag, "--state=open", "--limit=6",
                            "--json=repository,number,title,url"], capture_output=True, text=True, timeout=20)
        if r.returncode:
            raise RuntimeError(r.stderr.strip()[:80] or "gh failed")
        out.append((name, parse_prs(r.stdout)))
    return out
