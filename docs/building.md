# 自己 build

不想用 Releases 上的 tarball,或要改 patch,就自己 build。

## wine runner
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
腳本做的事:
1. 從 `dl.winehq.org` 下載上游的 wine release tarball(版本釘在 `build/WINE_VERSION`、sha256 釘在
   `build/WINE_SHA256`,下載後一定校驗)
2. 用 `patch -p1 -F0` 套 [`patches/`](../patches/README.md)
3. 以 `--enable-archs=i386,x86_64`(WoW64)編
4. 放進 GE-Proton 的 DXVK / vkd3d-proton(版本釘在 `build/GE_PROTON_VERSION`,下載後以官方 sha512 校驗;
   已經有解開的 GE-Proton 就用 `GE_DIR=…` 指過去)
5. 編 `tools/*.c`(mingw)
6. 打成 `maplestory-tw-wine-<版本>.tar.xz`,裡面附 patch 與 base 版本 + sha256(LGPL 義務)

產出的 `out/` 直接就是 `WINE_ROOT`。原始碼樹與 `obj/` 每次重跑都會重建,所以這支腳本可以無狀態地重複執行。

## gamescope(選用:要看得到中文輸入法候選窗)
發行版的 gamescope 能玩,只是看不到候選窗。要候選窗就自己編:
```bash
sudo apt install meson ninja-build glslang-tools libsdl2-dev libinput-dev libluajit-5.1-dev   # 加上 gamescope 上游 README 的依賴
build/build-gamescope.sh                 # 裝到 ~/.local/share/maplestory-tw/gamescope
```
然後在 `env.sh` 加 `export PATH=$HOME/.local/share/maplestory-tw/gamescope/bin:$PATH`
(gamescope 靠 PATH 找 `gamescopereaper`,找不到會秒退)。Ubuntu 26.04 實測;24.04 的系統函式庫太舊,不建議。
為什麼需要 gamescope、這個 patch 做什麼:[how-it-works §13](how-it-works.md)。

## 發版(CI)
Releases 上的 tarball 就是 `build/build-wine.sh` 在 GitHub Actions(ubuntu-24.04)上跑出來的:
推 `v*` tag(major.minor.patch,例如 `v0.0.2`)會觸發 [`.github/workflows/release.yml`](../.github/workflows/release.yml),
build 完連同 `SHA256SUMS` 掛到該版的 Release。在 Actions 頁手動 Run workflow 則只 build、不發版,產物放在 workflow artifact。

## 檔案放哪
repo 只放腳本、patch、文件;大檔預設在 `~/.local/share/maplestory-tw/`(可用 `MAPLE_DATA` 改):
```
~/.local/share/maplestory-tw/build/       build/build-wine.sh 的 build 目錄(out/ = wine runner)
~/.local/share/maplestory-tw/gamescope/   build/build-gamescope.sh 的安裝目錄
~/.local/share/maplestory-tw/instances/   多開的第 2~9 組(maple -N setup)
~/.config/maplestory-tw/env.sh            WINE_ROOT / WINEPREFIX / GAME_DIR / FONTS_DIR(從 env.example 複製)
~/.cache/maplestory-tw/                   每次開遊戲的 log
$XDG_RUNTIME_DIR/maplestory-tw/           beanfun session(tmpfs,重開機就消失 —— 刻意的)
```
