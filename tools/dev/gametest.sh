#!/bin/bash
# 跑一次遊戲啟動測試,最後印一行機器可讀的判定。
#
# 用法:
#   WINE_ROOT=… WINEPREFIX=… GAME_DIR=… tools/dev/gametest.sh [--duration SEC] [--label NAME]
#   LAUNCHER=/path/to/launcher.sh   # 選用,預設 $REPO/run.sh
#   GAMETEST_LOGS=/dir              # 選用,預設 $XDG_STATE_HOME/maplestory-tw/gametest
#   GAMETEST_WSDEBUG=1              # 選用,用 `wineserver -d1 -f -p` 跑,紀錄每一筆 server request
#
# 判定:
#   LOGIN   遊戲 log 出現 "Buffer size:  1920x1080"
#           (DXVK 把 swapchain 重建成登入畫面的解析度 = 真的畫到登入畫面了)
#   NETFAIL 沒有上面那行,但曾出現寬 < 600 的 MapleStory.exe toplevel
#           (那是「與登入伺服器連線中斷」對話框,實測 344x87)
#   BLACK   兩者皆無
#
# 本腳本【不截圖、不搶焦點、不呼叫 wmctrl -a、不用 xdotool】,對被測環境是被動觀測。
#
# 設計上刻意避開的坑(每一條都真的害過人):
#   * 找視窗一律比對 _NET_WM_PID → /proc/<pid>/comm,不用視窗標題
#     (Konsole 的標題會顯示 cwd,曾被當成遊戲視窗)。
#   * 找行程一律看誰 map 了 $GAME_DIR,不用行程名稱
#     (comm 上限 15 字元,BlackCipher64.aes 會被截成 BlackCipher64.a)。
#   * 不用 head -1 / 「取最大的」 挑候選,全部候選一起處理並列出。
#   * 每個 skip 分支都印出為什麼跳過,靜默跳過會讓失敗看起來像正常的 0。
set -uo pipefail

REPO=$(cd "$(dirname "$0")/../.." && pwd)
DURATION=75
LABEL=run
while [ $# -gt 0 ]; do
    case $1 in
        --duration) DURATION=${2:?--duration 後面要接秒數}; shift 2 ;;
        --label)    LABEL=${2:?--label 後面要接名稱};       shift 2 ;;
        *) echo "不認得的參數:$1" >&2; exit 2 ;;
    esac
done
case $DURATION in ''|*[!0-9]*) echo "--duration 必須是整數秒:$DURATION" >&2; exit 2 ;; esac
[ "$DURATION" -ge 15 ] || { echo "--duration 至少 15 秒" >&2; exit 2; }

: "${WINE_ROOT:?請設定 WINE_ROOT}" "${WINEPREFIX:?請設定 WINEPREFIX}" "${GAME_DIR:?請設定 GAME_DIR}"
LAUNCHER=${LAUNCHER:-$REPO/run.sh}
export WINE_ROOT WINEPREFIX GAME_DIR
# Wayland 下 XWayland 的 DISPLAY 不一定是 :0;猜錯會安靜地連不上,看起來像遊戲沒開視窗。不猜。
: "${DISPLAY:?請設定 DISPLAY(XWayland 下用 echo \$DISPLAY 看)}"
export DISPLAY

WINESERVER=$WINE_ROOT/bin/wineserver
[ -x "$WINESERVER" ]  || { echo "找不到可執行的 $WINESERVER" >&2; exit 2; }
[ -x "$LAUNCHER" ]    || { echo "找不到可執行的 launcher:$LAUNCHER" >&2; exit 2; }
[ -d "$GAME_DIR" ]    || { echo "GAME_DIR 不是目錄:$GAME_DIR" >&2; exit 2; }
[ -d "$WINEPREFIX" ]  || { echo "WINEPREFIX 不是目錄:$WINEPREFIX" >&2; exit 2; }

