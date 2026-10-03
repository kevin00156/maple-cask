# tools/dev —— 開發用量測工具

玩遊戲用不到這裡的任何東西。這些是改 patch 時拿來**不開遊戲**(或不靠肉眼)量結果的探針,
每一支都對應 `docs/` 裡某個問題的驗證方式。

`*.c` 是 Win32 程式,要在**同一個 prefix** 裡用 `$WINE_ROOT/bin/wine` 跑;建置指令在各檔檔頭
(`x86_64-w64-mingw32-gcc …`),`build/build-wine.sh` 不會編這個目錄。

| 檔案 | 量什麼 | 對應 |
|---|---|---|
| `gametest.sh` | 啟動遊戲一次,印一行判定(`LOGIN` / `NETFAIL` / …)與行程、socket、log 摘要 | `docs/known-issues.md`「一定要經 gamescope」 |
| `focusthief.c` + `focustest.sh` | 一支只會對自己 `SetForegroundWindow` 的視窗;量桌面焦點會不會被搶回去 | `patches/0008` |
| `imeprobe.c` + `imetest.py` | 形狀跟遊戲一樣的裸視窗;用 XTEST 自動打注音,看 Win32 收到什麼訊息 | `patches/0010`、`0011` |
| `keyrepeat-probe.c` | 按住一個鍵時,訊息佇列的 repeat 與 `GetAsyncKeyState` 各看到什麼 | `patches/0012` |
| `modeprobe.c` + `modetest.sh` | D3D9 全螢幕切 1024x768 等解析度時,gamescope 輸出是補黑邊還是拉伸、滑鼠座標對不對(headless,不干擾遊戲) | `docs/known-issues.md`「拍賣場被拉伸」 |
| `netprobe.c` / `netprobe.sh` | 對登入伺服器只做 TCP connect / 列出這個 wine 實例實際持有的 TCP 連線 | 登入伺服器連線中斷(`NETFAIL`) |

`NETFAIL` = 遊戲彈出「與登入伺服器連線中斷,請稍後再試。」。

紀律:**對遊戲不送任何合成輸入**。反作弊活著時,XTEST / xdotool 在它眼裡就是巨集;
需要按鍵的量測(`keyrepeat-probe`、`imeprobe`)都是在沒有遊戲的獨立視窗上做的。
