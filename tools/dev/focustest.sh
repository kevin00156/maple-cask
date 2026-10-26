#!/bin/bash
# 量「遊戲會不會把桌面焦點搶回去」。
#
# 判準:啟動遊戲 → 等登入畫面(1920x1080 的 MapleStory.exe toplevel)→ 把焦點切走一次 →
#       之後 30 秒純被動取樣 `_NET_ACTIVE_WINDOW` 的擁有者行程,數「焦點回到遊戲」的秒數。
#       0/30 = 不搶。
#
# 整支腳本只做一個會改變使用者環境的動作:那一次 `wmctrl -i -a`(開跑前會印警告)。
# 之後不再 activate、不截圖、不看視窗標題、不拿 window id 當身分 —— 這三樣在
# 開發時各騙過我們一次。取樣比對的是「焦點視窗屬於哪個行程」。
#
# 用法:
#   source ~/.config/maplestory-tw/env.sh
#   tools/dev/focustest.sh
#
# 環境變數:
#   LAUNCH_CMD        啟動遊戲的命令(預設 <repo>/run.sh)
#   FOCUS_TARGET_PID  要把焦點切過去的那個視窗的行程 pid(預設:啟動遊戲前的作用中視窗)
#   SAMPLES           取樣秒數(預設 30)
#   WAIT_TIMEOUT      等登入畫面的上限秒數(預設 180)
#   MIN_W / MIN_H     「登入畫面」視窗的最小尺寸(預設 1900x1000;遊戲視窗會跟著螢幕大小走)
#   PROC_NAME         要等誰的視窗(預設 MapleStory.exe)。驗 patches/0008 用的探針:
#                     PROC_NAME=focusthief.exe MIN_W=400 MIN_H=300 LAUNCH_CMD=<跑 focusthief.exe 的腳本>
#   GAMELOG           遊戲 stdout/stderr 丟去哪(預設 $TMPDIR/focustest-game.log)
set -uo pipefail

REPO=$(cd "$(dirname "$0")/../.." && pwd)
LAUNCH_CMD=${LAUNCH_CMD:-$REPO/run.sh}
SAMPLES=${SAMPLES:-30}
WAIT_TIMEOUT=${WAIT_TIMEOUT:-180}
GAMELOG=${GAMELOG:-${TMPDIR:-/tmp}/focustest-game.log}
PROC_NAME=${PROC_NAME:-MapleStory.exe}
: "${GAME_DIR:?請先 source env.sh(要 GAME_DIR)}"
WINESERVER_BIN=${WINESERVER:-${WINE_ROOT:-}/bin/wineserver}
[ -x "$WINESERVER_BIN" ] || { echo "找不到 wineserver:$WINESERVER_BIN"; exit 1; }
for t in wmctrl xprop; do command -v $t >/dev/null || { echo "缺 $t"; exit 1; }; done

# 螢幕鎖定會抓住 X selection,把好的 build 量成壞的(2026-09-13 踩過)
if command -v qdbus >/dev/null; then
    locked=$(qdbus org.freedesktop.ScreenSaver /ScreenSaver GetActive 2>/dev/null || echo unknown)
    [ "$locked" = "true" ] && { echo "螢幕是鎖定的,測出來的數字不能用。先解鎖。"; exit 1; }
fi

norm() { printf '0x%08x' "$((${1}))"; }          # 0x4800011 與 0x04800011 是同一個視窗
active_win() { norm "$(xprop -root _NET_ACTIVE_WINDOW | grep -o '0x[0-9a-f]*' | head -1)"; }
win_pid() { xprop -id "$1" _NET_WM_PID 2>/dev/null | grep -o '[0-9]*$'; }
comm_of() { cat "/proc/$1/comm" 2>/dev/null; }

# 遊戲的行程不只 MapleStory.exe(NxOverlay 的 DwarfAxe.exe / CrBrowserMain 也會開視窗)。
# 用「誰把遊戲目錄 map 進來」認人,不用行程名 —— comm 只有 15 字元,會把名字截斷。
game_pids() {
    local p
    for p in /proc/[0-9]*; do
        grep -qF "$GAME_DIR" "$p/maps" 2>/dev/null && echo "${p#/proc/}"
    done
}

echo "=============================================================="
echo " 接下來會【啟動遊戲】,並在登入畫面出現後【把焦點切走一次】。"
echo " 之後 $SAMPLES 秒純被動觀察,不會再動你的視窗。結束時會關掉遊戲。"
echo "=============================================================="
echo "啟動命令:$LAUNCH_CMD"
echo "WINEPREFIX:${WINEPREFIX:-未設}"

# 焦點要切到哪:預設用「啟動遊戲之前的作用中視窗」(此刻遊戲還沒開,一定不是遊戲的)
TARGET_WIN=""
if [ -n "${FOCUS_TARGET_PID:-}" ]; then
    while read -r id _ pid _; do
        [ "$pid" = "$FOCUS_TARGET_PID" ] && TARGET_WIN=$(norm "$id") && break
    done < <(wmctrl -lGp)
    [ -n "$TARGET_WIN" ] || { echo "FOCUS_TARGET_PID=$FOCUS_TARGET_PID 沒有對應的 toplevel"; exit 1; }
else
    TARGET_WIN=$(active_win)
fi
TARGET_PID=$(win_pid "$TARGET_WIN")
echo "焦點要切去的視窗:$TARGET_WIN pid=$TARGET_PID comm=$(comm_of "${TARGET_PID:-0}")"
[ -n "$TARGET_PID" ] || { echo "那個視窗沒有 _NET_WM_PID,認不出是誰的,不做。"; exit 1; }

echo "== 啟動遊戲 =="
"$LAUNCH_CMD" >"$GAMELOG" 2>&1 &

