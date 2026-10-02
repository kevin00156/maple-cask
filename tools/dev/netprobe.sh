#!/bin/bash
# netprobe.sh [pid...] — 列出遊戲/反作弊「這個 wine 實例」真正持有的 TCP 連線
#
# 為什麼不用 ss -tanp:wine 的 socket 常由別的執行緒/行程持有,ss 的 pid 欄位會是空的。
# 改用 fd -> socket inode -> /proc/net/tcp 對應。
#
# ⚠ 2026-09-14 修正:第一版只掃 MapleStory.exe 與 *.aes,結果在「成功的對照輪」
#   也量到 0 條連線 —— 因為 wine 的 socket 多半掛在 wineserver 底下。
#   沒有對照組的話,這個 0 會被當成「失敗時連不上伺服器」的證據。
#   現在預設把 wineserver 與所有 wine 行程一起掃。
hex2ip(){ printf "%d.%d.%d.%d" "0x${1:6:2}" "0x${1:4:2}" "0x${1:2:2}" "0x${1:0:2}"; }
declare -A ST=( [01]=ESTAB [02]=SYN_SENT [03]=SYN_RECV [04]=FIN_WAIT1 [05]=FIN_WAIT2
                [06]=TIME_WAIT [07]=CLOSE [08]=CLOSE_WAIT [09]=LAST_ACK [0A]=LISTEN [0B]=CLOSING )
declare -A INO
# 欄位:sl local rem st tx:rx tr:tm retrnsmt uid timeout inode ...
while read -r _ _ rem st _ _ _ _ _ ino _; do
  [ "$ino" = "0" ] && continue
  INO[$ino]="$(hex2ip "${rem%:*}"):$((16#${rem#*:})) ${ST[$st]:-$st}"
done < <(tail -n +2 /proc/net/tcp)
pids="$*"
[ -z "$pids" ] && pids=$(ps -eo pid=,comm= | awk '$2 ~ /\.(aes|exe)$/ || $2 ~ /^wineserver$/ {print $1}')
# 一律補上 wineserver —— 遊戲的 socket 常常在它身上
pids="$pids $(ps -o pid= -C wineserver 2>/dev/null)"
# shellcheck disable=SC2086  # 故意不加引號:把 pids 裡的空白/換行攤平成一個個 pid
for p in $(echo $pids | tr ' ' '\n' | sort -un); do
  [ -d "/proc/$p" ] || continue
  out=""
  for fd in "/proc/$p/fd"/*; do
    l=$(readlink "$fd" 2>/dev/null) || continue
    case "$l" in socket:\[*\]) ino=${l:8:-1};; *) continue;; esac
    [ -n "${INO[$ino]}" ] && out="$out    ${INO[$ino]}"$'\n'
  done
  [ -n "$out" ] && { echo "[$p $(cat "/proc/$p/comm" 2>/dev/null)]"; printf '%s' "$out"; }
done
