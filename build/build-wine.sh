#!/bin/bash
# 建 MapleStory TW 用的 wine runner:
#   上游 wine release tarball(dl.winehq.org,版本釘在 build/WINE_VERSION、
#   校驗碼釘在 build/WINE_SHA256)+ patches/,WoW64(i386 + x86_64),
#   再放進 GE-Proton 的 DXVK / vkd3d-proton 二進位。
#
# 用法:  build/build-wine.sh                       # build 目錄預設在 ~/.local/share/maplestory-tw/build
#        BUILD_DIR=/path JOBS=8 build/build-wine.sh
#        GE_DIR=/path/to/GE-ProtonXX-Y build/build-wine.sh   # 已經有解開的 GE-Proton 就指過去,省下載
# 產出:  $BUILD_DIR/out/                                     # 直接可當 WINE_ROOT
#        $BUILD_DIR/maplestory-tw-wine-<version>.tar.xz      # Lutris / Heroic 的 wine runner
#        tools/*.exe                                         # 輔助工具,不進 git
#
# 每次執行都會重新解開原始碼樹再套 patch,所以可以重跑;
# $BUILD_DIR/wine-<版本>/ 與 $BUILD_DIR/obj/ 裡的東西會被丟掉。
set -euo pipefail

REPO=$(cd "$(dirname "$0")/.." && pwd)
BUILD_DIR=${BUILD_DIR:-${MAPLE_DATA:-${XDG_DATA_HOME:-$HOME/.local/share}/maplestory-tw}/build}
BUILD_DIR=$(mkdir -p "$BUILD_DIR" && cd "$BUILD_DIR" && pwd)
WINE_VERSION=$(cat "$REPO/build/WINE_VERSION")
WINE_SHA256=$(cat "$REPO/build/WINE_SHA256")
SRC=$BUILD_DIR/wine-$WINE_VERSION
OBJ=$BUILD_DIR/obj
OUT=$BUILD_DIR/out
TARBALL=$BUILD_DIR/wine-$WINE_VERSION.tar.xz
URL=https://dl.winehq.org/wine/source/${WINE_VERSION%%.*}.x/wine-$WINE_VERSION.tar.xz
JOBS=${JOBS:-$(nproc)}
GE_VERSION=$(cat "$REPO/build/GE_PROTON_VERSION")
GE_DIR=${GE_DIR:-$HOME/.steam/root/compatibilitytools.d/${GE_VERSION}-x86_64}
VERSION=$(git -C "$REPO" describe --tags --always 2>/dev/null || echo dev)

echo "== 0. build 依賴 =="
missing=""
for tool in x86_64-w64-mingw32-gcc i686-w64-mingw32-gcc pkg-config curl sha256sum tar patch; do
    command -v "$tool" >/dev/null || missing="$missing $tool"
done
if [ -n "$missing" ]; then
    echo "缺:$missing"
    echo "Ubuntu/Debian:sudo apt install build-essential pkg-config mingw-w64 curl xz-utils,再加上編上游 wine 需要的那些(見 README)"
    exit 1
fi

echo "== 1. 原始碼:上游 wine-$WINE_VERSION =="
# 上游 release tarball 自帶 configure 與所有生成檔,不需要 autoreconf /
# make_vulkan / make_specfiles / make_requests —— 那些是 Valve 樹才缺的東西。
if [ ! -f "$TARBALL" ]; then
    echo "   下載 $URL"
    curl -fL --retry 3 -o "$TARBALL.part" "$URL"
    mv "$TARBALL.part" "$TARBALL"
fi
echo "$WINE_SHA256  $TARBALL" | sha256sum -c -
rm -rf "$SRC"
tar -C "$BUILD_DIR" -xJf "$TARBALL"
[ -x "$SRC/configure" ] || { echo "解開後找不到 $SRC/configure"; exit 1; }

echo "== 2. patches =="
# tarball 沒有 .git,所以用 patch 而不是 git apply。-F0 = 不准 fuzz:
# patch 一旦要靠 fuzz 才套得上,就表示上游動過那段程式碼,要人看過再說。
for p in "$REPO"/patches/[0-9]*.patch; do
    echo "   $(basename "$p")"
    (cd "$SRC" && patch -p1 -F0 < "$p")
done

echo "== 3. configure + make(WoW64:i386 + x86_64,$JOBS jobs)=="
# $OBJ 每次清掉重建:$SRC 是重新解開的,tarball 保留的是上游的 mtime(比既有的 .o 舊),
# 增量 make 會把舊 .o 當成最新的而不重編 —— 換 base 的時候那會把上一棵樹的產物連進來。
case $OBJ in */obj) rm -rf "$OBJ" ;; *) echo "OBJ 路徑不對:$OBJ"; exit 1 ;; esac
mkdir -p "$OBJ" && cd "$OBJ"
"$SRC/configure" --enable-archs=i386,x86_64 --disable-tests --prefix="$OUT"
make -j"$JOBS"
case $OUT in */out) rm -rf "$OUT" ;; *) echo "OUT 路徑不對:$OUT"; exit 1 ;; esac
make install

echo "== 4. DXVK + vkd3d-proton(取自 $GE_VERSION)=="
if [ ! -d "$GE_DIR/files/lib/wine/dxvk" ]; then
    mkdir -p "$BUILD_DIR/ge"
    tarball=$BUILD_DIR/ge/$GE_VERSION.tar.gz
    [ -f "$tarball" ] || curl -L -o "$tarball" \
        "https://github.com/GloriousEggroll/proton-ge-custom/releases/download/$GE_VERSION/$GE_VERSION.tar.gz"
    tar -C "$BUILD_DIR/ge" -xzf "$tarball"
    GE_DIR=$(ls -d "$BUILD_DIR/ge"/GE-Proton*/ | head -1)
fi
cp -a "$GE_DIR/files/lib/wine/dxvk" "$GE_DIR/files/lib/wine/vkd3d-proton" "$OUT/lib/wine/"

echo "== 5. tools/*.exe(mingw)=="
# 建置指令只有一份,寫在各 .c 的檔頭註解裡(旗標每支不一樣:gdi32、-municode…)。
# 這裡撈出來直接跑,免得同一條命令在兩個地方各寫一次、然後走鐘。
for c in "$REPO"/tools/*.c; do
    cmd=$(grep -m1 -o 'x86_64-w64-mingw32-gcc .*' "$c" || true)
    [ -n "$cmd" ] || { echo "$(basename "$c") 檔頭沒有 mingw 建置指令"; exit 1; }
    echo "   $cmd"
    (cd "$REPO/tools" && eval "$cmd")
done

echo "== 6. 打包(LGPL:二進位旁邊附上 patch 與 base 版本)=="
mkdir -p "$OUT/patches"
cp "$REPO"/patches/[0-9]*.patch "$OUT/patches/"
echo "wine-$WINE_VERSION (dl.winehq.org) sha256=$WINE_SHA256" > "$OUT/patches/BASE"
cp "$REPO/LICENSE" "$OUT/LICENSE"
NAME=maplestory-tw-wine-$VERSION
XZ_OPT=-T0 tar -C "$BUILD_DIR" --transform "s,^out,$NAME," -cJf "$BUILD_DIR/$NAME.tar.xz" out
sha256sum "$BUILD_DIR/$NAME.tar.xz"
echo "完成:WINE_ROOT=$OUT"
