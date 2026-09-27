/* keyrepeat-probe.c — 量「按住一個鍵時,Windows 應用實際收到什麼」
 *
 * 為什麼需要這支:楓之谷「按住 Shift 只觸發一次」這個問題,不能用 xdotool 之類的
 * 合成輸入去測(BlackCipher 活著時那看起來就是巨集),只能請人真的按住鍵。
 * 這支程式把兩條可能的輸入路徑同時記錄下來,一次按鍵就能分辨是哪一條斷掉:
 *
 *   A. 訊息佇列  WM_KEYDOWN 的重複(lParam bit 0..15 = repeat count,bit 30 = 前一次狀態)
 *   B. 輪詢      GetAsyncKeyState 每 16ms 取樣
 *
 * 判讀:
 *   A 有重複、B 持續為按下  → 輸入層正常,問題在遊戲或反作弊
 *   A 沒重複、B 持續為按下  → auto-repeat 沒送到訊息佇列(這才是 wine 的 bug)
 *   A 沒重複、B 一下一下跳  → X server 或驅動把 repeat 拆成了 press/release 對
 *
 * 編譯: x86_64-w64-mingw32-gcc -O2 -o keyrepeat-probe.exe keyrepeat-probe.c -lgdi32
 * 用法: wine keyrepeat-probe.exe        然後按住 Shift(或任何鍵)約 3 秒,15 秒後自動結束
 */
#include <windows.h>
#include <stdio.h>

static DWORD t0;
static int down_count[256];

static LRESULT CALLBACK wndproc( HWND hwnd, UINT msg, WPARAM wp, LPARAM lp )
{
    switch (msg)
    {
    case WM_KEYDOWN:
    case WM_SYSKEYDOWN:
        down_count[wp & 0xff]++;
        printf( "[%5lu ms] WM_%sKEYDOWN vk=0x%02X repeat_count=%u prev_state=%d  (第 %d 次)\n",
                GetTickCount() - t0, msg == WM_SYSKEYDOWN ? "SYS" : "",
                (unsigned)wp, (unsigned)(lp & 0xffff), (lp & (1 << 30)) ? 1 : 0,
                down_count[wp & 0xff] );
        fflush( stdout );
        break;
    case WM_KEYUP:
    case WM_SYSKEYUP:
        printf( "[%5lu ms] WM_%sKEYUP   vk=0x%02X\n", GetTickCount() - t0,
                msg == WM_SYSKEYUP ? "SYS" : "", (unsigned)wp );
        fflush( stdout );
        break;
    case WM_DESTROY:
        PostQuitMessage( 0 );
        break;
    }
    return DefWindowProcW( hwnd, msg, wp, lp );
}

int main( void )
{
    WNDCLASSW wc = { 0 };
    HWND hwnd;
    MSG msg;
    SHORT prev[256] = { 0 };
    DWORD last_poll = 0;
    UINT speed = 0, delay = 0;

    wc.lpfnWndProc = wndproc;
    wc.hInstance = GetModuleHandleW( NULL );
    wc.lpszClassName = L"KeyRepeatProbe";
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    RegisterClassW( &wc );
    hwnd = CreateWindowW( L"KeyRepeatProbe", L"Key Repeat Probe - 按住一個鍵約 3 秒",
                          WS_OVERLAPPEDWINDOW | WS_VISIBLE, 100, 100, 640, 200,
                          NULL, NULL, wc.hInstance, NULL );
    SetForegroundWindow( hwnd );

    SystemParametersInfoW( SPI_GETKEYBOARDSPEED, 0, &speed, 0 );
    SystemParametersInfoW( SPI_GETKEYBOARDDELAY, 0, &delay, 0 );
    printf( "SPI_GETKEYBOARDSPEED=%u (0..31,越大越快)  SPI_GETKEYBOARDDELAY=%u (0..3)\n", speed, delay );
    printf( "請點一下這個視窗讓它取得焦點,然後按住 Shift 約 3 秒。15 秒後自動結束。\n\n" );
    fflush( stdout );

    t0 = GetTickCount();
    while (GetTickCount() - t0 < 15000)
    {
        while (PeekMessageW( &msg, NULL, 0, 0, PM_REMOVE ))
        {
            if (msg.message == WM_QUIT) goto done;
            TranslateMessage( &msg );
            DispatchMessageW( &msg );
        }
        if (GetTickCount() - last_poll >= 16)
        {
            int vk;
            last_poll = GetTickCount();
            for (vk = 0x08; vk < 0x100; vk++)
            {
                SHORT s = (GetAsyncKeyState( vk ) & 0x8000) ? 1 : 0;
                if (s != prev[vk])
                {
                    printf( "[%5lu ms]   GetAsyncKeyState vk=0x%02X -> %s\n",
                            GetTickCount() - t0, vk, s ? "按下" : "放開" );
                    fflush( stdout );
                    prev[vk] = s;
                }
            }
        }
        Sleep( 1 );
    }
done:
    printf( "\n--- 結束。各鍵收到的 WM_KEYDOWN 次數 ---\n" );
    {
        int vk;
        for (vk = 0; vk < 256; vk++)
            if (down_count[vk]) printf( "  vk=0x%02X : %d 次\n", vk, down_count[vk] );
    }
    return 0;
}
