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
  hardlink 需要跟主遊戲目錄在同一個檔案系統;不同的話把 `MAPLE_DATA` 設到同一顆碟上(設在登入環境;已經裝好的,
  `env.sh` 的 `WINE_ROOT` / `WINEPREFIX` 也要改過去、舊的 `runners/`、`prefix/` 搬過去,對不上 `maple update` 會擋下來說)。
- 寫 `~/.config/maplestory-tw/env-N.sh`(沿用主設定,只換 `WINEPREFIX` 與 `GAME_DIR`),跑 `setup-prefix.sh` 建全新 prefix。

隔離:prefix 不同 = wineserver 不同,兩組互相看不到對方的行程與 mutex;`maple -N` 只看、只關自己那組的行程;
自動登入只會填進自己那組(`mapletype.exe` 只連得到那組的 wineserver);「上次選的帳號」每組各記各的(`prefs-N.json`)。
wine 本身可以共用。

主目錄更新後(不論是 cmsdl 還是 `Patcher.exe` 更新的),`maple -N` 開遊戲前會發現第 N 組跟主目錄不一致
(`MapleStory.exe` 內容不同,或 `Data/Base/Base.wz` 不是同一個 inode),自動重建那組的遊戲目錄:
截圖搬過去、log 丟掉、prefix 不動(遊戲設定在 prefix 的登錄檔裡)。

⚠ 不要在第 N 組裡讓 `Patcher.exe` 更新:它改的 `Data/` 是跟主目錄共用的 hardlink。
主目錄先更新好(`maple` 開第 1 組),第 N 組自然跟上。

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

