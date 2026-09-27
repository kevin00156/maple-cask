#!/usr/bin/env python3
"""imetest.py — 自動化測「wine 底下打不打得出中文」,不需要人按鍵。

為什麼可以自動化:這個測試**不開遊戲**,所以 BlackCipher 沒在跑,
XTEST 合成輸入沒有被判定成巨集的問題。docs 裡那條「量鍵盤只能請人真的按鍵」
是針對遊戲的紀律,對這支不適用 —— 它測的是 wine ↔ fcitx 這一段,遊戲不參與。

做的事:
  1. 用 $WINE_ROOT/bin/wine 開 tools/dev/imeprobe.exe(裸視窗,形狀跟遊戲一樣)
  2. 等它的 X 視窗出現,把輸入焦點指過去
  3. fcitx5-remote -o 啟用中文輸入法(比送 Ctrl+Space 可靠:直接作用在當前 IC)
  4. XTEST 送一串注音鍵 + 空白選字
  5. fcitx5-remote -c 還原,收 probe 的 stdout 判定

判定看 probe 自己印的最後一行。probe 收得到中文 = wine 層通,問題在遊戲;
收不到 = wine 層就斷了。

⚠️ 會搶走桌面焦點約 10 秒。遊戲開著的話先關,或至少不要在打王。

用法:
  source ~/.config/maplestory-tw/env.sh
  tools/dev/imetest.py                      # 預設注音打「ㄘㄜˋ」選第一個候選
  tools/dev/imetest.py --keys 'hk4 g4 '     # 自己指定按鍵序列
  tools/dev/imetest.py --style root         # 先把 InputStyle 設成 root 再測
"""
import argparse, os, shutil, subprocess, sys, time

try:
    from Xlib import X, XK, display
    from Xlib.ext import xtest
except ImportError:
    sys.exit("缺 python3-xlib:sudo apt install python3-xlib")

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 大千式注音鍵盤:ㄘ=h ㄜ=k ˋ=4,空白選第一個候選。
# 打出哪個字不重要 —— 要驗的是「有沒有非 ASCII 字元穿過 wine 進到訊息佇列」。
DEFAULT_KEYS = "hk4 "


def find_window(dpy, name_part, timeout=15):
    """在 X 視窗樹裡找標題含 name_part 的視窗。wine 的視窗被 WM 重新 parent 過,
    所以要遞迴走整棵樹,不能只看 root 的直接子視窗。"""
    net_wm_name = dpy.intern_atom("_NET_WM_NAME")
    utf8 = dpy.intern_atom("UTF8_STRING")
    deadline = time.time() + timeout
    while time.time() < deadline:
        found = _walk(dpy.screen().root, name_part, net_wm_name, utf8)
        if found:
            return found
        time.sleep(0.3)
    return None


def _walk(win, name_part, net_wm_name, utf8):
    """WM_NAME 與 _NET_WM_NAME 都要看。中文標題塞不進 Latin-1 的 WM_NAME,
    只會出現在 _NET_WM_NAME(UTF8_STRING)裡 —— 只讀前者會整個找不到視窗。
    atom 必須由呼叫端算好傳進來:win.display 是 protocol display,沒有 intern_atom。"""
    try:
        names = [win.get_wm_name()]
        prop = win.get_full_property(net_wm_name, utf8)
        if prop:
            names.append(prop.value.decode("utf-8", "replace"))
        if any(n and name_part in n for n in names if isinstance(n, str)):
            return win
    except Exception:
        pass
    # 子樹要在自己的 try 外面走:上面任何一個屬性讀取失敗都不該讓整棵子樹被跳過
    try:
        children = win.query_tree().children
    except Exception:
        return None
    for child in children:
        r = _walk(child, name_part, net_wm_name, utf8)
        if r:
            return r
    return None


def send_key(dpy, keysym_name, ctrl=False):
    """XTEST 送一個按鍵。XTEST 產生的事件在 X server 眼中跟真鍵盤沒有差別,
    所以 fcitx 的 XIM 前端一樣會攔到它。"""
    ks = XK.string_to_keysym(keysym_name)
    kc = dpy.keysym_to_keycode(ks)
    if not kc:
        print(f"  ⚠ 找不到 {keysym_name} 的 keycode,跳過")
        return
    ctrl_kc = dpy.keysym_to_keycode(XK.XK_Control_L) if ctrl else None
    if ctrl_kc:
        xtest.fake_input(dpy, X.KeyPress, ctrl_kc)
    xtest.fake_input(dpy, X.KeyPress, kc)
    xtest.fake_input(dpy, X.KeyRelease, kc)
    if ctrl_kc:
        xtest.fake_input(dpy, X.KeyRelease, ctrl_kc)
    dpy.sync()


CHAR_TO_KEYSYM = {" ": "space", "/": "slash", ";": "semicolon", ",": "comma", ".": "period", "-": "minus"}


def wait_focus(dpy, win, timeout=6.0):
    """等到 X 的輸入焦點真的落在 win(或它的子視窗)上。

    不能 set_input_focus 完就 sleep 一個固定秒數了事:KWin 可能把焦點搶回去,
    而 wine 要收到 FocusIn 才會 XSetICFocus。焦點沒到位就送 fcitx5-remote -o,
    那個 -o 會作用到**別的 input context** 上,這一輪就整個空轉。"""
    root = dpy.screen().root
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            cur = dpy.get_input_focus().focus
            while cur and getattr(cur, "id", 0) and cur.id != root.id:
                if cur.id == win.id:
                    return True
                cur = cur.query_tree().parent
        except Exception:
            pass
        time.sleep(0.2)
    return False


