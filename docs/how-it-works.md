# 它為什麼能動 — 每個設定背後的理由

這份文件記錄每一個 patch / 登錄檔 / 環境變數**為什麼存在**。不知道理由的設定遲早會被人拿掉,然後壞掉。
所有結論都是實測(`WINEDEBUG` 追蹤、`wineserver -d1` 全請求 log、pcap、自寫的最小重現程式),不是猜的。

## 1. Code page 950 必須在 prefix「建立時」決定
客戶端一開頭就檢查 `GetACP() == 950`,不是就跳
`This client can be executed only in Traditional Chinese code-page` 然後結束。

wine 的 ACP 是 `wineboot` 建 prefix 時從 locale 決定、寫進
`HKLM\System\CurrentControlSet\Control\Nls\CodePage\ACP` 的;**之後再改環境變數沒用**。
所以 `setup-prefix.sh` 全程跑在 `LANG=LC_ALL=zh_TW.UTF-8`,建完會檢查 `system.reg` 裡 `"ACP"="950"`。

(給之後要做 Steam compatibilitytool 的人:Proton 的 `proton` 啟動腳本會主動 pop 掉 `LC_ALL`,得改用 `HOST_LC_ALL` 才傳得進去。)

## 2. BlackCipher 的「乾淨複本比對」與 `.msf` patch(patches/0001)
這是整個專案的核心,也是上游 wine 跑不起來的**唯一**根本原因。

**現象(沒有這個 patch 時)**:遊戲開得起來、不崩、TCP 連上登入伺服器、DXVK 每幀 present,但畫面全黑、
Draw call = 0,幾分鐘後「與登入伺服器連線中斷」。`wineserver -d1` 看到主執行緒每秒約 40 次
`select()` 三個 handle:`0xFFFFFFF0、0xFFFFFFF0、NULL` —— 兩個哨兵值加一個空值,**這三個同步物件從來沒被建立過**。
遊戲在等一個永遠不會好的初始化。

**根因**:Nexon 的反作弊 BlackCipher(NGS)會把 `ntdll.dll`、`kernelbase.dll`、`ws2_32.dll`、`iphlpapi.dll`
位元組原封複製到 `%TEMP%\*.tmp` 再 `LoadLibrary` 那份複本 —— 反作弊標準手法:從磁碟載一份乾淨的,
跟記憶體裡的比,找 inline hook。在 Windows 上兩者一致。在 wine 上,PE 版的 `ntdll.dll` 只是薄殼,
記憶體裡的 syscall thunk 在載入時被改寫成跳進 unix 側 —— 在比對器眼裡就是滿滿的 hook
→ NGS 判定被竄改 → 不完成初始化 → 上面那三個 handle 永遠不會被建立。

**修法(Nexon 官方 macOS 版自己出貨的做法)**:`CopyFile(X.dll → Y.tmp)` 時旁寫一個 `Y.tmp.msf` 記下原名;
`LoadLibrary(Y.tmp)` 看到有 `.msf` 就改載 `X.dll` → 回傳的是**已經載入的同一個模組** → 比對相同 → 通過。
NGS 照樣跑它所有的檢查,只是拿到它要的那個模組。這段程式碼來自 Nexon 依 LGPL 公開的 CrossOver 樹
(`dlls/kernelbase/{file,loader}.c`,標記 `MapleStory HACK`),本專案只是改寫成 wine 風格、修掉一個記憶體洩漏。

驗證:遊戲跑起來後 `ls $WINEPREFIX/drive_c/users/steamuser/AppData/Local/Temp/*.msf` 應該有檔案
(`nst*.tmp.msf`、`BC*.tmp.msf`;Valve 的 wine 把 prefix 使用者固定叫 `steamuser`)。

## 3. `CreateFileA("ws2_32.dll")` 重導向(patches/0002)
同一棵 CrossOver 樹裡、緊鄰 `.msf` 的另一段未標記 hack:BlackCipher 用**裸檔名**開 `ws2_32.dll` 讀磁碟複本,
相對路徑解析到遊戲目錄 → wine 下沒這個檔 → 開失敗。把那個精確字串改指到 `C:\windows\system32\ws2_32.dll`。
獨立成一個 patch 是為了可以單獨拔掉對照。

