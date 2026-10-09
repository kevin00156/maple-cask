# 已知問題與限制

## 一定要經 gamescope(`tools/gs-run.sh` / `maple`)
直接在桌面的 X(或 KDE Wayland 的 Xwayland)上跑 `run.sh`,遊戲**常常在畫出登入畫面之前**就彈
「與登入伺服器連線中斷,請稍後再試。」;經 gamescope 就不會。2026-09-26 同一台機器、同一時段交錯實測:

| 啟動方式 | 到登入畫面 |
|---|---|
| `tools/gs-run.sh`(gamescope) | **10/10** |
| `run.sh` 直接跑在桌面上 | 1/7(其餘 ~30 秒後斷線) |

機制還沒定位(推測跟桌面 WM 的焦點 / 視窗事件有關:gamescope 的 Xwayland 裡只有遊戲自己)。gamescope 另外兩個好處:遊戲不會搶你桌面的焦點,
解析度也不受桌面縮放影響。所以 Lutris / Heroic 若要用,啟動命令請設成 `tools/gs-run.sh` 而不是 wine 本身。

## 多開:`maple -2 setup` 一次,之後 `maple -2`
```bash
maple -2 setup      # 建第 2 組(一次就好,約 30 秒)
maple -2            # 開第 2 組並登入;maple -2 stop / status / login … 用法跟第 1 組完全一樣
```
`-2` ~ `-9` 都可以。`setup` 做的事:
- 從主設定的遊戲目錄分出一份到 `~/.local/share/maplestory-tw/instances/N/game`:`Data/`(68GB,執行時不會被寫)用
  hardlink 不佔空間,其餘約 600MB 真的複製(BlackCipher 的 log 寫在遊戲目錄裡,兩組共用會互搶)。截圖不帶。
  hardlink 需要跟主遊戲目錄在同一個檔案系統;不同的話把 `MAPLE_DATA` 設到同一顆碟上。
- 寫 `~/.config/maplestory-tw/env-N.sh`(沿用主設定,只換 `WINEPREFIX` 與 `GAME_DIR`),跑 `setup-prefix.sh` 建全新 prefix。

隔離:prefix 不同 = wineserver 不同,兩組互相看不到對方的行程與 mutex;`maple -N` 只看、只關自己那組的行程;
自動登入只會填進自己那組(`mapletype.exe` 只連得到那組的 wineserver);「上次選的帳號」每組各記各的(`prefs-N.json`)。
wine 本身可以共用。

⚠ `Patcher.exe` 更新遊戲後,第 N 組的遊戲目錄要重建(刪掉 `instances/N/game` 與 `env-N.sh` 再 `maple -N setup`),
不然兩組版本可能不一致。

2026-09-27 實測:第 1、2 組同時開,都停在登入畫面;`maple -2 stop` 只關第 2 組。

