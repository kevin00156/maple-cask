/* mapletype.c — 用 PostMessage 把 beanfun 的帳號 sid + 一次性 OTP 打進楓之谷登入表單。
 *
 * --login 打字走 PostMessage(WM_CHAR)—— 直接進目標視窗的訊息佇列;控制鍵(Ctrl+A / Tab / Enter)
 * 走 SendInput。兩者都不搶焦點、也不碰 X(不用 xdotool)。只做登入表單這一件事。
 *
 * 三個坑,每個都會讓你白開一次遊戲:
 *
 * 1. desktop 隔離。若你自己開了 AppDefaults\MapleStory.exe\Explorer 的 "Desktop",
 *    遊戲會跑在另一個 Win32 desktop 物件上,這支工具的 EnumWindows 就找不到它的視窗
 *    (而且是靜默回空、不設 last error)。本專案預設不開。
 *
 * 2. 大寫會靜默變小寫。對方的 TranslateMessage 會把你 post 的 WM_KEYDOWN 翻成 WM_CHAR,
 *    而它查的是**對方佇列的**按鍵狀態(win32u/message.c: NtUserGetKeyboardState →
 *    NtUserToUnicodeEx),PostMessage 不會更新那個狀態 → Shift 永遠是放開的 →
 *    "MSaB12345" 會變成 "msab12345"。登入失敗時看起來活像「OTP 錯了」。
 *    所以文字預設走 --mode char(WM_CHAR 直送,不經過翻譯)。
 *
 * 3. 用錯 wine。一定要 "$WINE_ROOT/bin/wine",不能用發行版的 /usr/bin/wine ——
 *    版本不符會觸發 wineboot 去更新 prefix,而且是在遊戲跑著的時候。
 *
 * ── 2026-09-14 首次對真登入表單實測(遊戲不在 gamescope 裡)──────────────────
 * 打字這一半通,操作表單那一半不通。每一條都對著遊戲的登入框量過、截圖比對過:
 *
 *   可列印字元(WM_CHAR)        ✅ 進「當下有焦點的那一欄」。大小寫正確(MSaB9 原樣),
 *                                 不重複(送 aaaa 就是 4 個 a),11 字元零掉字(當時 gap=40ms;
 *                                 2026-09-20 起 --login 的 gap 預設 0,見 type_text() 上方)。
 *                                 視窗不必在前景 —— probe 顯示 focus=0/active=0 時照樣收。
 *   控制鍵 TAB / BACKSPACE      ❌ WM_KEYDOWN(VK_TAB/VK_BACK) 與 WM_CHAR(0x09/0x08)
 *                                 四種組合全部無效,欄位一個字都沒動。
 *   滑鼠 MOUSEMOVE/LBUTTON*     ❌ 點密碼欄沒反應,點完打字仍進帳號欄;
 *                                 連有視覺回饋的「記憶帳號」圓鈕都點不動
 *                                 → 不是座標算錯,是滑鼠訊息整條不通。
 *
 * 同一個根因,就是上面第 2 點的延伸:**PostMessage 只投遞訊息,不改變輸入狀態**。
 * 字元自己帶在 WM_CHAR 的 wParam 裡,所以進得去;控制鍵與滑鼠要的是「狀態」——
 * 這個遊戲是自繪 UI(主視窗底下零子視窗、caret=0、rcCaret 全零),
 * 焦點與滑鼠靠輪詢 GetAsyncKeyState / GetCursorPos 讀**全域**狀態,PostMessage 動不到那個。
 *
 * 當時的結論(**已被下面 09-20 那段取代**,留著是因為 PostMessage 這條路的行為沒變):
 *   工具是焦點跟隨的,只能填使用者已經點好的那一欄;清不掉舊 sid、切不到密碼欄、
 *   --submit 的 Enter 也送不出去,流程只能半自動。
 *   滑鼠(--click / --field2)到今天仍然是死的 —— 那是另一半,跟鍵盤無關。
 *
 * ── 2026-09-20 gamescope 之後 ──────────────────────────────────────────────
 * 上面那段量的是遊戲 deactivate 時的 PostMessage;gamescope 裡遊戲永遠有焦點(§13),
 * 鍵盤事件整條都通了。--login 因此照人的做法走:每一欄 **Ctrl+A 全選再打**,打字自己覆蓋掉
 * 選取範圍 —— 帳號欄會記住上次的 sid,不清就是新舊兩串黏在一起。
 * 字元仍走 WM_CHAR(--mode,預設 char;大小寫才會對),控制鍵 Ctrl+A / TAB / ENTER 走 SendInput
 * —— 它們要的是全域按鍵狀態,WM_CHAR 的 wParam 帶不了(組合鍵尤其:Ctrl 的按鍵狀態送不過去,
 * 對方收到的就只是一顆普通的 A)。
 * 不要用「BACKSPACE 砍 N 下」清欄位:要猜長度、一欄兩秒,砍不夠還會留下舊 sid 黏在前面。
 *
 * OTP 不從 argv 傳(會出現在 /proc/<pid>/cmdline,同機誰都讀得到),走 stdin。
 *
 * 建置: x86_64-w64-mingw32-gcc -O2 -municode -fexec-charset=UTF-8 -o mapletype.exe mapletype.c
 *
 * 用法:
 *   mapletype.exe --probe                         列出全域前景 + 所有視窗 / 焦點 / caret
 *   mapletype.exe --hwnd 0x30062 --text TEST      打字(探測用假字串,不燒 OTP)
 *   mapletype.exe --key CTRL+A --text TEST        全選再打,驗覆蓋(不燒 OTP)
 *   mapletype.exe --hwnd 0x30062 --key TAB        送單鍵
 *   mapletype.exe --hwnd 0x30062 --click 420,318  送點擊(client 座標)
 *   printf '%s\n%s\n' "$sid" "$otp" | mapletype.exe --login --wait 180000 [--submit]
 *
 * --gap N   字元之間等 N ms(預設 0:OTP 一次灌完,不裝人類)。掉字了才調高,40 是實測過的人類節奏。
 * --hold N  一顆鍵按下到放開撐 N ms(預設 40)。**不要設 0** —— 遊戲每幀輪詢按鍵狀態,
 *           比一幀(60fps = 16.7ms)還短的按壓會整顆消失,Ctrl+A 失效就等於舊 sid 沒清掉。
 *
 * --key 吃組合鍵:CTRL+A、SHIFT+TAB。單一字元不必進 KEYS 表。
 * --clear N(打字前砍 N 下 BACKSPACE)留給真的 Win32 EDIT 視窗,--login 不用它。
 *
 * --click 永遠是「動手之前先點這裡一下」。--login 要跳到第二欄(密碼)用 --field2,
 * 不給就送 Tab。兩件事不同語意,所以是兩個旗標。
 *
 * --submit(送 Enter)預設關閉。表單只能送一次,送錯要整個重開遊戲 ——
 * 所以探測階段永遠不要按:帳號欄是明文、密碼欄數點點,字對不對看得出來。
 */
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <wchar.h>

