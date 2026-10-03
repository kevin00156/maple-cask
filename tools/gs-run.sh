#!/bin/bash
# 在 gamescope 裡跑楓之谷。這是建議(實際上是必要)的啟動方式,理由見 docs/known-issues.md「一定要經 gamescope」:
#   - 直接跑在桌面的 X 上,常常還沒畫出登入畫面就「與登入伺服器連線中斷」(實測 1/7);經 gamescope 10/10。
#   - 遊戲活在 gamescope 自己的 Xwayland 裡,永遠是唯一有焦點的視窗:不會搶你桌面的焦點,
#     你切去別的視窗時它也不會收到 deactivate。
# 前提:遊戲已關、wineserver 已死(wine 的 explorer desktop 得在 gamescope 的 Xwayland 上重生)。
#   W/H = gamescope 內部解析度 = 遊戲選單能選的最大解析度,預設 1920x1080;全螢幕:GS_ARGS="-W 1920 -H 1080 -f" tools/gs-run.sh
#   比它方正的模式(拍賣場 1024x768)由 wine 補黑邊,見 prefix/reg/maplestory.reg 的 EmulateModeset。
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
export MAPLE_LOG=${MAPLE_LOG:-$HOME/.cache/maplestory-tw/gs-$(date +%m%d-%H%M%S).log}
echo "log → $MAPLE_LOG"
exec gamescope ${GS_ARGS:--W 1920 -H 1080} -- "$(dirname "$(readlink -f "$0")")/../run.sh"