TS=$(date +%H%M%S)
LOGROOT=${GAMETEST_LOGS:-${XDG_STATE_HOME:-$HOME/.local/state}/maplestory-tw/gametest}
LOGDIR=$LOGROOT/$LABEL-$TS
mkdir -p "$LOGDIR" || { echo "建不出 $LOGDIR" >&2; exit 2; }
LOG=$LOGDIR/game.log
WINFILE=$LOGDIR/windows.txt; : > "$WINFILE"
MODFILE=$LOGDIR/modules.txt; : > "$MODFILE"

echo "== gametest: label=$LABEL duration=${DURATION}s =="
echo "   WINE_ROOT  = $WINE_ROOT"
echo "   WINEPREFIX = $WINEPREFIX"
echo "   GAME_DIR   = $GAME_DIR"
echo "   LAUNCHER   = $LAUNCHER"
echo "   紀錄       = $LOGDIR"

# ---- 1. 鎖屏檢查 -----------------------------------------------------------
# 鎖定畫面會抓住 X 的 selection,遊戲會卡在 clipboard 逾時,整輪數據都是假的。
lock=$(qdbus org.freedesktop.ScreenSaver /ScreenSaver GetActive 2>/dev/null)
echo "== 1. 鎖屏檢查:GetActive=${lock:-<讀不到>}"
if [ "$lock" = "true" ]; then
    echo "   ❌ 螢幕鎖定中,數據會是假的,中止"
    exit 2
fi

# ---- 共用函式 --------------------------------------------------------------
# 誰 map 了遊戲目錄底下的檔案,誰就是這一輪的行程。零硬編行程名稱。
# 誰 map 了遊戲目錄。
# 但「map 了 GAME_DIR」還不夠:兩個 prefix(受測的與對照組)
# 共用同一個遊戲目錄,對方在玩的時候那邊的行程也會被撈進來,於是這一輪的執行緒數、
# TCP 連線、記憶體圖全部混到別人的。所以再用 /proc/<pid>/environ 的 WINEPREFIX 篩一次,
# 只留下屬於【本輪 prefix】的行程。(身分要用穩定的東西定義,不是「名字對得上」。)
gamepids() {
    local d pfx
    for d in /proc/[0-9]*; do
        grep -qsF "$GAME_DIR" "$d/maps" || continue
        pfx=$(tr '\0' '\n' < "$d/environ" 2>/dev/null | sed -n 's/^WINEPREFIX=//p' | head -1)
        # 讀不到 environ(權限/行程剛消失)就保留,寧可多算也不要靜默漏掉
        [ -n "$pfx" ] && [ "$pfx" != "$WINEPREFIX" ] && continue
        echo "${d##*/}"
    done
}

# 本輪遊戲行程的 TCP 連線。用 fd 的 socket inode 對 /proc/net/tcp,不靠 ss
# (ss -p 要 root 才看得到別人的行程,而且我們只要本輪這幾個 pid)。
# 這是分辨「wine 根本沒連出去」與「連上了但被對方斷掉」的唯一辦法 ——
# 前者是我們的 bug,後者是伺服器端在擋,兩者的修法完全不同。
tcp_conns() {
    local p ino inodes
    for p in $(gamepids | sort -u); do
        inodes=$(ls -l "/proc/$p/fd" 2>/dev/null | grep -o 'socket:\[[0-9]*\]' | grep -o '[0-9]*')
        for ino in $inodes; do
            awk -v ino="$ino" -v pid="$p" 'NR>1 && $10==ino {
                split($2,l,":"); split($3,r,":");
                printf "%s %d.%d.%d.%d:%d -> %d.%d.%d.%d:%d st=%s\n", pid,
                  strtonum("0x" substr(l[1],7,2)),strtonum("0x" substr(l[1],5,2)),strtonum("0x" substr(l[1],3,2)),strtonum("0x" substr(l[1],1,2)),strtonum("0x" l[2]),
                  strtonum("0x" substr(r[1],7,2)),strtonum("0x" substr(r[1],5,2)),strtonum("0x" substr(r[1],3,2)),strtonum("0x" substr(r[1],1,2)),strtonum("0x" r[2]), $4
            }' /proc/net/tcp
        done
    done
}