#ifndef VK_PACKET
#define VK_PACKET 0xE7
#endif

#define MODE_CHAR   1   /* WM_CHAR 直送。自繪文字欄位九成吃這個,大小寫正確 */
#define MODE_PACKET 2   /* WM_KEYDOWN(VK_PACKET):讓對方的 TranslateMessage 生 WM_CHAR,大小寫也對 */
#define MODE_KEY    4   /* WM_KEYDOWN(真 VK)。大寫會掉成小寫,見檔頭第 2 點 */
#define MODE_INPUT  8   /* SendInput:走 wineserver 的硬體輸入路徑,會更新該 desktop 的 keystate(GetAsyncKeyState
                         * 看得到),訊息投給該 desktop 前景執行緒的佇列。X 焦點離開遊戲時 winex11 會把前景設成
                         * desktop window(獨立 desktop 也一樣),遊戲同時收到 deactivate 而不吃鍵 ——
                         * 所以人不在遊戲視窗上時這條路沒有目標。見 input_key() 上方 */

/* gap = 打字時「字元與字元之間」的間隔,0 = 不等(--login 預設,OTP 一次灌完)。
 * hold = 一顆鍵「按下到放開」撐多久。這個不能歸零:遊戲是自繪 UI,靠每幀輪詢
 * GetAsyncKeyState 讀按鍵狀態(檔頭第 2 點),60fps 一幀 16.7ms —— 按下去 0ms 就放開,
 * 整顆鍵會落在兩幀之間、誰都沒看見。Ctrl+A 沒生效 = 舊 sid 沒清掉 = 新舊黏一起。
 * 兩件事語意不同,以前共用一個 gap 是錯的。 */
