#!/bin/bash
# 建有中文輸入法候選窗的 gamescope(選用;發行版的 gamescope 也能玩,只是看不到候選窗)。
#   上游 ValveSoftware/gamescope(版本釘在 build/GAMESCOPE_VERSION)+ patches/gamescope-*.patch
#
# 用法:  build/build-gamescope.sh                 # 裝到 ~/.local/share/maplestory-tw/gamescope
#        GS_PREFIX=/path JOBS=8 build/build-gamescope.sh
# 之後在 env.sh 加:export PATH=<GS_PREFIX>/bin:$PATH(gamescope 靠 PATH 找 gamescopereaper)
#
# 依賴(Ubuntu 26.04 實測):gamescope 上游 README 的那些,加上
#   sudo apt install meson ninja-build glslang-tools libsdl2-dev libinput-dev libluajit-5.1-dev
# 24.04 的 wayland / libdrm / libxkbcommon / pixman 低於 wlroots 0.20 的門檻,要另外自建,不建議。
set -euo pipefail

REPO=$(cd "$(dirname "$0")/.." && pwd)
DATA=${MAPLE_DATA:-${XDG_DATA_HOME:-$HOME/.local/share}/maplestory-tw}
BUILD_DIR=${BUILD_DIR:-$DATA/build}
GS_PREFIX=${GS_PREFIX:-$DATA/gamescope}
VERSION=$(cat "$REPO/build/GAMESCOPE_VERSION")
SRC=$BUILD_DIR/gamescope-$VERSION
JOBS=${JOBS:-$(nproc)}

echo "== 1. 原始碼:gamescope $VERSION =="
# 每次重抓:patch 要套在乾淨的樹上,-F0 不准 fuzz(同 build-wine.sh)
case $SRC in */gamescope-*) rm -rf "$SRC" ;; *) echo "SRC 路徑不對:$SRC"; exit 1 ;; esac
mkdir -p "$BUILD_DIR"
git -c advice.detachedHead=false clone -q --depth 1 --recurse-submodules --shallow-submodules \
    -b "$VERSION" https://github.com/ValveSoftware/gamescope.git "$SRC"

echo "== 2. patches =="
# 上游漏了 <cfloat>,gcc 13 以後 DBL_MAX 未宣告
grep -q '<cfloat>' "$SRC/src/wlserver.cpp" || sed -i '0,/^#include/s//#include <cfloat>\n#include/' "$SRC/src/wlserver.cpp"
for p in "$REPO"/patches/gamescope-*.patch; do
    echo "   $(basename "$p")"
    (cd "$SRC" && patch -p1 -F0 < "$p")
done

echo "== 3. meson + ninja =="
# werror=false:新版 libinput 多了一個 enum,wlroots 的 -Werror=switch 會炸
# enable_tests=false:測試要 catch2,用不到
meson setup "$SRC/build" "$SRC" --buildtype=release --prefix="$GS_PREFIX" \
    -Dwlroots:werror=false -Denable_tests=false
ninja -C "$SRC/build" -j "$JOBS"
ninja -C "$SRC/build" install

"$GS_PREFIX/bin/gamescope" --version 2>&1 | head -1 || true
echo "完成。env.sh 加一行:export PATH=$GS_PREFIX/bin:\$PATH"
