/* WinHTTP WebSocket client: ws:// and wss://, the system's TLS and proxy.
 *
 * WinHTTP allows one send and one receive in flight at once on a WebSocket
 * handle ("Concurrency in WinHTTP"), so the receiving thread owns the handles
 * and closes them in ani_ws_free; senders serialise on send_lock, and
 * ani_ws_shutdown sends the close frame that makes a blocked receive return. */
#if defined(_WIN32)
#include "ap_ws.h"

#include <windows.h>
#include <winhttp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct AniWs {
    HINTERNET session, connect, request, socket;
    CRITICAL_SECTION send_lock;
    volatile LONG closing;
};

bool ani_ws_supports_tls(void) { return true; }

static void close_handles(AniWs *ws)
{
    if (ws->socket) WinHttpCloseHandle(ws->socket);
    if (ws->request) WinHttpCloseHandle(ws->request);
    if (ws->connect) WinHttpCloseHandle(ws->connect);
    if (ws->session) WinHttpCloseHandle(ws->session);
}

AniWs *ani_ws_connect(const char *host, int port, bool secure,
                      char *err, size_t errlen)
{
    wchar_t whost[256];
    AniWs *ws = calloc(1, sizeof *ws);
    DWORD status = 0, size = sizeof status;
    DWORD timeout = 10000;

    if (!ws) return NULL;
    InitializeCriticalSection(&ws->send_lock);
    if (!MultiByteToWideChar(CP_UTF8, 0, host, -1, whost, 256)) {
        snprintf(err, errlen, "bad host name");
        goto fail;
    }
    ws->session = WinHttpOpen(L"AnimaniacsRecompiled-AP/1",
                              WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY,
                              WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    if (!ws->session) {   /* AUTOMATIC_PROXY needs Windows 8.1 */
        ws->session = WinHttpOpen(L"AnimaniacsRecompiled-AP/1",
                                  WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                                  WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    }
    if (!ws->session) goto fail_win;
    WinHttpSetTimeouts(ws->session, timeout, timeout, timeout, timeout);
    ws->connect = WinHttpConnect(ws->session, whost, (INTERNET_PORT)port, 0);
    if (!ws->connect) goto fail_win;
    ws->request = WinHttpOpenRequest(ws->connect, L"GET", L"/", NULL,
                                     WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES,
                                     secure ? WINHTTP_FLAG_SECURE : 0);
    if (!ws->request) goto fail_win;
    if (!WinHttpSetOption(ws->request, WINHTTP_OPTION_UPGRADE_TO_WEB_SOCKET, NULL, 0))
        goto fail_win;
    if (!WinHttpSendRequest(ws->request, WINHTTP_NO_ADDITIONAL_HEADERS, 0,
                            WINHTTP_NO_REQUEST_DATA, 0, 0, 0) ||
        !WinHttpReceiveResponse(ws->request, NULL))
        goto fail_win;
    WinHttpQueryHeaders(ws->request, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                        WINHTTP_HEADER_NAME_BY_INDEX, &status, &size, WINHTTP_NO_HEADER_INDEX);
    if (status != 101) {
        snprintf(err, errlen, "upgrade refused (HTTP %lu)", (unsigned long)status);
        goto fail;
    }
    ws->socket = WinHttpWebSocketCompleteUpgrade(ws->request, 0);
    if (!ws->socket) goto fail_win;
    WinHttpCloseHandle(ws->request);
    ws->request = NULL;
    return ws;
fail_win:
    snprintf(err, errlen, "WinHTTP error %lu", (unsigned long)GetLastError());
fail:
    close_handles(ws);
    DeleteCriticalSection(&ws->send_lock);
    free(ws);
    return NULL;
}

int ani_ws_send(AniWs *ws, const char *text, size_t len)
{
    DWORD rc;
    EnterCriticalSection(&ws->send_lock);
    rc = ws->closing ? ERROR_CANCELLED
         : WinHttpWebSocketSend(ws->socket, WINHTTP_WEB_SOCKET_UTF8_MESSAGE_BUFFER_TYPE,
                                (PVOID)text, (DWORD)len);
    LeaveCriticalSection(&ws->send_lock);
    return rc == NO_ERROR ? 0 : -1;
}

int ani_ws_recv(AniWs *ws, char **out, size_t *outlen)
{
    size_t cap = 65536, len = 0;
    char *msg = malloc(cap + 1);

    if (!msg) return -1;
    for (;;) {
        DWORD got = 0;
        WINHTTP_WEB_SOCKET_BUFFER_TYPE type;
        DWORD rc;
        if (cap - len < 16384) {
            char *grown = cap < (64u << 20) ? realloc(msg, cap * 2 + 1) : NULL;
            if (!grown) { free(msg); return -1; }
            msg = grown;
            cap *= 2;
        }
        rc = WinHttpWebSocketReceive(ws->socket, msg + len, (DWORD)(cap - len), &got, &type);
        if (rc != NO_ERROR) { free(msg); return -1; }
        if (type == WINHTTP_WEB_SOCKET_CLOSE_BUFFER_TYPE) { free(msg); return 0; }
        len += got;
        if (type == WINHTTP_WEB_SOCKET_UTF8_MESSAGE_BUFFER_TYPE ||
            type == WINHTTP_WEB_SOCKET_BINARY_MESSAGE_BUFFER_TYPE) {
            msg[len] = 0;
            *out = msg;
            *outlen = len;
            return 1;
        }
    }
}

void ani_ws_shutdown(AniWs *ws)
{
    EnterCriticalSection(&ws->send_lock);
    if (!InterlockedExchange(&ws->closing, 1))
        WinHttpWebSocketShutdown(ws->socket, WINHTTP_WEB_SOCKET_SUCCESS_CLOSE_STATUS, NULL, 0);
    LeaveCriticalSection(&ws->send_lock);
}

void ani_ws_free(AniWs *ws)
{
    if (!ws) return;
    close_handles(ws);
    DeleteCriticalSection(&ws->send_lock);
    free(ws);
}
#endif