static int mode = MODE_CHAR, gap = 0, hold = 40;

#define KMOD_CTRL  1    /* MOD_* 這個名字 imm.h 佔走了,別再撞 */
#define KMOD_SHIFT 2
#define KMOD_ALT   4
static const wchar_t *match = L"MapleStory";
static HWND found;

/* 寬字串轉 UTF-8 再 printf。不用 wprintf —— wine 的 msvcrt 寬字元輸出到 Unix 終端會亂 */
static const char *u8(const wchar_t *w)
{
    static char buf[4][512];
    static int n;
    char *p = buf[n = (n + 1) & 3];
    if (!WideCharToMultiByte(CP_UTF8, 0, w, -1, p, sizeof(buf[0]), NULL, NULL)) p[0] = 0;
    return p;
}

/* bits 0-15 repeat=1、16-23 scan code、24 延伸鍵、30/31 keyup 才設。
 * scan code 一定要填對:真鍵盤永遠有 scan code,填 0 是合成輸入的經典指紋。 */
static LPARAM key_lparam(int vk, int up)
{
    UINT sc = MapVirtualKeyW(vk, MAPVK_VK_TO_VSC);
    int ext = (vk >= VK_PRIOR && vk <= VK_DOWN) || vk == VK_INSERT || vk == VK_DELETE ||
              vk == VK_RCONTROL || vk == VK_RMENU || vk == VK_NUMLOCK || vk == VK_DIVIDE;
    return (up ? 0xC0000001 : 0x00000001) | ((LPARAM)(sc & 0xFF) << 16) | (ext ? 0x01000000 : 0);
}

/* 延伸鍵:方向鍵、Ins/Del/Home/End/PgUp/PgDn、PrtSc、Pause、
 * 右 Ctrl/Alt、小鍵盤 /、NumLock。少了這個旗標 wine 會把 VK_LEFT 當成小鍵盤 4 */
static int is_extended(int vk)
{
    return (vk >= VK_PRIOR && vk <= VK_DELETE) || vk == VK_PAUSE || vk == VK_RCONTROL || vk == VK_RMENU
        || vk == VK_DIVIDE || vk == VK_NUMLOCK;
}

/* SendInput 一顆鍵。**這裡刻意沒有 SetForegroundWindow**,兩個理由:
 * 一、沒有用。前景與 keystate 確實是 per-desktop 的,但 winex11 在 X FocusOut 時會自己把前景設成
 *     desktop window(winex11 event.c focus_out「lost focus, setting fg to desktop」),獨立 desktop
 *     擋不住 —— FocusOut 是送給遊戲自己的 X 視窗的。2026-09-16 X 焦點在終端機時每 10ms 抽 8 秒,
 *     GetForegroundWindow() 全程 NULL。遊戲收過 deactivate 就不吃鍵,跟 Windows 版一樣。
 *     (前一版註解說「X 焦點在哪完全無關」是錯的:那次量測時使用者人在遊戲裡,X 焦點根本沒離開。)
 * 二、碰了會死,而且不可逆。對遊戲視窗呼叫 SetForegroundWindow 會觸發 HCBT_ACTIVATE,
 *     hook 拿到的 CBTACTIVATESTRUCT.hWndActive 是**當下作用中**的視窗 —— 也就是遊戲自己 ——
 *     wine 的 dinput 拿它比對持有裝置的視窗,相符就 unacquire
 *     (dinput_main.c cbt_hook_proc → handle_foreground_lost,條件是 window == impl->win),
 *     指望應用程式在 WM_ACTIVATE 裡自己重新 Acquire —— 但遊戲從沒失去啟動、不會跑那條路。
 *     結果 dinput 鍵盤從此 unacquired:技能鍵全死,連使用者的實體鍵盤一起死,
 *     要手動點別的視窗再點回來才復原(2026-09-15 實測)。方向鍵不受影響(讀 desktop keystate,不經 dinput)。 */
