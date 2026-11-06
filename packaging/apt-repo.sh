#!/bin/bash
# apt-repo.sh DEB OUTDIR — 用一個 .deb 產出簽好的 apt repo(OUTDIR 就是 https://dl.qazsskevin.org/apt/ 那一層)。
#   簽章用目前 GNUPGHOME 裡的私鑰(SIGNING_KEY 指定 key id/fingerprint;沒給就用 gpg 的預設 key)。
#   APT_PUBKEY:放進 OUTDIR/maple-cask.gpg、也拿來驗簽的公鑰(預設 assets/maple-cask.gpg)。
#     本機用拋棄式金鑰測試時指到測試公鑰;CI 用預設值 —— 簽錯 key(secret 放錯)在這裡就會失敗,不會發出去。
#   要 apt-ftparchive(apt-utils)、gpg、gpgv。只產檔不上傳,上傳在 .github/workflows/release.yml。
#
# 產出:
#   pool/main/m/maple-cask/maple-cask_<ver>_all.deb
#   dists/stable/{Release,InRelease,Release.gpg}
#   dists/stable/main/binary-{all,amd64}/Packages{,.gz} 與 by-hash/{SHA256,SHA512}/<雜湊>
#   maple-cask.gpg
#
# 索引只列這一版:R2 上的 pool 會累積歷代 .deb(上傳只加不刪),但 apt 只看得到最新版。
# 要降版就自己下載舊 .deb 來裝,這樣不必每次發版都把 R2 上的舊索引拉下來合併。
#
# Architectures 寫 "all amd64",兩個 binary-* 放同一份 Packages:
#   apt 在 Release 有列 all 時會同時抓 binary-all 與 binary-<本機架構>,同一個套件兩邊都有不會衝突;
#   只列 all 的話舊一點的 apt 不認,只列 amd64 的話 binary-all 就白放。遊戲只有 x86_64,不需要別的架構。
#
# Acquire-By-Hash:dists/ 的 CDN 快取 5 分鐘,新 InRelease 配到舊 Packages(或反過來)會 Hash Sum mismatch。
# 開 by-hash 後 apt 用 InRelease 裡的雜湊去抓 by-hash/<演算法>/<雜湊>,那個路徑內容永不改,快取多舊都對得上。
# 舊的 by-hash 檔留在 R2 不刪(同 pool),所以拿到舊 InRelease 的人也抓得到對應的 Packages。
set -euo pipefail
umask 022

HERE=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
DEB=${1:?用法:apt-repo.sh DEB OUTDIR}
OUT=${2:?用法:apt-repo.sh DEB OUTDIR}
APT_PUBKEY=${APT_PUBKEY:-$HERE/../assets/maple-cask.gpg}
DIST=dists/stable
ARCHES=(all amd64)

die() { echo "apt-repo.sh: $*" >&2; exit 1; }

[ -f "$DEB" ] || die "沒有 $DEB"
[ -f "$APT_PUBKEY" ] || die "沒有公鑰 $APT_PUBKEY"
[ -e "$OUT" ] && [ -n "$(ls -A "$OUT")" ] && die "$OUT 不是空的(索引只列這次的 .deb,不要疊在舊產物上)"

pkg=$(dpkg-deb -f "$DEB" Package)
ver=$(dpkg-deb -f "$DEB" Version)
arch=$(dpkg-deb -f "$DEB" Architecture)
[ "$arch" = all ] || die "$DEB 是 $arch,這個 repo 只放 Architecture: all"
pool=pool/main/${pkg:0:1}/$pkg

mkdir -p "$OUT/$pool"
cd "$OUT"
install -m 644 "$DEB" "$pool/${pkg}_${ver}_${arch}.deb"
install -m 644 "$APT_PUBKEY" maple-cask.gpg

# 在 OUTDIR 裡跑,Packages 的 Filename 才會是 pool/... 這種相對 repo 根的路徑
for a in "${ARCHES[@]}"; do
    d=$DIST/main/binary-$a
    mkdir -p "$d"
    apt-ftparchive packages pool > "$d/Packages"
    gzip -9n < "$d/Packages" > "$d/Packages.gz"
done

apt-ftparchive \
    -o APT::FTPArchive::Release::Origin=maple-cask \
    -o APT::FTPArchive::Release::Label=maple-cask \
    -o APT::FTPArchive::Release::Suite=stable \
    -o APT::FTPArchive::Release::Codename=stable \
    -o APT::FTPArchive::Release::Components=main \
    -o "APT::FTPArchive::Release::Architectures=${ARCHES[*]}" \
    -o APT::FTPArchive::Release::Acquire-By-Hash=yes \
    -o APT::FTPArchive::Release::Description="maple-cask (MapleStory TW launcher)" \
    release "$DIST" > Release.tmp
mv Release.tmp "$DIST/Release"

# by-hash 在 Release 產完才放:Release 只該列 Packages 本身,不列它們的 by-hash 副本。
# apt 用 Release 裡最強的雜湊去抓(實測是 SHA512);SHA256 也放,給只認 SHA256 的舊 apt
for a in "${ARCHES[@]}"; do
    d=$DIST/main/binary-$a
    for h in SHA256 SHA512; do
        mkdir -p "$d/by-hash/$h"
        for f in Packages Packages.gz; do
            cp "$d/$f" "$d/by-hash/$h/$("${h,,}sum" "$d/$f" | cut -d' ' -f1)"
        done
    done
done

key=()
[ -n "${SIGNING_KEY:-}" ] && key=(--local-user "$SIGNING_KEY")
gpg --batch --yes "${key[@]}" --digest-algo SHA512 --clearsign -o "$DIST/InRelease" "$DIST/Release"
gpg --batch --yes "${key[@]}" --digest-algo SHA512 --armor --detach-sign -o "$DIST/Release.gpg" "$DIST/Release"

# 用要發出去的那把公鑰驗(gpgv 只信 --keyring 給的 key,不看 GNUPGHOME 的信任設定),跟 apt 的 signed-by 同一個條件
gpgv --keyring "$(readlink -f maple-cask.gpg)" "$DIST/InRelease"
gpgv --keyring "$(readlink -f maple-cask.gpg)" "$DIST/Release.gpg" "$DIST/Release"
echo "apt repo:$OUT($pkg $ver)"