## 4. NGS Error `0xe1000501` = 你的 wine 是純 64 位元
`NGService.exe`(NGS 服務程序)與 `BlackXchg.aes` 是 **32 位元**。純 `--enable-win64` 的 build 沒有
`i386-windows`,NGS 服務起不來(`failed to load \??\C:\windows\syswow64\ntdll.dll`),進遊戲幾分鐘後被踢:
`NGS Error : 0xe1000501(-520092415)`。所以 runner 一定是 `--enable-archs=i386,x86_64`(WoW64)build。

## 5. 為什麼不走 Proton 的 `proton` 啟動腳本
同一顆 wine,經過 `proton run` 腳本啟動 → Themida 丟出的例外 unwind 之後 TEB 的堆疊界限變成零長度
(`invalid frame ... (0x12000-0x12000)`),wine 拒絕 dispatch 例外,程序秒死。
直接執行 `bin/wine MapleStory.exe` → 正常。是腳本設定的**某個環境**(Steam Runtime 容器 / 環境變數)造成的,
根因未查。所以目前交付 Lutris / Heroic 式的 runner(它們直接執行 `bin/wine`),不做 Steam compatibilitytool。

## 6. 圖形:DXVK、vkd3d-proton、`dxvk.conf`、NxOverlay
- `d3d11 / d3d10core / dxgi / d3d9` 用 DXVK(64 與 32 位元都放,NGS 那側是 32 位元);`d3d12 / d3d12core` 用 vkd3d-proton。
- `dxvk.conf`:`dxgi.hideNvidiaGpu = False`、`dxgi.nvapiHack = False`。NGS 會蒐集硬體資訊,
  DXVK 預設假裝成 AMD 卡,對反作弊來說「一張不存在的卡」很可疑。在 AMD 卡上這兩個設定無作用。
- **NxOverlay**(`DwarfAxe.exe`,遊戲內嵌的 CEF 瀏覽器)用 D3D11 共享材質跟遊戲本體交換畫面,
  需要 `VK_KHR_external_memory_win32`。**上游 wine 與 CrossOver 樹都沒有實作它,只有 Valve 的 wine 有**
  (為 DXVK 共享材質做的)。
  本專案的 base 是**上游 10.16,沒有這個擴充**;CrossOver 同樣沒有,而兩者實測長時間遊玩都**沒有凍住**,
  所以它不再是選 base 的理由。
  真的凍住的話(log 會出現 `Failed to create shared resource: VK_KHR_EXTERNAL_MEMORY_WIN32 not supported`
  → `RtlpWaitForCriticalSection ... retrying (60 sec)` ×3),匯入
  `prefix/reg/dwarfaxe-wined3d.reg`:只讓 `DwarfAxe.exe` 走 wined3d,遊戲本體照舊 DXVK。

## 7. 字型(patches/0003、0004 + `prefix/reg/fonts.reg`)
`WINEDEBUG=+font` 追蹤證明遊戲走 GDI(數千次 `SelectFont` / glyph outline),而且只請求 5 種字面:

| 請求 | 次數 | 說明 |
|---|---|---|
| `System` h=+16 w=7 wt=700 charset=136(Big5) | 佔九成 | Windows 的 16×7 DBCS **點陣**系統字型(`cvgasys.fon`,wine 自帶),沒有中文字,中文靠 font-link 從細明體補 |
| `Tahoma` -11/-13 | 次多 | wine 自帶 |
| `Courier` +16/+12 charset=136 | 少 | wine 自帶 `.fon` |
| `MS Shell Dlg` -12 charset=136 | 少 | → Tahoma |
| `simsun` / `Nsimsun` -12..-20 charset=136 | 少 | 需代換到 PMingLiU |

