# patches/

套在上游 wine-10.16 release tarball 上(`build/build-wine.sh` 用 `patch -p1 -F0`,不准 fuzz:
套不上就表示上游動過那段,要人看過再說)。每個 patch 的檔頭是完整的 commit message,寫著問題、根因與實測。

| | 檔案 | 用途 | 上游? |
|---|---|---|---|
| 0001 | `kernelbase` `.msf` sidecar | BlackCipher 乾淨複本比對(沒有它就黑畫面;每輪產生 8 個 `.msf`、一個 `.tmp` 都沒有)。作法來自 Nexon 依 LGPL 公開的 CrossOver 原始碼樹,見 [how-it-works §2](../docs/how-it-works.md) | 遊戲專屬,不送 |
| 0002 | `kernelbase` `CreateFileA("ws2_32.dll")` 重導向 | 同上,BlackCipher 用裸檔名開 ws2_32 | 遊戲專屬,不送 |
| 0003 | `win32u` GASP 在有次像素能力的系統上也生效 | 字型:新細明體的 1-bit 點陣 strike 才會被用 | **通用 bug,待送** |
| 0004 | `win32u` 點陣基礎字型不做抗鋸齒 | 字型:不污染 font-link 鏈的 aa_flags | **通用 bug,待送** |
| 0005 | `kernelbase` `CharPrevExA` NULL 解參考 | `CharPrevExA(950, NULL, NULL, 0)` 會炸;上游 11.17 已修,本 base(10.16)仍需要 | 上游已修 |
| 0007 | `ntdll` 新執行緒堆疊清零 960KB(10.0 的值;10.16 是 60KB) | **未證實有效**,診斷時留下的候選 | 不送 |
| 0008 | `winex11` 每-app 關掉 `_NET_ACTIVE_WINDOW` 請求 | 不經 gamescope 時遊戲每幾秒把桌面焦點搶回去;鍵設在 `AppDefaults\<exe>\X11 Driver`,預設維持上游行為(實測 28/30 → **0/30**) | 通用機制,可考慮送上游 |
| 0009 | `win32u` 純水平縮放時保留點陣 strike 並自己壓縮 | 字型:遊戲九成的字送 `System h=16 w=7`,wine 只要有縮放矩陣就丟掉內嵌點陣、改走外框,筆畫斷裂。對 Windows 實測墨水像素 1700 → **2003**(Windows 1986),advance 一致。細節 [how-it-works §7](../docs/how-it-works.md) | **通用 bug,待送** |
| 0010 | `win32u` IME 通知繞過被 subclass 的 IME 視窗 | 遊戲內打中文(遊戲換掉了 Default IME 視窗的 wndproc) | 可考慮送上游 |
| 0011 | `imm32` IME UI 視窗隨 owner 死掉後重建 | 遊戲內打中文(wine bug:`imc->ui_hwnd` 指向死 handle) | **通用 bug,待送** |
| 0012 | `winex11` 由 wineserver 做 Windows 式 auto-repeat | 綁在 Shift / Ctrl / Alt 的技能按住會連發(X server 寫死修飾鍵不 repeat) | 可考慮送上游 |
| gamescope-0001 | gamescope 畫輸入法的 override-redirect 視窗(當 decoration 畫,不拿鍵盤焦點) | 中文輸入法候選窗(選用,`build/build-gamescope.sh`) | gamescope,可考慮送 |

量測用的探針在 [`tools/dev/`](../tools/dev/README.md)。
