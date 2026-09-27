<img src="assets/icon.svg" width="128" align="right" alt="">

# MapleCask

maple-cask(楓木桶)—— 讓台版新楓之谷在 Linux 上跑起來。名字取自楓木桶熟成的加拿大威士忌:甜,但是烈。

一個上游 wine 加一組小 patch 的 wine runner、一支把 prefix 建對的腳本,和一個幫你拿 beanfun OTP、
填進登入表單的指令。

**狀態**:✅ 可以玩。登入、長時間遊玩、遊戲內打中文、修飾鍵技能按住連發都實測過。

## 關於反作弊與帳號
- 本專案**沒有停用、沒有繞過** BlackCipher / NGS,它們全程照常運作。唯一相關的 patch 做的事,
  跟 Nexon 官方 macOS 版自己出貨的作法相同([細節](docs/how-it-works.md))。也不接受任何「讓反作弊失效」方向的貢獻。
- **不提供、也不接受任何遊戲內自動化**(巨集、自動戰鬥、外掛類功能)。唯一會對遊戲送輸入的是登入表單的自動填入,
  跟你自己貼上帳號與 OTP 是同一件事。
- 這仍是**非官方環境**,橘子 / Nexon 的服務條款怎麼看待它,本專案無法保證。用自己的帳號,自己承擔。

## 需求
- Linux x86_64,有 Vulkan 的 GPU 驅動(實測 NVIDIA;AMD / Intel 未測)
- `gamescope`、`winetricks`、`mingw-w64`、Python 3 的 `requests` 與 `cryptography`,以及 `zh_TW.UTF-8` locale。Ubuntu:
  ```bash
  sudo apt install gamescope winetricks mingw-w64 python3-requests python3-cryptography
  sudo locale-gen zh_TW.UTF-8
  ```
- 一份現成的 MapleStory 目錄(含 `MapleStory.exe`、`Patcher.exe`)—— 本專案不處理遊戲下載 / 安裝
- 一支 beanfun 手機 App(第一次要掃 QR 登入)
- 選用:一份 Windows 的 `C:\Windows\Fonts`(至少 `mingliu.ttc`),沒有的話字會糊

## 安裝
```bash
git clone https://github.com/kevin00156/maple-cask.git && cd maple-cask

# 1. 設路徑:填 GAME_DIR(必填)、FONTS_DIR;WINE_ROOT 保持預設 = 交給 maple update 管
mkdir -p ~/.config/maplestory-tw
cp env.example ~/.config/maplestory-tw/env.sh && $EDITOR ~/.config/maplestory-tw/env.sh

# 2. 下載 wine runner(Releases 最新版,校驗 SHA256)並建 prefix
tools/maple update

# 3. 把 maple 放進 PATH(~/.local/bin 是這步才建的話,要重新登入 PATH 才會有它)
mkdir -p ~/.local/bin && ln -sf "$PWD/tools/maple" ~/.local/bin/maple
```
想自己編 wine,或要看得到中文輸入法的候選窗:[docs/building.md](docs/building.md)。

## 使用
```bash
maple                     # 開遊戲 → 等登入表單出現 → 鑄 OTP 填進去
maple login --no-submit   # 第一次建議用這個:填好但不按登入,確認兩欄都對再自己按
maple stop                # 關遊戲
maple help                # 全部指令
```
- 請一律用 `maple`(經 gamescope)開遊戲,不要直接跑 wine —— 不經 gamescope 常常連不上登入伺服器。
- 多開:`maple -2 setup` 一次,之後 `maple -2`(`-2`~`-9`)。
- 全螢幕 / 改解析度:`GS_ARGS="-W 1366 -H 768 -f" maple game`。
- 用 Lutris / Heroic:執行檔設成 `tools/gs-run.sh`(不是 wine 本身),環境變數照 `env.sh` 填。

## 更新
`maple` 開遊戲時一天查一次有沒有新 Release,有的話會印一行。要更新:
```bash
maple stop && maple update    # 腳本 git 快轉、下載新 runner、每一組 prefix 重跑 setup
maple update --rollback       # 新 runner 有問題:退回上一版(只留一版)
```
- 腳本只有在你沒改過追蹤中的檔案時才更新;runner 只有在 `WINE_ROOT` 是預設的 `runners/current` 時才更新。
  不符合的那一項會跳過並說明原因,不會動你自己的東西。
- 腳本要一起退版:`git checkout v0.0.1`(換成要的版本);回來用 `git checkout main && maple update`。

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