所以**真正非要不可的專有字型只有 `mingliu.ttc`**(新細明體 / 細明體,Windows 內建)。
沒有它:所有中文掉到 fontconfig 的 Noto Sans CJK TC,行高 1.448 em vs 新細明體 1.0 em → 高 45%、基線下沉、
高亮條切字、行距互壓。

四個 wine 問題疊在一起:
1. **GASP 在現代系統上是死碼**(0003):`freetype_get_aa_flags()` 只要 `is_subpixel_rendering_enabled()` 就跳出,
   GASP 檢查永遠跑不到。那個函式是「FreeType 有沒有編 LCD filter」的**能力探測**,不是使用者設定,
   現代系統一律 TRUE。新細明體的 GASP 明寫 ppem 9..48 不要灰階、還帶 1-bit 內嵌點陣 strike,全被無視。
2. **點陣基礎字型的 aa_flags 污染整條 font-link 鏈**(0004):DC 只有一個 aa_flags,取自基礎字型。
   `System` 是點陣字型、沒有外框可抗鋸齒,wine 卻給它次像素模式,補上來的細明體就被迫走次像素。
   修:`if (!font->scalable) return GGO_BITMAP;`
3. **登錄檔 `FontSubstitutes` 會被字型自己的英文別名蓋掉**(不修,繞過):wine 載入字型時先用字型的英文別名
   註冊代換,讀登錄檔的 `load_gdi_font_subst()` 在 `font_init` 最後才跑,而 `add_gdi_font_subst` 是先到先贏。
   所以只要 prefix 裡有 `simsun.ttc`,`"SimSun"="PMingLiU"` 就無效 —— 而 SimSun 的 OS/2 沒有 Big5 位元,
   wine 會拒絕它再退給 fontconfig → Noto。**解法:不要把 simsun.ttc / simsunb.ttf / SimsunExtG.ttf 裝進 prefix。**
   (這是 wine 的順序 bug,但影響面太大、無法完整迴歸,本專案不動它。)

4. **有矩陣就丟掉內嵌點陣 strike**(0009):遊戲九成的字送 `System h=16 **w=7**`。7 正是
   `cvgasys.fon` 自己的 `tmAveCharWidth`,英數照原尺寸從點陣 strike 出來;但中文是 font-link 去
   新細明體拿的,它在這個尺寸原生是 8(這個請求還要 weight=700,fake bold 後算 9),於是
   `get_transform_matrices()` 給子字型一個 0.875 的水平縮放矩陣。接著:

   ```c
   if (matrices || format != GGO_BITMAP) load_flags |= FT_LOAD_NO_BITMAP;   /* 改前 */
   ```

   **只要有矩陣就放棄內嵌點陣**。新細明體帶 ppem 11/12/13/15/16/20 的 1-bit strike、GASP 也明寫
   這段範圍要 1-bit —— strike 才是它在 16px 的正解 —— 卻改走外框:hinting 先對著「未縮放」的網格
   grid-fit,**之後**才整個乘 0.875。先對齊再縮放等於沒對齊,mono 光柵器把落不到像素邊界的部分
   直接丟掉,筆畫就斷了、糊成一團。
   修:矩陣只有水平縮放時保留 strike,在這裡自己壓(每個目標欄 = 它涵蓋的來源欄 **OR** 起來;
   用取樣的話 0.875 會整欄整欄刪,那正是外框路徑失敗的方式)。

   對真 Windows 實測(`tools/gamefont.exe` 在 VM 裡跑同一支,主力那條的墨水像素 / advance):

   | | 墨水像素 | advance |
   |---|---|---|
   | Windows | 1986 | 15px |
   | 改前(外框) | 1700 | 15px |
   | 改後(壓 strike) | **2003** | 15px |

   剩下的形狀差異是 Windows 改在「縮放後的網格」上重新 grid-fit,我們是壓點陣;**advance 一致**,
   所以版面與度量兩邊相同。其餘 5 種請求逐像素完全不變。

另外 `AntialiasFakeBoldOrItalic="n"`:遊戲要 weight=700 的新細明體,它沒有 Bold 字面,wine 做 fake bold 時
預設強制抗鋸齒跳過 GASP;Windows 是把點陣圖位移疊加、仍然 1-bit。