cleanup() {
    echo "== 收尾:關掉這個 prefix 的 wineserver =="
    "$WINESERVER_BIN" -k 2>/dev/null
    "$WINESERVER_BIN" -w 2>/dev/null
    local left
    left=$(ps -o pid=,args= -C wine -C wineserver 2>/dev/null)
    if [ -n "$left" ]; then
        echo "還有 wine 行程在(可能是別人的 prefix,沒有動它):"; echo "$left"
    else
        echo "wine / wineserver 都沒了。"
    fi
}
trap cleanup EXIT

# 等登入畫面 = MapleStory.exe 的「大視窗」。
# 尺寸不能寫死:同一台機器上不同 wine build 量過 1920x1080 與 2560x1440(跟螢幕一樣大)兩種。
# 啟動階段的黑畫面視窗是 1366x768,錯誤對話框是 344x87,兩個都在門檻外。
MIN_W=${MIN_W:-1900} MIN_H=${MIN_H:-1000}
echo "== 等 $PROC_NAME 的大視窗(>= ${MIN_W}x${MIN_H},上限 ${WAIT_TIMEOUT}s)=="
GAME_WIN=""
declare -A seen
for ((t = 0; t < WAIT_TIMEOUT; t++)); do
    NETFAIL_WIN=""
    while read -r id _ pid _ _ w h _; do
        [ "$(comm_of "$pid")" = "$PROC_NAME" ] || continue
        # 看到的每個遊戲視窗都印一次(含尺寸)。尺寸對不上時要看得見,不能靜默空等。
        [ -n "${seen[$id-$w-$h]:-}" ] || { echo "   t=${t}s 看到 $id ${w}x${h}"; seen[$id-$w-$h]=1; }
        # 「與登入伺服器連線中斷」那個小對話框(實測 344x87)。它一出現這一輪就完了,
        # 不要再空等 —— 那是還沒解的 NETFAIL(「與登入伺服器連線中斷」,見 docs/known-issues.md),與焦點無關。
        [ "$PROC_NAME" = "MapleStory.exe" ] && [ "$w" -lt 500 ] && [ "$h" -lt 200 ] && NETFAIL_WIN=$(norm "$id")
        [ "$w" -ge "$MIN_W" ] && [ "$h" -ge "$MIN_H" ] && GAME_WIN=$(norm "$id")
    done < <(wmctrl -lGp)
    [ -n "$GAME_WIN" ] && break
    if [ -n "$NETFAIL_WIN" ]; then
        echo "❌ 第 ${t}s 出現 ${NETFAIL_WIN} 這個小對話框(MapleStory.exe,應該是「與登入伺服器連線中斷」)。"
        echo "   這是已知的 NETFAIL,跟焦點無關,這一輪不算數。"
        exit 3
    fi
    sleep 1
done
if [ -z "$GAME_WIN" ]; then
    echo "❌ ${WAIT_TIMEOUT}s 內沒等到登入畫面。當下的視窗清單(id/pid/大小/comm):"
    while read -r id _ pid _ _ w h _; do
        echo "   $id pid=$pid ${w}x${h} comm=$(comm_of "$pid")"
    done < <(wmctrl -lGp)
    echo "   遊戲 log:$GAMELOG"
    exit 2
fi
echo "登入畫面出現:$GAME_WIN(等了 ${t}s)"

mapfile -t GPIDS < <(game_pids)
echo "被測相關行程($(echo "${GPIDS[@]}" | wc -w) 個):$(for p in "${GPIDS[@]}"; do printf '%s(%s) ' "$p" "$(comm_of "$p")"; done)"

echo "== 唯一一次主動動作:把焦點切到 $TARGET_WIN =="
wmctrl -i -a "$TARGET_WIN"
sleep 2
echo "   切完之後的作用中視窗:$(active_win) comm=$(comm_of "$(win_pid "$(active_win)")")"

echo "== 被動取樣 ${SAMPLES}s =="
is_game_pid() {
    local p
    for p in "${GPIDS[@]}"; do [ "$p" = "$1" ] && return 0; done
    # 沒看過的 pid:重掃一次(遊戲會開新行程),再判一次
    mapfile -t GPIDS < <(game_pids)
    for p in "${GPIDS[@]}"; do [ "$p" = "$1" ] && return 0; done
    return 1
}
steal_maple=0 steal_game=0 first_steal=""
declare -A tally
for ((i = 1; i <= SAMPLES; i++)); do
    aw=$(active_win); apid=$(win_pid "$aw"); acomm=$(comm_of "${apid:-0}")
    [ -n "$acomm" ] || acomm="(pid=${apid:-?} 無 comm)"
    tally[$acomm]=$((${tally[$acomm]:-0} + 1))
    if [ "$acomm" = "$PROC_NAME" ]; then
        steal_maple=$((steal_maple + 1)); steal_game=$((steal_game + 1))
        [ -z "$first_steal" ] && first_steal=$i
    elif [ -n "$apid" ] && is_game_pid "$apid"; then
        steal_game=$((steal_game + 1))
        [ -z "$first_steal" ] && first_steal=$i
    fi
    printf '%2ds %s %s\n' "$i" "$aw" "$acomm"
    sleep 1
done

echo "=============================================================="
echo "焦點在 $PROC_NAME 行程: $steal_maple/$SAMPLES"
echo "焦點在任一遊戲行程:        $steal_game/$SAMPLES"
[ -n "$first_steal" ] && echo "第一次被搶回:第 ${first_steal}s" || echo "整段期間一次都沒被搶回。"
echo "取樣分佈:"
for k in "${!tally[@]}"; do printf '   %3d  %s\n' "${tally[$k]}" "$k"; done
echo "=============================================================="
