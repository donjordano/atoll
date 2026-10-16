#!/bin/sh
# Build dist/atoll_<version>_all.deb. Install: sudo apt install ./dist/atoll_*_all.deb
set -eu
umask 022
VERSION=${VERSION:-0.1.0}
cd "$(dirname "$0")/.."
python3 island.py --test && python3 tabs.py && python3 usage_stats.py
root=$(mktemp -d)
chmod 755 "$root"
trap 'rm -rf "$root"' EXIT
app=$root/opt/atoll
mkdir -p "$app/icons" "$root/usr/bin" "$root/usr/share/applications" \
         "$root/usr/share/icons/hicolor/scalable/apps" "$root/DEBIAN"
install -m 644 island.py tabs.py usage_stats.py "$app/"
install -m 644 icons/* "$app/icons/"
printf '#!/bin/sh\nexec python3 /opt/atoll/island.py "$@"\n' > "$root/usr/bin/atoll"
chmod 755 "$root/usr/bin/atoll"
install -m 644 packaging/atoll.desktop "$root/usr/share/applications/"
install -m 644 packaging/atoll.svg "$root/usr/share/icons/hicolor/scalable/apps/"
cat > "$root/DEBIAN/control" <<CONTROL
Package: atoll
Version: $VERSION
Architecture: all
Maintainer: donjordano <komyagency@gmail.com>
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-3.0, librsvg2-common
Recommends: gh, git
Section: utils
Priority: optional
Description: Floating usage island for Claude Code, Codex and Pi
 A GTK pill that shows Claude Code and Codex plan limits, Pi and
 OpenRouter spend, token heatmaps, git status, PRs, a focus timer,
 tasks and system activity.
CONTROL
mkdir -p dist
dpkg-deb --root-owner-group --build "$root" "dist/atoll_${VERSION}_all.deb"