驗證:`tools/gamefont.exe` 一字不差重現遊戲的 5 個 `CreateFont`,印出實得字型、`tmHeight`、`intLead`
與畫出來的一條字內不同 RGB 值的數量。全部 `intLead=0`(1.0 em 明體家族)、RGB 值 2~3(純 1-bit)就是對的,
不必開遊戲。

## 8. 每-app 虛擬桌面 —— 不做了
原本想用 wine 的虛擬桌面繞開 NVIDIA + Xorg 在 `miValidateTree` 的 segfault,但那個設定
**從來沒生效過**(尺寸鍵放錯位置),而且修好之後遊戲會被關進固定尺寸視窗、不是全螢幕。
`prefix/reg/vdesk.reg` 已經刪掉。

附帶的好處:沒有 `"Desktop"="maple"` 就沒有獨立的 Win32 desktop 物件,
遊戲留在 `Default` desktop,`tools/mapletype.exe` 用一般的 `EnumWindows` 就找得到視窗。

## 9. `prefix/reg/maplestory.reg` 的來源
umu-protonfixes 對 GMS(Steam app 216150)的修正的等價登錄檔(源自 oldschoola/linux_maplestory),
拿掉 GMS / Steam 專屬的部分(nxsteam、SteamConnectorHelper),補上台版的 `Patcher.exe`。
內容:X11 不搶 focus / 不 grab、DirectInput 非獨佔、`MapleStory.exe` 與 `Patcher.exe` 報 win10、
`nxl://` protocol handler。
另外自己加的一段:`AppDefaults\{MapleStory,DwarfAxe}.exe\X11 Driver` 的
`"RequestNetActiveWindow"="N"` —— 叫 `winex11` 不要為這兩個 exe 送 `_NET_ACTIVE_WINDOW`
給視窗管理員(`patches/0008`),不然遊戲每幾秒就把桌面焦點搶回去。全域段不設,別的程式不受影響。
要驗這個鍵有沒有生效**不必開遊戲**:`tools/dev/focusthief.exe` 是一支只會對自己
`SetForegroundWindow` 的探針,配 `PROC_NAME=focusthief.exe … tools/dev/focustest.sh` 量一次
(沒鍵 30/30、有鍵 0/30)。遊戲那條路徑要先過登入伺服器,而連線是間歇失敗的,不適合當量測載具。

## 10. 真的微軟 VC++ 2022 runtime
wine 沒有內建 `vcruntime140_threads.dll`。`setup-prefix.sh` 用 `winetricks vcrun2022` 抓微軟官方 redist 安裝
(合法;本專案不散布任何微軟 DLL)。

## 11. 取得 OTP(`tools/maple-login`)
台版登入表單要的不是帳密,是**遊戲帳號 sid + 一次性密碼 (OTP)**。這兩樣純 HTTPS 就能拿到 ——
不需要 beanfun 的 WebView 登入器(它在 wine 下是黑的,見 known-issues),也不碰遊戲與反作弊。

**為什麼不能用帳密登入。** beanfun 對帳密流程掛了 reCAPTCHA:`Login/InitLogin` 會回報這個
session 要不要過人機驗證,一旦要,`AccountLogin` 沒有 token 就一定失敗,而那個 token 只有
真瀏覽器拿得到。原有的 **QR 登入** 用 beanfun 手機 App 掃碼；另有選用的 GamaPass passkey 路徑，由真瀏覽器執行網站自己的 JS，不繞過 CAPTCHA 或站方限制。
(裸 GET 也會被風控標記後逼出 reCAPTCHA,所以 `bfotp.py` 的每個 request 都帶齊
`User-Agent` / `sec-ch-ua` / `Accept-Language`,而且 UA 與 `sec-ch-ua` 的 Chrome 主版號必須一致。)

