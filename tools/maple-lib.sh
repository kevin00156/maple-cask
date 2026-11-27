# shellcheck shell=bash disable=SC2034  # 變數給 source 它的腳本用
# 各腳本共用的定義,用 source 載入、不直接執行(MC-14)。同一件事只寫在這裡一次,不然各份會各自漂走。
# 只定義變數與函式:不 set 選項、不讀 WINEPREFIX —— maple 在載入 env.sh 之前就 source 它。

# 設定 / 資料 / 快取(log、update 的鎖與時戳)目錄,照 XDG
CFG=${XDG_CONFIG_HOME:-$HOME/.config}/maplestory-tw
DATA=${MAPLE_DATA:-${XDG_DATA_HOME:-$HOME/.local/share}/maplestory-tw}
CACHE=${XDG_CACHE_HOME:-$HOME/.cache}/maplestory-tw

# setup-prefix.sh 放進 prefix 的 dll,也是 run.sh 強制用 native(WINEDLLOVERRIDES =n)的那幾個
DXVK=(d3d11 d3d10core dxgi d3d9)    # 64 與 32 位元都要(NGS 那側是 32 位元)
VKD3D=(d3d12 d3d12core)             # 只有 64 位元

# prefix_has PREFIX PGREP參數…:pgrep 找到的行程裡,有沒有屬於這個 prefix 的(看 /proc/<pid>/environ 的 WINEPREFIX)。
# 多開時每組一個 prefix,別組在跑不相干。例:prefix_has "$WINEPREFIX" -x wineserver
prefix_has() {
    local pfx=$1 p
    shift
    for p in $(pgrep "$@"); do
        tr '\0' '\n' <"/proc/$p/environ" 2>/dev/null | grep -qxF "WINEPREFIX=$pfx" && return 0
    done
    return 1
}
