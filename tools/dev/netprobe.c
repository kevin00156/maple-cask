/* 連線探針:在 wine 底下對指定 host:port 做 getaddrinfo + connect,印出每一步的結果與耗時。
 *
 * 用途:分辨「遊戲連不上登入伺服器」是 (a) 我們這個 wine 的 winsock 路徑有問題,
 * 還是 (b) 遊戲/反作弊層的問題,還是 (c) 伺服器端在擋。
 * 只做 TCP 連線,不送任何資料、不帶任何帳密。
 *
 * build: x86_64-w64-mingw32-gcc -O2 -municode -o netprobe.exe netprobe.c -lws2_32
 */
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <stdio.h>

int wmain(int argc, wchar_t **argv)
{
    WSADATA wsa;
    struct addrinfo hints = { 0 }, *res = NULL, *ai;
    char host[256], port[16];
    LARGE_INTEGER f, t0, t1;
    int rc, n = 0;

    wcstombs(host, (argc > 1) ? argv[1] : L"tw.login.maplestory.beanfun.com", sizeof(host));
    wcstombs(port, (argc > 2) ? argv[2] : L"8484", sizeof(port));
    QueryPerformanceFrequency(&f);

    if ((rc = WSAStartup(MAKEWORD(2,2), &wsa)) != 0) { printf("WSAStartup failed: %d\n", rc); return 1; }
    printf("target %s:%s\n", host, port);

    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    QueryPerformanceCounter(&t0);
    rc = getaddrinfo(host, port, &hints, &res);
    QueryPerformanceCounter(&t1);
    printf("getaddrinfo: rc=%d (%.0f ms)\n", rc, (t1.QuadPart - t0.QuadPart) * 1000.0 / f.QuadPart);
    if (rc != 0) { printf("  WSAGetLastError=%d\n", WSAGetLastError()); return 2; }

    for (ai = res; ai; ai = ai->ai_next)
    {
        struct sockaddr_in *sa = (struct sockaddr_in *)ai->ai_addr;
        SOCKET s = socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);
        printf("  [%d] %s:%d  ", n++, inet_ntoa(sa->sin_addr), ntohs(sa->sin_port));
        if (s == INVALID_SOCKET) { printf("socket() failed WSA=%d\n", WSAGetLastError()); continue; }
        QueryPerformanceCounter(&t0);
        rc = connect(s, ai->ai_addr, (int)ai->ai_addrlen);
        QueryPerformanceCounter(&t1);
        if (rc == 0) printf("connect OK (%.0f ms)\n", (t1.QuadPart - t0.QuadPart) * 1000.0 / f.QuadPart);
        else         printf("connect FAILED WSA=%d (%.0f ms)\n", WSAGetLastError(),
                            (t1.QuadPart - t0.QuadPart) * 1000.0 / f.QuadPart);

        if (rc == 0 && argc > 3 && !wcscmp(argv[3], L"spin"))
        {
            u_long nb = 1;
            char buf[4096];
            DWORD start = GetTickCount(), last = start;
            long long total = 0, calls = 0, wouldblock = 0;
            ioctlsocket(s, FIONBIO, &nb);
            printf("  spin: 非阻塞 recv 迴圈,30 秒\n");
            while (GetTickCount() - start < 30000)
            {
                int n = recv(s, buf, sizeof(buf), 0);
                calls++;
                if (n > 0) total += n;
                else if (n < 0 && WSAGetLastError() == WSAEWOULDBLOCK) wouldblock++;
                else { printf("  recv 回 %d WSA=%d,結束\n", n, WSAGetLastError()); break; }
                if (GetTickCount() - last >= 2000)
                {
                    last = GetTickCount();
                    printf("  t=%2lus  收到累計 %lld B   recv 呼叫 %lld 次(其中 WOULDBLOCK %lld)\n",
                           (unsigned long)((last - start) / 1000), total, calls, wouldblock);
                    fflush(stdout);
                }
            }
            printf("  結束:收到 %lld B,recv %lld 次,WOULDBLOCK %lld 次\n", total, calls, wouldblock);
        }
        closesocket(s);
    }
    freeaddrinfo(res);
    WSACleanup();
    return 0;
}

/* 第二種模式(argv[3] = "spin"):連上之後把 socket 設成非阻塞,然後照遊戲的做法
 * 狂打 recv() —— 遊戲的接收迴圈就是 recv → WSAGetLastError → 若是 10035 就立刻重試。
 * 同時每秒印一次收到多少位元組。搭配 Linux 端的 `ss -tn` 看 Recv-Q:
 *   Recv-Q>0 而這裡一直 WSAEWOULDBLOCK = wine 沒把核心已收到的資料交出來。 */