**選用 passkey（`tools/maple_passkey.py`）。** 日常順序是先驗證已存 session；無法使用才試專用 passkey；只有未嘗試登入的缺憑證/缺依賴才退一次原有 QR，真正嘗試後失敗立即結束；需要使用者解鎖/確認/真人驗證時停止並報告，不自動開始 QR。`login` 強制重登，`login --qr` 跳過 passkey。缺憑證、Chromium 或 `secret-tool` 不影響 QR；OTP stdout、帳號選擇與 session 格式不變。

`passkey-setup` 必須在互動終端機由使用者在場操作：新視窗自行登入、確認、處理 CAPTCHA，再新增自己的一把專用 passkey，不沿用 Bitwarden。工具會對新分頁掛 CDP 虛擬 authenticator，取得新憑證後以 stdin 交給 `secret-tool store`，並讀回驗證；既有 keyring 值須使用者輸入 yes 才能取代。Secret Service 屬性固定為 `service=maple-login account=gamapass`；私鑰、cookie 與 token 不寫診斷或明文憑證檔。

優先系統預設 Chromium 系瀏覽器，再選已知 Chromium。CDP 使用 `--remote-debugging-pipe`、fd3/fd4、NUL 分隔 JSON，沒有開 TCP 除錯埠，也不偽裝 UA。每次使用 `/run/user/...` tmpfs 的新臨時 profile；登入可選 Xvfb（無則有視窗），setup 永遠有視窗。CDP 讀寫及 buffered event 處理都檢查硬 deadline。只清理自己的 process group 與臨時 profile，不接管使用者原有瀏覽器：即使 leader 已退出，也等待非 zombie 後代收尾，必要時有界升級 SIGKILL；其他 child/fd 清理各有 finally 保護。

`$XDG_CONFIG_HOME/maplestory-tw/passkey.lock` 序列化憑證讀取/登入/計數保存，`passkey-state.json` 保存非秘密的 dirty 安全狀態，不對使用者施加本機登入次數或冷卻限制。舊檔的 count/last 欄位忽略，不需手動刪檔；QR、passkey、setup 仍共用互斥鎖，並遵守站方限制。登入時只有一個 authenticator 持有該憑證並可 assertion；其他分頁不載入副本。切換 target 時先停用舊 presence、查核最新計數並移除舊副本，再以最新 signCount 啟用新 target。assertion 事件與最終 `getCredentials` 的最大 signCount 寫回 keyring，即使網站登入失敗也保存；若保存/確認計數失敗或程序被中止，dirty 狀態阻擋下次 passkey，必須重新 setup 一把新憑證或使用 QR，不能靜默重用舊計數。`forget` 維持原有 session 行為，不刪 passkey 或清除 dirty 防護。

登入逾時可能涉及確認，或偵測可見 CAPTCHA 時，以 `UserActionRequired` 停止，工具不代解 CAPTCHA、不自動退 QR。keyring 使用 `gdbus`（Ubuntu `libglib2.0-bin`）先查非秘密的 SearchItems 鎖定狀態，保存前也確認預設 collection 未鎖；不主動 Unlock/Prompt。缺依賴/無憑證仍可退 QR，但無法確認 keyring 狀態、鎖住或保存失敗時請使用者操作。setup 保存失敗請不要把網站新增成功當作工具保存成功。

**OTP 一次恢復。** 帳號清單成功但 `get_otp` 發生 BFError 或 requests 網路錯誤，不代表 session 必然失效（也可能是服務異常或另有登入 session）。若本次尚未取得新 session，僅以既有專用 passkey 取得一次新 session，安全保存並沿用保活，再申請一次 OTP。無 passkey、不足依賴、登入失敗、第二次 OTP 失敗均停止，不退 QR。若命令起始已取得新 session（含 QR），OTP 失敗就停止。恢復以第一次選定的穩定 sid 在新帳號清單找同一帳號、使用新的 ssn；找不到或停用就報錯，不再次詢問、不改選或更新偏好成別的帳號。每次命令最多一次新 session、最多兩次 OTP，重新執行命令才有新預算。選帳號、等待表單、交付/自動輸入、`--run` 與使用者中止的錯誤不觸發恢復；成功只交付一次，`get_otp` 本身不隱藏重試。 若在新 session 尚未返回呼叫端時中止（保存、保活、網站收尾或 signCount 同步），會關閉該 session 並原樣傳回 `KeyboardInterrupt`／`SystemExit`，不轉成 QR 或重登；signCount 同步中止保留 dirty 防護。