static void input_key(int vk, int up)
{
    INPUT in = {0};
    in.type = INPUT_KEYBOARD;
    in.ki.wVk = vk;
    in.ki.wScan = MapVirtualKeyW(vk, MAPVK_VK_TO_VSC);
    in.ki.dwFlags = (up ? KEYEVENTF_KEYUP : 0) | (is_extended(vk) ? KEYEVENTF_EXTENDEDKEY : 0);
    if (!SendInput(1, &in, sizeof(in))) printf("SendInput 失敗 err=%lu\n", GetLastError());
}

static void send_char(HWND h, wchar_t ch)
{
    SHORT vs = VkKeyScanW(ch);
    int vk = (vs == -1) ? 0 : (vs & 0xFF);

    if (mode & MODE_INPUT)
    {
        int shift = (vs >> 8) & 1;
        if (shift) input_key(VK_SHIFT, 0);
        input_key(vk, 0); Sleep(hold); input_key(vk, 1);
        if (shift) input_key(VK_SHIFT, 1);
        return;
    }
    if ((mode & MODE_KEY) && vk) PostMessageW(h, WM_KEYDOWN, vk, key_lparam(vk, 0));
    /* 只送 KEYDOWN:TranslateMessage 不看 KEYUP,而 keyup 的 bit31 會蓋掉字元的高位元 */
    if (mode & MODE_PACKET)      PostMessageW(h, WM_KEYDOWN, VK_PACKET, ((LPARAM)ch << 16) | 1);
    /* WM_CHAR 的 lParam 就是產生它的那個 WM_KEYDOWN 的 lParam 原封不動(見 message.c) */
    if (mode & MODE_CHAR)        PostMessageW(h, WM_CHAR, ch, vk ? key_lparam(vk, 0) : 1);
    if ((mode & MODE_KEY) && vk) PostMessageW(h, WM_KEYUP, vk, key_lparam(vk, 1));
}

/* 預設 gap=0:WM_CHAR 是 PostMessage,字元一顆顆排進對方的訊息佇列,不會因為送得快而遺失
 * —— 佇列就是為了這個存在的。掉字的風險在 --mode key/input(走硬體輸入路徑,吃按鍵狀態),
 * 那兩條路 send_char 內部有 hold 撐著。
 * 慢速人類節奏(2026-09-14 實測 11 字元零掉字的那組)是 --gap 40,打不進去時再退回去。 */
static void type_text(HWND h, const wchar_t *s)
{
    for (; *s; s++) { send_char(h, *s); if (gap) Sleep(gap + rand() % 20); }
}

/* "x,y" -> (x, y)。沒有逗號就當 y=0 */
static void parse_xy(const wchar_t *s, int *x, int *y)
{
    wchar_t *p;
    *x = wcstol(s, &p, 10);
    *y = (*p == L',') ? wcstol(p + 1, NULL, 10) : 0;
}

static void send_key(HWND h, int vk)
{
    if (mode & MODE_INPUT) { input_key(vk, 0); Sleep(hold); input_key(vk, 1); return; }
    PostMessageW(h, WM_KEYDOWN, vk, key_lparam(vk, 0));
    Sleep(hold);
    PostMessageW(h, WM_KEYUP, vk, key_lparam(vk, 1));
}

/* 控制鍵一律走 SendInput,不看 --mode —— 理由見檔頭 2026-09-20 那段:
 * 字元自己帶在 WM_CHAR 的 wParam 裡,控制鍵要的是全域按鍵狀態,只有 SendInput 給得起。 */
static void ctrl_key(int vk)
{
    input_key(vk, 0);
    Sleep(hold / 2 + 5);
    input_key(vk, 1);
    Sleep(hold / 2 + 5);
}

/* 修飾鍵要跟按鍵一起走 SendInput。PostMessage 改不到全域按鍵狀態,
 * 對方眼裡 Ctrl 永遠是放開的,組合鍵就只是一顆普通的 A(檔頭第 2 點的同一個根因)。 */
static void combo_key(int mods, int vk)
{
    static const int KMOD_VK[3] = { VK_CONTROL, VK_SHIFT, VK_MENU };
    int i;
    for (i = 0; i < 3; i++) if (mods & (1 << i)) { input_key(KMOD_VK[i], 0); Sleep(15); }
    ctrl_key(vk);
    for (i = 2; i >= 0; i--) if (mods & (1 << i)) { input_key(KMOD_VK[i], 1); Sleep(15); }
}

