"""The agents Atoll tracks, and which of them the user has switched on."""
from atoll import paths
from atoll.storage import read_json, write_json

AGENTS = [("claude", "Claude Code"), ("codex", "Codex"), ("pi", "Pi · OpenRouter")]
ICONS = {"claude": "claude-code", "codex": "codex", "pi": "pi"}  # file names in atoll/icons


def load_enabled(path=paths.AGENTS_FILE):
    """{agent: shown?}; agents missing from the file default to on."""
    saved = read_json(path, {})
    return {a: bool(saved.get(a, True)) for a, _ in AGENTS}


def save_enabled(agents, path=paths.AGENTS_FILE):
    write_json(path, agents)
