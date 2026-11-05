<img src="assets/icon.svg" width="128" align="right" alt="">

# MapleCask

maple-cask(楓木桶)—— 台版新楓之谷 in Linux。

## 關於反作弊與帳號
- 本專案**沒有停用、沒有繞過** BlackCipher / NGS,它們全程照常運作。唯一相關的 patch 做的事,
  跟 Nexon 官方 macOS 版自己出貨的作法相同([細節](docs/how-it-works.md))。也不接受任何「讓反作弊失效」方向的貢獻。
- **不提供、也不接受任何遊戲內自動化**(巨集、自動戰鬥、外掛類功能)。唯一會對遊戲送輸入的是登入表單的自動填入,
  跟你自己貼上帳號與 OTP 是同一件事。
- 這仍是**非官方環境**,橘子 / Nexon 的服務條款怎麼看待它,本專案無法保證。用自己的帳號,自己承擔。

## 需求
- Linux x86_64,有 Vulkan 的 GPU 驅動(實測 NVIDIA;AMD / Intel 未測)
- `zh_TW.UTF-8` locale。Ubuntu:
  ```bash
  sudo locale-gen zh_TW.UTF-8
  ```
  Debian 與 Arch / CachyOS 等 Arch 系的 `locale-gen` 不吃參數(照上面打會「成功」但什麼都沒生),要先在 `/etc/locale.gen` 打開那一行:
  ```bash
  sudo sed -i 's/^# *zh_TW.UTF-8 UTF-8/zh_TW.UTF-8 UTF-8/' /etc/locale.gen && sudo locale-gen
  locale -a | grep -i zh_TW     # 有 zh_TW.utf8 才算數
  ```
