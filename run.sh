#!/bin/bash
# 啟動 MapleStory TW。環境變數同 prefix/setup-prefix.sh(WINE_ROOT / WINEPREFIX / GAME_DIR,見 env.example)。
#
# 完全不帶參數啟動 → 遊戲自己開登入表單,手動輸入帳號(sid)與 OTP。
# 注意:空表單閒置約 2 分鐘會自動關,所以先把 OTP 拿好再開遊戲;OTP 打錯只能整個重開(橘子的設計)。
set -euo pipefail

REPO=$(cd "$(dirname "$0")" && pwd)
: "${WINE_ROOT:?請設定 WINE_ROOT}" "${WINEPREFIX:?請設定 WINEPREFIX}" "${GAME_DIR:?請設定 GAME_DIR}"
export WINEPREFIX WINEARCH=win64
export LANG=zh_TW.UTF-8 LC_ALL=zh_TW.UTF-8
export WINEDEBUG="${WINEDEBUG:-fixme-all,err+all}"
export WINEDLLOVERRIDES="mscoree,mshtml=;d3d11,d3d10core,dxgi,d3d9,d3d12,d3d12core=n"
export DXVK_CONFIG_FILE="${DXVK_CONFIG_FILE:-$REPO/dxvk.conf}"

cd "$GAME_DIR"

# 遊戲死掉時 wine 的 err: 行是唯一的死因線索,而它只出現在終端機 ——
# 2026-09-15 就因為沒存檔,一次當機的錯誤訊息只剩使用者的 scrollback。
MAPLE_LOG=${MAPLE_LOG:-$HOME/.cache/maplestory-tw/run-$(date +%m%d-%H%M%S).log}
mkdir -p "$(dirname "$MAPLE_LOG")"
echo "log:$MAPLE_LOG"
exec > >(tee -a "$MAPLE_LOG") 2>&1

# gamescope 的巢狀 Xwayland 上沒有 XIM server(fcitx5 只註冊在 KWin 的那個 display),中文輸入法會完全沒反應。
# 請 fcitx5 多接這個 display;wine 只在視窗拿到焦點時建 XIC,所以必須在 wine 啟動前做。不走 gamescope 時已有 server,自動跳過。
if ! xprop -root XIM_SERVERS 2>/dev/null | grep -q '@server='; then
    busctl --user call org.fcitx.Fcitx5 /controller org.fcitx.Fcitx.Controller1 OpenX11Connection s "$DISPLAY" || true
fi
export XMODIFIERS="${XMODIFIERS:-@im=fcitx}"

# 不 exec wine,留在這裡收尾。gamescope 視窗按 X = gamescope 對自己 raise(SIGTERM) → gamescopereaper 對整棵行程樹
# 同時送 SIGTERM:wineserver 收到就直接退出、不收 client,剩下的 wine 行程(實測是 winedevice.exe)卡在自己的
# wait pipe 上永遠不死,reaper 沒有逾時地等它們 → gamescope 視窗「沒有回應」。所以 TERM 由這裡把整個 prefix 收乾淨。
trap '"$REPO/tools/kill-prefix.sh"; exit 143' TERM INT HUP
"$WINE_ROOT/bin/wine" "$GAME_DIR/MapleStory.exe" &
rc=0; wait $! || rc=$?   # set -e 下非 0 會直接退出,下面的等待就被跳過了
# 遊戲版本舊了,MapleStory.exe 會叫起 Patcher.exe 然後自己先退。run.sh 這時退出 = reaper 的主行程死了,
# 它就對整棵樹送 SIGTERM,Patcher 剛寫完 log 開頭就被殺,遊戲永遠更新不了(2026-10-07)。
# 所以等這個 prefix 的 wine 全部走光再退;放背景再 wait,上面的 trap 才收得到訊號。
"$WINE_ROOT/bin/wineserver" -w &
wait $!
exit $rc
