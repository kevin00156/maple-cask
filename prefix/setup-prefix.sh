#!/bin/bash
# 建立 / 重整 MapleStory TW 的 WINEPREFIX。可重複執行。
#
# 需要的環境變數(見 env.example):
#   WINE_ROOT   runner 目錄(裡面有 bin/wine;build/build-wine.sh 的 out/ 或解開的 tarball)
#   WINEPREFIX  要建的 prefix(不存在會新建)
#   GAME_DIR    現成的 MapleStory 目錄(含 MapleStory.exe、Patcher.exe)
# 選用:
#   FONTS_DIR   一份 Windows 的 C:\Windows\Fonts 複本(至少要有 mingliu.ttc),沒給字會糊但能玩
#
# 步驟:ACP=950 建 prefix → 登錄檔 → DXVK/vkd3d-proton → VC++ 2022 runtime(winetricks 抓微軟官方 redist)→ 字型
#
# setup-prefix.sh --check:只讀,看第 1~4 步的產物都在不在(只要 WINEPREFIX)。maple / run.sh 開遊戲前跑;
# 缺了就印出缺哪些、exit 1。第 5 步字型是選用的,不查。
set -euo pipefail

REPO=$(cd "$(dirname "$0")/.." && pwd)
SYS32=${WINEPREFIX:-}/drive_c/windows/system32
WOW64=${WINEPREFIX:-}/drive_c/windows/syswow64
DXVK=(d3d11 d3d10core dxgi d3d9)    # 64 與 32 位元都要(NGS 那側是 32 位元);run.sh 的 WINEDLLOVERRIDES 要跟著改
VKD3D=(d3d12 d3d12core)             # 只有 64 位元

# 不是 wine 自己的 dll。setup 沒跑完的 prefix 裡,system32 的 d3d/dxgi 是 wine builtin 版(檔頭有這個標記);
# run.sh 強制這幾個 =n,遇到它就是 "dxgi.dll ... not found"
native() { [ -f "$1" ] && ! head -c 128 "$1" | grep -qa 'Wine builtin DLL'; }

# 每一步從第一版就有,所以任何版本只要 setup 跑完過都會過
check() {
    local d miss=()
    grep -q '^"ACP"="950"' "$WINEPREFIX/system.reg" 2>/dev/null || miss+=("1. ACP 不是 950")
    grep -qi '^\[Software\\\\Gamania\\\\MapleStory\]' "$WINEPREFIX/system.reg" 2>/dev/null || miss+=("2. 登錄檔(Gamania)")
    for d in "${DXVK[@]}" "${VKD3D[@]}"; do native "$SYS32/$d.dll" || miss+=("3. system32/$d.dll"); done
    for d in "${DXVK[@]}"; do native "$WOW64/$d.dll" || miss+=("3. syswow64/$d.dll"); done
    native "$SYS32/vcruntime140_threads.dll" || miss+=("4. system32/vcruntime140_threads.dll")
    [ ${#miss[@]} -eq 0 ] && return 0
    echo "prefix 沒建完($WINEPREFIX),缺:${miss[*]}" >&2
    echo "  補:maple setup(多開第 N 組:maple -N setup),或 source env.sh 後跑 prefix/setup-prefix.sh" >&2
    return 1
}
if [ "${1:-}" = --check ]; then
    : "${WINEPREFIX:?請設定 WINEPREFIX}"
    check; exit
fi
# 直接跑本腳本的人常忘了先載 env.sh(#5 的回報者就是),提示裡直接給兩種正確做法
need="未設定;用 maple setup,或先 source ~/.config/maplestory-tw/env.sh 再跑本腳本"
: "${WINE_ROOT:?$need}" "${WINEPREFIX:?$need}" "${GAME_DIR:?$need}"
WINE=$WINE_ROOT/bin/wine
WINESERVER=$WINE_ROOT/bin/wineserver
[ -x "$WINE" ] || { echo "找不到 $WINE"; exit 1; }
[ -f "$GAME_DIR/MapleStory.exe" ] || { echo "$GAME_DIR 裡沒有 MapleStory.exe"; exit 1; }
export WINE WINESERVER WINEPREFIX WINEARCH=win64
export WINEDEBUG=-all WINEDLLOVERRIDES="mscoree,mshtml="
# code page 950 是在 prefix「建立時」由 locale 決定的,之後改沒用;所以整支腳本都跑在 zh_TW
export LANG=zh_TW.UTF-8 LC_ALL=zh_TW.UTF-8

echo "== 1. prefix =="
# wine 只建 prefix 這一層;上一層不存在(新機:~/.local/share/maplestory-tw 還沒有)它會直接失敗
mkdir -p "$WINEPREFIX"
"$WINE" wineboot -u >/dev/null      # stderr 留著:這步失敗時那是唯一的線索
"$WINESERVER" -w
acp=$(grep -m1 '^"ACP"' "$WINEPREFIX/system.reg" || true)
case $acp in *950*) echo "   ACP=950 OK" ;;
    *) echo "   ACP 不是 950(拿到:$acp)。系統要有 zh_TW.UTF-8 locale(各發行版的做法見 README「需求」;locale -a 要看得到 zh_TW.utf8),然後刪掉 prefix 重跑"; exit 1 ;;
