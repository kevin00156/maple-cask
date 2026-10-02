#!/bin/bash
# 把一個 prefix 的 wine 全部收掉。環境變數同 run.sh(WINE_ROOT / WINEPREFIX)。
#
# 先走正常路徑 `wineserver -k`(server 會把自己的 client 全殺掉再退出);
# 剩下的只可能是「wineserver 已經死了」的孤兒,直接 SIGKILL。
# 為什麼會有孤兒:wineserver 收到 SIGTERM 是直接 exit,不收 client;而 wine 的每條執行緒
# 等在自己握著兩端的 wait pipe 上(ntdll/unix/server.c wait_fd),server 死了也讀不到 EOF,永遠不會自己走。
# 身分:/proc/<pid>/exe 在 $WINE_ROOT 底下 + environ 的 WINEPREFIX 相符 —— 別的 prefix、別的 wine 一律不碰。
set -u
: "${WINE_ROOT:?}" "${WINEPREFIX:?}"
ROOT=$(readlink -f "$WINE_ROOT")

# 一次 find 掃完(-lname 比對 exe 符號連結的目標),不要每個 pid fork 一次 readlink —— 上千個行程會慢到幾十秒
stragglers() {
    local e p
    # shellcheck disable=SC2044  # /proc/<pid>/exe 路徑不會有空白
    for e in $(find /proc -mindepth 2 -maxdepth 2 -name exe -lname "$ROOT/*" 2>/dev/null); do
        p=${e#/proc/}; p=${p%/exe}
        tr '\0' '\n' <"/proc/$p/environ" 2>/dev/null | grep -qxF "WINEPREFIX=$WINEPREFIX" && echo "$p"
    done
}
server_alive() {
    local p
    for p in $(stragglers); do [ "$(cat "/proc/$p/comm" 2>/dev/null)" = wineserver ] && return 0; done
    return 1
}

# server 還活著:叫它收(它會殺掉自己的 client),給 5 秒。
# server 已死:剩下的不可能自己走,只給 0.5 秒讓還在處理 SIGTERM 的行程退完,然後直接收。
if server_alive; then
    WINEPREFIX=$WINEPREFIX timeout 10 "$WINE_ROOT/bin/wineserver" -k 2>/dev/null
    tries=20
else
    tries=2
fi
for _ in $(seq $tries); do
    [ -z "$(stragglers)" ] && exit 0
    sleep 0.25
done
mapfile -t left < <(stragglers)
[ ${#left[@]} -gt 0 ] && { echo "kill-prefix:SIGKILL 殘留的 wine 行程 ${left[*]}" >&2; kill -9 "${left[@]}" 2>/dev/null; }
exit 0
