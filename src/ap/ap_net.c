#include "ap_net.h"
#include "ap_json.h"
#include "ap_ws.h"

#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#if defined(_WIN32)
#include <windows.h>
static void sleep_ms(int ms) { Sleep((DWORD)ms); }
#else
#include <unistd.h>
static void sleep_ms(int ms) { usleep((useconds_t)ms * 1000); }
#endif

typedef struct Out { uint64_t generation; char *text; struct Out *next; } Out;

static struct {
    pthread_mutex_t lock;
    pthread_cond_t wake;            /* outbound queued, seed known, or stopping */
    bool started, stopping;
    char host[256];
    int port;
    int scheme;                     /* 0: try wss then ws, 1: ws, 2: wss */
    char *connect_cmd;
    AniWs *ws;                      /* current socket, owned by the net thread */
    uint64_t generation;            /* of ws; 0 while disconnected */
    bool sending;                   /* the send thread is using ws */
    AniNetEvent *in;                /* inbound ring */
    size_t in_len, in_cap;
    Out *out_head, *out_tail;
    char seed[128];
} N = { PTHREAD_MUTEX_INITIALIZER, PTHREAD_COND_INITIALIZER };

static void push_event(AniNetKind kind, uint64_t gen, char *text)
{
    pthread_mutex_lock(&N.lock);
    if (N.in_len == N.in_cap) {
        size_t cap = N.in_cap ? N.in_cap * 2 : 64;
        AniNetEvent *grown = realloc(N.in, cap * sizeof *grown);
        if (!grown) { pthread_mutex_unlock(&N.lock); free(text); return; }
        N.in = grown;
        N.in_cap = cap;
    }
    N.in[N.in_len].kind = kind;
    N.in[N.in_len].generation = gen;
    N.in[N.in_len].text = text;
    N.in_len++;
    pthread_mutex_unlock(&N.lock);
}

static char *dupstr(const char *s)
{
    size_t n = strlen(s) + 1;
    char *d = malloc(n);
    if (d) memcpy(d, s, n);
    return d;
}

/* Answers RoomInfo with Connect, and records the seed for ani_net_wait_seed. */
static void on_message(AniWs *ws, const char *text)
{
    AjValue *root = aj_parse(text);
    for (const AjValue *p = root ? root->child : NULL; p; p = p->next) {
        const char *cmd = aj_str(aj_get(p, "cmd"), "");
        if (!strcmp(cmd, "RoomInfo")) {
            AjBuf b = {0};
            pthread_mutex_lock(&N.lock);
            snprintf(N.seed, sizeof N.seed, "%s", aj_str(aj_get(p, "seed_name"), ""));
            pthread_cond_broadcast(&N.wake);
            pthread_mutex_unlock(&N.lock);
            ajb_raw(&b, "[");
            ajb_raw(&b, N.connect_cmd);
            ajb_raw(&b, "]");
            if (!b.oom) ani_ws_send(ws, b.buf, b.len);
            ajb_free(&b);
        }
    }
    aj_free(root);
}

static AniWs *open_socket(char *err, size_t errlen)
{
    AniWs *ws = NULL;
    if (N.scheme != 1 && ani_ws_supports_tls())
        ws = ani_ws_connect(N.host, N.port, true, err, errlen);
    if (!ws && N.scheme != 2)
        ws = ani_ws_connect(N.host, N.port, false, err, errlen);
    return ws;
}

static void *net_thread(void *unused)
{
    int backoff = 1000;
    (void)unused;
    for (;;) {
        char err[256] = "";
        AniWs *ws;
        uint64_t gen;

        pthread_mutex_lock(&N.lock);
        if (N.stopping) { pthread_mutex_unlock(&N.lock); return NULL; }
        pthread_mutex_unlock(&N.lock);

        ws = open_socket(err, sizeof err);
        if (!ws) {
            char msg[320];
            snprintf(msg, sizeof msg, "%s:%d: %s", N.host, N.port, err);
            push_event(ANI_NET_DOWN, 0, dupstr(msg));
            sleep_ms(backoff);
            if (backoff < 30000) backoff *= 2;
            continue;
        }
        backoff = 1000;
        pthread_mutex_lock(&N.lock);
        gen = ++N.generation;
        N.ws = ws;
        pthread_mutex_unlock(&N.lock);
        push_event(ANI_NET_UP, gen, NULL);

        for (;;) {
            char *text = NULL;
            size_t len = 0;
            int rc = ani_ws_recv(ws, &text, &len);
            if (rc != 1) {
                push_event(ANI_NET_DOWN, gen, dupstr(rc == 0 ? "server closed the connection"
                                                             : "connection lost"));
                break;
            }
            on_message(ws, text);
            push_event(ANI_NET_PACKET, gen, text);
        }
        pthread_mutex_lock(&N.lock);
        N.ws = NULL;
        while (N.sending)
            pthread_cond_wait(&N.wake, &N.lock);
        pthread_mutex_unlock(&N.lock);
        ani_ws_free(ws);
        sleep_ms(1000);
    }
}

