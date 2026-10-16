# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed
- The code is now an `atoll` Python package with separate layers: `core` (pure logic), `agents` (one module per agent), `system` (git, GitHub, CPU/memory, keep-awake, autostart) and `ui` (window, charts, and one module per tab).
- Start it with `bin/atoll` or `python3 -m atoll` instead of `python3 island.py`. Start-at-login entries that point to `island.py` are updated automatically on the first start.
- Tests moved from inline self-checks to a `unittest` suite in `tests/`.
- The Keep Awake lock now shows up as "Atoll" in `systemd-inhibit --list`.

## [0.1.0] - 2026-10-16

### Added
- A floating pill that you can drag and that remembers its spot. It shows the agent you selected last, with green, orange or red percentages, and a click opens the panel.
- Claude Code and Codex tabs:
  - plan limits with a Current/Weekly toggle;
  - today's tokens and estimated API cost;
  - the model and project you used last;
  - a 26-week heatmap.
- Pi · OpenRouter tab: Pi's tokens, billed cost and models, plus OpenRouter key spending and the free-model daily quota.
- Claude Code alerts through hooks, for permission requests, waiting for input, and finished work.
- Git, Pull requests, Focus timer, Calendar, Tasks and Activity (with Keep Awake) tabs.
- Settings: turn agents on or off, start at login, check the alert hooks, reset the pill's position.
- A `.deb` package and only one Atoll running at a time.