- 遊戲本體(約 70GB):已經有現成的目錄,第一次開 `maple` 時告訴它路徑;沒有的話 `maple` 會問要不要用
  [cmsdl](https://github.com/HikariCalyx/cmsdl) 從橘子的 CDN 下載(中斷了重跑會接著下)
- 一支 beanfun 手機 App（QR 登入與 passkey 註冊時的備用驗證）
- 選用 passkey 自動重登：Chromium 系瀏覽器、`secret-tool` 與 `gdbus`（Ubuntu：`sudo apt install libsecret-tools libglib2.0-bin`）與已解鎖的 Secret Service/KWallet。`Xvfb` 選用（`sudo apt install xvfb`）；沒有就開可見視窗。不需要 `websocket-client`，缺少 passkey 依賴仍可 QR。
  ```bash
  tools/maple-login passkey-setup # 使用者在新視窗登入並新增專用 passkey，不沿用 Bitwarden
  tools/maple-login login        # passkey 優先，不可用才退 QR
  tools/maple-login login --qr   # 強制 QR
  ```
  `maple qr` 明確使用 QR，不會改走 passkey。使用者重新執行命令不受本機次數／10 分鐘冷卻限制；舊 `passkey-state.json` 的 count/last 自動忽略，無需刪檔。憑證互斥鎖、dirty 安全防護與站方限制仍保留。
  日常仍優先重用 session。缺少專用 passkey 或依賴（尚未嘗試登入）才退一次 QR；真正嘗試 passkey 後的失敗立即停止，不自動 QR 或再次登入。舊 session 的 OTP 請求故障可用 passkey 恢復一次，沿用原選帳號 sid，最多再申請一次 OTP；本次已取得新 session 就不再恢復。顯式 `otp --qr` 沿用舊 session 時若 OTP 故障，直接停止，不改用 passkey 或自動重新 QR。詳見 [登入機制 §11](docs/how-it-works.md#11-取得-otptoolsmaple-login)。本次整合已做本機與模擬測試，真實註冊/重登尚待使用者在場驗證。
- 選用:一份 Windows 的 `C:\Windows\Fonts`(至少 `mingliu.ttc`),沒有的話字會糊

## 安裝
三選一。裝好之後都只要打 `maple`:第一次會問遊戲目錄,接著下載 wine runner(校驗 SHA256)、
沒有遊戲就問要不要下載、建 prefix,然後開遊戲。中途斷了重跑 `maple` 會接著做。

**Ubuntu 25.10+ / Debian 13(apt)**:gamescope 在 Ubuntu 的 multiverse、Debian 的 trixie-backports,winetricks 在 Debian 的 contrib,要先開。
Ubuntu 24.04 的官方倉庫沒有 gamescope,請用下面的 git clone 並以 `build/build-gamescope.sh` 自己編。
```bash
# Ubuntu:sudo add-apt-repository multiverse
# Debian:sources 加 contrib,並加 trixie-backports(deb http://deb.debian.org/debian trixie-backports main contrib)
sudo curl -fsSLo /etc/apt/keyrings/maple-cask.gpg https://dl.qazsskevin.org/apt/maple-cask.gpg
echo 'deb [signed-by=/etc/apt/keyrings/maple-cask.gpg] https://dl.qazsskevin.org/apt stable main' | sudo tee /etc/apt/sources.list.d/maple-cask.list
sudo apt update && sudo apt install maple-cask
```

**Arch / CachyOS**:AUR 還在註冊中,先從 clone 自己打包(打的是 clone 當下的檔案;之後更新:`git pull && makepkg -si`):
```bash
git clone https://github.com/kevin00156/maple-cask.git && cd maple-cask/packaging/arch && makepkg -si
```
兩種套件都會一併裝好依賴,以及下面 git clone 第 2、3 步的系統設定(split lock、ntsync)。

**git clone**(開發者、自己編 wine)
```bash
git clone https://github.com/kevin00156/maple-cask.git && cd maple-cask
sudo apt install gamescope winetricks mingw-w64 python3-requests python3-cryptography   # Arch 系換成對應的套件

# 1. 把 maple 放進 PATH
mkdir -p ~/.local/bin && ln -sf "$PWD/tools/maple" ~/.local/bin/maple
command -v maple || echo '~/.local/bin 不在 PATH:bash 在 ~/.bashrc 加 export PATH="$HOME/.local/bin:$PATH";fish 跑 fish_add_path ~/.local/bin'

# 2. 關掉 kernel 對 split lock 的罰睡 —— 不關的話反作弊會讓遊戲主執行緒每秒被睡 30 多次、每次 10ms(間歇卡頓)
echo 'kernel.split_lock_mitigate = 0' | sudo tee /etc/sysctl.d/99-split-lock.conf && sudo sysctl --system

# 3. (kernel 6.14 起)開機自動載入 ntsync —— 遊戲的同步呼叫不必全擠在單執行緒的 wineserver;沒有也能玩
echo ntsync | sudo tee /etc/modules-load.d/ntsync.conf && sudo modprobe ntsync
```
設定檔在 `~/.config/maplestory-tw/env.sh`(第一次 `maple` 從 `env.example` 產生);`FONTS_DIR` 等選用項目在裡面改。
想自己編 wine,或要看得到中文輸入法的候選窗:[docs/building.md](docs/building.md)。

## 使用
```bash
maple                     # 開遊戲 → 等登入表單出現 → 鑄 OTP 填進去
maple login --no-submit   # 第一次建議用這個:填好但不按登入,確認兩欄都對再自己按
maple stop                # 關遊戲
maple help                # 全部指令
```
- 請一律用 `maple`(經 gamescope)開遊戲,不要直接跑 wine —— 不經 gamescope 常常連不上登入伺服器。
- `maple` 說「prefix 沒建完」(或 log 裡有 `dxgi.dll ... not found`):在終端機跑 `maple` 會自動補跑 setup;
  setup 本身失敗的話,修好原因後跑 `maple setup`,不用自己去抓 DXVK。
- 遊戲更新:`maple` 開遊戲前會查,有新版就先用 cmsdl 更新再開(比遊戲自己的 Patcher.exe 快很多)。
  有任何一組還在跑、或查不到時就照開,由 Patcher.exe 接手。
- 多開:`maple -2 setup` 一次,之後 `maple -2`(`-2`~`-9`)。主目錄更新過,`maple -N` 會自動重建那組的遊戲目錄。
- 解析度:遊戲是**視窗模式**時,gamescope 自動用遊戲裡設定的解析度(要 1920x1080 就在遊戲裡選);遊戲是全螢幕時固定 1366x768
  (登入畫面固定 1366x768,換別的會在登入前斷線,見 `docs/known-issues.md`「拍賣場被拉伸」)。要自己指定:`GS_ARGS="-W 1366 -H 768 -f" maple game`。
- 用 Lutris / Heroic:執行檔設成 `tools/gs-run.sh`(不是 wine 本身),環境變數照 `env.sh` 填。

## 更新
runner 跟著腳本的版本走(每一版腳本都有同版的 runner)。腳本換了版,下次 `maple` 會問要不要把 runner 與 prefix
同步過去(預設要)。
- 套件安裝:腳本跟著 `sudo apt upgrade` / `sudo pacman -Syu` 更新。
- git clone:`maple` 開遊戲前一天查一次有沒有新 Release,有的話會問要不要先更新(預設不更新)。

要自己更新:
```bash
maple stop && maple update    # git clone 的腳本 git 快轉;runner 換成同版;每一組 prefix 重跑 setup(套件安裝只做後兩件)
maple update --rollback       # 新 runner 有問題:退回上一版(只留一版);之後開遊戲不會再問要不要同步回去
```
- 腳本只有在你沒改過追蹤中的檔案時才更新;runner 只有在 `WINE_ROOT` 是預設的 `runners/current` 時才更新。
  不符合的那一項會跳過並說明原因,不會動你自己的東西。
- git clone 的腳本要一起退版:`git checkout v0.0.1`(換成要的版本);回來用 `git checkout main && maple update`。

## 解除安裝
```bash
maple uninstall    # 先列出要刪的再確認:runner、prefix、多開、設定、快取、beanfun session、passkey
```
`maple` 下載的遊戲會另外問(預設不刪);自己放的遊戲目錄、`env.sh` 裡指到別處的 `WINEPREFIX` / `WINE_ROOT`
只印路徑,不動。遊戲目錄放在要刪的目錄裡(例如裝在 prefix 的 `drive_c` 底下)的話,那個目錄整個留著,
除非你選擇連遊戲一起刪。最後移除腳本本身:`sudo apt remove maple-cask` / `sudo pacman -R maple-cask`;
git clone 則 `rm ~/.local/bin/maple` 並刪掉 clone 目錄。

## 從 git clone 換成套件
裝好套件後 `rm ~/.local/bin/maple` 就好(不刪的話 PATH 上的 clone 會蓋過套件版,`maple` 會提示)。
設定、runner、prefix、遊戲都沿用;clone 目錄不用了可以刪。

遇到問題先看 [docs/known-issues.md](docs/known-issues.md)。

## 文件
- [docs/known-issues.md](docs/known-issues.md) —— 已知問題、多開、字型、輸入法、解析度
- [docs/how-it-works.md](docs/how-it-works.md) —— 每個設定背後的理由
- [docs/building.md](docs/building.md) —— 自己 build、發版、檔案放哪
- [patches/README.md](patches/README.md) —— 每個 wine patch 做什麼、要不要送上游

## 授權
LGPL-2.1-or-later(與 wine 相同)。patch 是對 wine 的修改,本來就必須如此;其餘腳本與文件一併採用同一授權。
不含任何遊戲檔、微軟字型、微軟 DLL、橘子的程式。

## 致謝
- **CodeWeavers / CrossOver** 與 **Nexon**:Nexon 官方 macOS 版建在 CrossOver 之上,並依 LGPL 公開了那棵 wine
  原始碼樹。`patches/0001`、`0002` 的作法直接來自那裡;開發初期也是以那棵樹自建的 wine 當「能玩」的對照組,
  才一路把問題縮小到今天這一組小 patch。沒有 CrossOver 的工作,這個專案不會存在。
- [dspp779](https://github.com/dspp779) 的 [Cyder](https://github.com/dspp779/cyder-wine-engine) /
  [CitrusGate](https://github.com/dspp779/CitrusGate) 與巴哈文章
  〈[等不到台版官方支援，我讓新楓之谷在 Mac 上跑起來了](https://forum.gamer.com.tw/C.php?bsn=7650&snA=1037767)〉:
  台版在 wine 上該打哪些 patch,是照著這篇的指引找到的。本專案是 Linux 版的移植,未複製其原始碼。
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
- 遊戲下載與更新用 [HikariCalyx/cmsdl](https://github.com/HikariCalyx/cmsdl)(MIT)的 release 執行檔,
  版本與 sha256 釘在 `build/CMSDL_VERSION`、`build/CMSDL_SHA256`。感謝作者與做逆向工程的 @Deneo。
