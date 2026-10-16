# Contributing to Atoll

Thanks for helping out! Bug reports, ideas, docs fixes and code are all welcome.

## Before you start

- **For bugs,** [open an issue](https://github.com/donjordano/atoll/issues/new/choose) with your distro, desktop (GNOME version, X11 or Wayland), Python version, and the output of `bin/atoll` run in a terminal.
- **For new features,** open an issue first so we can agree on the approach before you spend time on code. Small fixes can go straight to a pull request.
- **To support a new agent** (another coding CLI), say in the issue where it keeps its session logs and what a log line looks like. Remove any secrets from the sample first.

Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).

## How the project is laid out

```
atoll/
  app.py            startup: single-instance lock, data migration, styling, window
  paths.py          every file and folder Atoll reads or writes
  storage.py        atomic JSON read/write
  core/             pure logic, no GTK: tokens, pricing, formatting, history, heatmap math, alerts, backoff
  agents/           one module per agent (claude.py, codex.py, pi.py): log parser, stats(), remote fetchers
  system/           the desktop around Atoll: git, GitHub CLI, CPU/memory, keep-awake, autostart
  ui/
    style.py        the CSS sheet and usage-level colors
    widgets.py      label/button helpers, icons, bg() for off-thread work
    charts.py       heatmap and sparkline
    window.py       the island window: pill, dragging, tab bar, alerts, refresh
    tabs/           one module per tab; tabs/__init__.py sets the tab order
  icons/            agent logos (Lobe Icons, MIT)
bin/atoll           launcher (also: python3 -m atoll)
tests/              unittest suite; test_ui.py needs a display
docs/               README images and the script that makes them
packaging/          .deb build script, desktop entry and app icon
```

The layers only import downward: `ui` uses `agents`, `system` and `core`; `agents` and `system` use `core`; `core` uses nothing from Atoll except `paths` and `storage`. Keep GTK out of `core` and `agents` so they stay easy to test.

**Adding an agent:** create `atoll/agents/<name>.py` with `parse_file()`, a `scanner` and `stats()`, following `codex.py`. Then add it to `AGENTS` and `ICONS` in `atoll/agents/__init__.py` and give it a tab: an `AgentTab` in `ui/window.py` if it has plan limits, or its own module in `ui/tabs/` otherwise.

**Adding a tab:** subclass `Tab` from `ui/tabs/base.py` in a new module, and add it to `TABS` in `ui/tabs/__init__.py`.

## Development setup

```sh
git clone https://github.com/<you>/atoll.git
cd atoll
bin/atoll          # run it from the source folder (or: python3 -m atoll)
```

To restart after a change, use Settings → **Quit island**, then run it again. Only one Atoll runs at a time, so quit the installed copy first if it's running.

## Tests

The tests use Python's built-in `unittest`, so there's nothing to install. Run them before opening a pull request:

```sh
python3 -m unittest discover -s tests -t .
```

`tests/test_ui.py` needs a display. On a desktop that's automatic; CI runs the tests under `xvfb-run` and also builds the `.deb`.

If you add logic, such as a parser, a calculation or a branch, add a test for it in the matching `tests/test_*.py` file. Changes to the look need a check by eye: please attach a screenshot to your pull request.

To update the README images, run `python3 docs/screenshot.py` on an X11 desktop. It needs ImageMagick. It draws the pill and three tabs from your own data and replaces project names with "atoll", but your token counts and spending still show, so check the images before committing them.

## Code guidelines

- **No new dependencies.** Atoll uses only Python's standard library plus PyGObject and GTK 3, which are already on most GNOME desktops. Calling a tool the user may have, like `git` or `gh`, is fine if the feature fails gracefully without it.
- **Match the surrounding code** in naming, comment style and structure. Keep functions small, and only add comments that explain *why*.
- **Keep the UI responsive.** Network and slow disk work runs off the GTK thread through `bg()` in `atoll/ui/widgets.py`, which hands the result back to the GTK thread.
- **Respect rate limits.** Anything that calls a remote API must cache its result and back off after errors; see `FETCH_EVERY` and `BACKOFF` in `atoll/core/net.py`.
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
