# 安裝:apt 以外的方式

Ubuntu 25.10+ / Debian 13 請用 [README](../README.md#安裝) 的 apt。裝好之後的用法都一樣:打 `maple`。

## Arch / CachyOS
AUR 還在註冊中,先從 clone 自己打包。打的是 clone 當下的檔案,依賴與系統設定(split lock、ntsync)會一併裝好:
```bash
git clone https://github.com/kevin00156/maple-cask.git && cd maple-cask/packaging/arch && makepkg -si
```
更新:`git pull && makepkg -si`。解除安裝:`maple uninstall` 之後 `sudo pacman -R maple-cask`。

## git clone(其他發行版、Ubuntu 24.04、開發者)
套件會一併裝好依賴與下面第 2、3 步的系統設定;能用套件就用套件。
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
Ubuntu 24.04 的官方倉庫沒有 gamescope,只能走這條,並用 `build/build-gamescope.sh` 自己編([building.md](building.md#gamescope選用要看得到中文輸入法候選窗))。

更新:`maple` 開遊戲前一天查一次有沒有新 Release,有的話問要不要先更新(預設不更新);也可以自己跑 `maple stop && maple update`
(腳本 git 快轉、runner 換成同版、每一組 prefix 重跑 setup)。
- 腳本只有在你沒改過追蹤中的檔案時才更新;runner 只有在 `WINE_ROOT` 是預設的 `runners/current` 時才更新。
  不符合的那一項會跳過並說明原因,不會動你自己的東西。
- 腳本要一起退版:`git checkout v0.0.1`(換成要的版本);回來用 `git checkout main && maple update`。

解除安裝:`maple uninstall` 之後 `rm ~/.local/bin/maple` 並刪掉 clone 目錄。

## 從 git clone 換成套件
裝好套件後 `rm ~/.local/bin/maple` 就好(不刪的話 PATH 上的 clone 會蓋過套件版,`maple` 會提示)。
設定、runner、prefix、遊戲都沿用;clone 目錄不用了可以刪。
