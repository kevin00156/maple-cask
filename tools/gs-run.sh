#!/bin/bash
# 在 gamescope 裡跑楓之谷。這是建議(實際上是必要)的啟動方式,理由見 docs/known-issues.md「一定要經 gamescope」:
#   - 直接跑在桌面的 X 上,常常還沒畫出登入畫面就「與登入伺服器連線中斷」(實測 1/7);經 gamescope 10/10。
#   - 遊戲活在 gamescope 自己的 Xwayland 裡,永遠是唯一有焦點的視窗:不會搶你桌面的焦點,
#     你切去別的視窗時它也不會收到 deactivate。
# 前提:遊戲已關、wineserver 已死(wine 的 explorer desktop 得在 gamescope 的 Xwayland 上重生)。
#   沒給 GS_ARGS 時照遊戲自己存的設定挑(docs/known-issues.md「拍賣場被拉伸」):
#     遊戲是「視窗模式」→ -w/-h(遊戲選單能選的上限)固定 1920x1080,-W/-H(gamescope 視窗)= 遊戲設定的解析度。
#                        gamescope 把遊戲視窗縮放成 -W/-H ÷ 視窗大小,跟 -w/-h 無關,所以照樣 1:1;
#                        兩者若綁在一起,選了 1366 下次就只開 1366、選單選不回 1920。遊戲裡換解析度,重開才回到 1:1。
#     遊戲是「全螢幕」  → 固定 1366x768 = 登入畫面的解析度。換別的,登入畫面要切非原生模式 → 卡死斷線(實測 1/12)。
#   要自己指定:GS_ARGS="-W 1366 -H 768 -f" tools/gs-run.sh
#   要用自建的 gamescope(中文輸入法候選窗,patches/gamescope-0001),把它的 bin/ 放進 PATH 最前面即可(env.sh 裡設)。
set -euo pipefail
if [ -z "${WINE_ROOT:-}" ]; then
    source "${MAPLE_ENV:-${XDG_CONFIG_HOME:-$HOME/.config}/maplestory-tw/env.sh}"
fi
: "${WINE_ROOT:?請設定 WINE_ROOT(見 env.example)}" "${WINEPREFIX:?請設定 WINEPREFIX}"
command -v gamescope >/dev/null || { echo "找不到 gamescope(Ubuntu/Debian:sudo apt install gamescope)" >&2; exit 1; }
# 只看「這個 prefix」的 wineserver:多開時別的實例(別的 prefix)在跑不相干
for p in $(pgrep -x wineserver); do
    if tr '\0' '\n' <"/proc/$p/environ" 2>/dev/null | grep -qxF "WINEPREFIX=$WINEPREFIX"; then
        echo "這個 prefix 的 wineserver 還活著;先關遊戲,再 WINEPREFIX=$WINEPREFIX \"$WINE_ROOT/bin/wineserver\" -k,不然 explorer 的 desktop 留在桌面的 display" >&2; exit 2
    fi
done
# 遊戲把畫面設定存在 HKLM\Software\Wow6432Node\Wizet\MapleStory;soScreenMode 1 = 視窗
game_size() {
    local reg=$WINEPREFIX/system.reg w h
    grep -q '^"soScreenMode"=dword:00000001' "$reg" 2>/dev/null || { echo "-W 1366 -H 768"; return; }
    w=$(sed -n 's/^"soResolutionWidth"=dword:\([0-9a-f]*\).*/\1/p' "$reg")
    h=$(sed -n 's/^"soResolutionHeight"=dword:\([0-9a-f]*\).*/\1/p' "$reg")
    [ -n "$w" ] && [ -n "$h" ] && echo "-w 1920 -h 1080 -W $((16#$w)) -H $((16#$h))" || echo "-W 1366 -H 768"
}
GS_ARGS=${GS_ARGS:-$(game_size)}
echo "gamescope $GS_ARGS"
export MAPLE_LOG=${MAPLE_LOG:-$HOME/.cache/maplestory-tw/gs-$(date +%m%d-%H%M%S).log}
echo "log → $MAPLE_LOG"
exec gamescope $GS_ARGS -- "$(dirname "$(readlink -f "$0")")/../run.sh"
