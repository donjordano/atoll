"""Git status and recent commits for the project you used last."""
import subprocess


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
    """parse_git() of the repo at path, or None if it isn't one."""
    try:
        r = subprocess.run(["git", "-C", path, "status", "--porcelain=v2", "--branch"],
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return parse_git(r.stdout) if r.returncode == 0 else None


def recent_commits(path, n=6):
    return subprocess.run(["git", "-C", path, "log", f"-{n}", "--format=%h  %s  · %cr"],
                          capture_output=True, text=True, timeout=5).stdout