# 清場:wineserver -k && -w,再確認沒有行程 map 遊戲目錄。
clear_stage() {
    local tag=$1 left p
    echo "== $tag 清場:$WINESERVER -k && -w"
    "$WINESERVER" -k >/dev/null 2>&1
    "$WINESERVER" -w >/dev/null 2>&1
    left=$(gamepids | sort -u | tr '\n' ' ')
    if [ -n "${left// /}" ]; then
        echo "   wineserver 收完仍有行程 map 著遊戲目錄:$left → kill -9"
        for p in $left; do kill -9 "$p" 2>/dev/null; done
        sleep 3
        "$WINESERVER" -k >/dev/null 2>&1
        "$WINESERVER" -w >/dev/null 2>&1
    else
        echo "   wineserver 收完已無行程 map 遊戲目錄"
    fi
    left=$(gamepids | sort -u | tr '\n' ' ')
    if [ -n "${left// /}" ]; then
        echo "   ❌ 清場失敗,仍有:$left"
        return 1
    fi
    echo "   清場完成"
    return 0
}

# sidecar 計數:所有使用者目錄一起算。
# (曾經用 head -1 只看 users/<登入名>,而遊戲真正在用的是 users/steamuser → 整個實驗量了個空目錄。)
sidecar_count() {
    local n=0 d c found=0
    for d in "$WINEPREFIX"/drive_c/users/*/AppData/Local/Temp; do
        if [ ! -d "$d" ]; then
            echo "   sidecar 略過 $d:不是目錄" >&2
            continue
        fi
        found=1
        c=$(find "$d" -maxdepth 1 -type f -name '*.msf' 2>/dev/null | wc -l)
        echo "   sidecar $d = $c" >&2
        n=$((n + c))
    done
    [ "$found" = 1 ] || echo "   ⚠ 一個 Temp 目錄都沒找到" >&2
    echo "$n"
}

# BlackCipher 的 log 大小。內容是加密的,但【增量】= 反作弊這一輪走了多遠。
# (兩個 build 共用同一個 GAME_DIR,所以只有「一輪之內的增量」有意義,絕對值沒有。)
bc_sizes() {
    local f
    for f in "$GAME_DIR"/BlackCipher/*.log; do
        [ -f "$f" ] || continue
        echo "$(basename "$f") $(stat -c %s "$f")"
    done
}

# 每個執行緒的 context switch 累計值。純讀 /proc,零開銷,反作弊看不到。
# 這是分辨「使用者空間 CPU 空轉」與「等鎖」的唯一辦法 —— 兩者在 wineserver log 裡
# 長得一模一樣(都是沒有請求),因為 wine 10.x 的 critical section 走 futex、不經過 server:
#   voluntary 不動 + nonvoluntary 爬 = 純空轉,一個 syscall 都沒發
#   voluntary 爬但 server request 沒跟著爬 = 卡在 futex,而且看不見在等誰
dump_ctxt() {
    local out=$1 p t st
    : > "$out"
    for p in $(gamepids | sort -u); do
        for t in "/proc/$p/task/"*; do
            st=$t/status
            [ -r "$st" ] || continue
            # 執行緒可能在兩次 sed 之間消失,那是正常的,不要把錯誤噴到判定輸出裡
            # 欄位:pid tid name vol nonvol wchar minflt majflt utime stime
            #   wchar  = write() 出去的位元組數。寫入已開啟的檔案【不會產生 server request】,
            #            所以這是看出「wineserver log 裡完全隱形」的執行緒有沒有在做事的唯一欄位。
            #   minflt = 次要 page fault 數。分辨「純計算自旋」與「例外/fault 風暴」——
            #            後者不產生 voluntary switch、不發 server request、不寫檔,唯一的足跡就是 fault。
            #   utime/stime = user/kernel 時間(clock ticks)。stime 高但沒有 syscall = 在處理 fault。
            # /proc/<tid>/stat 的 comm 欄可能含空白與括號,所以先砍到最後一個 ")" 之後再取欄位。
            echo "$p ${t##*/} $(sed -n 's/^Name:\t//p' "$st" 2>/dev/null) \
