#!/bin/bash
# install.sh DESTDIR [VERSION] — 把 maple-cask 裝進 DESTDIR(打包用,不會碰真正的 /)。
#   「裝哪些檔」只有這一份:packaging/build-deb.sh 與 packaging/arch/PKGBUILD 都呼叫它。
#   VERSION 是 tag(v0.2.3 或 0.2.3 都行);沒給就用 git describe --tags --abbrev=0。
#   LICENSE_DIR:LICENSE 放哪(預設跟文件一起在 /usr/share/doc/maple-cask;Arch 給 /usr/share/licenses/maple-cask)
#
# 裝好的 /usr/share/maple-cask 沒有 .git —— tools/ 的腳本靠這點判斷「套件模式」,絕不能把 .git 裝進去。
# 要 x86_64-w64-mingw32-gcc:mapletype.exe / gamefont.exe 在這裡編好(套件目錄唯讀,runtime 沒辦法編)。
set -euo pipefail
umask 022

SRC=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)
DEST=${1:?用法:install.sh DESTDIR [VERSION]}
VER=${2:-$(git -C "$SRC" describe --tags --abbrev=0)}
VER=v${VER#v}
SHARE=/usr/share/maple-cask
DOC_DIR=/usr/share/doc/maple-cask
LICENSE_DIR=${LICENSE_DIR:-$DOC_DIR}

# 要裝的檔(相對 repo 根,裝到 $SHARE 底下同一個相對路徑)。目錄另外在 list_files 展開
FILES=(
    tools/maple tools/maple-game tools/maple-login tools/maple-update
    tools/maple_passkey.py tools/gs-run.sh tools/kill-prefix.sh
    tools/mapletype.c tools/gamefont.c
    run.sh dxvk.conf env.example
    build/CMSDL_VERSION build/CMSDL_SHA256
)
EXES=(mapletype gamefont)      # tools/<名字>.c → tools/<名字>.exe

die() { echo "install.sh: $*" >&2; exit 1; }

# FILES 加上整個 prefix/ 與 tools/beanfun/(不含 __pycache__)
list_files() {
    printf '%s\n' "${FILES[@]}"
    (cd "$SRC" && find prefix tools/beanfun -type f ! -path '*/__pycache__/*' ! -name '*.pyc' | sort)
}

# 照來源的執行位元:可執行 755,其餘 644(權限在 git 裡,不另外抄一份清單)
put() {
    local src=$SRC/$1 dst=$2 mode=644
    [ -f "$src" ] || die "缺 $1"
    [ -x "$src" ] && mode=755
    install -D -m "$mode" "$src" "$dst"
}

# 建置指令只有一份,在 .c 檔頭(跟 setup-prefix.sh / maple-login / build-wine.sh 同樣的撈法)。
# 在目的地裡就地編:exe 一定比剛裝好的 .c 新,runtime 比 mtime 就不會想重編
build_exe() {
    local name=$1 cmd dir
    cmd=$(grep -m1 -o 'x86_64-w64-mingw32-gcc .*' "$SRC/tools/$name.c") || die "tools/$name.c 檔頭沒有建置指令"
    echo "編 $name.exe:$cmd"
    dir=$DEST$SHARE/tools
    (cd "$dir" && eval "$cmd")
    chmod 755 "$dir/$name.exe"
    # .deb 的 tar 只記到秒,同一秒編好會變成「一樣新」→ 明確晚 .c 一秒
    touch -d "@$(($(stat -c %Y "$dir/$name.c") + 1))" "$dir/$name.exe"
}

# kernel 設定:套件只放 /usr/lib(發行版預設層),使用者要蓋就放同名檔到 /etc
write_system_conf() {
    install -d -m 755 "$DEST/usr/lib/sysctl.d" "$DEST/usr/lib/modules-load.d"
    cat > "$DEST/usr/lib/sysctl.d/99-maple-cask.conf" <<'EOF'
# maple-cask:關掉 kernel 對 split lock 的罰睡。
# 楓之谷的反作弊(NGS)會大量觸發 split lock;開著的話遊戲主執行緒每秒被睡 30 多次、每次 10ms,
# 結果就是間歇卡頓。只影響「偵測到 split lock 時要不要讓該執行緒睡」,不影響其他程式的正確性。
# 要恢復 kernel 預設:放一份同名檔到 /etc/sysctl.d/ 寫 kernel.split_lock_mitigate = 1。
kernel.split_lock_mitigate = 0
EOF
    cat > "$DEST/usr/lib/modules-load.d/maple-cask.conf" <<'EOF'
# maple-cask:開機載入 ntsync(kernel 6.14 起),wine 的同步呼叫不必全擠在單執行緒的 wineserver。
# kernel 沒有這個模組也沒關係,遊戲照樣能玩。
ntsync
EOF
    chmod 644 "$DEST"/usr/lib/sysctl.d/99-maple-cask.conf "$DEST"/usr/lib/modules-load.d/maple-cask.conf
}

install_docs() {
    local f
    install -D -m 644 "$SRC/LICENSE" "$DEST$LICENSE_DIR/LICENSE"
    for f in "$SRC"/README.md "$SRC"/docs/*.md; do
        install -D -m 644 "$f" "$DEST$DOC_DIR/${f##*/}"
    done
}

main() {
    local f
    command -v x86_64-w64-mingw32-gcc >/dev/null || die "要 x86_64-w64-mingw32-gcc(Debian/Ubuntu:mingw-w64;Arch:mingw-w64-gcc)"
    install -d -m 755 "$DEST"
    list_files | while read -r f; do put "$f" "$DEST$SHARE/$f"; done
    for f in "${EXES[@]}"; do build_exe "$f"; done
    echo "$VER" > "$DEST$SHARE/VERSION"
    chmod 644 "$DEST$SHARE/VERSION"
    install -d -m 755 "$DEST/usr/bin"
    ln -sfn ../share/maple-cask/tools/maple "$DEST/usr/bin/maple"
    write_system_conf
    install_docs
    echo "已裝到 $DEST($VER)"
}

main
