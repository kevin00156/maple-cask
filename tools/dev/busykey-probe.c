/* busykey-probe.c — 量「應用程式忙著的時候放開鍵,會不會多收到連發」,以及按住時的連發節奏
 *
 * 楓之谷用 Enter 確認瞬移石:遊戲收到 keydown 就開始換圖,主執行緒一秒以上不抽訊息。
 * winex11 只在這條執行緒抽訊息時才處理 X 事件,所以 wineserver 要等它載完才知道鍵放開了;
 * 這段時間 server 的連發計時器(patches/0012)會替一個早就放開的鍵排連發 keydown
 * (lParam bit 30),TranslateMessage 再生出 '\r' → 到新地圖聊天框自己彈出來(MC-20)。
 *
 * 這支程式重現那個順序,而且盡量像遊戲:
 *   - 每 pump_ms 抽一次訊息(遊戲是每幀一次;1ms 的迴圈量不出節奏問題)
 *   - 收到第一個 WM_KEYDOWN 後「忙」1500ms:
 *       busy=1  Sleep,完全不碰 X
 *       busy=2  每 10ms UpdateWindow 一次 —— win32u 會用 QS_PAINT 去處理 X 事件,Xlib 把 socket
 *               讀空,但按鍵事件留在 Xlib 的記憶體佇列裡沒處理(載入畫面在重畫時就是這樣)
 *   - 結束時印每個鍵連發間隔的分布
 *
 * 判讀:KEYUP 之後(或「忙」結束後、KEYUP 之前)出現 prev_state=1 的 KEYDOWN,就是幽靈連發。
 *
 * 編譯: x86_64-w64-mingw32-gcc -O2 -o busykey-probe.exe busykey-probe.c -lgdi32
 * 用法: wine busykey-probe.exe [秒數=10] [pump_ms=16] [busy=1]
 *       在獨立的 Xvfb 上用 xdotool 送鍵,不要對遊戲的 display 送。
 */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

static DWORD t0, busy_mode = 1;
static BOOL busy_done;
static DWORD last_down[256], n_rep[256], sum_gap[256], max_gap[256], min_gap[256];

static void busy( HWND hwnd )
{
    DWORD end = GetTickCount() + 1500;

    printf( "[%5lu ms]   忙 1500ms(busy=%lu)\n", GetTickCount() - t0, busy_mode );
    fflush( stdout );
    if (busy_mode == 1) Sleep( 1500 );
    else while (GetTickCount() < end)
    {
        InvalidateRect( hwnd, NULL, FALSE );
        UpdateWindow( hwnd );
        Sleep( 10 );
    }
    printf( "[%5lu ms]   忙完\n", GetTickCount() - t0 );
    fflush( stdout );
}

static LRESULT CALLBACK wndproc( HWND hwnd, UINT msg, WPARAM wp, LPARAM lp )
{
    DWORD now = GetTickCount() - t0, vk = wp & 0xff;

    switch (msg)
    {
    case WM_KEYDOWN:
    case WM_SYSKEYDOWN:
        if (lp & (1 << 30))
        {
            DWORD gap = now - last_down[vk];
            if (!n_rep[vk] || gap < min_gap[vk]) min_gap[vk] = gap;
            if (gap > max_gap[vk]) max_gap[vk] = gap;
            sum_gap[vk] += gap;
            n_rep[vk]++;
        }
        last_down[vk] = now;
        printf( "[%5lu ms] KEYDOWN vk=0x%02X prev_state=%d\n", now, (unsigned)vk, (lp & (1 << 30)) ? 1 : 0 );
        fflush( stdout );
        if (!busy_done && busy_mode)
        {
            busy_done = TRUE;
            busy( hwnd );
        }
        break;
    case WM_KEYUP:
    case WM_SYSKEYUP:
        printf( "[%5lu ms] KEYUP   vk=0x%02X\n", now, (unsigned)vk );
        fflush( stdout );
        break;
    case WM_CHAR:
        printf( "[%5lu ms] CHAR    0x%02X\n", now, (unsigned)wp );
        fflush( stdout );
        break;
    case WM_PAINT:
        ValidateRect( hwnd, NULL );
        return 0;
    case WM_DESTROY:
        PostQuitMessage( 0 );
        break;
    }
    return DefWindowProcW( hwnd, msg, wp, lp );
}

int main( int argc, char **argv )
{
    WNDCLASSW wc = { 0 };
    DWORD secs = argc > 1 ? atoi( argv[1] ) : 10;
    DWORD pump_ms = argc > 2 ? atoi( argv[2] ) : 16;
    HWND hwnd;
    MSG msg;
    int vk;

    if (argc > 3) busy_mode = atoi( argv[3] );

    wc.lpfnWndProc = wndproc;
    wc.hInstance = GetModuleHandleW( NULL );
    wc.lpszClassName = L"BusyKeyProbe";
    RegisterClassW( &wc );
    hwnd = CreateWindowW( L"BusyKeyProbe", L"Busy Key Probe", WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                          0, 0, 400, 200, NULL, NULL, wc.hInstance, NULL );
    SetForegroundWindow( hwnd );
    printf( "ready\n" );
    fflush( stdout );

    t0 = GetTickCount();
    while (GetTickCount() - t0 < secs * 1000)
    {
        while (PeekMessageW( &msg, NULL, 0, 0, PM_REMOVE ))
        {
            TranslateMessage( &msg );
            DispatchMessageW( &msg );
        }
        Sleep( pump_ms );
    }
    for (vk = 0; vk < 256; vk++)
        if (n_rep[vk]) printf( "連發 vk=0x%02X: %lu 次,間隔 平均 %lu / 最小 %lu / 最大 %lu ms\n", vk,
                               n_rep[vk], sum_gap[vk] / n_rep[vk], min_gap[vk], max_gap[vk] );
    return 0;
}
