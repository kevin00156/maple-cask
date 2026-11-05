#!/bin/bash
# build-deb.sh [VERSION] [OUTDIR] — 打出 OUTDIR/maple-cask_<ver>_all.deb(預設 OUTDIR=.)。
#   VERSION 是 tag(v0.2.3 或 0.2.3);沒給就用 git describe --tags --match 'v*' --abbrev=0。套件版本號去掉 v。
#   要 dpkg-deb 與 x86_64-w64-mingw32-gcc(mingw-w64)。裝哪些檔在 install.sh,這裡只包 DEBIAN/。
set -euo pipefail
umask 022

HERE=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
VER=${1:-$(git -C "$HERE/.." describe --tags --match 'v*' --abbrev=0)}
VER=${VER#v}
OUT=${2:-.}

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
ROOT=$STAGE/root           # mktemp 的目錄是 700,不能直接當套件根(會變成 / 的權限)

"$HERE/install.sh" "$ROOT" "v$VER"
size=$(du -sk "$ROOT" | cut -f1)
install -d -m 755 "$ROOT/DEBIAN"
sed -e "s/@VERSION@/$VER/" -e "s/@SIZE@/$size/" "$HERE/deb/control" > "$ROOT/DEBIAN/control"
install -m 755 "$HERE/deb/postinst" "$HERE/deb/postrm" "$ROOT/DEBIAN/"

mkdir -p "$OUT"
dpkg-deb --root-owner-group --build "$ROOT" "$OUT/maple-cask_${VER}_all.deb"