顯式 `otp --qr` 若沿用舊 session 而 OTP 故障，該命令直接停止，不偷偷改用 passkey 或新增自動 QR 恢復；重新執行命令的正常登入選擇仍可用。

本次一次恢復變更僅以 mock 故障注入與本機 fixture 回歸，沒有 live 登入；之前專用 passkey → 新 session → OTP 的受控成功記錄見 `tasks/todo.md`。取得 OTP 不要求關閉遊戲；測試 session/OTP 不等同操作遊戲。

**流程分三段。** 完整的 15 步在 `tools/beanfun/bfotp.py` 檔頭,這裡只講形狀:

1. **QR 登入 → `bfWebToken`**
   跟著 `bflogin/default.aspx` 的轉址鏈拿到 `pSKey`,抓 `Login/Index` 的
   `__RequestVerificationToken`,`Login/InitLogin` 換一張 QR,然後每秒問一次
   `QRLogin/CheckLoginStatus` 等使用者在 App 上按確認;確認後走 `SendLogin` →
   `return.aspx` 收尾,`bfWebToken` 從 cookie jar 拿。
   這個 token **等同登入憑證**,約 1~2 小時過期。
2. **列遊戲帳號**
   `auth.aspx` 先把 cookie 打好,再抓 `game_server_account_list.aspx`,
   解出每個帳號的 `sid`(登入表單要填的那串)、`ssn`、顯示名稱。
3. **五步換一張 OTP**
   `game_start_step2.aspx`(拿 longPollingKey / 加密 blob / createTime)→
   `get_cookies.ashx`(拿 `m_strSecretCode`)→ `record_service_start.ashx` →
   `get_result.ashx` 長輪詢 → `get_webstart_otp.ashx`,回來的是 `"1;{8 碼金鑰}{密文hex}"`。
   最後 **DES/ECB/NoPadding** 用那 8 碼金鑰解密、去掉尾端 NUL,就是 8 碼 OTP。

**加密的兩處細節。** 2026-08 之後新楓之谷走 `get_webstart_otp_v2.ashx`,參數藏在
`game_start_step2.aspx` 的 `m_objData.data` 裡:首字元是表選擇碼,其餘每個字元換成它在
16 進位取代表裡的索引,拿掉其中 8 個字元當 DES 金鑰,剩下的是密文 —— 這套是 GGM 自己的
`GGMWebStart.Command.DecryptParam()`。上游沒定論該用哪張表,所以 `decode_launch_blob()`
八張逐一試到解出 `LaunchTicket=` / `ppppp=` 為止(錯的表只會產生雜訊,不會剛好拼出欄位名)。
v2 另外要帶 GGM 的版本與雜湊做 client attestation(`GGM_CV` / `GGM_HASH`),
Gamania 出新版 GGM 時要跟著換,偵測點是 `CheckVersion.ashx`。

**自動輸入(`tools/mapletype.exe`)。** 偵測到遊戲在跑就把 sid + OTP 直接打進登入表單。
字元走 `PostMessageW(hwnd, WM_CHAR, ...)` —— 訊息直接進目標視窗的訊息佇列,不搶焦點、不經過 X11;
換欄與全選(Tab / Ctrl+A / Enter)走 `SendInput`。它**只做一件事**:在登入表單填 sid 與 OTP,
跟你自己貼上去是同一個結果。遊戲畫面裡的任何操作都不碰。

三個實作上的坑,每個都寫在 `tools/mapletype.c` 檔頭:**desktop 隔離**(自己把
`AppDefaults\…\Explorer\Desktop` 開起來的話,`EnumWindows` 看不到而且靜默回空 ——
預設沒開,見 §8)、**大寫會靜默變小寫**
(對方的 `TranslateMessage` 查的是它自己佇列的按鍵狀態,PostMessage 不會更新它,所以
文字要走 `WM_CHAR` 而不是 `WM_KEYDOWN`)、**一定要用 `$WINE_ROOT/bin/wine`**
(發行版的那份會在遊戲跑著時觸發 wineboot 更新 prefix)。

