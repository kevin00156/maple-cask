/* imeprobe.c — 量「在 wine 底下打中文時,Win32 應用實際收到什麼訊息」
 *
 * 為什麼需要這支:遊戲打不出中文,但斷點可能在三個地方
 *   (a) fcitx 根本沒被觸發    (b) wine 的 XIM 沒把結果字串轉成 Win32 訊息
 *   (c) 訊息有到但遊戲不吃它
 * 開遊戲只能看到「打不出來」這個結果,分不出是哪一個。這支把 (a)(b) 獨立出來測:
 * 它是一個**裸視窗**,故意做成跟遊戲同一個形狀 —— 沒有 EDIT 子控制項、不自己畫 caret、
 * 不呼叫任何 Imm* 去「幫忙」啟用 IME。所以:
 *
 *   probe 收得到中文 → wine 這一層是通的,問題在遊戲(往 (c) 查)
 *   probe 收不到     → wine 這一層就斷了,遊戲再怎麼改也沒用
 *
 * ── 已知的背景(2026-09-14 用 WINEDEBUG=+xim 量到)────────────────────────
 * wine 要求 on-the-spot(0x202 = preedit callbacks + status callbacks),
 * fcitx5 的 XIM server **一種 callbacks style 都不提供**,wine 退到
 * 0x104(preedit position + status area, over-the-spot)。
 * 在這個 style 下組字過程不會變成 WM_IME_COMPOSITION(fcitx 自己畫候選窗),
 * 但選定的字走 winex11.drv/keyboard.c 的
 *   XmbLookupString → status==XLookupChars → xim_set_result_string → WM_IME_CHAR
 * 這條路。所以**要看的就是 WM_IME_CHAR 到底有沒有來**。
 *
 * ⚠ --ansi:遊戲的 wndproc 是 ANSI 還是 Unicode 決定了完全不同的一條路。
 *   Unicode wndproc 收到的 WM_CHAR 是原始的 UTF-16 碼位(U+6E2C)。
 *   ANSI wndproc 收到的是 wine 幫忙轉成 **ACP(這裡是 CP950)的雙位元組**,
 *   而且是**拆成兩個 WM_CHAR**、一次一個 byte 送 —— 應用要自己把 lead/trail byte 拼回來。
 *   ACP 只要不是 950,U+6E2C 根本轉不出去,會變成 '?' 或整個掉。
 *   預設是 Unicode;加 --ansi 就扮成 ANSI wndproc,兩種都測才知道遊戲踩的是哪條。
 *
 * 判讀表:
 *   WM_IME_CHAR(非 ASCII)          → wine 層通。問題在遊戲。
 *   只有 WM_KEYDOWN、沒有 IME 訊息 → fcitx 沒攔到這個視窗的按鍵(XIC 沒 focus,
 *                                     或 Ctrl+Space 被別人吃掉)
 *   WM_IME_STARTCOMPOSITION 有、
 *   WM_IME_CHAR 沒有               → 組字有進來但 commit 斷了 → 往 style 協商查
 *   WM_CHAR 帶一個 ASCII 的 'h'    → fcitx 根本沒切到注音,按鍵直接穿過去了
 *
 * 建置: x86_64-w64-mingw32-gcc -O2 -municode -fexec-charset=UTF-8 -o imeprobe.exe imeprobe.c -limm32
 * 用法: wine imeprobe.exe [--seconds 30]
 *       開起來之後點一下視窗 → Ctrl+Space 切輸入法 → 打幾個中文字。
 *       tools/dev/imetest.py 會用 XTEST 幫你做完這整段,不必自己按。
 */
#include <windows.h>
#include <imm.h>
#include <stdio.h>

static DWORD t0;
static int ime_char_count, wm_char_nonascii_count;
static int ansi_mode;
static int filter_hwnd;
static int own_by_ime;    /* 把主視窗的 owner 設成 default IME window(重現遊戲) */   /* 訊息迴圈只收自己主視窗的訊息(模擬遊戲) */
static unsigned char dbcs_lead;   /* ANSI 模式下,收到一半的 DBCS 字元 */

/* 寬字串轉 UTF-8 再 printf。不用 wprintf —— wine 的 msvcrt 寬字元輸出到 Unix 終端會亂
 * (跟 tools/mapletype.c 同一個坑) */
static const char *u8( const wchar_t *w, int len )
{
    static char buf[4][512];
    static int n;
    char *p = buf[n = (n + 1) & 3];
    int r = WideCharToMultiByte( CP_UTF8, 0, w, len, p, sizeof(buf[0]) - 1, NULL, NULL );
    p[r > 0 ? r : 0] = 0;
    return p;
}