## 字型:要自備 `mingliu.ttc`
新細明體是微軟的,本專案不能附。沒有它遊戲**能玩**,但中文會糊、行距會跑(掉到 Noto Sans CJK TC,行高高 45%)。
修法:從任何一台 Windows 的 `C:\Windows\Fonts` 複製出來(至少 `mingliu.ttc`;整個目錄複製也行),
設 `FONTS_DIR` 指過去再跑一次 `prefix/setup-prefix.sh`。腳本會自動排除 `simsun.ttc / simsunb.ttf / SimsunExtG.ttf`
—— 這三個**一定不能裝進 prefix**,理由見 [how-it-works.md §7](how-it-works.md#7-字型patches00030004--prefixregfontsreg)。
驗證用 `tools/gamefont.exe`,不必開遊戲。

## 不能從 Steam 介面直接選(沒有 Proton compatibilitytool)
經過 Proton 的 `proton` 啟動腳本遊戲會秒死(`invalid frame (0x12000-0x12000)`),根因未查。
目前只提供 Lutris / Heroic 式的 wine runner(直接執行 `bin/wine`)。

## 遊戲檔取得不在範圍內
你需要一份**現成的** MapleStory 目錄(約 70GB)。橘子官方安裝程式在 wine 下**沒測過**;
目前已知可行的是從 Windows 安裝後把整個目錄複製過來。之後 `Patcher.exe` 在 wine 下能正常自我更新
(它會下載新的 `MapleStory.exe` 蓋掉舊的)。

## 登入流程的兩個時間限制
- **空的登入表單閒置約 2 分鐘會自己關**。建議的順序是**先開遊戲、等表單出現,再跑 `tools/maple-login`** ——
  它偵測到遊戲在跑就直接把帳密打進去,OTP 從鑄出來到用掉只有幾秒。
  舊順序(先鑄 OTP 再開遊戲,也就是 `--run`)仍然可用,只是要跟那 2 分鐘賽跑。
- OTP 是一次性的,打錯或過期只能整個重開遊戲(橘子的設計,同一個視窗不給重試)。
  所以自動輸入第一次用建議加 `--no-submit`,確認兩欄都對了再自己按登入。
- beanfun 的登入 session 閒置約 1~2 小時過期。現在 `maple-login login` 會裝一個 systemd user timer
  每 10 分鐘保活,正常情況下不會再過期;真的過期了它會跳通知叫你重掃。
  **但 session 在 tmpfs,重開機一定要重掃**,這是刻意的(那個 token 等同登入憑證,不放磁碟)。

## 帳號欄要填的是 sid,不是帳號名稱
遊戲登入表單的「帳號」是 beanfun 的遊戲帳號 sid(`T9…` 開頭那串),不是你在 beanfun 網站上看到的帳號名稱。
`tools/maple-login` 會一併列給你。

## 只在這個環境測過
- Ubuntu 24.04(X11)與 26.04(KDE Plasma Wayland,遊戲在 gamescope 的 Xwayland 裡),NVIDIA 專有驅動 595。
- **AMD / Intel GPU 沒測過**(Steam Deck 是 AMD)。理論上 DXVK 一樣跑,`dxvk.conf` 那兩個 NVIDIA 相關設定在 AMD 上無作用。
- Wayland:只在 KDE Plasma Wayland + gamescope 上實玩過。升級時做過的準備與留下的觀察點:
  - 已做:`maplestory.reg` 釘死 `Drivers\Graphics="x11"`(走 XWayland,wine 看到的仍是 X11,
    本專案量過的 desktop 隔離 / per-desktop 前景與 keystate / dinput CBT hook 全在 wineserver 與
    winex11 層,不受影響);`gametest.sh` 不再猜 `DISPLAY=:0`。
  - 焦點:patches/0008 的前提是 KWin(X11)無條件放行 pager 來源的 `_NET_ACTIVE_WINDOW`;
    KWin Wayland 對 XWayland 客戶端走自己的 focus-stealing prevention,行為不保證相同。
    升級後 `tools/dev/focustest.sh` 重跑(走 gamescope 的話不相干:巢狀 Xwayland 裡沒有別的視窗可搶)。
  - NVIDIA:上面那個 Xorg `miValidateTree` segfault 是 Xorg + NVIDIA DDX 的;Wayland 下 Xorg 不存在,
    **可能**消失,但 XWayland 也是 X server 程式碼,不保證。多張顯卡的機器要確認
    KWin 的 `KWIN_DRM_DEVICES` 沒把合成丟到較弱的那張。
  - 縮放:XWayland 客戶端在 fractional scaling 下會模糊或尺寸錯,症狀看起來像 wine 壞了。
    **走 `tools/gs-run.sh`(gamescope)的話這條不存在**,遊戲只看到 gamescope 給的解析度。
    不經 gamescope 又黑屏的話**先懷疑這條**;用 100% 或 KWin 的「Xwayland 應用程式自行縮放」。
  - 驗收:升級後跑同一支唯讀探針(`mapletype.exe --probe`),
    同樣的 X 焦點狀態下預期 foreground 那行**一字不差**(焦點在遊戲=遊戲 hwnd、在別處=NULL;
    跑之前先 `xprop -root _NET_ACTIVE_WINDOW` 確認焦點在哪);不一樣才是合成器層動到了 winex11 的焦點同步。
  - 不要現在切 winewayland.drv:Wayland 不准客戶端自己 activate,遊戲的 `SetForegroundWindow`
    迴圈在那裡是無效操作,對背景注入理論上更有利,但 wl_keyboard leave 之後 winewayland
    怎麼處理內部 foreground、dinput 那條路會不會被觸發,一格都沒量過。病灶未定位的遊戲一次只動一個變數。
- NVIDIA + Xorg 下,遊戲重建 swapchain 那一刻 Xorg 可能在 `miValidateTree` segfault。以前想用每-app
  虛擬桌面繞過,但那個設定從來沒生效過、修好了又不能全螢幕,已經拿掉;
  `prefix/reg/maplestory.reg` 會順手把舊 prefix 留下的鍵清掉。

## SteamOS / Steam Deck:安裝流程能走完,遊戲畫面還沒驗證(2026-10-01,VM 實測)
在 SteamOS 3.8.14 的 VM 裡照「安裝」一節逐字跑(官方 recovery 映像裝的,桌面模式下的 Konsole):

| 項目 | 結果 |
|---|---|
| `maple update` 下載的 runner(v0.0.2) | ✅ 能跑(SteamOS 的 glibc 2.41 夠新) |
| `zh_TW.UTF-8` locale → ACP 950 | ✅ SteamOS **預先編好了**,不用 `locale-gen` |
| gamescope、xdotool、ss、python3 | ✅ 系統內建(gamescope 3.16.23) |
| `winetricks` | ❌ **沒有**,`setup-prefix.sh` 第 4 步會停下來 |
| `cabextract` | ❌ **沒有**,winetricks 裝 vcrun2022 要用 |

SteamOS 的系統分割區是唯讀的,不能直接 `pacman -S`。兩個工具都放進 `~/.local/bin` 就行
(winetricks 是一支 shell script;cabextract 從 Arch 套件解出 binary,只依賴 glibc):
```bash
mkdir -p ~/.local/bin && cd /tmp
curl -sSLo ~/.local/bin/winetricks https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks
f=$(curl -s https://archlinux.org/packages/extra/x86_64/cabextract/json/ | python3 -c 'import json,sys;print(json.load(sys.stdin)["filename"])')
curl -sSLO https://geo.mirror.pkgbuild.com/extra/os/x86_64/$f && tar -xf $f usr/bin/cabextract
install -m755 usr/bin/cabextract ~/.local/bin/ && chmod +x ~/.local/bin/winetricks
export PATH=~/.local/bin:$PATH      # 然後重跑 tools/maple update(或 prefix/setup-prefix.sh)
```
補上這兩個之後,`setup-prefix.sh` 全部完成。

**還沒驗證的(VM 測不了,要真機):** 遊戲本身能不能到登入畫面、Game Mode、加成「非 Steam 遊戲」。
原因是 VM 的 GPU:SteamOS 沒有 NVIDIA 的 Vulkan 驅動(沒有 NVK),只能走 virtio-gpu venus;
gamescope 在 venus 上合成視窗會 abort,遊戲直接開在桌面上也會在 DXVK 初始化附近退出。
這些都發生在 VM 的虛擬 GPU 驅動裡,**不能**當成 Steam Deck(AMD)的結論。有 Deck 的人歡迎回報。

## NxOverlay 長時間穩定性(警告已降級)
遊戲內嵌的 NxOverlay(`DwarfAxe.exe`)需要 `VK_KHR_external_memory_win32`,**只有 Valve 的 wine 有實作**,
上游與 CrossOver 都沒有。本專案的 base 是上游 wine-10.16,所以沒有這個擴充。

先前記「沒有它約 20 分鐘後會凍住」。實際上用同樣沒有這個擴充的 CrossOver build 與本專案的 build(經 gamescope)
都**長時間遊玩沒有凍住或閃退**,所以這條警告降級為「未再重現」。
若你真的遇到凍住(log 出現 `VK_KHR_EXTERNAL_MEMORY_WIN32 not supported` 接著
`RtlpWaitForCriticalSection ... retrying (60 sec)`),匯入 `prefix/reg/dwarfaxe-wined3d.reg`
讓 NxOverlay 改走 wined3d,並回報 issue。

## beanfun 登入器 GUI 在 wine 下是黑的
WebView2 需要 DirectComposition,wine 沒有實作。本專案不處理那個 GUI 登入器;取 OTP 走 `tools/maple-login`
(純 HTTPS 就能做到,不需要 WebView)。

## 帳號風險
這是非官方環境。反作弊沒有被停用或繞過(見 README 的說明),但橘子 / Nexon 的服務條款怎麼看待「在 Linux 上跑」
不是本專案能保證的。**用自己的帳號、自己承擔。**

## 遊戲內打不出中文 —— ✅ 已修(2026-09-22/23,四個斷點,全部實測)
症狀分兩層:gamescope 裡連輸入法都切不了;直接在 X 上能切、fcitx 有候選窗,但選定的字進不了遊戲。
跟 wine base 無關(CrossOver 的 build 症狀相同)。修完之後:注音顯示在遊戲自己的輸入列、字正確送出、
候選窗出現在遊戲視窗**左上角**(見最後一條)。

斷點與修法,由外往內:

| # | 斷點 | 證據 | 修法 |
|---|---|---|---|
| 1 | gamescope 的巢狀 Xwayland 上**沒有 XIM server**(fcitx5 只註冊在桌面那個 display) | `DISPLAY=:2 xprop -root XIM_SERVERS` 沒有 atom;`:1` 是 `@server=fcitx` | `run.sh` 在 exec wine 前呼叫 fcitx5 的 DBus `OpenX11Connection $DISPLAY`。要在 wine 啟動前做:wine 只在視窗 FocusIn 時建 XIC,gamescope 裡焦點永遠不變 |
| 2 | 遊戲 **subclass 掉 Default IME 視窗**(換掉 wndproc,IME 訊息一律丟 DefWindowProc) | `+imm`:每筆 `post_ime_update` 後有 `handle_internal_message` 的 `get_default_ime_window`(內部訊息有被撈出來、也通過 parent 檢查),但 `__wine_ime_wnd_proc` 從 WM_ACTIVATEAPP 後再沒收過任何東西,取而代之是 DefWindowProc 的 WM_IME_NOTIFY 路徑 | `patches/0010`:win32u 把 wine 私有的 `IMN_WINE_SET_COMP_STRING` 直接 dispatch 到**內建** IME class wndproc,不經過視窗現在的 wndproc。Windows 上遊戲這樣做沒事,因為 Windows 的組字結果不經過那個視窗 |
| 3 | **wine bug**:IME UI 視窗 owned by 當時的 Default IME 視窗;遊戲砍掉 bootstrap 視窗時它跟著死,但 `imc->ui_hwnd` 沒清 | `+imm`:UI 視窗早早收到 WM_DESTROY,之後 `ime_ui_notify` 0 次 —— `__wine_ime_wnd_proc` 一直 SendMessage 到死 handle | `patches/0011`:imm32 `get_ime_ui_window()` 對 cache 的 handle 做 `IsWindow`,死了就重建。上游 10.16 同樣的碼 |
| 4 | **gamescope 只畫跟焦點視窗同 pid / 同 appid 的 override-redirect 視窗**(`is_good_override_candidate`),fcitx5 的候選窗永遠不會被畫 | 記事本實驗:fcitx5 在巢狀 display 上確實建了候選窗且 `IsViewable`;gamescope 原始碼那條 pid 檢查 | `patches/gamescope-0001`:ConVar `foreign_override_process_names`(預設 `fcitx5,ibus-daemon,ibus-ui-gtk3`),行程名符合的 override-redirect 視窗當 **decoration** 畫(只畫、不拿鍵盤焦點)。**不能放進 override slot**,理由見下一段 |

**打完中文後第一個鍵自己連發(2026-09-27 修)**:gamescope-0001 第一版是把 fcitx 的視窗放進 override slot,
而 gamescope 會把 Wayland 鍵盤焦點交給 override(`steamcompmgr.cpp` `keyboardFocusWindow = overrideWindow ? …`)。
fcitx 切中/英時跳出的提示框只 map 約 0.5 秒;這段時間按下的鍵,焦點切過去再切回來後,放開事件就丟了。
wine 因此以為那個鍵一直按著,0012 開了 server 端連發,於是變成自己連發。證據是在 winex11
`X11DRV_ProcessEvents` 的 `XFilterEvent` 前面暫時加的 trace:它記下了 X 讀進來的**每一個**按鍵事件,
包括被 XIM 過濾掉的,但那個鍵的 KeyRelease 一次都沒出現。所以不是 fcitx/XIM 吃掉的,是根本沒送到 wine 的 X 連線。
改成 decoration 後,提示框照樣看得到,按下/放開也成對了(實測)。
**先修錯的兩版(留作教訓)**:在 winex11 補送「被輸入法過濾掉的 release」—— 事件根本沒進 wine,補不到。
下次先用 trace 確認事件**有沒有進到那一層**,再去改那一層。

**之前寫在這裡的兩個假設都錯了**(留作教訓):「被 `ime_hwnd == GetParent(hwnd)` 丟掉」—— 實測主視窗與 Default IME
視窗的 owner/parent 全是 0,條件不成立;「遊戲的訊息迴圈過濾掉內部訊息」—— log 證明有撈出來。
真正的斷點在再下一站,而且是兩個疊在一起。

**候選窗為什麼在左上角**:遊戲從不呼叫 `ImmSetCompositionWindow`,wine 也只在 XIM `PreeditPosition` style
才送 `XNSpotLocation`(我們是 on-the-spot callbacks),fcitx5 拿不到座標就貼在焦點視窗原點。Windows 上這遊戲是
**自己畫候選字**(`IMN_OPENCANDIDATE` + `ImmGetCandidateList`),而 wine 的內建 IME 從 XIM 拿不到候選清單,
所以那條路做不到。要改位置只能改 wine(callbacks style 也送 spot)+ 猜遊戲聊天框座標,目前不值得。

**沒 gamescope 時**(`run.sh` 直接跑在桌面的 X 上):斷點 1 與 4 本來就不存在,只需要 0010 / 0011。

**工具**(不需要開遊戲,`tools/dev/imetest.py --help` 有全部選項):
```bash
source ~/.config/maplestory-tw/env.sh
tools/dev/imetest.py --ansi          # 扮成 ANSI wndproc(遊戲就是這條)
tools/dev/imetest.py --xim-trace     # 同時收 WINEDEBUG=+xim
```
`tools/dev/imeprobe.c` 是一個裸視窗(沒有 EDIT 子控制項、不主動呼叫 `Imm*`),形狀刻意做得跟遊戲一樣;
`tools/dev/imetest.py` 用 XTEST 自動打注音。**測 IME 不開遊戲,所以反作弊不在場**。
⚠️ probe **不會**重現斷點 2 與 3(它不 subclass IME 視窗、也不先開再砍一個視窗),所以「probe 通、遊戲不通」
是預期中的;要看遊戲的實況只能 `WINEDEBUG=fixme-all,err+all,+imm,+ime,+xim tools/gs-run.sh`(沒有 +relay,不碰反作弊)。

fcitx5 這邊需要 `~/.config/fcitx5/conf/xim.conf` 的 `UseOnTheSpot=True`(wine 要求 preedit callbacks 樣式,
組字序列才完整)。還原:`rm ~/.config/fcitx5/conf/xim.conf && fcitx5 -r -d`。

## 字糊 / 聊天室鋸齒:gamescope 非整數縮放(2026-09-27,不修)
活動視窗大字糊、聊天室字粗細不均。量使用者截圖:遊戲畫面實際顯示大小對遊戲解析度的比例是
1.134、1.19、0.93(視窗被拉大、或在 1080p 螢幕上被迫縮小),gamescope 用線性濾波縮放 → 糊;
非整數倍率讓 1px 筆畫變 1 或 2px → 鋸齒。字型檔 / FontSmoothing registry 在不同 wine build 的 prefix 間逐檔相同,不是字型問題。
KDE 的輸出縮放全是 1,不是 KWin 放大。

- 要清楚只有一個條件:**遊戲解析度 = gamescope 視窗實際大小(1:1)**。遊戲選單上限 = gamescope 內部解析度
  (`-W/-H`,或 `-w/-h`),預設 `-W 1920 -H 1080`;視窗被 KWin 或手動改了大小就又縮放。
- ⚠ **不要用 `-S integer`**:拍賣場等固定低解析度畫面不再被放大,貼在左上角留大片黑邊。

## 拍賣場被拉伸成 16:9 → `EmulateModeset`;1920 只能用視窗模式 + gamescope-0002/0003(2026-10-03)
症狀:進拍賣場(固定 1024×768)畫面被橫向拉滿,而不是左右補黑邊;內部解析度壓在 1366×768,遊戲選不到 1920×1080。

**拉伸的根因**:拍賣場用 D3D9 獨占全螢幕切模式(DXVK log `Setting display mode: 1024x768`)。winex11 把它
交給 gamescope 的 Xwayland(有 `XWAYLAND_FORCE_ENABLE_EXTRA_MODES` 的假模式),遊戲頂層視窗縮成 1024×768,
但 Vulkan 畫的那個子視窗還是整個輸出大小,DXVK 的 swapchain 跟著是 1366×768;gamescope 依 swapchain 大小縮放 → 滿版、變形。

**修法**:`HKCU\Software\Wine\X11 Driver` 的 `"EmulateModeset"="Y"`(上游 wine 本來就有,`prefix/reg/maplestory.reg`)。
wine 不真的切模式,改用虛擬模式:視窗在實體座標上等比縮放、置中,swapchain 是遊戲要的 1024×768,gamescope
照比例放、旁邊留黑。滑鼠座標由 win32u 換算回虛擬座標。

探針實測(`tools/dev/modetest.sh`,headless gamescope + D3D9,不開遊戲):

| 內部解析度 | EmulateModeset | 切 1024×768 的畫面 | 滑鼠 |
|---|---|---|---|
| 1366×768 | N(舊) | 1366×768,比例 1.779(拉伸) | — |
| 1366×768 | Y | 1024×768 置中,比例 1.333 | (683,384)→512,384 |
| 1920×1080 | Y | 1440×1080 置中,比例 1.333 | (960,540)→512,384;(240,0)→0,0 |
| 1920×1080 | Y,切 1280×1024 | 1346×1078 置中,比例 1.25 | (960,540)→640,512 |

真遊戲:登入正常(3/3);**進拍賣場未實測**。

### 為什麼預設還是 1366×768:遊戲「全螢幕」時登入畫面會卡死
**登入畫面固定 1366×768**,跟遊戲設定的解析度(`HKLM\Software\Wow6432Node\Wizet\MapleStory` 的
`soResolutionWidth/Height`)無關,選角進遊戲後才換成設定值。`soScreenMode` 0 = 全螢幕、1 = 視窗。

內部解析度 ≠ 1366×768 時,全螢幕的登入畫面一定要切到非原生模式。不管這個切換由誰做(wine 的 EmulateModeset 或
Xwayland 的假模式),主執行緒切完就停在 poll 不再前進,另一條遊戲執行緒滿載空轉等它(`/proc/<pid>/task/*/stat`,
跟「一定要經 gamescope」那節的連線中斷同一種),畫面全黑,約 45 秒後 `_ms_report.ini` 寫 `CONNECTION_FROM_LOGIN_CLOSED`。
2026-10-03 主 prefix 循序實測(到登入表單 = 第一條 :443 後撐 15 秒):

| 遊戲 | 內部解析度 | 其他 | 結果 |
|---|---|---|---|
| 全螢幕 | 1366×768 | EmulateModeset N / Y | 5/5、3/3 |
| 全螢幕 | 1920×1080 | EmulateModeset Y | 1/12 |
| 全螢幕 | 1920×1080 | EmulateModeset N | 0/4 |
| 全螢幕 | 1920×1080 | DXVK 限 60fps | 0/4 |
| 全螢幕 | 1920×1080 | 遊戲設定改 1920×1080(登入畫面照樣要 1368×768) | 0/2(其中一次跟 headless gamescope 測試重疊) |
| 全螢幕 | 1920×1080 | xrandr 補一個真的 1366 寬的模式(遊戲改要 1366×768) | 0/1 |
| **視窗** | 1920×1080 | EmulateModeset Y / N | **3/3、3/3** |

- 1920×1080 的 Xwayland 沒有 1366×768(只有 1368×768;`cvt 1366` 也會取整成 1368)。
- 三組多開並行測試會互相干擾(最後啟動的那組 1/6,舊設定也斷),量這種 race 要單開循序跑。

**要 1920×1080**:遊戲改成視窗模式、遊戲裡選 1920×1080。`tools/gs-run.sh` 沒給 `GS_ARGS` 時讀 `soScreenMode`:
視窗模式用 `-w 1920 -h 1080 -W <soResolutionWidth> -H <soResolutionHeight>`,全螢幕一律 1366×768,不會再組出「全螢幕 + 1920」。

nested(`-w/-h`)跟 output(`-W/-H`)要分開給(2026-10-09):遊戲選單的上限是 nested,畫面是不是 1:1 看 output。
原本只給 `-W/-H`(nested 跟著等於 output)= 拿遊戲上次選的解析度去限制這次能選的 —— 選過 1366 就只開 1366、選單裡沒有 1920,
永遠選不回去。gamescope 的縮放是 `(nested ÷ 視窗) × (output ÷ nested) = output ÷ 視窗`(`steamcompmgr.cpp` `calc_scale_factor_scaler`),
nested 約掉,所以 output = 遊戲解析度就是 1:1。遊戲裡換解析度的那一輪會縮放,重開就對。
探針(`PROBE_MODES="w1366x768:8 r1024x768:8 w1366x768:6" tools/dev/modetest.sh Y -w 1920 -h 1080 -W 1366 -H 768`):
1366 的 popup 沒被 gamescope 撐成 root 大小(client 一直 1366×768),拍賣場 1024×768 照比例置中。
headless 截圖是 nested 大小(`gamescopectl` 傳不了截圖種類),output 那張截不到,1:1 靠上面的公式。

### 視窗模式進拍賣場只畫在左上角 → patches/gamescope-0002 + 0003
進拍賣場時遊戲把 1920×1080 的 `WS_POPUP`(style `94080000`)換成可調整大小的 1032×802 視窗(style `14ce0000`,
client 1024×768)。wine(`+x11drv`)對已 map 的視窗,每送一個 `_NET_WM_STATE` / `_MOTIF_WM_HINTS` / configure 請求,
都要等 WM 的回應(屬性寫回、ConfigureNotify)才送下一個(`... is updating ..., delaying request`)。gamescope 兩種回應都缺:

1. **不寫回 `_NET_WM_STATE`**:只改自己的旗標。→ `gamescope-0002` 照 EWMH 寫回屬性。
2. **不回 no-op 的 ConfigureRequest**:登入畫面是 1366×768 popup,進遊戲放大成 1920×1080 時 gamescope 早已把它撐滿 root,
   wine 要 (0,0)-(1920,1080) 等於沒變,X server 不產生 ConfigureNotify,wine 永遠等著。→ `gamescope-0003` 照 ICCCM 4.1.5 補合成事件。

只有 0002 時,一開始就是 1920 的探針會好,但真遊戲(先 1366 再 1920)照樣卡在 2,所以兩個都要。
`GAMESCOPE_WSI_FORCE_BYPASS=1` 無效(不是 bypass 的問題)。

實測:探針重現遊戲的完整順序(1366 popup → 1920 popup → `14ce0000` 1032×802 → 回 1920 popup,D3D9 視窗模式):
修之前 X 視窗卡 1920×1080、畫面在左上角;修之後拍賣場 X 視窗 1024×768、gamescope 放成 1440×1080 置中,離開後回 1920×1080 滿版。
全螢幕切模式探針結果不變。真遊戲登入 視窗 1920 3/3、全螢幕 1366 3/3。
查遊戲視窗狀態用的是唯讀的 `GetWindowLong/GetWindowRect`(不送輸入);探針與查詢工具在 session scratch,沒進 repo。

## 鍵盤重複:修飾鍵在 X 下永遠不連發 → patch 0012 修(2026-09-27)
症狀:綁在 Shift / Ctrl / Alt 的技能按住只放一次;改綁一般鍵(J)就會連發。Windows / VM 沒這問題。

**根因在 X server,而且不是設定**(Xorg 與 Xwayland 同一份程式碼,這台是 Xwayland 24.1):
- soft repeat:`xkb/xkbActions.c` `_XkbFilterSetState()` 在修飾鍵初次按下時 `AccessXCancelRepeatKey()`,
  把剛啟動的 repeat 計時器取消 —— **per-key 位元開了也沒用**;
- 硬體 repeat:`dix/getevents.c` `GetKeyboardEvents()` 對 modmap 裡的鍵直接丟掉重複的 press
  (`/* ... or we have a modifier, don't generate a repeat event. */`)。
- 再加上 gamescope 的 SDL 後端丟掉所有上游 repeat(`SDLBackend.cpp` `if ( event.key.repeat ) break;`),
  連發只能由遊戲所在的 Xwayland(`:2`)自己產生,而它不會替修飾鍵產生。

實測(gamescope `:2`,被動 XI2 監聽):J 按 2.1s → 114 個 X repeat;左 Shift 按 1.9s → 0 個,
core 與 slave 鍵盤的 Shift repeat 位元都是開的。所以 ~~`xset r 50 62`~~(09-15 的結論)無效,
`:1` / `:2` 上怎麼 `xset` 都一樣。

**修法**:[patches/0012](../patches/0012-winex11-server-side-key-repeat.patch)。wineserver 本來就有
Windows 式的 auto-repeat(最後按下的鍵重複,速率讀 registry 的 KeyboardDelay/KeyboardSpeed),
上游只有 winewayland 會開;0012 讓 winex11 也開,並讓 server 丟掉 X 自己送的重複 keydown,
repeat 只剩一個來源。只影響遊戲的 wine,桌面設定一律不動。SendInput 不受影響。

keyrepeat-probe 驗證(獨立 prefix、gamescope 內、按住 2 秒):Shift / Ctrl / Alt / J 全部
500ms 後開始、每 12ms 一次;先按住 Shift 再按住 J → 換成 J 重複(同 Windows)。

限制:
- 速率是 wine 的換算:KeyboardSpeed=31 → 每 12ms(Windows 實際約 33ms)。之前 J 在 `:2` 上是 X 的
  300/62(約 16ms),遊戲吃得下。要調就改 prefix 的 `HKCU\Control Panel\Keyboard`。
- 一般鍵的速率從此由 wine 決定,**`xset r rate` 對遊戲不再有效**。

## 取得帳號 sid 與 OTP
遊戲登入表單的「帳號」要填 beanfun 的遊戲帳號 **sid**(`T9…` 那串),不是帳號名稱。
用 `tools/maple-login`:session 失效會自動帶你掃 QR,列出所有帳號與 sid,鑄一張新的 OTP,
把 sid 寫進剪貼簿;加 `--run` 會在印完的瞬間接著開遊戲(`tools/gs-run.sh`)。
session 存在 `$XDG_RUNTIME_DIR/maplestory-tw/session.json`(tmpfs、0600),**重開機就沒了**
—— 那是刻意的,裡面的 bfWebToken 等同登入憑證。協定細節見
[how-it-works.md §11](how-it-works.md#11-取得-otptoolsmaple-login)。
