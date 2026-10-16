# Installing Atoll

Atoll runs on Linux with GNOME on X11 and needs Python 3.10 or newer, PyGObject and GTK 3.

## 1. Install the dependencies

Ubuntu, Pop!_OS and Debian usually ship these already:

```sh
sudo apt install python3 python3-gi gir1.2-gtk-3.0 librsvg2-common
```

On Fedora:

```sh
sudo dnf install python3 python3-gobject gtk3 librsvg2
```

On Arch:

```sh
sudo pacman -S python python-gobject gtk3 librsvg
```

Optional:
- `git` for the Git tab.
- `gh` for the Pull requests tab. Run `gh auth login` once after installing it.

## 2. Choose how to run it

### Option A: install the .deb package (Debian, Ubuntu, Pop!_OS)

```sh
git clone https://github.com/donjordano/atoll.git
cd atoll
./packaging/build-deb.sh
sudo apt install ./dist/atoll_0.1.0_all.deb
```

The build script runs the self-tests first and stops if any of them fail. To build a different version, run `VERSION=0.2.0 ./packaging/build-deb.sh`. Use a higher number for each new release, or apt won't treat it as an upgrade.

After installing:
- **Atoll** appears in your app launcher.
- You can start it from a terminal with `atoll`.
- The app's files are in `/opt/atoll`.

### Option B: run from the source folder (any distro)

```sh
git clone https://github.com/donjordano/atoll.git
cd atoll
python3 island.py
```

## 3. Start at login

In the open panel, go to **Settings** (the gear) and turn on **Start at login**. This creates `~/.config/autostart/atoll.desktop`, which starts whichever copy you turned the switch on from.

Only one Atoll runs at a time. Starting a second one prints `atoll is already running` and exits.

## 4. Set up Claude Code alerts (optional)

See [Set up Claude Code alerts](README.md#set-up-claude-code-alerts) in the README.

## Updating

- **Package:** pull the latest code, rebuild with a higher `VERSION`, and install the new `.deb`.
- **Source folder:** `git pull`, then restart Atoll. To restart, use Settings → **Quit island**, then start it again.

## Uninstalling

```sh
sudo apt remove atoll                          # if you installed the package
rm -f ~/.config/autostart/atoll.desktop        # start at login
rm -rf ~/.local/share/atoll ~/.cache/atoll     # history, tasks, settings
```

If you added the alert hooks, also remove the `~/.cache/atoll` entries from `~/.claude/settings.json`.

## Troubleshooting

| Problem | What to do |
|---|---|
| The pill shows ⚠ or "offline, retrying" | Hover over the pill to see the error. `HTTP Error 429` means the usage API is limiting requests; Atoll waits and tries again on its own. `401` means your Claude Code login expired: run `claude` once to refresh it. |
| Nothing appears | Make sure you're on an X11 session (`echo $XDG_SESSION_TYPE` should print `x11`), then run `python3 island.py` in a terminal to see any errors. |
| Logos show as text symbols | Install `librsvg2-common` (Debian/Ubuntu) or `librsvg2` (Fedora), which GTK needs to draw SVG files. |
| The Pull requests tab shows an error | Run `gh auth status`; if you're not logged in, run `gh auth login`. |
| The Git tab says it's not a repository | It follows the folder of your last Claude Code or Codex session. Start a session in a git project. |