static void log_line( const char *fmt, ... )
{
    va_list ap;
    printf( "[%5lu ms] ", GetTickCount() - t0 );
    va_start( ap, fmt );
    vprintf( fmt, ap );
    va_end( ap );
    putchar( '\n' );
    fflush( stdout );
}

/* WM_IME_COMPOSITION 的 lParam 是一組 GCS_* 旗標,要自己去 IMC 把字串撈出來。
 * 撈不到不算錯 —— over-the-spot 下組字內容本來就可能不經過我們 */
static void dump_composition( HWND hwnd, LPARAM lp )
{
    HIMC imc = ImmGetContext( hwnd );
    wchar_t buf[256];
    LONG n;

    if (!imc) { log_line( "    ImmGetContext = NULL(這個視窗沒有 IME context)" ); return; }

    if (lp & GCS_COMPSTR)
    {
        n = ImmGetCompositionStringW( imc, GCS_COMPSTR, buf, sizeof(buf) - 2 );
        if (n > 0) log_line( "    GCS_COMPSTR  = \"%s\"", u8( buf, n / sizeof(wchar_t) ) );
    }
    if (lp & GCS_RESULTSTR)
    {
        n = ImmGetCompositionStringW( imc, GCS_RESULTSTR, buf, sizeof(buf) - 2 );
        if (n > 0)
        {
            log_line( "    GCS_RESULTSTR = \"%s\"  ★ 結果字串進來了", u8( buf, n / sizeof(wchar_t) ) );
            ime_char_count++;
        }
    }
    ImmReleaseContext( hwnd, imc );
}

static LRESULT CALLBACK wndproc( HWND hwnd, UINT msg, WPARAM wp, LPARAM lp )
{
    wchar_t ch;

    switch (msg)
    {
    case WM_KEYDOWN:
    case WM_SYSKEYDOWN:
        /* VK_PROCESSKEY(0xE5)= 這個按鍵被 IME 吃掉了,是 IME 有在運作的第一個跡象 */
        log_line( "WM_%sKEYDOWN vk=0x%02X%s", msg == WM_SYSKEYDOWN ? "SYS" : "",
                  (unsigned)wp, wp == VK_PROCESSKEY ? "  ← VK_PROCESSKEY(IME 攔走了)" : "" );
        break;
    case WM_KEYUP:
    case WM_SYSKEYUP:
        log_line( "WM_%sKEYUP   vk=0x%02X", msg == WM_SYSKEYUP ? "SYS" : "", (unsigned)wp );
        break;

    case WM_CHAR:
    case WM_SYSCHAR:
        if (ansi_mode)
        {
            /* ANSI wndproc:wine 把字轉成 ACP 再一個 byte 一個 WM_CHAR 送。
             * 遊戲在 Windows 上就是這樣拼回來的,所以我們也要拼,不然看到的都是半個字 */
            unsigned char b = (unsigned char)wp;
            log_line( "WM_CHAR    byte=0x%02X%s", b,
                      dbcs_lead ? " (trail)" : (b > 0x7F ? " (lead?)" : "") );
            if (dbcs_lead)
            {
                char pair[2] = { (char)dbcs_lead, (char)b };
                wchar_t out[4] = {0};
                int n = MultiByteToWideChar( CP_ACP, 0, pair, 2, out, 4 );
                dbcs_lead = 0;
                wm_char_nonascii_count++;
                if (n > 0) log_line( "    → 拼回 U+%04X \"%s\"  ★ 非 ASCII 進來了", out[0], u8( out, 1 ) );
                else       log_line( "    → MultiByteToWideChar 失敗(ACP 轉不出這個字)" );
            }
            else if (IsDBCSLeadByte( b )) dbcs_lead = b;
            break;
        }
        ch = (wchar_t)wp;
        if (wp > 0x7F) wm_char_nonascii_count++;
        log_line( "WM_%sCHAR    U+%04X \"%s\"%s", msg == WM_SYSCHAR ? "SYS" : "",
                  (unsigned)wp, u8( &ch, 1 ), wp > 0x7F ? "  ★ 非 ASCII" : "" );
        break;
    case WM_DEADCHAR:
        log_line( "WM_DEADCHAR U+%04X", (unsigned)wp );
        break;

    /* 這才是重點。wine 的 XIM commit 路徑最後就是送這個 */
    case WM_IME_CHAR:
        ime_char_count++;
        if (ansi_mode)
        {
            /* ANSI 下 WM_IME_CHAR 的 wParam 是 ACP 的雙位元組打包在一起
             * (高位 lead、低位 trail),跟 WM_CHAR 拆兩次送不一樣 */
            char pair[2] = { (char)((wp >> 8) & 0xFF), (char)(wp & 0xFF) };
            wchar_t out[4] = {0};
            int n = MultiByteToWideChar( CP_ACP, 0, pair[0] ? pair : pair + 1, pair[0] ? 2 : 1, out, 4 );
            log_line( "WM_IME_CHAR wParam=0x%04X → %s  ★★ wine 層通了", (unsigned)wp,
                      n > 0 ? u8( out, 1 ) : "(ACP 轉不出來)" );
            break;
        }
        ch = (wchar_t)wp;
        log_line( "WM_IME_CHAR U+%04X \"%s\"  ★★ wine 層通了", (unsigned)wp, u8( &ch, 1 ) );
        break;

    case WM_IME_STARTCOMPOSITION:
        log_line( "WM_IME_STARTCOMPOSITION" );
        break;
    case WM_IME_COMPOSITION:
        log_line( "WM_IME_COMPOSITION lParam=0x%lX%s%s", (unsigned long)lp,
                  (lp & GCS_COMPSTR) ? " GCS_COMPSTR" : "", (lp & GCS_RESULTSTR) ? " GCS_RESULTSTR" : "" );
        dump_composition( hwnd, lp );
        break;
    case WM_IME_ENDCOMPOSITION:
        log_line( "WM_IME_ENDCOMPOSITION" );
        break;
    case WM_IME_NOTIFY:
        log_line( "WM_IME_NOTIFY wParam=0x%X", (unsigned)wp );
        break;
    case WM_IME_SETCONTEXT:
        log_line( "WM_IME_SETCONTEXT active=%d", (int)wp );
        break;

    case WM_INPUTLANGCHANGE:
        log_line( "WM_INPUTLANGCHANGE hkl=%p", (void *)lp );
        break;

    case WM_SETFOCUS:
        log_line( "WM_SETFOCUS   ← 視窗拿到焦點了(XIC 應該在這時 XSetICFocus)" );
        break;
    case WM_KILLFOCUS:
        log_line( "WM_KILLFOCUS" );
        break;

    case WM_DESTROY:
        PostQuitMessage( 0 );
        break;
    }
    return ansi_mode ? DefWindowProcA( hwnd, msg, wp, lp )
                     : DefWindowProcW( hwnd, msg, wp, lp );
}

