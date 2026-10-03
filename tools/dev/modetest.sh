#!/bin/bash
# modetest.sh —— 量「切到比螢幕方正的全螢幕解析度(拍賣場 1024x768)時,是補黑邊還是被拉伸」,不開遊戲。
#   用 headless gamescope(不開視窗,不干擾開著的遊戲)跑 modeprobe.exe,每 2 秒截一次 gamescope 的輸出,
#   量紅色區的寬高比:= 遊戲解析度的比例 → 補黑邊(對);= 輸出比例 → 被拉伸(錯)。
#   探針用一個獨立的拋棄式 prefix,不碰遊戲的 prefix。
#
# 用法: tools/dev/modetest.sh [EmulateModeset Y|N] [gamescope 參數…]
#   tools/dev/modetest.sh                      # 預設 Y、-W 1920 -H 1080(= gs-run.sh 預設)
#   tools/dev/modetest.sh N -W 1366 -H 768     # 重現舊行為:1024x768 被拉滿 1366x768
#   PROBE_MODES="1024x768:10 1920x1080:6" MOUSE_PTS="4@960,540 6@240,0" tools/dev/modetest.sh
#     MOUSE_PTS:第 N 秒用 xdotool 把游標移到測試 Xwayland 的 (x,y)(只送給探針,遊戲不在那個 display 上),
#     probe.txt 會印出 Win32 看到的座標 —— 1920 輸出、1024x768 模式時 (960,540) 應該是 512,384。
# 需要:env.sh(WINE_ROOT)、gamescope、x86_64-w64-mingw32-gcc、xdotool、python3-pil。
# 輸出:$OUT(預設 /tmp/modetest-<時間>)/ s*.png、probe.txt、x.txt、gs.log,最後印量測結果。
set -euo pipefail
HERE=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
[ -n "${WINE_ROOT:-}" ] || source "${MAPLE_ENV:-${XDG_CONFIG_HOME:-$HOME/.config}/maplestory-tw/env.sh}"
emu=${1:-Y}; shift || true
[ $# -gt 0 ] || set -- -W 1920 -H 1080
OUT=${OUT:-/tmp/modetest-$(date +%m%d-%H%M%S)}
PROBE_MODES=${PROBE_MODES:-"1024x768:8 1920x1080:6 1280x1024:6"}
mkdir -p "$OUT"
export WINEPREFIX=${MODETEST_PREFIX:-$HOME/.cache/maplestory-tw/modetest-pfx} WINEARCH=win64 WINEDEBUG=-all WINEDLLOVERRIDES="d3d9=n"
unset DXVK_CONFIG_FILE

probe=$HERE/modeprobe.exe
[ "$probe" -nt "$HERE/modeprobe.c" ] || (cd "$HERE" && eval "$(grep -m1 -o 'x86_64-w64-mingw32-gcc .*' modeprobe.c)")
if [ ! -f "$WINEPREFIX/system.reg" ]; then
    echo "建測試 prefix:$WINEPREFIX"
    "$WINE_ROOT/bin/wine" wineboot -u >/dev/null 2>&1
fi
cp -f "$WINE_ROOT/lib/wine/dxvk/x86_64-windows/d3d9.dll" "$WINEPREFIX/drive_c/windows/system32/"
"$WINE_ROOT/bin/wine" reg add 'HKCU\Software\Wine\X11 Driver' /v EmulateModeset /d "$emu" /f >/dev/null 2>&1
"$WINE_ROOT/bin/wineserver" -w

gamescope --backend headless "$@" -- bash -c "'$WINE_ROOT/bin/wine' '$probe' $PROBE_MODES > '$OUT/probe.txt' 2>&1; '$WINE_ROOT/bin/wineserver' -k" >"$OUT/gs.log" 2>&1 &
gpid=$!
for _ in $(seq 40); do sleep 0.5; grep -q "Starting Xwayland" "$OUT/gs.log" && break; done
wl=$(sed -n "s/.*wayland display '\(gamescope-[0-9]*\)'.*/\1/p" "$OUT/gs.log" | head -1)
xd=$(sed -n 's/.*Starting Xwayland on \(:[0-9]*\).*/\1/p' "$OUT/gs.log" | head -1)
# gamescopectl 找不到 display 時會預設連 gamescope-0 —— 那通常是正在玩的遊戲,寧可不截
if [ -z "$wl" ] || [ -z "$xd" ]; then
    echo "抓不到測試 gamescope 的 display(wl=$wl x=$xd),見 $OUT/gs.log" >&2; kill $gpid; exit 1
fi
for i in $(seq 30); do
    sleep 2
    kill -0 $gpid 2>/dev/null || break
    pt=$(tr ' ' '\n' <<<"${MOUSE_PTS:-}" | sed -n "s/^$((i * 2))@//p")
    [ -z "$pt" ] || { DISPLAY=$xd xdotool mousemove ${pt/,/ }; echo "t=$((i * 2)) mousemove $pt" >>"$OUT/x.txt"; }
    GAMESCOPE_WAYLAND_DISPLAY=$wl gamescopectl screenshot "$OUT/s$(printf %02d $((i * 2))).png" >/dev/null 2>&1 || true
done
{ kill $gpid; wait $gpid; } 2>/dev/null || true     # headless gamescope 結束時會 segfault,無害
"$WINE_ROOT/bin/wineserver" -k 2>/dev/null || true

grep -E '^t=|Buffer size' "$OUT/probe.txt" | sed 's/^ *info: *//' || true
python3 - "$OUT"/s*.png <<'EOF'
import sys
from PIL import Image
for f in sys.argv[1:]:
    im = Image.open(f).convert('RGB'); W, H = im.size; px = im.load()
    red = lambda p: p[0] > 200 and p[1] < 60 and p[2] < 60
    xs = [x for x in range(0, W, 2) if any(red(px[x, y]) for y in range(0, H, 4))]
    ys = [y for y in range(0, H, 2) if any(red(px[x, y]) for x in range(0, W, 4))]
    if not xs:
        print(f"{f.rsplit('/', 1)[-1]}  輸出 {W}x{H}  沒有紅色區"); continue
    w, h = xs[-1] - xs[0] + 2, ys[-1] - ys[0] + 2
    print(f"{f.rsplit('/', 1)[-1]}  輸出 {W}x{H}  畫面 {w}x{h} @x={xs[0]}  比例 {w / h:.3f}")
EOF
echo "截圖與 log:$OUT"