static void *send_thread(void *unused)
{
    (void)unused;
    pthread_mutex_lock(&N.lock);
    for (;;) {
        Out *o;
        while (!N.out_head && !N.stopping)
            pthread_cond_wait(&N.wake, &N.lock);
        if (N.stopping) break;
        o = N.out_head;
        N.out_head = o->next;
        if (!N.out_head) N.out_tail = NULL;
        if (N.ws && o->generation == N.generation) {
            AniWs *ws = N.ws;
            /* The net thread waits for `sending` to clear before it frees ws. */
            N.sending = true;
            pthread_mutex_unlock(&N.lock);
            ani_ws_send(ws, o->text, strlen(o->text));
            pthread_mutex_lock(&N.lock);
            N.sending = false;
            pthread_cond_broadcast(&N.wake);
        }
        free(o->text);
        free(o);
    }
    pthread_mutex_unlock(&N.lock);
    return NULL;
}

void ani_net_start(const char *address, const char *connect_cmd)
{
    const char *a = address, *colon;
    pthread_t t;

    if (N.started) return;
    N.scheme = 0;
    if (!strncmp(a, "ws://", 5)) { N.scheme = 1; a += 5; }
    else if (!strncmp(a, "wss://", 6)) { N.scheme = 2; a += 6; }
    colon = strrchr(a, ':');
    N.port = 38281;
    if (colon) {
        snprintf(N.host, sizeof N.host, "%.*s", (int)(colon - a), a);
        N.port = atoi(colon + 1);
    } else {
        snprintf(N.host, sizeof N.host, "%s", a);
    }
    if (N.host[strlen(N.host) - 1] == '/') N.host[strlen(N.host) - 1] = 0;
    N.connect_cmd = dupstr(connect_cmd);
    N.started = true;
    pthread_create(&t, NULL, net_thread, NULL);
    pthread_detach(t);
    pthread_create(&t, NULL, send_thread, NULL);
    pthread_detach(t);
}

void ani_net_stop(void)
{
    pthread_mutex_lock(&N.lock);
    N.stopping = true;
    if (N.ws) ani_ws_shutdown(N.ws);
    pthread_cond_broadcast(&N.wake);
    pthread_mutex_unlock(&N.lock);
}

bool ani_net_wait_seed(int timeout_ms, char *seed, size_t n)
{
    struct timespec until;
    bool ok;
    clock_gettime(CLOCK_REALTIME, &until);
    until.tv_sec += timeout_ms / 1000;
    until.tv_nsec += (long)(timeout_ms % 1000) * 1000000L;
    if (until.tv_nsec >= 1000000000L) { until.tv_sec++; until.tv_nsec -= 1000000000L; }
    pthread_mutex_lock(&N.lock);
    while (!N.seed[0] && !N.stopping)
        if (pthread_cond_timedwait(&N.wake, &N.lock, &until) != 0) break;
    ok = N.seed[0] != 0;
    if (ok) snprintf(seed, n, "%s", N.seed);
    pthread_mutex_unlock(&N.lock);
    return ok;
}

size_t ani_net_drain(AniNetEvent *out, size_t max)
{
    size_t n;
    pthread_mutex_lock(&N.lock);
    n = N.in_len < max ? N.in_len : max;
    memcpy(out, N.in, n * sizeof *out);
    memmove(N.in, N.in + n, (N.in_len - n) * sizeof *N.in);
    N.in_len -= n;
    pthread_mutex_unlock(&N.lock);
    return n;
}

void ani_net_send(uint64_t generation, const char *json)
{
    Out *o = malloc(sizeof *o);
    if (!o || !(o->text = dupstr(json))) { free(o); return; }
    o->generation = generation;
    o->next = NULL;
    pthread_mutex_lock(&N.lock);
    if (N.out_tail) N.out_tail->next = o; else N.out_head = o;
    N.out_tail = o;
    pthread_cond_broadcast(&N.wake);
    pthread_mutex_unlock(&N.lock);
}
