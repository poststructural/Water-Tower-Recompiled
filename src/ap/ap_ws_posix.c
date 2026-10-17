/* Plain-socket WebSocket client (RFC 6455), ws:// only. Used off Windows,
 * and by the host tests. */
#if !defined(_WIN32)
#include "ap_ws.h"

#include <errno.h>
#include <netdb.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

struct AniWs {
    int fd;
    pthread_mutex_t send_lock;
    uint32_t rng;
};

bool ani_ws_supports_tls(void) { return false; }

static int write_all(int fd, const void *p, size_t n)
{
    const char *c = p;
    while (n) {
        ssize_t w = send(fd, c, n, MSG_NOSIGNAL);
        if (w < 0 && errno == EINTR) continue;
        if (w <= 0) return -1;
        c += w;
        n -= (size_t)w;
    }
    return 0;
}

static int read_all(int fd, void *p, size_t n)
{
    char *c = p;
    while (n) {
        ssize_t r = recv(fd, c, n, 0);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) return -1;
        c += r;
        n -= (size_t)r;
    }
    return 0;
}

static uint32_t next_rand(AniWs *ws)
{
    ws->rng ^= ws->rng << 13;
    ws->rng ^= ws->rng >> 17;
    ws->rng ^= ws->rng << 5;
    return ws->rng;
}

static void b64(const unsigned char *in, size_t n, char *out)
{
    static const char t[] =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    size_t i;
    for (i = 0; i + 2 < n; i += 3) {
        *out++ = t[in[i] >> 2];
        *out++ = t[((in[i] & 3) << 4) | (in[i + 1] >> 4)];
        *out++ = t[((in[i + 1] & 15) << 2) | (in[i + 2] >> 6)];
        *out++ = t[in[i + 2] & 63];
    }
    if (n - i == 1) {
        *out++ = t[in[i] >> 2]; *out++ = t[(in[i] & 3) << 4]; *out++ = '='; *out++ = '=';
    } else if (n - i == 2) {
        *out++ = t[in[i] >> 2]; *out++ = t[((in[i] & 3) << 4) | (in[i + 1] >> 4)];
        *out++ = t[(in[i + 1] & 15) << 2]; *out++ = '=';
    }
    *out = 0;
}

AniWs *ani_ws_connect(const char *host, int port, bool secure,
                      char *err, size_t errlen)
{
    struct addrinfo hints = {0}, *res = NULL, *ai;
    char portstr[16], req[1024], resp[4096], key[32];
    unsigned char nonce[16];
    size_t got = 0;
    int fd = -1, one = 1;
    AniWs *ws;
    struct timeval tv = { 10, 0 }, none = { 0, 0 };

    if (secure) {
        snprintf(err, errlen, "wss:// needs TLS, which this build lacks");
        return NULL;
    }
    snprintf(portstr, sizeof portstr, "%d", port);
    hints.ai_socktype = SOCK_STREAM;
    if (getaddrinfo(host, portstr, &hints, &res) != 0) {
        snprintf(err, errlen, "cannot resolve %s", host);
        return NULL;
    }
    for (ai = res; ai; ai = ai->ai_next) {
        fd = socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);
        if (fd < 0) continue;
        setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
        if (connect(fd, ai->ai_addr, ai->ai_addrlen) == 0) break;
        close(fd);
        fd = -1;
    }
    freeaddrinfo(res);
    if (fd < 0) {
        snprintf(err, errlen, "cannot connect to %s:%d", host, port);
        return NULL;
    }
    setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);

    ws = calloc(1, sizeof *ws);
    ws->fd = fd;
    ws->rng = (uint32_t)time(NULL) ^ (uint32_t)(uintptr_t)ws ^ 0x9E3779B9u;
    if (!ws->rng) ws->rng = 1;
    pthread_mutex_init(&ws->send_lock, NULL);
    for (int i = 0; i < 16; i++) nonce[i] = (unsigned char)next_rand(ws);
    b64(nonce, 16, key);
    snprintf(req, sizeof req,
             "GET / HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\n"
             "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
             "Sec-WebSocket-Version: 13\r\n\r\n", host, port, key);
    if (write_all(fd, req, strlen(req)) != 0) goto fail_io;
    /* Read the response headers byte by byte so no frame data is consumed. */
    while (got < sizeof resp - 1) {
        if (read_all(fd, resp + got, 1) != 0) goto fail_io;
        got++;
        if (got >= 4 && !memcmp(resp + got - 4, "\r\n\r\n", 4)) break;
    }
    resp[got] = 0;
    if (strncmp(resp, "HTTP/1.1 101", 12)) {
        char *eol = strstr(resp, "\r\n");
        if (eol) *eol = 0;
        snprintf(err, errlen, "upgrade refused: %s", resp);
        goto fail;
    }
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &none, sizeof none);
    return ws;