$(sed -n 's/^voluntary_ctxt_switches:[ \t]*//p' "$st" 2>/dev/null) \
$(sed -n 's/^nonvoluntary_ctxt_switches:[ \t]*//p' "$st" 2>/dev/null) \
$(sed -n 's/^wchar:[ \t]*//p' "$t/io" 2>/dev/null) \
$(sed 's/.*) //' "$t/stat" 2>/dev/null | cut -d' ' -f8,10,12,13)" | tr -s ' \n' ' ' >> "$out"
            echo >> "$out"
        done
    done
}

# 每條連線的位元組計數與最後收/送的時間。
#   bytes_sent 有、bytes_received = 0  → 我們送了,對方不回(伺服器端)
#   兩個都是 0                          → 連上之後自己卡住沒送(我們這邊)
#   先動後停,看 lastsnd/lastrcv        → handshake 中途停在哪一步
# ss -p 要 root 才看得到行程,所以先用 tcp_conns 拿到本輪的 src/dst,再用它們去問 ss。
tcp_stats() {
    local pid lo arrow re st
    tcp_conns | while read -r pid lo arrow re st; do
        [ -n "$lo" ] || continue
        printf '%s %s -> %s  %s\n' "$pid" "$lo" "$re" \
            "$(ss -tin "src $lo dst $re" 2>/dev/null | tail -n +2 | tr -s ' \n' ' ' |
               grep -oE '(^| )(bytes_sent|bytes_acked|bytes_received|data_segs_out|data_segs_in|lastsnd|lastrcv|lastack):[0-9]+' |
               tr '\n' ' ')"
    done
}

# 列出屬於 MapleStory.exe 的 toplevel 幾何(一行一個 WxH)。
# 身分判準:_NET_WM_PID → /proc/<pid>/comm。"MapleStory.exe" 是 14 字元,沒踩到 comm 的 15 字元上限。
list_game_windows() {
    local id rest pid comm geo w h wpfx
    while read -r id rest; do
        [ -n "$id" ] || continue
        pid=$(xprop -id "$id" _NET_WM_PID 2>/dev/null | sed -n 's/.*= *\([0-9][0-9]*\)$/\1/p')
        if [ -z "$pid" ]; then
            echo "   skip $id ($rest):沒有 _NET_WM_PID" >&2
            continue
        fi
        comm=$(cat "/proc/$pid/comm" 2>/dev/null)
        if [ "$comm" != "MapleStory.exe" ]; then
            echo "   skip $id:pid $pid 的 comm=${comm:-<行程已消失>},不是 MapleStory.exe" >&2
            continue
        fi
        # 同一個 GAME_DIR 可能有另一個 prefix 的遊戲在跑(對照組),
        # 它的視窗也叫 MapleStory.exe。不篩掉的話它的尺寸會被算進本輪的判定。
        wpfx=$(tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null | sed -n 's/^WINEPREFIX=//p' | head -1)
        if [ -n "$wpfx" ] && [ "$wpfx" != "$WINEPREFIX" ]; then
            echo "   skip $id:pid $pid 屬於別的 prefix($wpfx)" >&2
            continue
        fi
        geo=$(xwininfo -id "$id" 2>/dev/null)
        w=$(echo "$geo" | sed -n 's/^ *Width: *\([0-9][0-9]*\)$/\1/p')
        h=$(echo "$geo" | sed -n 's/^ *Height: *\([0-9][0-9]*\)$/\1/p')
        if [ -z "$w" ] || [ -z "$h" ]; then
            echo "   skip $id:pid $pid 是遊戲,但 xwininfo 讀不到寬高" >&2
            continue
        fi
        echo "${w}x${h}"
    done < <(wmctrl -l)
}