順帶更正一條舊註記:`prefix/reg/maplestory.reg` 裡的 `Grab` / `UseLinuxInputEvents` /
`KeyboardUseNonExclusive` / `MouseUseNonExclusive` 在 wine-10.16 全樹**沒有任何人讀**,
是從 protonfixes 移植時一起帶進來的死鍵。只有 `UseTakeFocus` 與 `GrabFullscreen` 是活的。

**session 重用。** OTP 是一次性的,但**登入 session 不是**。`maple-login` 把 `bfWebToken` 與
整個 cookie jar 存在 `$XDG_RUNTIME_DIR/maplestory-tw/session.json`(tmpfs、0600),
之後每次只重跑第 3 段鑄一張新的,不用再掃 QR。放 tmpfs 是刻意的:**重開機就消失**,
登入憑證不該落在磁碟上。`MAPLE_SESSION_FILE` 可以覆寫路徑。

**保活。** cookie 裡有兩個 `ASP.NET_SessionId`,而 ASP.NET 的 session state 預設是
sliding expiration(閒置計時器,每次請求重置),所以定期戳一下就能續命。只要 `maple-login`
手上拿到一個活的 session(掃 QR 或鑄一張 OTP 都算),就會裝一個 systemd user timer
(`maple-keepalive.timer`),每 10 分鐘跑一次 `keepalive` 子命令打一次 `list_accounts`。
session 死了它會自己停掉並跳桌面通知。安裝條件綁在「有活 session」而不是某個子命令上:
重開機後 tmpfs 清空,timer 會自己收攤拆掉,日常那條路(`maple` → 預設的 `otp` 子命令)
若不負責裝,保活就再也回不來。
上面那個「約 1~2 小時」是**閒置**觀察值;`bfWebToken` 有沒有另一個絕對壽命上限還沒測出來,
`journalctl --user -u maple-keepalive` 的紀錄就是這個問題的答案。
注意 session 仍在 tmpfs，**重開機需要重登入**（已設專用 passkey 則先試它，否則 QR），保活救不了那一半。

寫 session 檔走的是「臨時檔 + `os.rename()`」的原子換檔。保活跑在背景,會跟前景指令
同時碰同一個檔;直接 `O_TRUNC` 就地寫的話中間有一段是半截的 JSON,讀到的人會判定
session 壞掉、把你送去重掃 QR —— 實測並發下有 81.8% 的讀取會中招。

**QR 怎麼顯示。** 畫在終端機上,不叫外部程式。`maple-login` 自己解那張 PNG
(stdlib 的 `zlib` + 40 行反過濾,不用 Pillow),照模組中心取樣還原成 61x61 的模組矩陣,
再用半格區塊字元 `▀` 一列塞兩排模組印出來 —— 字元格本來就是 1:2,這樣一個模組才是方的。
背景自己塗白(`\033[107;30m`),不然深色主題的終端機掃不出來。

**這不是重繪。** `bfotp.init_qr()` 除了 PNG 還回傳一個 `gameplapp://` deeplink,
但實測解碼那張 PNG,QR 裡裝的是另一個字串
(`https://play.games.gamania.com/deeplink?url=beanfunapp://…`),兩者不是同一個東西 ——
拿 deeplink 重新編碼會做出一張內容不同的 QR。這裡走的是**取樣伺服器原圖**:
把模組矩陣照 3 px/模組攤回去與原圖逐像素比對,0 個像素不符,內容逐位元相同。