fail_io:
    snprintf(err, errlen, "connection lost during the handshake");
fail:
    close(fd);
    pthread_mutex_destroy(&ws->send_lock);
    free(ws);
    return NULL;
}

static int send_frame(AniWs *ws, int opcode, const void *data, size_t len)
{
    unsigned char hdr[14];
    size_t h = 0;
    uint32_t mask = next_rand(ws);
    unsigned char m[4] = { (unsigned char)mask, (unsigned char)(mask >> 8),
                           (unsigned char)(mask >> 16), (unsigned char)(mask >> 24) };
    unsigned char *buf;
    int rc;

    hdr[h++] = (unsigned char)(0x80 | opcode);
    if (len < 126) hdr[h++] = (unsigned char)(0x80 | len);
    else if (len < 65536) {
        hdr[h++] = 0x80 | 126; hdr[h++] = (unsigned char)(len >> 8); hdr[h++] = (unsigned char)len;
    } else {
        hdr[h++] = 0x80 | 127;
        for (int i = 7; i >= 0; i--) hdr[h++] = (unsigned char)((uint64_t)len >> (8 * i));
    }
    memcpy(hdr + h, m, 4);
    h += 4;
    buf = malloc(h + len);
    if (!buf) return -1;
    memcpy(buf, hdr, h);
    for (size_t i = 0; i < len; i++) buf[h + i] = ((const unsigned char *)data)[i] ^ m[i & 3];
    rc = write_all(ws->fd, buf, h + len);
    free(buf);
    return rc;
}

int ani_ws_send(AniWs *ws, const char *text, size_t len)
{
    int rc;
    pthread_mutex_lock(&ws->send_lock);
    rc = send_frame(ws, 1, text, len);
    pthread_mutex_unlock(&ws->send_lock);
    return rc;
}

int ani_ws_recv(AniWs *ws, char **out, size_t *outlen)
{
    char *msg = NULL;
    size_t len = 0;

    for (;;) {
        unsigned char h[2], ext[8];
        uint64_t n;
        int op, fin;
        char *p;

        if (read_all(ws->fd, h, 2) != 0) goto lost;
        fin = h[0] & 0x80;
        op = h[0] & 0x0F;
        n = h[1] & 0x7F;
        if (n == 126) {
            if (read_all(ws->fd, ext, 2) != 0) goto lost;
            n = ((uint64_t)ext[0] << 8) | ext[1];
        } else if (n == 127) {
            if (read_all(ws->fd, ext, 8) != 0) goto lost;
            n = 0;
            for (int i = 0; i < 8; i++) n = n << 8 | ext[i];
        }
        if (h[1] & 0x80 || n > (64u << 20)) goto lost;  /* servers never mask */
        p = malloc((size_t)n + 1);
        if (!p || read_all(ws->fd, p, (size_t)n) != 0) { free(p); goto lost; }
        if (op == 8) {                     /* close: echo it, then report */
            pthread_mutex_lock(&ws->send_lock);
            send_frame(ws, 8, p, n >= 2 ? 2 : 0);
            pthread_mutex_unlock(&ws->send_lock);
            free(p);
            free(msg);
            return 0;
        }
        if (op == 9) {                     /* ping */
            pthread_mutex_lock(&ws->send_lock);
            send_frame(ws, 10, p, (size_t)n);
            pthread_mutex_unlock(&ws->send_lock);
            free(p);
            continue;
        }
        if (op == 10) { free(p); continue; }  /* pong */
        if (op == 1 || op == 2 || op == 0) {
            char *grown = realloc(msg, len + (size_t)n + 1);
            if (!grown) { free(p); goto lost; }
            msg = grown;
            memcpy(msg + len, p, (size_t)n);
            len += (size_t)n;
            msg[len] = 0;
            free(p);
            if (fin) { *out = msg; *outlen = len; return 1; }
            continue;
        }
        free(p);
    }
lost:
    free(msg);
    return -1;
}

void ani_ws_shutdown(AniWs *ws)
{
    shutdown(ws->fd, SHUT_RDWR);
}

void ani_ws_free(AniWs *ws)
{
    if (!ws) return;
    close(ws->fd);
    pthread_mutex_destroy(&ws->send_lock);
    free(ws);
}
#endif