# 取一次快照:誰 map 了遊戲目錄、map 了哪些 .aes/.tmp/.msf、遊戲有哪些 toplevel。
snapshot() {
    local tag=$1 snap=$2 pids p mods
    {
        echo "=== $tag  $(date +%T) ==="
        pids=$(gamepids | sort -u | tr '\n' ' ')
        if [ -z "${pids// /}" ]; then
            echo "沒有任何行程 map 遊戲目錄"
        else
            for p in $pids; do
                mods=$(grep -ioE "[^/]*\.(aes|tmp|msf)" "/proc/$p/maps" 2>/dev/null | sort -u | tr '\n' ' ')
                echo "[$p $(cat "/proc/$p/comm" 2>/dev/null)] ${mods:-<沒有 .aes/.tmp/.msf>}"
                # 整份記憶體圖留檔:上面那行只留模組名,但要回答「某個位址落在哪個模組」
                # (例如 wineserver log 裡的 init_thread entry)就得有區段界限。
                # 檔名沿用 $snap 而不是 $tag —— tag 含空格("#1 t=15s")。
                cp "/proc/$p/maps" "${snap%.txt}-maps-$p.txt" 2>/dev/null
                if [ -n "$mods" ]; then
                    echo "$mods" | tr ' ' '\n' >> "$MODFILE"
                fi
            done
        fi
        echo "--- MapleStory.exe toplevel ---"
        list_game_windows | tee -a "$WINFILE"
    } 2>&1 | tee "$snap"
    dump_ctxt "${snap%.txt}-ctxt.txt"
}

# ---- 2. 清場 ---------------------------------------------------------------
clear_stage "2." || exit 3

# ---- 2b. 可選:帶 -d1 的 wineserver(內部狀態插樁) --------------------------
# 這【不是】除錯器,是 wine 自己的 server 端 trace:每一筆 server request 一行。
# 遊戲程序看不到它。代價是 server 變慢 → 所以對照組一定要開同樣的旗標。
WSPID=
if [ "${GAMETEST_WSDEBUG:-0}" = 1 ]; then
    echo "== 2b. $WINESERVER -d1 -f -p(log → $LOGDIR/wineserver.log)"
    "$WINESERVER" -d1 -f -p > "$LOGDIR/wineserver.log" 2>&1 &
    WSPID=$!
    sleep 2
    if kill -0 "$WSPID" 2>/dev/null; then
        echo "   wineserver pid=$WSPID 就緒"
    else
        echo "   ❌ wineserver 起不來:"; sed 's/^/      /' "$LOGDIR/wineserver.log"; exit 3
    fi
fi

# ---- 3. sidecar 起始數 + BlackCipher log 起始大小 ---------------------------
echo "== 3. sidecar(.msf)起始數"
sc0=$(sidecar_count)
echo "   合計 sc0=$sc0"
bc_sizes > "$LOGDIR/bc-before.txt"
echo "   BlackCipher log 起始大小 → $LOGDIR/bc-before.txt"
sed 's/^/      /' "$LOGDIR/bc-before.txt"

# ---- 4. 啟動 ---------------------------------------------------------------
echo "== 4. 啟動 $LAUNCHER(log → $LOG)"
"$LAUNCHER" > "$LOG" 2>&1 &
LPID=$!
echo "   launcher pid=$LPID"

# ---- 4b. BlackCipher log 的細粒度時間軸 ------------------------------------
# 每 2 秒一筆。反作弊寫自己的 log 用的是已開啟的 fd,【不會產生 server request】,
# 所以一條在使用者空間空轉的反作弊執行緒,在 wineserver log 裡是完全隱形的 ——
# 這條時間軸是唯一能看出「它在那段時間有沒有在做事」的東西。
BCPID=
if [ -d "$GAME_DIR/BlackCipher" ]; then
    ( t=0
      while [ "$t" -le "$DURATION" ]; do
          printf '%s %s\n' "$t" "$(bc_sizes | tr '\n' ' ')" >> "$LOGDIR/bc-timeline.txt"
          printf '=== t=%ss ===\n%s\n' "$t" "$(tcp_stats)" >> "$LOGDIR/tcp-timeline.txt"
          sleep 2; t=$((t + 2))
      done ) &
    BCPID=$!
    echo "   BlackCipher log 時間軸取樣中(每 2 秒)→ $LOGDIR/bc-timeline.txt"
