#!/bin/bash
# update-pkgbuild.sh [VERSION] — 發版後把 PKGBUILD 換成這個 tag:pkgver、pkgrel=1、tag tarball 的 sha256。
#   VERSION 是 tag(v0.2.3 或 0.2.3);沒給就用 git describe --tags --abbrev=0。
#   tag 要已經推上 GitHub(要下載 tarball 算 sha)。有 makepkg(Arch 上)就順便產 .SRCINFO(AUR 要)。
set -euo pipefail

HERE=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
VER=${1:-$(git -C "$HERE/../.." describe --tags --abbrev=0)}
VER=${VER#v}
URL=https://github.com/kevin00156/maple-cask/archive/refs/tags/v$VER.tar.gz

sha=$(curl -fsSL "$URL" | sha256sum | cut -d' ' -f1)
sed -i -e "s/^pkgver=.*/pkgver=$VER/" -e "s/^pkgrel=.*/pkgrel=1/" \
    -e "s/^sha256sums=.*/sha256sums=('$sha')/" "$HERE/PKGBUILD"
echo "PKGBUILD → $VER($sha)"

if command -v makepkg >/dev/null; then
    (cd "$HERE" && makepkg --printsrcinfo > .SRCINFO)
    echo ".SRCINFO 已更新"
else
    echo "沒有 makepkg,.SRCINFO 沒產(在 Arch 上:cd packaging/arch && makepkg --printsrcinfo > .SRCINFO)"
fi
