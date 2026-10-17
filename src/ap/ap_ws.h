/**
 * WebSocket transport for the Archipelago client: text messages only.
 * Windows uses WinHTTP (ws:// and wss://); elsewhere a plain-socket client
 * (ws:// only for now).
 *
 * One thread receives while another may send; ani_ws_shutdown() from any
 * thread asks the connection to close and makes a blocked receive return.
 */
#pragma once
#include <stdbool.h>
#include <stddef.h>

typedef struct AniWs AniWs;

/* Blocking connect and upgrade. path is normally "/". */
AniWs *ani_ws_connect(const char *host, int port, bool secure,
                      char *err, size_t errlen);
/* 0 on success. */
int ani_ws_send(AniWs *ws, const char *text, size_t len);
/* Blocks for one whole message: 1 with *out (malloc'd, NUL-terminated),
 * 0 when the peer closed, -1 on error. */
int ani_ws_recv(AniWs *ws, char **out, size_t *len);
void ani_ws_shutdown(AniWs *ws);
/* Only after the receiving thread has returned. */
void ani_ws_free(AniWs *ws);
bool ani_ws_supports_tls(void);