/* 清空「當下有焦點的那一欄」= Ctrl+A 全選,接著打字直接覆蓋選取範圍 —— 人就是這樣做的。
 * 欄位內容讀不到(自繪 UI:主視窗底下零子視窗,沒有 WM_GETTEXT 可問),全選不必知道長度,
 * 一顆鍵解決;砍 BACKSPACE 那套要猜次數、一欄兩秒,砍不夠還會留下舊 sid 黏在前面。 */
static void select_all(void) { combo_key(KMOD_CTRL, 'A'); }

/* client 座標,不要 ScreenToClient —— 滑鼠訊息的 lParam 依規格就是 client 座標,
 * 再轉一次只會錯。wmain 有宣告 DPI awareness(SetProcessDPIAware),所以 --probe
 * 印出來的 cli=WxH 就是實際像素,量到什麼就直接餵給 --click */
static void send_click(HWND h, int x, int y)
{
    LPARAM pos = MAKELPARAM(x, y);
    PostMessageW(h, WM_MOUSEMOVE, 0, pos);              /* 先更新 hover / hit-test */
    PostMessageW(h, WM_LBUTTONDOWN, MK_LBUTTON, pos);
    Sleep(40);                                          /* 0ms 的點擊很多 UI 不認 */
    PostMessageW(h, WM_LBUTTONUP, 0, pos);
}

static void dump(HWND h, int depth)
{
    wchar_t cls[64] = L"", title[128] = L"";
    RECT wr = {0}, cr = {0};
    DWORD pid = 0, tid = GetWindowThreadProcessId(h, &pid);
    HWND c;

    GetClassNameW(h, cls, 64);
    GetWindowTextW(h, title, 128);   /* 跨行程不會送 WM_GETTEXT,不會卡住 */
    GetWindowRect(h, &wr);
    GetClientRect(h, &cr);
    printf("%*s%p %s%s %-24s scr=%ld,%ld cli=%ldx%ld pid=%lu \"%s\"\n", depth * 2, "", h,
           IsWindowVisible(h) ? "V" : "-", IsWindowUnicode(h) ? "U" : "A",
           u8(cls), wr.left, wr.top, cr.right, cr.bottom, pid, u8(title));

    if (depth == 1)
    {
        GUITHREADINFO g = {0};
        g.cbSize = sizeof(g);
        if (GetGUIThreadInfo(tid, &g))
            printf("%*s  focus=%p active=%p caret=%p rcCaret=%ld,%ld %ldx%ld\n", depth * 2, "",
                   g.hwndFocus, g.hwndActive, g.hwndCaret, g.rcCaret.left, g.rcCaret.top,
                   g.rcCaret.right - g.rcCaret.left, g.rcCaret.bottom - g.rcCaret.top);
    }
    for (c = GetWindow(h, GW_CHILD); c; c = GetWindow(c, GW_HWNDNEXT)) dump(c, depth + 1);
}

/* 全域前景。非印不可:上面每個視窗那行的 focus/active 是 GetGUIThreadInfo(tid),
 * 那是**該執行緒的**焦點,跟「這個 desktop 的前景是誰」是兩件事 ——
 * 2026-09-16 就是因為 probe 少了這一格,看到遊戲那行 focus=0/active=0 就誤判
 * 「遊戲不在前景」,其實 GetForegroundWindow() 一直是它。tid=0 問的才是前景執行緒。 */
static void dump_foreground(void)
{
    HWND fg = GetForegroundWindow();
    GUITHREADINFO g = {0};

    g.cbSize = sizeof(g);
    printf("前景:%p tid=%lu", fg, GetWindowThreadProcessId(fg, NULL));
    if (GetGUIThreadInfo(0, &g))
        printf(" focus=%p active=%p\n", g.hwndFocus, g.hwndActive);
    else
        printf(" GetGUIThreadInfo(0) err=%lu(這個 desktop 沒有前景執行緒)\n", GetLastError());
}