## 遊戲下載與更新(cmsdl)
`maple install` 用 [cmsdl](https://github.com/HikariCalyx/cmsdl) 把整份遊戲(約 70GB)下載到 `GAME_DIR`;
只接受不存在、空的、或上次沒下完(有 `.incomplete_tms` / `Data/.incomplete`)的目錄。
從 Windows 複製過來的目錄也照樣能用。橘子官方安裝程式在 wine 下**沒測過**。

`maple` 開遊戲前會查版本(cmsdl `--upgrade-path-check`,只抓 273 bytes 的 `Base.wz`)與
`MapleStory.exe` 熱修補(CDN 上 `ExePatch.dat` 的大小 vs 本機),有一項對不上才跑 `cmsdl --patch latest`。
不直接每次跑 `--patch latest`:版本已是最新時它仍會重下 177MB 的 `ExePatch.dat`(cmsdl v0.2.9)。

不做「修復」:cmsdl 修復壞檔是原地改寫,會連多開組共用的 hardlink 一起改。同理,任何一組在跑時不更新主目錄。
cmsdl 查不到、更新失敗時照開遊戲,遊戲版本舊了會自己叫 `Patcher.exe`(慢,但能用)。

2026-10-27/28 實測(cmsdl v0.2.9):`maple install` 從零下載 69G 約 3 小時 → 全新 prefix → 登入到選伺服器畫面;
開遊戲前偵測到新的 `ExePatch.dat` 並自動套用;V283 主目錄判斷為最新;第 2 組自動重建成功。
**還沒實測**:大版本更新的 patch 鏈(例如 V283 → V284)—— 下次改版時驗。

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
export PATH=~/.local/bin:$PATH      # 然後 maple setup(不是 maple update:已是最新版時它不會重跑 setup)
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
**只支援 fcitx5**:斷點 1 的修法是 fcitx5 的 DBus 介面;IBus 沒有對應的「接上另一個 X display」,在 gamescope 裡打不了中文
(沒測過、也沒做)。沒有 fcitx5 時 `run.sh` 會印一行提示。

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

### 瞬移石按 Enter,到新地圖聊天框自己彈出來(MC-20,2026-11-14)
症狀:瞬移石用 Enter 確認換圖,到了新地圖聊天輸入框自己彈出來、拿走焦點(偶發);滑鼠點、傳送點按「上」都不會,Windows 不會。

**根因在 0012**:server 要等遊戲執行緒處理到 KeyRelease 才知道鍵放開了,而 winex11 只在那條執行緒抽訊息時才處理 X 事件。
遊戲收到 Enter 就開始換圖,主執行緒一秒以上不抽訊息;server 以為 Enter 還按著,500ms 後開始每 12ms 排連發 keydown,
TranslateMessage 把每個都變成 `'\r'`,載完圖聊天框就開了。Windows 上放開是系統的輸入執行緒即時處理的,跟應用程式忙不忙無關。

證據:XI2 被動監聽看到 X 只有一次 press / release(輕點 50ms 也中);`WINEDEBUG=+key` 看到放開之後遊戲又
TranslateMessage 一個 `VK_RETURN scancode 401c`(bit 30 = 前一次狀態按下),換圖 10 次有 9 次。

**修法**(併入 0012):server 沒辦法提早知道鍵放開了,所以改成「放開一到,就把多排的連發收回來」:
- winex11 一讀到 KeyRelease(送進輸入法**之前**)就通知 server(`SEND_HWMSG_KEY_RELEASED`):停掉那個鍵的連發,
  並把佇列裡還沒被執行緒取走的連發 keydown 移掉。不產生訊息、不動按鍵狀態。
- 真正的 key-up 到 server 時也做同樣的清除(給不送通知的 driver)。

win32u 的 PeekMessage / GetMessage 會先處理 X 事件再去 server 拿訊息(節流:每 125µs 最多一次),所以執行緒拿不到「放開之後」才排的連發。
連發的節奏(500ms 後每 12ms、最後按的鍵連發)完全沒動。

遊戲內確認(2026-11-15,`WINEDEBUG=+timestamp,+key,+rawinput`):瞬移石 Enter 換圖 16 次,`VK_RETURN 401c` 0 次、聊天框沒再跳;
按住 Z / Shift 共 13 段,第 1→2 下 500~507ms,之後平均 12.0~12.6ms。遊戲有註冊 rawinput 鍵盤(usage 6,`RIDEV_INPUTSINK`),
幽靈連發的 `WM_INPUT` 沒有造成可見問題。第 1→2 下的 500ms 是 `KeyboardDelay=1`(Windows 預設值),要短就把它設成 0(250ms)。

`tools/dev/busykey-probe.c` 實測(Xvfb,盡量像遊戲:X 連發 600/25、接 fcitx5 XIM、每 16ms 抽一次訊息、
收到 keydown 後 1500ms 不抽訊息;xdotool 輕點 Enter 5~800ms):

| | 輕點後多收到的連發 | 按住 J 2 秒 | 按住右鍵再按住 Shift 1.5 秒 |
|---|---|---|---|
| 修之前 | 83~84 個,每個一個 `'\r'` | 128 | Shift 84 |
| 修之後 | **0**(21 次,有/無 XIM、兩種忙法) | 124 | Shift 83 |

少掉的那幾個是「放開之後、處理到放開之前」排的。Enter 一路按到忙完之後才放:連發照常持續到放開為止。

**修錯的兩版(留作教訓)**,都是在遊戲裡被打回來的(第 1 版的證據是遊戲的 `+key` trace,第 2 版事後用同一支探針離線重現):
1. *server 只連發修飾鍵,一般鍵還給 X*:聊天框好了,但 X 對按住的方向鍵的連發會一直把 Shift 的連發取消(trace:按著右鍵再按住 Shift,Shift 一次都沒連發),
   一般鍵退回 X 的 600 / 40ms,技能連發變卡。
2. *連發前先看執行緒的 X 連線有沒有沒讀的資料,有就跳過這一拍*:兩頭都錯。載入時只要重畫(`UpdateWindow` → `QS_PAINT`),
   Xlib 就把 socket 讀空、KeyRelease 留在它自己的記憶體佇列裡沒處理,檢查看不到(84 個幽靈連發照舊);
   而平常按住時 X 自己的連發事件讓 socket 多半是可讀的,連發被跳掉一堆(J 127 → 89,按著右鍵的 Shift 85 → 45)。

教訓:第一版探針每 1ms 抽一次訊息、忙的時候只 `Sleep`、沒接 XIM —— 三個地方都不像遊戲,所以兩個錯的修法都「驗證通過」。
第三版(只在 key-up 清除)也是接上 XIM 才量出還會漏 3~10 個:KeyRelease 被送去 fcitx 再轉回來的那 1ms 內,執行緒已經先拿走幾個連發。

已知限制:幽靈連發在被收回之前,已經送給 rawinput(`WM_INPUT`)與 low-level keyboard hook 了(0012 一直都是這樣);
`GetAsyncKeyState` 在執行緒處理到放開之前仍回報按著(上游 winex11 本來就是)。

## 手把預設關閉:要用就設 `MAPLE_GAMEPAD=1`(2026-11-19)
wine 的 winebus 用 SDL / hidraw / evdev **直接開 `/dev` 底下的手把**,不經過 gamescope。
鍵盤走 X 事件,gamescope 只轉給有焦點的視窗;手把沒有這層,而且 gamescope 裡只有遊戲一個視窗,
wine 永遠認為它在前景(遊戲用 `DISCL_FOREGROUND` 也擋不住)。結果:切到別的視窗玩手把,楓之谷裡的角色照樣動。

另一個同源的坑:主機板 RGB(實測 ASRock LED Controller `26ce:01a2`)這類 HID 描述寫得亂的裝置
會被當成搖桿,它從不送資料,hat 停在 0 = 北 → 遊戲裡「上」一直被按住,kernel 和 wine 的鍵盤狀態卻都查不到。

所以 `run.sh` 每次啟動前把這個 prefix 的 winebus 三個後端設成關
(`HKLM\System\CurrentControlSet\Services\winebus`:`Enable SDL`=0、`DisableHidraw`=1、`DisableInput`=1),
遊戲看不到任何手把。只影響遊戲的 prefix,桌面上其他程式的手把照常。
要在遊戲裡用手把:`~/.config/maplestory-tw/env.sh` 加 `export MAPLE_GAMEPAD=1`,下次開遊戲生效
(winebus 只在 wineserver 啟動時讀設定,值有變時 `run.sh` 會先寫入、等 wineserver 退出再開遊戲;多開組各自套用)。
開了之後背景亂動與假搖桿的問題會回來,假搖桿可以改在 `HKCU\Software\Wine\DirectInput\Joysticks`
把它的名稱設成 `"disabled"`。

## 間歇卡頓、畫面忽快忽慢:kernel 的 split lock 懲罰 → `kernel.split_lock_mitigate=0`(2026-10-23)
症狀:同一個場景有時順有時卡,打王時特別明顯;MangoHud 看平均幀率不低,但 1% low 很差。

**根因**:遊戲行程裡的反作弊模組(NGS,`NGClient64.aes` 載入的那段程式碼)每 ~30ms 在**遊戲主執行緒**
做一次跨 cache line 的 lock 指令(split lock)。Windows 不管這個;Linux 在支援 split lock 偵測的 CPU 上
(Intel 較新的 CPU,12 代桌機起都有)預設 `kernel.split_lock_mitigate=1`,每抓到一次就**故意讓該執行緒睡 10ms**
(`arch/x86/kernel/cpu/bus_lock.c` `split_lock_warn()` 的 "misery factor")。

實測(i7-14700F,kernel 7.0,站著不動的場景):主執行緒每 29ms 被睡 10-12ms 一次 = **33 次/秒,36% 的時間在睡**;
DXVK 送幀變成「2ms 一張連發 6-8 張,然後停 16ms」。dmesg 只在每個行程第一次時印一行,看起來不嚴重,其實每次都在罰:

    x86/split lock detection: #AC: MapleStory.exe/2074273 took a split_lock trap at address: 0x7ba3e139

同樣間隔的 split lock 用 10 行 C 重現:每次 11-15ms。

**修法**(需要 root,立刻生效,遊戲不必重開):
```bash
sudo sysctl kernel.split_lock_mitigate=0                                    # 這次開機
echo 'kernel.split_lock_mitigate = 0' | sudo tee /etc/sysctl.d/99-split-lock.conf  # 永久
```
`=0` 只是不罰睡,偵測與 dmesg 警告照舊。SteamOS 等遊戲向發行版預設就關;Proton 上的遊戲遇到的是同一件事。
`run.sh` 啟動時若看到 `=1` 會印警告。

修好之後也重測過把整個 prefix 綁在 P-core(大小核 CPU 上的常見建議):三輪交錯各 60 秒,p99 6.8 → 6.5ms,
感覺不出來,所以 `run.sh` 不綁(P-core 少的筆電綁了反而可能更慢)。想綁自己 `taskset -c <P-core> maple`。

## 開機太久:選角後卡「伺服器連線中」→ `maple-timens`(2026-11-20,MC-27)

症狀:登入、選角畫面都正常,按「遊戲開始」後一直轉「伺服器連線中」。登入伺服器(8484)的連線還在,也會 ACK,但不再回任何資料;遊戲也不會去連頻道伺服器。

原因:電腦開機超過 2^31 ms(24 天 20.5 小時)。wine 的 `GetTickCount` 是 `CLOCK_MONOTONIC`(開機到現在)換算成毫秒,遊戲把它當 32 位元有號數用,超過就變成負的。已實測:用 time namespace 讓遊戲以為開機 25 天,一定會卡;歸零就正常。

處理:`gs-run.sh` 透過 `tools/maple-timens` 啟動 `run.sh`,用 user + time namespace 讓 wine 看到的開機時間從 0 開始算。只動 monotonic / boottime 兩個時鐘,牆上時鐘(`CLOCK_REALTIME`)跟外面完全一樣。之後才從外面啟動的 wine 行程(例如 `maple-login` 的 mapletype)用 `maple-timens --prefix "$WINEPREFIX" …` 加入同一個 namespace:wine client 會用自己的開機時間算等待的截止時間,再交給 wineserver 比較。

- Ubuntu 23.10 起預設不准一般程式建 user namespace。套件安裝時會把 `/etc/apparmor.d/maple-cask` 放進去並載入,只放行 `/usr/share/maple-cask/tools/maple-timens` 這一支(寫法跟系統附的 steam 規則一樣)。它 exec 遊戲前會切回一般的 unconfined,所以遊戲和它的子行程不會繼承這個權限。AppArmor 太舊、解析不了這份規則(Debian 12 / Ubuntu 22.04)就不放;那些版本本來就沒有這個限制。
- 建不了 namespace(git clone 直接跑、AppArmor 規則沒載入、kernel < 5.6)就照原樣啟動,遊戲照樣能玩;開機超過 23.8 天時 `run.sh` 會警告,重開機就好。
- 加入既有的 namespace 不需要 AppArmor 放行,任何同一個使用者的行程都能做。

## VRAM:一個 client 約 1.6-2 GB;顯卡小又要同時跑別的遊戲,可以限制在 1 GB(選用,2026-11-15,MC-28)

楓之谷畫面走 **D3D11**(DXVK log 只有 `D3D11InternalCreateDevice`,沒建任何 D3D9 裝置),所以網路上常見的
`d3d9.*` 設定(`d3d9.textureMemory` 只對 32 位元有效、`d3d9.maxAvailableMemory` 只改回報值)都沒作用。

實測(i7-14700F、RTX 3070 Ti 8 GB、NVIDIA 595.99.02、DXVK 3.1,1920×1080,開遊戲約 2 分鐘後讀 `dxvk.hud = memory` 與 `nvidia-smi`):

| 設定 | nvidia-smi | DXVK 配置 / 實際使用 | 搬到系統記憶體 |
|---|---|---|---|
| 預設 | 1594 MiB(連換多張地圖後 1982) | 1517 / 1259 MB | 0 |
| `dxgi.maxDeviceMemory = 2048` | 1420 MiB | 1341 / 1214 MB | 0 |
| `dxvk.maxMemoryBudget = 1024` | 1146 MiB | 1069 / 1068 MB | 671 MB |

- 畫面緩衝(1920×1080 × 4 張)約 33 MB、gamescope 約 50 MiB、NxOverlay 約 35 MiB,幾乎全部都是遊戲自己載的貼圖。
- 換地圖會往上加幾百 MB,之後會回落,沒有一直漲。
- `dxgi.maxDeviceMemory`(騙遊戲顯卡比較小)**沒效**:遊戲不看這個數字決定要載多少。
- `dxvk.maxMemoryBudget` 是硬上限,超出的貼圖由 DXVK 搬到系統記憶體。楓之谷是 2D、GPU 很閒(實測 12-34% 使用率),
  所以**幀率感覺不出差別**,只有過圖偶爾慢一點。連用兩週沒有問題。

**什麼時候值得開**:8 GB 以下的獨立顯卡,又會跟別的 3D 遊戲(或 AI 繪圖之類吃 VRAM 的程式)同時跑。
實測上 VRAM 滿的時候 NVIDIA 驅動(595.99)會讓之後的配置直接失敗(`vkAllocateMemory` 回 `VK_ERROR_OUT_OF_DEVICE_MEMORY`、
dmesg 出現 `Failed to allocate NVKMS memory`),不像 Windows 那樣換頁到系統記憶體;
gamescope 遇到配置失敗會直接 abort,遊戲跟著被關掉(MC-26)。這個上限只管遊戲裡的 DXVK,管不到 gamescope 自己。

**怎麼開**:`~/.config/maplestory-tw/env.sh` 加一行,下次開遊戲生效:
```bash
export DXVK_CONFIG="dxvk.maxMemoryBudget = 1024"
```
(要看實際用量就改成 `"dxvk.maxMemoryBudget = 1024; dxvk.hud = memory"`,畫面左上角會顯示。)

**為什麼不是預設**:DXVK 文件把這個選項標成除錯用,警告「效能會嚴重下降」。2D 的楓之谷剛好不受影響,
但 VRAM 夠大的人只會白白多一點過圖延遲,系統記憶體少的機器還要多吃幾百 MB RAM(遊戲本身已經吃 7 GB 左右)。
AMD / Intel 獨顯沒測過;內顯(包括 Steam Deck)上 DXVK 不執行這個限制,設了也沒差別。
不設的話,DXVK 也會在驅動回報的預算不夠時自己把少用的貼圖搬出去,只是要等到超過預算才動作。

## 取得帳號 sid 與 OTP
遊戲登入表單的「帳號」要填 beanfun 的遊戲帳號 **sid**(`T9…` 那串),不是帳號名稱。
用 `tools/maple-login`:session 失效會自動帶你掃 QR,列出所有帳號與 sid,鑄一張新的 OTP,
把 sid 寫進剪貼簿;加 `--run` 會在印完的瞬間接著開遊戲(`tools/gs-run.sh`)。
session 存在 `$XDG_RUNTIME_DIR/maplestory-tw/session.json`(tmpfs、0600),**重開機就沒了**
—— 那是刻意的,裡面的 bfWebToken 等同登入憑證。協定細節見
[how-it-works.md §11](how-it-works.md#11-取得-otptoolsmaple-login)。