**為什麼不 `xdg-open`。** 以前的做法是把 PNG 寫到 tmpfs 再 `xdg-open`,而 `xdg-open`
照 mime 資料庫把檔案轉手給預設處理器 —— 那個處理器很可能是 snap / flatpak 包的瀏覽器。
沙盒裡的程式跑在自己的 mount namespace,**看不到 `$XDG_RUNTIME_DIR`**,
使用者只會看到瀏覽器跳出「沒有權限查看」(實測 snap chromium 讀 `/run/user/1000/…` 直接 EPERM;
同一台機器上原生 deb 裝的 Brave 讀得到 —— 差別在沙盒,不在瀏覽器)。
終端機畫不下(需要 69 欄 x 41 列)才退回找看圖程式,而且會先問 `xdg-mime query default image/png`
轉給誰,答案的 `.desktop` 出現在 snap / flatpak 的 exports 目錄就不用它。

**規格來源**:[pungin/Beanfun](https://github.com/pungin/Beanfun)(Rust + Tauri 的第三方客戶端)的
協定行為;取代表與常數則來自 Gamania 自己出貨的 `GGMWebStart`。`bfotp.py` 是照這些行為重寫的,
沒有複製它的程式碼。

## 13. 為什麼要 gamescope(`tools/gs-run.sh`)

**一、連線。** 直接跑在桌面的 X 上,遊戲常常在畫出登入畫面前就「與登入伺服器連線中斷」;
在 gamescope 裡不會(2026-09-26 交錯實測 10/10 vs 1/7,見 known-issues)。機制未定位。

**二、焦點。** 遊戲收到 deactivate 就不吃鍵(Windows 上也一樣)。在單一 X server 上,你點別的視窗 →
遊戲的 X 視窗收 FocusOut → winex11 `focus_out()` 把前景設成 desktop window → 遊戲 deactivate;
10.16 起遊戲還會用 `_NET_ACTIVE_WINDOW` 把桌面焦點搶回去(patches/0008 處理)。一個 X server 只有一個鍵盤焦點,
遊戲和你在搶同一個。gamescope 讓遊戲活在它自己的 Xwayland 裡,是那個世界唯一的視窗、永遠有焦點;
宿主端焦點離開不會轉成 X FocusOut。你的實體鍵盤只在 gamescope 視窗有焦點時才進得去。

**兩個硬前提。** (1) 起遊戲前 wineserver 必須是死的 —— wine 的 explorer desktop 在哪個 DISPLAY 上誕生
就留在那裡,留在桌面的 display 上的話遊戲視窗會跑錯地方;`gs-run.sh` 會檢查。
(2) 自建的 gamescope 要把它的 `bin/` 放進 PATH,它靠 PATH 找 `gamescopereaper`,
找不到就 `Primary child shut down!` 秒退。

**發行版的 gamescope 能用,但看不到中文輸入法的候選窗。** 候選窗需要
`patches/gamescope-0001-paint-ime-candidate-windows.patch`(見 known-issues「遊戲內打不出中文」#4)。
要它就自己編:`build/build-gamescope.sh`(版本釘在 `build/GAMESCOPE_VERSION`,裝到
`~/.local/share/maplestory-tw/gamescope`,然後在 `env.sh` 把它的 `bin/` 放進 PATH)。腳本會順手補上游漏掉的
`#include <cfloat>`、關掉要 catch2 的單元測試、以 `-Dwlroots:werror=false` 繞過新版 libinput 的 enum 警告。
Ubuntu 26.04 實測;24.04 的 wayland / libdrm / libxkbcommon / pixman 低於 wlroots 0.20 的門檻,要另外自建,不建議。

**中文輸入法在 gamescope 裡要多兩件事**(細節與證據見 known-issues):`run.sh` 會叫 fcitx5 把 XIM server
掛到 gamescope 的巢狀 Xwayland 上(DBus `OpenX11Connection`);gamescope 本身只畫跟遊戲同 pid 的 override-redirect
視窗,`gamescope-0001` 讓行程名是 `fcitx5` 的候選窗也被畫。它是當 decoration 畫的,不拿鍵盤焦點,不然會丟按鍵的放開事件。候選窗會在遊戲左上角,原因也在那一節。

順帶:gamescope 也把 Wayland 下 Xwayland fractional scaling 的問題(known-issues)一起帶走了 ——
遊戲看到的永遠是 gamescope 給的那個解析度。