static BOOL CALLBACK on_window(HWND h, LPARAM probe)
{
    wchar_t cls[64] = L"", title[128] = L"";
    RECT cr;

    /* probe 模式借 found 當「至少列到一個」的旗標,給 wmain 判斷要不要喊 desktop 隔離 */
    if (probe) { dump(h, 1); found = h; return TRUE; }
    if (!IsWindowVisible(h)) return TRUE;
    GetClassNameW(h, cls, 64);
    GetWindowTextW(h, title, 128);
    if (!wcscmp(cls, L"DwarfWebBrowserClass")) return TRUE;   /* NxOverlay,不是它 */
    if (!wcsstr(cls, match) && !wcsstr(title, match)) return TRUE;
    GetClientRect(h, &cr);
    if (cr.right < 320 || cr.bottom < 240) return TRUE;       /* 排掉隱形 / 迷你視窗 */
    found = h;
    return FALSE;
}

/* 輪詢而不是找一次就算:這支工具可能比遊戲早啟動 */
static HWND find_target(int wait_ms)
{
    int waited = 0;
    for (;;)
    {
        found = NULL;
        EnumWindows(on_window, 0);
        if (found || waited >= wait_ms) return found;
        Sleep(250);
        waited += 250;
    }
}

/* 只收 ASCII 可見字元:CP950 下非 ASCII 的 WM_CHAR 會被拆成 2 bytes,行為無法解釋 */
static int read_ascii(wchar_t *out, int n)
{
    char buf[256];
    int i, j = 0;
    out[0] = 0;
    if (!fgets(buf, sizeof(buf), stdin)) return 0;
    for (i = 0; buf[i] && j < n - 1; i++)
        if ((unsigned char)buf[i] > 0x20 && (unsigned char)buf[i] < 0x7F) out[j++] = buf[i];
    out[j] = 0;
    return j;
}

static const struct { const wchar_t *name; int vk; } KEYS[] = {
    { L"TAB", VK_TAB }, { L"RETURN", VK_RETURN }, { L"ENTER", VK_RETURN },
    { L"BACK", VK_BACK }, { L"ESC", VK_ESCAPE },
    { L"LEFT", VK_LEFT }, { L"RIGHT", VK_RIGHT }, { L"UP", VK_UP }, { L"DOWN", VK_DOWN },
};

/* "CTRL+A" → mods=KMOD_CTRL, vk='A'。單一 ASCII 字元不必進 KEYS 表,查鍵盤配置就有。
 * 自己切 '+' 不用 wcstok:mingw 只有 C90 那個兩參數版本,不可重入。 */
static int parse_key(const wchar_t *spec, int *mods, int *vk)
{
    wchar_t tok[32];
    const wchar_t *p = spec, *plus;
    unsigned k;
    size_t len;

    *mods = *vk = 0;
    for (;;)
    {
        plus = wcschr(p, L'+');
        len = plus ? (size_t)(plus - p) : wcslen(p);
        if (!len || len >= 32) return 0;
        wmemcpy(tok, p, len);
        tok[len] = 0;

        if      (!wcscmp(tok, L"CTRL"))  *mods |= KMOD_CTRL;
        else if (!wcscmp(tok, L"SHIFT")) *mods |= KMOD_SHIFT;
        else if (!wcscmp(tok, L"ALT"))   *mods |= KMOD_ALT;
        else
        {
            for (k = 0; k < sizeof(KEYS) / sizeof(KEYS[0]); k++)
                if (!wcscmp(tok, KEYS[k].name)) *vk = KEYS[k].vk;
            if (!*vk && len == 1 && tok[0] < 128)
            {
                SHORT vs = VkKeyScanW(tok[0]);
                if (vs != -1) *vk = vs & 0xFF;
            }
            if (!*vk) return 0;
        }
        if (!plus) break;
        p = plus + 1;
    }
    return *vk != 0;
}



