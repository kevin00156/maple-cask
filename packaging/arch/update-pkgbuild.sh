#!/bin/bash
# update-pkgbuild.sh VERSION OUTDIR — 產出 AUR 用的套件檔:OUTDIR/{PKGBUILD,maple-cask.install,.SRCINFO}。
#   VERSION 是 tag(v0.2.3 或 0.2.3),要已經推上 GitHub:下載 tag tarball 算 sha256,並確認裡面有
#   packaging/install.sh(沒有打包檔的舊 tag,例如 v0.2.2,打不了包,直接失敗)。
#   內容從 repo 裡的 PKGBUILD 來(depends 等只維護一份):「本地 checkout 專用」那段換成固定的版本,
#   source 換成 tag tarball。repo 裡那份不改 —— 它從本地 checkout 打包,tag 樹裡的檔案不可能含自己 tarball 的 sha。
#   .SRCINFO 要 makepkg(Arch 上);沒有就只產另外兩個並說怎麼補。
set -euo pipefail

HERE=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
USAGE="用法:update-pkgbuild.sh VERSION OUTDIR"
VER=${1:?$USAGE}
OUT=${2:?$USAGE}
VER=${VER#v}
URL=https://github.com/kevin00156/maple-cask/archive/refs/tags/v$VER.tar.gz

die() { echo "update-pkgbuild.sh: $*" >&2; exit 1; }

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# 下載 tarball:印 sha256,並把解開後的頂層目錄名記在 $TMP/top(GitHub 會去掉 tag 的 v,不自己猜)
fetch() {
    local tgz=$TMP/src.tar.gz top
    curl -fsSL -o "$tgz" "$URL" || die "下載不到 $URL(tag 推上 GitHub 了嗎?)"
    top=$(tar -tzf "$tgz" | awk -F/ 'NR == 1 {print $1}')
    tar -tzf "$tgz" "$top/packaging/install.sh" >/dev/null 2>&1 ||
        die "v$VER 的 tarball 裡沒有 packaging/install.sh(這個 tag 還沒有打包檔),打不了包"
    echo "$top" >"$TMP/top"
    sha256sum "$tgz" | cut -d' ' -f1
}

# repo 的 PKGBUILD → AUR 版。$1 = tarball 頂層目錄,$2 = sha256
render() {
    # shellcheck disable=SC2016  # $pkgname 等要原樣寫進 PKGBUILD,由 makepkg 展開
    awk -v top="$1" -v tag="v$VER" -v ver="${VER//-/_}" -v sha="$2" -v q="'" \
        -v src='source=("$pkgname-$pkgver.tar.gz::$url/archive/refs/tags/$_tag.tar.gz")' '
        /^# 從本地 checkout 打包/ { print "# AUR 版:由 maple-cask 的 packaging/arch/update-pkgbuild.sh 從 repo 的 PKGBUILD 產生,不要手改。"; next }
        /^# AUR 用的版本/ { next }
        # 「本地 checkout 專用」頭尾兩行標記之間整段換掉
        /^# --- 本地 checkout 專用/ && skip { skip = 0; next }
        /^# --- 本地 checkout 專用/ {
            skip = 1; n++
            print "_src=" top "   # tag tarball 解開的目錄(package() 在 $srcdir 裡跑)"
            print "_tag=" tag
            print "pkgver=" ver
            next
        }
        skip { next }
        /^source=\(\)$/ { print src; n++; next }
        /^sha256sums=\(\)$/ { print "sha256sums=(" q sha q ")"; n++; next }
        { print }
        END { if (n != 3) exit 1 }
    ' "$HERE/PKGBUILD"
}

main() {
    local sha
    sha=$(fetch)
    mkdir -p "$OUT"
    render "$(cat "$TMP/top")" "$sha" >"$OUT/PKGBUILD" || die "repo 的 PKGBUILD 格式變了(找不到要換的段落),改 render()"
    install -m 644 "$HERE/maple-cask.install" "$OUT/maple-cask.install"
    echo "PKGBUILD → $OUT(v$VER,sha256 $sha)"
    if command -v makepkg >/dev/null; then
        (cd "$OUT" && makepkg --printsrcinfo > .SRCINFO)
        echo ".SRCINFO → $OUT"
    else
        echo "沒有 makepkg,.SRCINFO 沒產(在 Arch 上:cd $OUT && makepkg --printsrcinfo > .SRCINFO)"
    fi
}

main
