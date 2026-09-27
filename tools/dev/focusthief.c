/* 焦點竊取探針:行為跟 MapleStory 一樣 —— 不斷對自己呼叫 SetForegroundWindow。
 *
 * 用途:驗 patches/0008(winex11 的 "RequestNetActiveWindow" 登錄鍵)有沒有生效,
 * 不必開遊戲。遊戲那條路徑要先過登入伺服器,而伺服器連線是間歇失敗的
 * (docs/known-issues.md 的「一定要經 gamescope」),拿它當量測載具等於在擲骰子。
 *
 * 量法:tools/dev/focustest.sh 的 PROC_NAME=focusthief.exe 模式。
 *   沒有那個鍵    → 桌面焦點會被它搶走(上游 10.16 行為)
 *   "N"           → 搶不走(wine 10.0 行為)
 *
 * build: x86_64-w64-mingw32-gcc -O2 -municode -o focusthief.exe focusthief.c
 */
#include <windows.h>

int wmain(int argc, wchar_t **argv)
{
    WNDCLASSW wc = { 0 };
    HWND hwnd;
    MSG msg;
    int ms = (argc > 1) ? _wtoi(argv[1]) : 500;   /* 每幾毫秒搶一次 */

    wc.lpfnWndProc = DefWindowProcW;
    wc.hInstance = GetModuleHandleW(NULL);
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    wc.lpszClassName = L"FocusThiefClass";
    RegisterClassW(&wc);

    hwnd = CreateWindowExW(0, L"FocusThiefClass", L"FocusThief", WS_OVERLAPPEDWINDOW,
                           200, 200, 800, 600, NULL, NULL, wc.hInstance, NULL);
    if (!hwnd) return 1;
    ShowWindow(hwnd, SW_SHOW);

    for (;;)
    {
        while (PeekMessageW(&msg, NULL, 0, 0, PM_REMOVE))
        {
            if (msg.message == WM_QUIT) return 0;
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
        SetForegroundWindow(hwnd);
        Sleep(ms);
    }
}