int wmain(int argc, wchar_t **argv)
{
    int i, probe = 0, login = 0, submit = 0, wait_ms = 0, clear = 0, key = 0;
    int key_mods = 0;       /* --key CTRL+A 的修飾鍵 */
    int cx = -1, cy = 0;    /* --click:動手之前先點一下 */
    int fx = -1, fy = 0;    /* --field2:--login 時跳到第二欄的點法(不給就送 Tab) */
    const wchar_t *text = NULL;
    HWND h = NULL;

    SetProcessDPIAware();
    srand(GetTickCount());

    for (i = 1; i < argc; i++)
    {
        wchar_t *a = argv[i];
        int more = i + 1 < argc;
        if      (!wcscmp(a, L"--probe"))  probe = 1;
        else if (!wcscmp(a, L"--login"))  login = 1;
        else if (!wcscmp(a, L"--submit")) submit = 1;
        else if (!wcscmp(a, L"--hwnd")  && more) h = (HWND)(ULONG_PTR)wcstoull(argv[++i], NULL, 0);
        else if (!wcscmp(a, L"--find")  && more) match = argv[++i];
        else if (!wcscmp(a, L"--text")  && more) text = argv[++i];
        else if (!wcscmp(a, L"--wait")  && more) wait_ms = wcstol(argv[++i], NULL, 10);
        else if (!wcscmp(a, L"--gap")   && more) gap = wcstol(argv[++i], NULL, 10);
        else if (!wcscmp(a, L"--hold")  && more) hold = wcstol(argv[++i], NULL, 10);
        else if (!wcscmp(a, L"--clear") && more) clear = wcstol(argv[++i], NULL, 10);
        else if (!wcscmp(a, L"--click")  && more) parse_xy(argv[++i], &cx, &cy);
        else if (!wcscmp(a, L"--field2") && more) parse_xy(argv[++i], &fx, &fy);
        else if (!wcscmp(a, L"--key") && more)
        {
            if (!parse_key(argv[++i], &key_mods, &key))
            { printf("不認得的按鍵 %s(TAB / CTRL+A / SHIFT+TAB 這種)\n", u8(argv[i])); return 2; }
        }
        else if (!wcscmp(a, L"--mode") && more)
        {
            const wchar_t *m = argv[++i];
            mode = !wcscmp(m, L"char")   ? MODE_CHAR
                 : !wcscmp(m, L"packet") ? MODE_PACKET
                 : !wcscmp(m, L"key")    ? MODE_KEY
                 : !wcscmp(m, L"input")  ? MODE_INPUT
                 : !wcscmp(m, L"both")   ? (MODE_CHAR | MODE_KEY)  /* 診斷用,會重複字元 */
                 : 0;
            if (!mode) { printf("--mode 只能是 char|packet|key|both|input\n"); return 2; }
        }
        else { printf("不認得的參數 %s(用法看檔頭)\n", u8(a)); return 2; }
    }

    if (probe)
    {
        printf("V=可見 U=Unicode wndproc A=ANSI wndproc\n");
        dump_foreground();
        found = NULL;
        EnumWindows(on_window, 1);
        /* 只在真的一個都沒列到時才喊。以前這句是無條件印的,底下卻跟著一大串視窗,自己打自己的臉 */
        if (!found) printf("遊戲在跑卻一個視窗都沒列到 = desktop 隔離,見檔頭第 1 點。\n");
        return 0;
    }

    if (!h)
    {
        if (!(h = find_target(wait_ms)))
        { printf("找不到目標視窗(等了 %d ms)。先跑 --probe 看看。\n", wait_ms); return 3; }
        printf("目標:%p\n", h);
    }

    if (cx >= 0) { send_click(h, cx, cy); Sleep(120); }
    while (clear-- > 0)    { send_key(h, VK_BACK); Sleep(gap); }
    if (key)                 { if (key_mods) combo_key(key_mods, key); else send_key(h, key); }
    if (text)                type_text(h, text);

    if (login)
    {
        wchar_t sid[64], otp[64];
        if (read_ascii(sid, 64) < 4 || read_ascii(otp, 64) < 4)
        { printf("stdin 要給兩行:第一行 sid,第二行 otp\n"); return 2; }

        printf("全選帳號欄(Ctrl+A,接下來打字就覆蓋掉)…\n");
        select_all();
        printf("打帳號(%d 字元)…\n", (int)wcslen(sid));
        type_text(h, sid);
        Sleep(150);

        if (fx >= 0) { printf("點第二欄 %d,%d…\n", fx, fy); send_click(h, fx, fy); }
        else         { printf("送 Tab…\n");                 ctrl_key(VK_TAB); }
        Sleep(150);

        printf("全選密碼欄(Ctrl+A)…\n");
        select_all();
        printf("打密碼(%d 字元,不印內容)…\n", (int)wcslen(otp));
        type_text(h, otp);
        SecureZeroMemory(otp, sizeof(otp));

        if (submit) { Sleep(200); printf("送 Enter。\n"); ctrl_key(VK_RETURN); }
        else printf("沒給 --submit,不按 Enter。自己確認兩欄對不對再送出。\n");
    }
    return 0;
}
