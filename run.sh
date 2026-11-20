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

# setup 沒跑完的 prefix,遊戲只會留一行 "dxgi.dll ... not found" 就退出。maple 開遊戲前也查,這裡顧直接跑 gs-run.sh / Lutris 的人
"$REPO/prefix/setup-prefix.sh" --check

# 手把:wine 的 winebus 直接開 /dev 的手把(SDL / hidraw / evdev),不經過 gamescope,
# 視窗沒 focus 也照收 → 搖桿在背景讓角色亂動;主機板 RGB 之類的 HID 也會被當成搖桿、卡著「上」。
# 所以預設把三個後端全關,MAPLE_GAMEPAD=1 才開(docs/known-issues.md「手把預設關閉」)。
# winebus 只在 wineserver 起來時讀一次設定:值有變才寫,寫完等這個 prefix 的 wine 全退,下面的遊戲才會用到新值。
gamepad_set() {   # 印出 system.reg 裡 winebus 段落目前的三個值
    awk '/^\[/{s=index($0,"[System\\\\ControlSet001\\\\Services\\\\winebus]")==1}
         s&&/^"(Enable SDL|DisableHidraw|DisableInput)"=/' "$WINEPREFIX/system.reg" | sort
}
if [ "${MAPLE_GAMEPAD:-0}" = 1 ]; then on=1 off=0; else on=0 off=1; fi
want=$(printf '"DisableHidraw"=dword:0000000%s\n"DisableInput"=dword:0000000%s\n"Enable SDL"=dword:0000000%s\n' $off $off $on)
ws_alive() {      # 這個 prefix 的 wineserver 還在 → system.reg 可能沒寫回、新值也要等它重啟才生效
    for p in $(pgrep -x wineserver); do
        tr '\0' '\n' <"/proc/$p/environ" 2>/dev/null | grep -qxF "WINEPREFIX=$WINEPREFIX" && return 0
    done; return 1
}
if [ "$(gamepad_set)" != "$want" ]; then
    if ws_alive; then
        echo "提示:這個 prefix 的 wineserver 還在,手把設定(MAPLE_GAMEPAD)這次不套用,關掉遊戲再開" >&2
    else
        k='HKLM\System\CurrentControlSet\Services\winebus'
        for kv in "Enable SDL=$on" "DisableHidraw=$off" "DisableInput=$off"; do
            "$WINE_ROOT/bin/wine" reg add "$k" /v "${kv%=*}" /t REG_DWORD /d "${kv#*=}" /f >/dev/null || true
        done
        "$WINE_ROOT/bin/wineserver" -w || true
        [ $on = 1 ] || echo "提示:遊戲裡的手把已關閉(背景搖桿會讓角色亂動);要用手把在 env.sh 設 export MAPLE_GAMEPAD=1" >&2
    fi
fi

# gamescope 的巢狀 Xwayland 上沒有 XIM server(fcitx5 只註冊在 KWin 的那個 display),中文輸入法會完全沒反應。
# 請 fcitx5 多接這個 display;wine 只在視窗拿到焦點時建 XIC,所以必須在 wine 啟動前做。不走 gamescope 時已有 server,自動跳過。
if ! xprop -root XIM_SERVERS 2>/dev/null | grep -q '@server='; then
    busctl --user call org.fcitx.Fcitx5 /controller org.fcitx.Fcitx.Controller1 OpenX11Connection s "$DISPLAY" >/dev/null 2>&1 ||
        echo "提示:沒有 fcitx5,遊戲裡打不了中文(只支援 fcitx5;IBus 見 docs/known-issues.md「遊戲內打不出中文」)" >&2
fi
export XMODIFIERS="${XMODIFIERS:-@im=fcitx}"

# 反作弊在主執行緒上每 ~30ms 一次 split lock,kernel 預設每次罰睡 10ms → 間歇卡頓(docs/known-issues.md)
if [ "$(cat /proc/sys/kernel/split_lock_mitigate 2>/dev/null)" = 1 ]; then
    echo "警告:kernel.split_lock_mitigate=1,遊戲主執行緒會一直被罰睡 → 卡頓。修法見 docs/known-issues.md「split lock」" >&2
fi
# GetTickCount 是開機到現在的毫秒數,遊戲當 32 位元有號數用:超過 2^31 ms(24.8 天)選角就會卡「伺服器連線中」(MC-27)。
# 經 maple-timens 啟動的話,這裡看到的開機時間是從 0 開始的,不會觸發。留 1 天餘裕:遊戲開著也會跨過去
if [ "$(cut -d. -f1 /proc/uptime)" -gt 2059200 ]; then
    echo "警告:開機已超過 23.8 天,超過 24.8 天選角後會卡「伺服器連線中」。重開機,或見 docs/known-issues.md「開機太久」" >&2
fi
# ntsync:同步呼叫不必全排隊到單執行緒的 wineserver。沒有就退回 wineserver,能玩,只是只在做得到的時候提醒
# (v0.1.4 以前的 release runner 都沒編進去;kernel 太舊沒有這個模組就不提)。
# 查裝置路徑字串,不是 "ntsync":自建 runner 的安裝路徑常帶這個字,編進去的路徑會讓它永遠成立。
# 模組在不在看 modules.dep,不用 modinfo:Debian 一般使用者的 PATH 沒有 /usr/sbin。
if ! grep -qaF /dev/ntsync "$WINE_ROOT/bin/wineserver"; then
    echo "提示:這個 wine runner 沒編進 ntsync;maple update 可換成有 ntsync 的版本" >&2
elif [ -e /dev/ntsync ]; then
    [ -w /dev/ntsync ] || echo "提示:/dev/ntsync 沒有寫入權限(ls -l /dev/ntsync),ntsync 用不了" >&2
elif grep -q '/ntsync\.ko' "/lib/modules/$(uname -r)/modules.dep" 2>/dev/null; then
    echo "提示:ntsync 模組沒載入:sudo modprobe ntsync(永久:echo ntsync | sudo tee /etc/modules-load.d/ntsync.conf)" >&2
fi

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
