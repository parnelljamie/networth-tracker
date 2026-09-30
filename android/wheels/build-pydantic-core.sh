#!/bin/bash
# Builds pydantic-core for Chaquopy's Python 3.12 on arm64 Android (docs/07-mobile.md).
#
# FastAPI needs pydantic, whose core is a Rust extension. Neither PyPI nor Chaquopy's package
# repository has an Android build, so we cross-compile it here with the NDK and wrap it in a
# wheel that the app's pip step installs (android/app/build.gradle.kts, --find-links).
#
# Usage: build-pydantic-core.sh <output dir>
# Needs: rustup, curl, python3, and an Android NDK (ANDROID_NDK_LATEST_HOME or ANDROID_NDK_HOME,
# both set on GitHub's Ubuntu runners).
set -euo pipefail

OUT=$(mkdir -p "${1:?output dir}" && cd "$1" && pwd)
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)

PY=3.12
TARGET_VERSION=3.12.12-0   # com.chaquo.python:target on Maven Central
API=24                     # Chaquopy's minimum; the app itself needs 26
ABI=arm64-v8a
TRIPLE=aarch64-linux-android

# The same pydantic-core the PC runs.
VERSION=$(grep -A1 '^name = "pydantic-core"$' "$REPO/backend/uv.lock" | sed -n 's/^version = "\(.*\)"$/\1/p')
[ -n "$VERSION" ] || { echo "pydantic-core not found in backend/uv.lock" >&2; exit 1; }
WHEEL="pydantic_core-$VERSION-cp${PY/./}-cp${PY/./}-android_${API}_${ABI//-/_}.whl"
if [ -f "$OUT/$WHEEL" ]; then
    echo "$WHEEL already built"
    exit 0
fi

NDK=${ANDROID_NDK_LATEST_HOME:-${ANDROID_NDK_HOME:?set ANDROID_NDK_HOME}}
TOOLS=$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"

echo "== Chaquopy Python $TARGET_VERSION ($ABI)"
curl -fsSL -A Mozilla/5.0 -o target.zip \
    "https://repo.maven.apache.org/maven2/com/chaquo/python/target/$TARGET_VERSION/target-$TARGET_VERSION-$ABI.zip"
unzip -q target.zip "jniLibs/$ABI/*" -d target
LIBDIR=$WORK/target/jniLibs/$ABI
test -f "$LIBDIR/libpython$PY.so"

echo "== pydantic-core $VERSION source"
SDIST_URL=$(curl -fsSL "https://pypi.org/pypi/pydantic-core/$VERSION/json" \
    | python3 -c 'import json,sys; print(next(u["url"] for u in json.load(sys.stdin)["urls"] if u["packagetype"] == "sdist"))')
curl -fsSL -o src.tar.gz "$SDIST_URL"
tar xzf src.tar.gz
SRC=$WORK/pydantic_core-$VERSION

# PyO3 can't ask an Android Python about itself, so describe it.
cat > pyo3.cfg <<CFG
implementation=CPython
version=$PY
shared=true
abi3=false
lib_name=python$PY
lib_dir=$LIBDIR
pointer_width=64
build_flags=
suppress_build_script_link_lines=false
CFG

echo "== cargo build ($TRIPLE)"
rustup target add "$TRIPLE"
export PYO3_CONFIG_FILE=$WORK/pyo3.cfg
export CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER=$TOOLS/$TRIPLE$API-clang
export CC_aarch64_linux_android=$TOOLS/$TRIPLE$API-clang
export AR_aarch64_linux_android=$TOOLS/llvm-ar
(cd "$SRC" && cargo build --release --lib --target "$TRIPLE")
SO=$SRC/target/$TRIPLE/release/lib_pydantic_core.so
"$TOOLS/llvm-strip" --strip-unneeded "$SO"

echo "== wheel"
python3 "$HERE/make_wheel.py" "$SRC" "$SO" "$OUT/$WHEEL"
ls -l "$OUT/$WHEEL"