esac

echo "== 2. 登錄檔 =="
for r in maplestory fonts; do
    "$WINE" regedit /S "$REPO/prefix/reg/$r.reg"
done
# beanfun 的 GameInfo.ini 會從 HKLM\SOFTWARE\Gamania\MapleStory\ExecPath 讀客戶端路徑
winpath="Z:$(printf '%s' "$GAME_DIR" | sed 's,/,\\\\,g')"
cat > "$WINEPREFIX/gamania.reg" <<EOF
Windows Registry Editor Version 5.00

[HKEY_LOCAL_MACHINE\\SOFTWARE\\Gamania\\MapleStory]
"ExecPath"="$winpath"
EOF
"$WINE" regedit /S "$WINEPREFIX/gamania.reg"
"$WINESERVER" -w

echo "== 3. DXVK + vkd3d-proton(64 與 32 位元都放)=="
for d in "${DXVK[@]}"; do
    cp -f "$WINE_ROOT/lib/wine/dxvk/x86_64-windows/$d.dll" "$SYS32/$d.dll"
    cp -f "$WINE_ROOT/lib/wine/dxvk/i386-windows/$d.dll" "$WOW64/$d.dll"
done
for d in "${VKD3D[@]}"; do
    cp -f "$WINE_ROOT/lib/wine/vkd3d-proton/x86_64-windows/$d.dll" "$SYS32/$d.dll"
done

echo "== 4. VC++ 2022 runtime(wine 沒有 vcruntime140_threads.dll,要用微軟的)=="
if [ -f "$SYS32/vcruntime140_threads.dll" ]; then
    echo "   已裝過"
else
    for t in winetricks cabextract; do
        command -v $t >/dev/null || { echo "需要 $t(Ubuntu/Debian:sudo apt install $t;SteamOS 見 docs/known-issues.md「SteamOS」)"; exit 1; }
    done
    winetricks -q vcrun2022
    "$WINESERVER" -w
fi

echo "== 5. 字型 =="
if [ -n "${FONTS_DIR:-}" ]; then
    [ -f "$FONTS_DIR/mingliu.ttc" ] || echo "   警告:$FONTS_DIR 裡沒有 mingliu.ttc(新細明體),遊戲九成的字都靠它"
    FD=$WINEPREFIX/drive_c/windows/Fonts
    mkdir -p "$FD"
    cp -f "$FONTS_DIR"/* "$FD"/ 2>/dev/null || true
    # SimSun 沒有 Big5 位元又會蓋掉登錄檔的代換,一定要拿掉(理由見 reg/fonts.reg)
    rm -f "$FD"/simsun.ttc "$FD"/simsunb.ttf "$FD"/SimsunExtG.ttf
    echo "   $(ls "$FD" | wc -l) 個字型檔;驗證(全部應為 intLead=0,條內 RGB 值 2~3):"
    # gamefont.exe 不進 git(二進位),沒有就當場編;建置指令在 gamefont.c 檔頭
    GAMEFONT=$REPO/tools/gamefont.exe
    if [ ! -f "$GAMEFONT" ]; then
        build=$(grep -m1 -o 'x86_64-w64-mingw32-gcc .*' "$REPO/tools/gamefont.c")
        if command -v x86_64-w64-mingw32-gcc >/dev/null; then
            echo "   編 gamefont.exe:$build"
            (cd "$REPO/tools" && eval "$build")
        else
            echo "   沒有 gamefont.exe,也沒有 mingw,略過字型驗證。要驗的話:"
            echo "     sudo apt install mingw-w64 && cd $REPO/tools && $build"
        fi
    fi
    # 圖寫到 /tmp,不要在使用者的工作目錄留垃圾(不帶參數的話 exe 會寫在 cwd)
    [ -f "$GAMEFONT" ] && "$WINE" "$GAMEFONT" 'Z:\tmp\gamefont.bmp' 2>/dev/null || true
else
    echo "   沒設 FONTS_DIR,略過。遊戲能玩但中文會糊、行距會跑;要修就把 Windows 的 C:\\Windows\\Fonts"
    echo "   (至少 mingliu.ttc)複製到某處,設 FONTS_DIR 指過去再跑一次本腳本。"
fi

check || exit 1     # 上面各步與 --check 的清單對不上,在這裡就會現形
echo "== 完成:WINEPREFIX=$WINEPREFIX =="
