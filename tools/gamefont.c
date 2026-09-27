/* 一字不差重現 MapleStory 的 CreateFont 請求(取自 fonttrace.log 的 NtGdiHfontCreate),
 * 印出 metrics 並把文字畫進 DIB,用來離線驗證字型調整,不必每次開遊戲。
 * 建置: x86_64-w64-mingw32-gcc -O2 -municode -fexec-charset=UTF-8 -o gamefont.exe gamefont.c -lgdi32
 */
#include <windows.h>
#include <stdio.h>

static const wchar_t *TEXT = L"黑蘿 世界樹的守護者 目前無法使用技能。Lv.250";

struct req { const wchar_t *face; LONG h, w, weight; BYTE charset, paf; const char *note; };
static struct req reqs[] = {
    { L"System",       16,  7, 700, 136, 0x22, "主力:1339 次" },
    { L"System",       16,  0, 700, 136, 0x22, "變體" },
    { L"MS Shell Dlg", -12, 0, 400, 136, 0x22, "" },
    { L"Courier",      16,  0, 400, 136, 0x31, "" },
    { L"simsun",       -12, 0, 700, 136, 0x00, "" },
    { L"Tahoma",       -11, 0, 400, 1,   0x00, "" },
};

#define W 760
#define H (sizeof(reqs)/sizeof(reqs[0]) * 30 + 10)

int wmain(int argc, wchar_t **argv)
{
    HDC screen = GetDC(NULL);
    HDC dc = CreateCompatibleDC(screen);
    BITMAPINFO bi = {0};
    bi.bmiHeader.biSize = sizeof(bi.bmiHeader);
    bi.bmiHeader.biWidth = W;
    bi.bmiHeader.biHeight = -(LONG)H;
    bi.bmiHeader.biPlanes = 1;
    bi.bmiHeader.biBitCount = 24;
    bi.bmiHeader.biCompression = BI_RGB;
    void *bits = NULL;
    HBITMAP bmp = CreateDIBSection(dc, &bi, DIB_RGB_COLORS, &bits, NULL, 0);
    SelectObject(dc, bmp);
    RECT all = { 0, 0, W, (LONG)H };
    FillRect(dc, &all, (HBRUSH)GetStockObject(WHITE_BRUSH));
    SetBkMode(dc, TRANSPARENT);
    HBRUSH yellow = CreateSolidBrush(RGB(255, 200, 40));

    const DWORD stride = ((W*3+3)&~3);
    int y = 5;
    for (unsigned i = 0; i < sizeof(reqs)/sizeof(reqs[0]); i++) {
        LOGFONTW lf = {0};
        lf.lfHeight = reqs[i].h;
        lf.lfWidth  = reqs[i].w;
        lf.lfWeight = reqs[i].weight;
        lf.lfCharSet = reqs[i].charset;
        lf.lfPitchAndFamily = reqs[i].paf;
        lstrcpynW(lf.lfFaceName, reqs[i].face, LF_FACESIZE);

        HFONT f = CreateFontIndirectW(&lf);
        HGDIOBJ old = SelectObject(dc, f);

        wchar_t got[LF_FACESIZE] = {0};
        GetTextFaceW(dc, LF_FACESIZE, got);
        TEXTMETRICW tm; GetTextMetricsW(dc, &tm);
        SIZE sz = {0}; GetTextExtentPoint32W(dc, L"黑蘿", 2, &sz);

        char ureq[128], ugot[128];
        WideCharToMultiByte(CP_UTF8, 0, reqs[i].face, -1, ureq, sizeof(ureq), NULL, NULL);
        WideCharToMultiByte(CP_UTF8, 0, got, -1, ugot, sizeof(ugot), NULL, NULL);
        printf("  %-13s h=%-4ld w=%ld wt=%ld cs=%-3d -> %-18s tmH=%-3ld asc=%-3ld desc=%-3ld intLead=%-2ld 「黑蘿」=%ldx%ld  %s\n",
               ureq, reqs[i].h, reqs[i].w, reqs[i].weight, reqs[i].charset, ugot,
               tm.tmHeight, tm.tmAscent, tm.tmDescent, tm.tmInternalLeading,
               sz.cx, sz.cy, reqs[i].note);

        /* 黃底條高度 = tmHeight,就是遊戲配版面用的高度 */
        RECT r = { 150, y, W - 6, y + tm.tmHeight };
        FillRect(dc, &r, yellow);
        SetTextColor(dc, RGB(0,0,0));
        TextOutW(dc, 150, y, TEXT, lstrlenW(TEXT));

        /* 這條黃底裡有幾種不同的 RGB?純 1-bit 點陣 = 2(底色 + 黑),
         * 一旦被抗鋸齒或走外框縮放就會冒出一堆中間色 */
        DWORD seen[64]; int nseen = 0;
        for (LONG yy = y; yy < y + tm.tmHeight && yy < (LONG)H; yy++) {
            const BYTE *row = (const BYTE *)bits + (size_t)yy * stride;
            for (int xx = 150; xx < W - 6; xx++) {
                DWORD c = row[xx*3] | (row[xx*3+1] << 8) | (row[xx*3+2] << 16);
                int k = 0;
                while (k < nseen && seen[k] != c) k++;
                if (k == nseen && nseen < (int)(sizeof(seen)/sizeof(seen[0]))) seen[nseen++] = c;
            }
        }
        printf("%*sRGB 值 %d 種%s\n", 17, "", nseen, nseen <= 3 ? "" : "  <-- 不是純點陣");

        LOGFONTW lb = {0}; lb.lfHeight = -11; lstrcpynW(lb.lfFaceName, L"Tahoma", LF_FACESIZE);
        HFONT fb = CreateFontIndirectW(&lb); SelectObject(dc, fb);
        char lbl[160]; snprintf(lbl, sizeof(lbl), "%s %ld -> %s tmH=%ld", ureq, reqs[i].h, ugot, tm.tmHeight);
        wchar_t wl[160]; MultiByteToWideChar(CP_UTF8, 0, lbl, -1, wl, 160);
        TextOutW(dc, 4, y, wl, lstrlenW(wl));
        DeleteObject(fb);

        SelectObject(dc, old);
        DeleteObject(f);
        y += 30;
    }

    BITMAPFILEHEADER fh = {0};
    DWORD img = stride*H;
    fh.bfType = 0x4D42; fh.bfOffBits = sizeof(fh)+sizeof(bi.bmiHeader); fh.bfSize = fh.bfOffBits+img;
    /* 預設寫在目前目錄:這支 exe 也要能在真 Windows 上跑當基準,那邊沒有 Z: */
    const wchar_t *out = argc > 1 ? argv[1] : L"gamefont.bmp";
    FILE *o = _wfopen(out, L"wb");
    if (o) { fwrite(&fh,sizeof(fh),1,o); bi.bmiHeader.biSizeImage=img; fwrite(&bi.bmiHeader,sizeof(bi.bmiHeader),1,o); fwrite(bits,img,1,o); fclose(o); }
    printf("wrote %ls\n", o ? out : L"(nothing: fopen failed)");
    return 0;
}
