#!/usr/bin/env bash
# Linux counterpart of build-installer.ps1: one command from a clean checkout to
# dist/waymark_<version>_amd64.deb. Must run on Linux (PyInstaller can't cross-compile);
# the Release workflow runs it on Ubuntu 22.04 so the build works on 22.04 and newer.
#   ./scripts/build-linux.sh              # tests, lint, build
#   SKIP_TESTS=1 ./scripts/build-linux.sh # build only (CI runs the tests in its own job)
#
# Requires: uv, npm, dpkg-deb.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
backend_dir="$repo_root/backend"
frontend_dir="$repo_root/frontend"
packaging_dir="$repo_root/packaging"
dist_dir="$repo_root/dist"

for cmd in uv npm dpkg-deb; do
    command -v "$cmd" >/dev/null || { echo "$cmd is required but was not found on PATH." >&2; exit 1; }
done

version="$(sed -nE 's/^__version__ = "([^"]+)"/\1/p' "$backend_dir/app/__init__.py")"
echo "==> Building Waymark $version for Linux"

cd "$backend_dir"
uv sync --locked
if [ -z "${SKIP_TESTS:-}" ]; then
    echo "==> Backend tests and lint"
    uv run pytest -q
    uv run ruff check .
fi

echo "==> Building frontend"
cd "$frontend_dir"
npm ci
npm run build

echo "==> Running PyInstaller (one-folder build)"
cd "$backend_dir"
uv run pyinstaller "$packaging_dir/waymark.spec" --distpath "$dist_dir" \
    --workpath "$repo_root/build" --noconfirm --clean
app_dir="$dist_dir/Waymark"
[ -x "$app_dir/waymark" ] || { echo "Expected $app_dir/waymark after PyInstaller." >&2; exit 1; }

echo "==> Assembling the .deb"
stage="$repo_root/build/deb"
rm -rf "$stage"
mkdir -p "$stage/DEBIAN" "$stage/opt" "$stage/usr/bin" "$stage/usr/share/applications" \
    "$stage/usr/share/icons/hicolor/256x256/apps"
cp -a "$app_dir" "$stage/opt/waymark"
ln -s /opt/waymark/waymark "$stage/usr/bin/waymark"
install -m 644 "$packaging_dir/linux/waymark.desktop" "$stage/usr/share/applications/"
install -m 644 "$packaging_dir/waymark.png" "$stage/usr/share/icons/hicolor/256x256/apps/waymark.png"
install -m 755 "$packaging_dir/linux/postinst" "$packaging_dir/linux/postrm" "$stage/DEBIAN/"

installed_kb="$(du -sk --exclude=DEBIAN "$stage" | cut -f1)"
# Qt ships inside the build; these are the system libraries its xcb platform plugin and
# WebEngine (Chromium) load. The "|" alternatives cover Ubuntu 24.04's 64-bit time_t renames;
# the t64 name goes first because apt takes the first one that exists, and on 24.04 the old
# name "libasound2" is also provided by liboss4-salsa-asound2, which lacks the ALSA MIDI API.
cat > "$stage/DEBIAN/control" <<CONTROL
Package: waymark
Version: $version
Architecture: amd64
Maintainer: Jamie Parnell <47815625+parnelljamie@users.noreply.github.com>
Installed-Size: $installed_kb
Section: misc
Priority: optional
Depends: libc6 (>= 2.35), libgl1, libegl1, libfontconfig1, libfreetype6, libdbus-1-3,
 libglib2.0-0t64 | libglib2.0-0, libnss3, libasound2t64 | libasound2, libxkbcommon0,
 libxkbcommon-x11-0, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1,
 libxcb-randr0, libxcb-render-util0, libxcb-shape0, libxcb-xinerama0, libxcb-xkb1,
 libxcomposite1, libxdamage1, libxrandr2, libxtst6, libxshmfence1, libxkbfile1,
 libwayland-client0, libwayland-server0, libwayland-cursor0, libwayland-egl1, libgl1-mesa-dri,
 libstdc++6, zlib1g, libsqlite3-0, libssl3t64 | libssl3, libgssapi-krb5-2, libcups2t64 | libcups2,
 libgtk-3-0t64 | libgtk-3-0, libxcb-glx0, libxcb-shm0, libxcb-sync1, libxcb-xfixes0, libxi6,
 libxcursor1, libxinerama1, libgbm1, libepoxy0
Recommends: zenity
Conflicts: passbook
Replaces: passbook
Description: Waymark household net worth tracker
 Local, single-household net worth tracker (UK, GBP). Runs a private server on this
 computer and shows it in its own window. Data lives in ~/.local/share/Waymark.
CONTROL

deb="$dist_dir/waymark_${version}_amd64.deb"
dpkg-deb --root-owner-group --build "$stage" "$deb"
echo ""
echo "==> Built $deb"
sha256sum "$deb"
