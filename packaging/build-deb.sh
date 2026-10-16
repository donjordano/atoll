#!/bin/sh
# Build dist/atoll_<version>_all.deb. Install: sudo apt install ./dist/atoll_*_all.deb
set -eu
umask 022
cd "$(dirname "$0")/.."
VERSION=${VERSION:-$(python3 -c 'import atoll; print(atoll.__version__)')}
python3 -m unittest discover -s tests -t .
root=$(mktemp -d)
chmod 755 "$root"
trap 'rm -rf "$root"' EXIT
app=$root/opt/atoll
mkdir -p "$root/usr/bin" "$root/usr/share/applications" \
         "$root/usr/share/icons/hicolor/scalable/apps" "$root/DEBIAN"
find atoll -name __pycache__ -prune -o -type f -print | while read -r f; do
    install -D -m 644 "$f" "$app/$f"
done
install -D -m 755 bin/atoll "$app/bin/atoll"
ln -s /opt/atoll/bin/atoll "$root/usr/bin/atoll"
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
