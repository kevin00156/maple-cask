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
- `zh_TW.UTF-8` locale:
  ```bash
  sudo locale-gen zh_TW.UTF-8                                                            # Ubuntu
  sudo sed -i 's/^# *zh_TW.UTF-8 UTF-8/zh_TW.UTF-8 UTF-8/' /etc/locale.gen && sudo locale-gen   # Debian、Arch 系
  locale -a | grep -i zh_TW     # 有 zh_TW.utf8 才算數
  ```
- 遊戲本體(約 70GB):有現成的目錄就在第一次開 `maple` 時告訴它路徑;沒有的話 `maple` 會問要不要用
  [cmsdl](https://github.com/HikariCalyx/cmsdl) 從橘子的 CDN 下載
- 一支 beanfun 手機 App(QR 登入用)
- 選用:passkey 自動重登,要 Chromium 系瀏覽器、`secret-tool`、`gdbus` 與已解鎖的 Secret Service / KWallet。
  `maple passkey-setup` 註冊一把專用 passkey,之後登入優先用它,不能用才退回 QR([細節](docs/how-it-works.md#11-取得-otptoolsmaple-login))
- 選用:一份 Windows 的 `C:\Windows\Fonts`(至少 `mingliu.ttc`),沒有的話字會糊

## 安裝
裝好之後只要打 `maple`:第一次會問遊戲目錄,接著下載 wine runner、沒有遊戲就問要不要下載、建 prefix,然後開遊戲。
中途斷了重跑 `maple` 會接著做。套件會一併裝好依賴與系統設定(split lock、ntsync)。

**Ubuntu 25.10+ / Debian 13**:gamescope 在 Ubuntu 的 multiverse、Debian 的 trixie-backports,winetricks 在 Debian 的 contrib,要先開。
```bash
# Ubuntu:sudo add-apt-repository multiverse
# Debian:sources 加 contrib,並加 trixie-backports(deb http://deb.debian.org/debian trixie-backports main contrib)
sudo curl -fsSLo /etc/apt/keyrings/maple-cask.gpg https://dl.qazsskevin.org/apt/maple-cask.gpg
echo 'deb [signed-by=/etc/apt/keyrings/maple-cask.gpg] https://dl.qazsskevin.org/apt stable main' | sudo tee /etc/apt/sources.list.d/maple-cask.list
sudo apt update && sudo apt install maple-cask
```

Arch 系、其他發行版(含 Ubuntu 24.04)、或要自己編 wine:[docs/install.md](docs/install.md)。

**從 git clone 換成套件**:裝好套件後 `rm ~/.local/bin/maple` 就好;設定、runner、prefix、遊戲都沿用。

## 使用
```bash
maple                     # 開遊戲 → 等登入表單出現 → 鑄 OTP 填進去
maple login --no-submit   # 第一次建議用這個:填好但不按登入,確認兩欄都對再自己按
maple stop                # 關遊戲
maple -2 setup            # 多開:建第 2 組(一次就好),之後 maple -2(-2 ~ -9)
maple help                # 全部指令
```
- 一律用 `maple`(經 gamescope)開遊戲,不要直接跑 wine —— 不經 gamescope 常常連不上登入伺服器。
- 遊戲有新版時 `maple` 會先用 cmsdl 更新再開;設定檔在 `~/.config/maplestory-tw/env.sh`。
- 解析度、字型、輸入法、Lutris / Heroic 等:[docs/known-issues.md](docs/known-issues.md)。

## 更新與解除安裝
- 更新:`sudo apt upgrade` 更新腳本,下次 `maple` 會問要不要把 runner 與 prefix 同步到同一版(預設要)。
  新 runner 有問題:`maple update --rollback` 退回上一版。
- 解除安裝:`maple uninstall` 先列出要刪的再確認(遊戲另外問,預設不刪;你自己放的目錄不動),
  然後 `sudo apt remove maple-cask`。

## 文件
- [docs/install.md](docs/install.md) —— apt 以外的安裝方式(Arch、git clone)
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