def kill_stale():
    """殺掉上一輪殘留的 probe。只比對我們自己的執行檔名,不會碰到別的 wine 程式。"""
    subprocess.run(["pkill", "-f", "imeprobe.exe"], capture_output=True)
    time.sleep(1.2)   # 等 X connection 真的斷掉,fcitx 才會清掉舊的 XIC


def fcitx(*args):
    if not shutil.which("fcitx5-remote"):
        return None
    try:
        return subprocess.run(["fcitx5-remote", *args], capture_output=True,
                              text=True, timeout=5).stdout.strip()
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keys", default=DEFAULT_KEYS, help="要送的按鍵序列(一個字元一個鍵)")
    ap.add_argument("--seconds", type=int, default=20, help="probe 存活秒數")
    ap.add_argument("--gap", type=float, default=0.35, help="每個按鍵之間的間隔秒數")
    ap.add_argument("--style", help="測之前把 X11 Driver\\InputStyle 設成這個(root/overthespot/offthespot)")
    ap.add_argument("--xim-trace", action="store_true", help="同時收 WINEDEBUG=+xim")
    ap.add_argument("--own-by-ime", action="store_true",
                    help="把 probe 主視窗的 owner 設成 default IME window(重現遊戲的狀況)")
    ap.add_argument("--filter-hwnd", action="store_true",
                    help="probe 的訊息迴圈只收主視窗訊息(重現遊戲的行為)")
    ap.add_argument("--ansi", action="store_true",
                    help="讓 probe 扮成 ANSI wndproc(遊戲很可能是這條路)")
    args = ap.parse_args()

    wine_root = os.environ.get("WINE_ROOT")
    if not wine_root:
        sys.exit("請先 source ~/.config/maplestory-tw/env.sh(要 WINE_ROOT / WINEPREFIX)")
    wine = os.path.join(wine_root, "bin", "wine")
    probe = os.path.join(REPO, "tools", "dev", "imeprobe.exe")
    if not os.path.exists(probe):
        sys.exit(f"沒有 {probe},先編譯:\n  x86_64-w64-mingw32-gcc -O2 -municode "
                 f"-fexec-charset=UTF-8 -o tools/dev/imeprobe.exe tools/dev/imeprobe.c -limm32")

    if args.style:
        print(f"→ 設 InputStyle=\"{args.style}\"")
        subprocess.run([os.path.join(wine_root, "bin", "wine"), "reg", "add",
                        r"HKCU\Software\Wine\X11 Driver", "/v", "InputStyle",
                        "/t", "REG_SZ", "/d", args.style, "/f"],
                       capture_output=True, timeout=60)

    # ⚠ 一定要先清乾淨。wine 行程不會跟著 Popen 的 timeout 一起死,留下來的 probe
    # 視窗標題一模一樣 —— find_window 會抓到**舊的那個**,焦點與 XIC 全部錯位,
    # 表現出來就是「第一輪成功、後面每一輪都 0」。查這個花掉的時間比寫它多十倍。
    kill_stale()

    env = dict(os.environ, LANG="zh_TW.UTF-8", LC_ALL="zh_TW.UTF-8")
    env["WINEDEBUG"] = os.environ.get("IMETEST_WINEDEBUG") or ("+xim" if args.xim_trace else "fixme-all,err+all")

    print(f"→ 開 probe({args.seconds}s)…")
    cmd = [wine, probe, "--seconds", str(args.seconds)] + (["--ansi"] if args.ansi else []) + (["--filter-hwnd"] if args.filter_hwnd else []) + (["--own-by-ime"] if args.own_by_ime else [])
    proc = subprocess.Popen(cmd,
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, errors="replace")

    dpy = display.Display()
    win = find_window(dpy, "IME Probe")
    if not win:
        proc.kill()
        sys.exit("✗ 找不到 probe 視窗 —— wine 沒起來,或視窗被別的 desktop 隔離了")
    print(f"→ 找到視窗 {hex(win.id)},指定輸入焦點")
    win.set_input_focus(X.RevertToParent, X.CurrentTime)
    dpy.sync()
    if not wait_focus(dpy, win):
        proc.kill(); kill_stale()
        sys.exit("✗ 焦點沒能落在 probe 上(被 WM 搶走?)—— 這一輪的結果不可信,中止")
    print("→ 焦點已確認在 probe 上")
    time.sleep(0.5)

    before = fcitx("-n")
    print(f"→ fcitx 目前的輸入法:{before}")
    fcitx("-o")                      # 切到中文(DefaultIM,這台是 rime 注音)
    time.sleep(0.8)
    print(f"→ 啟用後:{fcitx('-n')}")

    print(f"→ XTEST 送按鍵:{args.keys!r}")
    for ch in args.keys:
        send_key(dpy, CHAR_TO_KEYSYM.get(ch, ch))
        time.sleep(args.gap)
    time.sleep(1.0)

    fcitx("-c")                      # 還原,不要把使用者的輸入法留在中文
    print(f"→ 還原後:{fcitx('-n')}")

    try:
        out, _ = proc.communicate(timeout=args.seconds + 20)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
        out = (out or "") + "\n⚠ probe 逾時被強制結束"
    kill_stale()   # Popen 收掉的是 wine loader,Windows 那側的行程要自己補刀
    print("\n" + "=" * 60 + "\nprobe 的輸出:\n" + "=" * 60)
    print(out)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