fi

# ---- 5. 每 15 秒取樣 -------------------------------------------------------
echo "== 5. 每 15 秒取樣,共 ${DURATION}s"
elapsed=0
i=0
while [ "$elapsed" -lt "$DURATION" ]; do
    step=15
    [ $((DURATION - elapsed)) -lt 15 ] && step=$((DURATION - elapsed))
    sleep "$step"
    elapsed=$((elapsed + step))
    i=$((i + 1))
    snapshot "#$i t=${elapsed}s" "$LOGDIR/snap-$(printf '%02d' "$i")-t${elapsed}s.txt"
    [ -n "$WSPID" ] && echo "   wineserver.log = $(stat -c %s "$LOGDIR/wineserver.log") bytes"
done

[ -n "$BCPID" ] && kill "$BCPID" 2>/dev/null

# ---- 6. 結束前再列一次 toplevel 幾何 ---------------------------------------
echo "== 6. 結束前的 toplevel 幾何"
snapshot "final t=${DURATION}s" "$LOGDIR/snap-final.txt"

# ---- 7. 清場 ---------------------------------------------------------------
if kill -0 "$LPID" 2>/dev/null; then
    echo "   launcher pid=$LPID 還活著(comm=$(cat "/proc/$LPID/comm" 2>/dev/null)),先 kill"
    kill -9 "$LPID" 2>/dev/null
fi
clear_stage "7." || exit 3

# ---- 8. 判定 ---------------------------------------------------------------
echo "== 8. BlackCipher log 增量"
bc_sizes > "$LOGDIR/bc-after.txt"
join -j1 "$LOGDIR/bc-before.txt" "$LOGDIR/bc-after.txt" 2>/dev/null \
  | awk '{printf "   %-20s %10d -> %10d  (+%d)\n", $1, $2, $3, $3-$2}' \
  | tee "$LOGDIR/bc-delta.txt"
[ -n "$WSPID" ] && echo "   wineserver.log = $(stat -c %s "$LOGDIR/wineserver.log") bytes"

echo "== 8b. sidecar 結束數"
sc1=$(sidecar_count)
delta=$((sc1 - sc0))
echo "   合計 sc1=$sc1,這一輪新增 $delta"

mods=$(sort -u "$MODFILE" | sed '/^$/d' | tr '\n' ' ' | sed 's/ *$//')
[ -n "$mods" ] || mods='-'
wins=$(sort -u "$WINFILE" | sed '/^$/d' | paste -sd, -)
[ -n "$wins" ] || wins='-'

login=$(grep -cF 'Buffer size:  1920x1080' "$LOG" 2>/dev/null)
login=${login:-0}
echo "   log 裡 'Buffer size:  1920x1080' 出現 $login 次"

narrow=0
while read -r g; do
    [ -n "$g" ] || continue
    w=${g%x*}
    case $w in ''|*[!0-9]*) echo "   略過無法解析的視窗幾何:$g"; continue ;; esac
    if [ "$w" -lt 600 ]; then
        echo "   出現寬 < 600 的遊戲 toplevel:$g(連線中斷對話框的特徵)"
        narrow=1
    fi
done < <(sort -u "$WINFILE" | sed '/^$/d')

if [ "$login" -gt 0 ]; then
    RESULT=LOGIN
elif [ "$narrow" = 1 ]; then
    RESULT=NETFAIL
else
    RESULT=BLACK
fi

line="RESULT=$RESULT sidecar=+$delta modules=$mods windows=$wins log=$LOG"
echo "$line" | tee "$LOGDIR/RESULT.txt"
