# maplestory-tw-linux

讓**台版新楓之谷**(beanfun / 橘子)在 Linux 上跑起來的 wine runner + prefix 配方。

**狀態(2026-09-27)**:✅ **可以玩**。上游 wine-10.16 + `patches/`,經 gamescope 啟動:
登入、進遊戲、長時間遊玩、遊戲內打中文、修飾鍵技能按住連發都實測過。

| 啟動方式 | 到登入畫面 |
|---|---|
| **`tools/gs-run.sh`**(gamescope,`maple` 預設就是這條) | ✅ 10/10 |
| `run.sh` 直接跑在桌面上 | ⚠️ 1/7,常常「與登入伺服器連線中斷」 |

所以**請一律經 gamescope 啟動**,理由見 [docs/known-issues.md](docs/known-issues.md)。

## 這是什麼 / 不是什麼
- ✅ 一個依上游 wine(`10.16` release tarball)加一組小 patch 建出來的 WoW64 wine runner,
  和一支把 prefix 建對(code page 950、登錄檔、DXVK、VC++ runtime、字型)的腳本。
- ✅ 每一個設定背後的理由都寫在 [docs/how-it-works.md](docs/how-it-works.md);已知問題在 [docs/known-issues.md](docs/known-issues.md)。
- ✅ **帳號 sid + OTP**:`tools/maple-login` 一個命令搞定 —— 掃一次 QR、之後直接鑄新的 OTP。
  多個遊戲帳號會列出來讓你挑;**遊戲開著就直接把帳號與 OTP 填進登入表單**,沒開就把 sid / OTP
  分兩段送進剪貼簿。只要 session 活著就會裝一個 systemd user timer 每 10 分鐘保活,省得一直重掃 QR。
  OTP 協定的作法參考自 [pungin/Beanfun](https://github.com/pungin/Beanfun)(第三方 beanfun 客戶端);
  本專案照它的協定行為以 Python 重寫,未複製其原始碼,細節見
  [docs/how-it-works.md §11](docs/how-it-works.md)。
- ❌ **不處理遊戲下載 / 安裝**(v0.1)。你需要一份現成的 MapleStory 目錄。
- ❌ 不含任何遊戲檔、微軟字型、微軟 DLL、橘子的程式。
- ❌ **不提供、也不接受任何遊戲內自動化**(巨集、自動戰鬥、外掛類功能)。唯一會對遊戲送輸入的是
  登入表單的自動填入,跟你自己貼上帳號與 OTP 是同一件事。

## 關於反作弊 —— 請先讀這段
本專案**沒有停用、沒有繞過** BlackCipher / NGS。它們全程照常運行、照常做所有檢查。

唯一跟反作弊有關的改動是 `patches/0001`:BlackCipher 會把幾個系統 DLL 複製到 `%TEMP%\*.tmp` 再載入,
用來跟記憶體裡的比對。wine 的 DLL 結構跟 Windows 不同,直接比一定不同。這個 patch 讓 `LoadLibrary(那個 .tmp)`
回傳它原本就要比對的那個模組 —— 這**正是 Nexon 官方 macOS 版自己出貨的做法**(程式碼來自 Nexon 依 LGPL
公開的 CrossOver 原始碼樹)。NGS 拿到它要的東西,然後繼續跑它自己的所有檢查。細節:[docs/how-it-works.md §2](docs/how-it-works.md)。

即便如此,這仍是**非官方環境**。橘子 / Nexon 的服務條款怎麼看待它,本專案無法保證。用自己的帳號,自己承擔。
本專案也不會接受任何「讓反作弊失效」方向的貢獻。

## 需求
- Linux x86_64,有 Vulkan 的 GPU 驅動(實測:NVIDIA 595;AMD / Intel 未測)
- **gamescope**(Ubuntu 26.04:`sudo apt install gamescope`;要看得到中文輸入法候選窗得用 `build/build-gamescope.sh` 自己編,見 [how-it-works §13](docs/how-it-works.md))
- 系統有 `zh_TW.UTF-8` locale(`sudo locale-gen zh_TW.UTF-8`)
- `winetricks`(裝 VC++ 2022 runtime 用)
- Python 3 + `requests` + `cryptography`(`tools/maple-login` 用;Ubuntu:`sudo apt install python3-requests python3-cryptography`)
- `mingw-w64`(`tools/maple-login` 第一次跑會自己編填表單用的 `tools/mapletype.exe`)
- 一份現成的 MapleStory 目錄(含 `MapleStory.exe`、`Patcher.exe`)
- 選用:一份 Windows 的 `C:\Windows\Fonts`(至少 `mingliu.ttc`),沒有的話字會糊
- 一支 beanfun 手機 App(`tools/maple-login` 第一次要掃 QR 登入)

## 快速開始
```bash
# 1. runner:從 Releases 下載 maplestory-tw-wine-*.tar.xz 解開(WINE_ROOT 指向解出來的目錄),
#    或自己 build(見下):
build/build-wine.sh                      # 產出在 ~/.local/share/maplestory-tw/build/out

# 2. 設路徑(tools/ 底下的指令會自己載這個檔)
mkdir -p ~/.config/maplestory-tw
cp env.example ~/.config/maplestory-tw/env.sh && $EDITOR ~/.config/maplestory-tw/env.sh

# 3. 建 prefix(可重複執行)
source ~/.config/maplestory-tw/env.sh && prefix/setup-prefix.sh

# 4. 開遊戲 → 等登入表單出現 → 鑄 OTP 填進去
ln -sf "$PWD/tools/maple" ~/.local/bin/maple
maple
```
`maple` = 開遊戲(gamescope)→ 等登入表單、鑄 OTP 打進去;`maple game` / `login` / `stop` / `status` 拆開用,
`maple help` 看全部。第一次用建議 `maple login --no-submit`,確認兩欄都對了再自己按登入(OTP 打錯要整個重開遊戲)。

多開:`maple -2 setup` 建一次第 2 組,之後 `maple -2` 就是第 2 組(`-2`~`-9`),見 [known-issues「多開」](docs/known-issues.md)。

全螢幕 / 改解析度:`GS_ARGS="-W 1366 -H 768 -f" maple game`。為什麼預設是 1366×768、
為什麼不要用 `-S integer`:[known-issues「字糊 / 聊天室鋸齒」](docs/known-issues.md)。

用 Lutris / Heroic 的話:執行檔設成 `tools/gs-run.sh`(不是 wine 本身),環境變數照 `env.sh` 填。

### 檔案放哪
repo 只放腳本、patch、文件;大檔預設在 `~/.local/share/maplestory-tw/`:
```
~/.local/share/maplestory-tw/build/   build/build-wine.sh 的 build 目錄(out/ = wine runner)
~/.config/maplestory-tw/env.sh        WINE_ROOT / WINEPREFIX / GAME_DIR / FONTS_DIR(從 env.example 複製)
~/.cache/maplestory-tw/               每次開遊戲的 log
$XDG_RUNTIME_DIR/maplestory-tw/       beanfun session(tmpfs,重開機就消失 —— 刻意的)
```

## 自己 build
```bash
build/build-wine.sh                      # BUILD_DIR=… JOBS=… 可覆寫
```
build 依賴(Ubuntu 24.04 / 26.04 實測;其他發行版對應同名套件):
```
sudo apt install build-essential bison flex pkg-config python3 perl mingw-w64 curl xz-utils \
  libx11-dev libxext-dev libxrandr-dev libxi-dev libxcursor-dev libxrender-dev libxfixes-dev \
  libxcomposite-dev libxinerama-dev libfreetype-dev libfontconfig-dev libvulkan-dev libgnutls28-dev \
  libasound2-dev libpulse-dev libgl-dev libegl-dev libudev-dev libunwind-dev libglib2.0-dev libsdl2-dev
```
腳本會從 `dl.winehq.org` 下載上游的 wine release tarball(版本釘在 `build/WINE_VERSION`、
sha256 釘在 `build/WINE_SHA256`,下載後一定校驗)、用 `patch -p1 -F0` 套 `patches/`、
以 `--enable-archs=i386,x86_64` 編、放進 GE-Proton 的 DXVK / vkd3d-proton(版本釘在 `build/GE_PROTON_VERSION`),
打成 tarball。tarball 裡附 patch 與 base 版本 + sha256(LGPL 義務)。
原始碼樹與 `obj/` 每次重跑都會重建,所以這支腳本可以無狀態地重複執行。

Releases 上的 tarball 就是這支腳本在 GitHub Actions(ubuntu-24.04)上跑出來的:推 `v*` tag 會觸發
[`.github/workflows/release.yml`](.github/workflows/release.yml),build 完連同 `SHA256SUMS` 掛到該版的 Release。
在 Actions 頁手動 Run workflow 則只 build、不發版,產物放在 workflow artifact。

## patches/
| | 檔案 | 用途 | 上游? |
|---|---|---|---|
| 0001 | `kernelbase` `.msf` sidecar | BlackCipher 乾淨複本比對(沒有它就黑畫面;每輪產生 8 個 `.msf`、一個 `.tmp` 都沒有) | 遊戲專屬,不送 |
| 0002 | `kernelbase` `CreateFileA("ws2_32.dll")` 重導向 | 同上,BlackCipher 用裸檔名開 ws2_32 | 遊戲專屬,不送 |
| 0003 | `win32u` GASP 在有次像素能力的系統上也生效 | 字型:新細明體的 1-bit 點陣 strike 才會被用 | **通用 bug,待送** |
| 0004 | `win32u` 點陣基礎字型不做抗鋸齒 | 字型:不污染 font-link 鏈的 aa_flags | **通用 bug,待送** |
| 0005 | `kernelbase` `CharPrevExA` NULL 解參考 | `CharPrevExA(950, NULL, NULL, 0)` 會炸;上游 11.17 已修,本 base(10.16)仍需要 | 上游已修 |
| 0007 | `ntdll` 新執行緒堆疊清零 960KB(10.0 的值;10.16 是 60KB) | **未證實有效**,診斷時留下的候選 | 不送 |
| 0008 | `winex11` 每-app 關掉 `_NET_ACTIVE_WINDOW` 請求 | 不經 gamescope 時遊戲每幾秒把桌面焦點搶回去;鍵設在 `AppDefaults\<exe>\X11 Driver`,預設維持上游行為(實測 28/30 → **0/30**) | 通用機制,可考慮送上游 |
| 0009 | `win32u` 純水平縮放時保留點陣 strike 並自己壓縮 | 字型:遊戲九成的字送 `System h=16 w=7`,wine 只要有縮放矩陣就丟掉內嵌點陣、改走外框,筆畫斷裂。對 Windows 實測墨水像素 1700 → **2003**(Windows 1986),advance 一致。細節 [how-it-works §7](docs/how-it-works.md) | **通用 bug,待送** |
| 0010 | `win32u` IME 通知繞過被 subclass 的 IME 視窗 | 遊戲內打中文(遊戲換掉了 Default IME 視窗的 wndproc) | 可考慮送上游 |
| 0011 | `imm32` IME UI 視窗隨 owner 死掉後重建 | 遊戲內打中文(wine bug:`imc->ui_hwnd` 指向死 handle) | **通用 bug,待送** |
| 0012 | `winex11` 由 wineserver 做 Windows 式 auto-repeat | 綁在 Shift / Ctrl / Alt 的技能按住會連發(X server 寫死修飾鍵不 repeat) | 可考慮送上游 |
| gamescope-0001 | gamescope 畫輸入法的 override-redirect 視窗 | 中文輸入法候選窗(選用,`build/build-gamescope.sh`) | gamescope,可考慮送 |

## 不做的事
- 不停用、不繞過、不「調整」反作弊;不在反作弊活著時掛除錯器
- 不做任何遊戲內自動化
- 不散布任何專有檔案
- 不做 Steam compatibilitytool(經 `proton` 腳本啟動會秒死,見 known-issues)

## 授權
LGPL-2.1-or-later(與 wine 相同)。patch 是對 wine 的修改,本來就必須如此;其餘腳本與文件一併採用同一授權。

## 致謝
- **CodeWeavers / CrossOver** 與 **Nexon**:Nexon 官方 macOS 版建在 CrossOver 之上,並依 LGPL 公開了那棵 wine
  原始碼樹。`patches/0001`、`0002` 的作法直接來自那裡;開發初期也是以那棵樹自建的 wine 當「能玩」的對照組,
  才一路把問題縮小到今天這一組小 patch。沒有 CrossOver 的工作,這個專案不會存在。
- **WineHQ** 與所有 wine 開發者:本專案的 base 就是上游 wine。
- [DXVK](https://github.com/doitsujin/dxvk)、[vkd3d-proton](https://github.com/HansKristian-Work/vkd3d-proton)
  (取自 [GE-Proton](https://github.com/GloriousEggroll/proton-ge-custom) 的建置)、
  [gamescope](https://github.com/ValveSoftware/gamescope)。
- `prefix/reg/maplestory.reg` 源自 [umu-protonfixes](https://github.com/Open-Wine-Components/umu-protonfixes)
  對 GMS 的修正與 [oldschoola/linux_maplestory](https://github.com/oldschoola/linux_maplestory)。
- OTP 流程(`tools/beanfun/bfotp.py`、`tools/maple-login`)的協定作法來自
  [pungin/Beanfun](https://github.com/pungin/Beanfun) —— 感謝原作者把 beanfun 的登入 / OTP
  流程摸清楚。本專案是照其協定行為重寫,未複製原始碼。該專案本身未附授權條款,
  若原作者對此處的引用方式有任何意見,歡迎開 issue。
