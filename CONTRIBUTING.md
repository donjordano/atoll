# Contributing to Atoll

Thanks for helping out! Bug reports, ideas, docs fixes and code are all welcome.

## Before you start

- **For bugs,** [open an issue](https://github.com/donjordano/atoll/issues/new/choose) with your distro, desktop (GNOME version, X11 or Wayland), Python version, and the output of `python3 island.py` run in a terminal.
- **For new features,** open an issue first so we can agree on the approach before you spend time on code. Small fixes can go straight to a pull request.
- **To support a new agent** (another coding CLI), say in the issue where it keeps its session logs and what a log line looks like. Remove any secrets from the sample first.

Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).

## How the project is laid out

| File | What's in it |
|---|---|
| `island.py` | The window: pill, dragging, tab bar, Claude Code and Codex tabs, heatmaps, alerts, and the entry point |
| `tabs.py` | The other tabs (Pi, Git, PRs, Timer, Calendar, Tasks, Activity, Settings, plus Media, currently turned off) and small widget helpers |
| `usage_stats.py` | Reading the agents' session logs, prices, plan-usage fetchers and the daily history. It doesn't touch GTK. |
| `icons/` | Agent logos (Lobe Icons, MIT) |
| `packaging/` | The `.deb` build script, desktop entry and app icon |

## Development setup

```sh
git clone https://github.com/<you>/atoll.git
cd atoll
python3 island.py          # run it from the source folder
```

To restart after a change, use Settings → **Quit island**, then run it again. Only one Atoll runs at a time, so quit the installed copy first if it's running.

## Tests

Each module has a built-in self-test. Run all three before opening a pull request:

```sh
python3 usage_stats.py && python3 tabs.py && python3 island.py --test
```

Each one prints `ok`. CI runs the same commands and also builds the `.deb`.

If you add logic, such as a parser, a calculation or a branch, add a small `assert` to the self-test of that module. Changes to the look need a check by eye: please attach a screenshot to your pull request.

## Code guidelines

- **No new dependencies.** Atoll uses only Python's standard library plus PyGObject and GTK 3, which are already on most GNOME desktops. Calling a tool the user may have, like `git` or `gh`, is fine if the feature fails gracefully without it.
- **Match the surrounding code** in naming, comment style and structure. Keep functions small, and only add comments that explain *why*.
- **Keep the UI responsive.** Network and slow disk work runs off the GTK thread through `bg()` in `tabs.py`, which hands the result back to the GTK thread.
- **Respect rate limits.** Anything that calls a remote API must cache its result and back off after errors; see `FETCH_EVERY` and `BACKOFF` in `island.py`.
- **Never print, log or save tokens or API keys.** Read them when you need them, from where the agent itself keeps them.
- **Write files atomically:** write a `.tmp` file, then `os.replace` it over the real one, so a crash can't leave a half-written file.
- **Note known limits in the code.** If you take a shortcut that has a limit, add a `# shortcut: <the limit>, <when to upgrade>` comment.

## Commits and pull requests

- Keep each pull request to one topic, with a short description of what changed and why.
- Write commit messages with a short title in the imperative mood ("Add Codex weekly reset time"), then a body explaining why if the title doesn't say it.
- Update `CHANGELOG.md` under **Unreleased** for anything a user would notice.
- Update the README or INSTALL guide if your change affects setup or what users see.

## Releasing (maintainers)

1. Move the **Unreleased** entries in `CHANGELOG.md` under a new version heading, and add the date.
2. Tag the release: `git tag v0.2.0 && git push --tags`.
3. Build it with `VERSION=0.2.0 ./packaging/build-deb.sh`, then attach `dist/atoll_0.2.0_all.deb` to a GitHub release.