int wmain( int argc, wchar_t **argv )
{
    WNDCLASSW wc = { 0 };
    HWND hwnd;
    MSG msg;
    int seconds = 30, i;
    HKL hkl;
    HIMC imc;

    for (i = 1; i < argc; i++)
    {
        if (!wcscmp( argv[i], L"--seconds" ) && i + 1 < argc) seconds = wcstol( argv[++i], NULL, 10 );
        else if (!wcscmp( argv[i], L"--ansi" )) ansi_mode = 1;
        else if (!wcscmp( argv[i], L"--filter-hwnd" )) filter_hwnd = 1;
        else if (!wcscmp( argv[i], L"--own-by-ime" )) own_by_ime = 1;
    }

    wc.lpfnWndProc = wndproc;
    wc.hInstance = GetModuleHandleW( NULL );
    wc.lpszClassName = L"MapleIMEProbe";
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    wc.hCursor = LoadCursorW( NULL, (const WCHAR *)IDC_ARROW );
    /* RegisterClassA 與 RegisterClassW 的差別不只是名字:它決定 user32 要不要幫這個視窗
     * 把 Unicode 訊息轉成 ACP。遊戲踩的是哪一條,就得用哪一條測 */
    if (ansi_mode)
    {
        WNDCLASSA wa = { 0 };
        wa.lpfnWndProc = wndproc;
        wa.hInstance = wc.hInstance;
        wa.lpszClassName = "MapleIMEProbeA";
        wa.hbrBackground = wc.hbrBackground;
        wa.hCursor = wc.hCursor;
        RegisterClassA( &wa );
    }
    else RegisterClassW( &wc );

    /* 故意不建任何子視窗、不用 EDIT:遊戲是自繪 UI,主視窗底下零子視窗(見 mapletype.c 檔頭)。
     * 用 EDIT 測會測到 user32 幫 EDIT 做的那一套,結論套不回遊戲。
     * 放在 (60,60) 的小視窗,不搶版面、不全螢幕 */
    /* 標題一定要純 ASCII:中文塞不進 Latin-1 的 WM_NAME,KWin 只會設 _NET_WM_NAME,
     靠 WM_NAME 找視窗的工具(python-xlib 的 get_wm_name 就是)會完全看不到它 */
    if (ansi_mode)
        hwnd = CreateWindowA( "MapleIMEProbeA", "IME Probe - click me, then type Chinese",
                              WS_OVERLAPPEDWINDOW | WS_VISIBLE, 60, 60, 560, 180,
                              NULL, NULL, wc.hInstance, NULL );
    else
        hwnd = CreateWindowW( L"MapleIMEProbe", L"IME Probe - click me, then type Chinese",
                              WS_OVERLAPPEDWINDOW | WS_VISIBLE, 60, 60, 560, 180,
                              NULL, NULL, wc.hInstance, NULL );
    SetForegroundWindow( hwnd );
    SetFocus( hwnd );

    {
        /* ★ win32u/message.c 的 handle_internal_message 有這一行:
         *     if (!ime_hwnd || ime_hwnd == NtUserGetParent( hwnd )) return 0;
         * GetParent() 對 top-level 視窗回傳的是 **owner**,不是 parent。
         * 只要主視窗的 owner 剛好是自己 thread 的 default IME window,
         * 整個 WM_IME_NOTIFY 就被丟掉 —— IME 從此不會產生任何字元訊息。 */
        HWND ime_wnd = ImmGetDefaultIMEWnd( hwnd );
        printf( "ImmGetDefaultIMEWnd=%p  GetParent(主視窗)=%p  相等=%s\n",
                ime_wnd, GetParent( hwnd ), ime_wnd == GetParent( hwnd ) ? "是 ← 會壞" : "否" );
        if (own_by_ime && ime_wnd)
        {
            SetWindowLongPtrW( hwnd, GWLP_HWNDPARENT, (LONG_PTR)ime_wnd );
            printf( "已把 owner 設成 IME 視窗,現在 GetParent=%p\n", GetParent( hwnd ) );
        }
    }

    hkl = GetKeyboardLayout( 0 );
    imc = ImmGetContext( hwnd );
    printf( "hwnd=%p  HKL=%p  ImmGetContext=%p  ImmIsIME=%d\n",
            hwnd, (void *)hkl, (void *)imc, ImmIsIME( hkl ) );
    printf( "wndproc=%s  IsWindowUnicode=%d  GetACP()=%u  GetOEMCP()=%u  訊息迴圈=%s\n",
            ansi_mode ? "ANSI" : "Unicode", IsWindowUnicode( hwnd ), GetACP(), GetOEMCP(),
            filter_hwnd ? "PeekMessage(hwnd) 只收主視窗" : "PeekMessage(NULL) 全收" );
    if (imc) ImmReleaseContext( hwnd, imc );
    printf( "視窗建好了。點一下它 → Ctrl+Space 切輸入法 → 打中文。%d 秒後自動結束。\n\n", seconds );
    fflush( stdout );

    t0 = GetTickCount();
    while (GetTickCount() - t0 < (DWORD)seconds * 1000)
    {
        /* ★ 這一行就是實驗本身。wine 的 IME 把 WM_IME_NOTIFY 非同步 PostMessage 到
         * **default IME window**(另一個 HWND),不是應用的主視窗。訊息迴圈只要帶了
         * hwnd 過濾,那個訊息就永遠取不出來 → IMC 不會 open、字元訊息不會產生。
         * 在 Windows 上這條路是同步走完的,所以同一份程式在 Windows 上沒事。 */
        while (PeekMessageW( &msg, filter_hwnd ? hwnd : NULL, 0, 0, PM_REMOVE ))
        {
            if (msg.message == WM_QUIT) goto done;
            TranslateMessage( &msg );
            DispatchMessageW( &msg );
        }
        Sleep( 5 );
    }
done:
    printf( "\n--- 結束 ---\n" );
    printf( "WM_IME_CHAR / GCS_RESULTSTR 次數 : %d\n", ime_char_count );
    printf( "非 ASCII 的 WM_CHAR 次數         : %d\n", wm_char_nonascii_count );
    printf( "判定: %s\n", (ime_char_count || wm_char_nonascii_count)
            ? "★ wine 層通 —— 中文有進到 Win32 訊息佇列。問題在遊戲那一側。"
            : "✗ wine 層沒通 —— 一個中文字元都沒進來。" );
    return (ime_char_count || wm_char_nonascii_count) ? 0 : 1;
}
