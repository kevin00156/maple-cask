/* modeprobe.c — 量「遊戲切到比螢幕方正的全螢幕解析度時,畫面是補黑邊還是被拉伸」
 *
 * 為什麼需要這支:楓之谷的拍賣場會用 D3D9 獨占全螢幕切到 1024x768(DXVK log:Setting display mode),
 * 要進拍賣場得先登入、有角色。這支用同一條路徑(D3D9 Windowed=FALSE → DXVK → ChangeDisplaySettings)
 * 依序切到命令列給的解析度,每個解析度畫:紅底 + 四角各一個 32x32 白塊 + 正中央一條 1px 的綠色十字,
 * 外面的人截 gamescope 的輸出圖就能量:紅色區寬高比 = 遊戲解析度的比例 → 補黑邊;= 輸出比例 → 被拉伸。
 *
 * 編譯: x86_64-w64-mingw32-gcc -O2 -o modeprobe.exe modeprobe.c -ld3d9
 * 用法: wine modeprobe.exe 1024x768:6 1920x1080:6   (每個解析度停 6 秒;stdout 印出切換時間點)
 * 每秒另印一行 cursor(GetCursorPos)與最後一個 WM_MOUSEMOVE 的座標,用來驗補黑邊時滑鼠有沒有對準。
 * 解析度前加 w / r 改走遊戲「視窗模式」的路徑(D3D9 Windowed=TRUE,不切模式):
 *   w1366x768:6 = 那個大小的 WS_POPUP(遊戲本體,style 94080000);
 *   r1024x768:6 = client 是那個大小、可調整大小的視窗(拍賣場,style 14ce0000)。
 */
#include <windows.h>
#include <d3d9.h>
#include <stdio.h>

static LPARAM last_move = -1;

static LRESULT CALLBACK wndproc( HWND hwnd, UINT msg, WPARAM wp, LPARAM lp )
{
    if (msg == WM_MOUSEMOVE) last_move = lp;
    return DefWindowProcA( hwnd, msg, wp, lp );
}

static void fill( IDirect3DDevice9 *dev, int x, int y, int w, int h, D3DCOLOR c )
{
    D3DRECT r = { x, y, x + w, y + h };
    IDirect3DDevice9_Clear( dev, 1, &r, D3DCLEAR_TARGET, c, 1.0f, 0 );
}

static void draw( IDirect3DDevice9 *dev, int w, int h )
{
    const D3DCOLOR white = D3DCOLOR_XRGB(255, 255, 255);
    IDirect3DDevice9_Clear( dev, 0, NULL, D3DCLEAR_TARGET, D3DCOLOR_XRGB(255, 0, 0), 1.0f, 0 );
    fill( dev, 0, 0, 32, 32, white );
    fill( dev, w - 32, 0, 32, 32, white );
    fill( dev, 0, h - 32, 32, 32, white );
    fill( dev, w - 32, h - 32, 32, 32, white );
    fill( dev, w / 2, 0, 1, h, D3DCOLOR_XRGB(0, 255, 0) );
    fill( dev, 0, h / 2, w, 1, D3DCOLOR_XRGB(0, 255, 0) );
}

int main( int argc, char **argv )
{
    IDirect3D9 *d3d = Direct3DCreate9( D3D_SDK_VERSION );
    IDirect3DDevice9 *dev = NULL;
    D3DPRESENT_PARAMETERS pp = { 0 };
    WNDCLASSA wc = { 0 };
    HWND hwnd;
    DWORD t0 = GetTickCount();
    int i;

    if (!d3d) { printf( "Direct3DCreate9 失敗\n" ); return 1; }
    wc.lpfnWndProc = wndproc;
    wc.hInstance = GetModuleHandleA( NULL );
    wc.lpszClassName = "modeprobe";
    RegisterClassA( &wc );
    hwnd = CreateWindowA( "modeprobe", "modeprobe", WS_POPUP | WS_VISIBLE, 0, 0, 640, 480,
                          NULL, NULL, wc.hInstance, NULL );

    for (i = 1; i < argc; i++)
    {
        int w, h, secs;
        DWORD end, next_report = 0;
        HRESULT hr;
        MSG msg;
        const char *arg = argv[i];
        char kind = (*arg == 'w' || *arg == 'r') ? *arg++ : 0;

        if (sscanf( arg, "%dx%d:%d", &w, &h, &secs ) != 3) { printf( "看不懂 %s\n", argv[i] ); return 1; }
        if (kind)
        {
            DWORD style = kind == 'w' ? 0x94080000 : 0x14ce0000;
            RECT rc = { 0, 0, w, h };
            AdjustWindowRect( &rc, style, FALSE );
            SetWindowLongA( hwnd, GWL_STYLE, style );
            SetWindowPos( hwnd, HWND_TOP, 0, 0, rc.right - rc.left, rc.bottom - rc.top,
                          SWP_FRAMECHANGED | SWP_SHOWWINDOW );
        }
        pp.Windowed = kind != 0;
        pp.SwapEffect = D3DSWAPEFFECT_DISCARD;
        pp.BackBufferWidth = w;
        pp.BackBufferHeight = h;
        pp.BackBufferFormat = D3DFMT_X8R8G8B8;
        pp.BackBufferCount = 1;
        pp.hDeviceWindow = hwnd;
        pp.PresentationInterval = D3DPRESENT_INTERVAL_ONE;
        if (!dev)
            hr = IDirect3D9_CreateDevice( d3d, D3DADAPTER_DEFAULT, D3DDEVTYPE_HAL, hwnd,
                                          D3DCREATE_SOFTWARE_VERTEXPROCESSING, &pp, &dev );
        else
            hr = IDirect3DDevice9_Reset( dev, &pp );
        {
            RECT wr;
            GetWindowRect( hwnd, &wr );
            printf( "t=%.1f mode %s hr=%#lx window %ldx%ld\n", (GetTickCount() - t0) / 1000.0, argv[i], hr,
                    wr.right - wr.left, wr.bottom - wr.top );
        }
        fflush( stdout );
        if (FAILED(hr)) return 1;

        end = GetTickCount() + secs * 1000;
        while (GetTickCount() < end)
        {
            while (PeekMessageA( &msg, NULL, 0, 0, PM_REMOVE )) DispatchMessageA( &msg );
            if (GetTickCount() >= next_report)
            {
                POINT pt;
                RECT cr;
                GetCursorPos( &pt );
                GetClientRect( hwnd, &cr );
                printf( "t=%.1f cursor %ld,%ld move %d,%d client %ldx%ld\n", (GetTickCount() - t0) / 1000.0, pt.x, pt.y,
                        last_move == -1 ? -1 : (short)LOWORD(last_move), last_move == -1 ? -1 : (short)HIWORD(last_move),
                        cr.right, cr.bottom );
                fflush( stdout );
                next_report = GetTickCount() + 1000;
            }
            draw( dev, w, h );
            IDirect3DDevice9_Present( dev, NULL, NULL, NULL, NULL );
        }
    }
    printf( "t=%.1f done\n", (GetTickCount() - t0) / 1000.0 );
    return 0;
}
