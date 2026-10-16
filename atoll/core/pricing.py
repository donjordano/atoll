"""API list prices, for the 'estimated API equivalent' figures."""

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


def price_for(model):
    for k, p in PRICES.items():  # prefix match handles dated ids like claude-haiku-4-5-20251001
        if model and model.startswith(k) and not model.startswith(k + "-5"):
            return p
    return None
