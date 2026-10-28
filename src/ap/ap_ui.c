#include "ap_ui.h"

#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

/* Popups in a ring, oldest first. Each lasts ANI_UI_TOAST_MS from when it
 * came in, so a burst (a release, a collect) goes away together instead of
 * queueing for minutes; what doesn't fit on screen is counted on the last
 * line. */
#define RING 64

static struct {
    pthread_mutex_t lock;
    struct { AniUiToast t; uint64_t at; } ring[RING];
    int head, count;            /* head: oldest */
    AniUiStatus status;
} U = { PTHREAD_MUTEX_INITIALIZER };

uint64_t ani_ui_now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000u + (uint64_t)ts.tv_nsec / 1000000u;
}

static void expire(uint64_t now)
{
    while (U.count && now - U.ring[U.head].at >= ANI_UI_TOAST_MS) {
        U.head = (U.head + 1) % RING;
        U.count--;
    }
}

void ani_ui_notify(AniUiKind kind, bool progression, const char *text, uint64_t now_ms)
{
    pthread_mutex_lock(&U.lock);
    if (U.count == RING) {
        U.head = (U.head + 1) % RING;
        U.count--;
    }
    int i = (U.head + U.count++) % RING;
    U.ring[i].at = now_ms;
    U.ring[i].t.kind = kind;
    U.ring[i].t.progression = progression;
    U.ring[i].t.fade = 1.0f;
    snprintf(U.ring[i].t.text, sizeof U.ring[i].t.text, "%s", text ? text : "");
    pthread_mutex_unlock(&U.lock);
}

int ani_ui_toasts(AniUiToast *out, int max, uint64_t now_ms)
{
    int n = 0;
    if (max > ANI_UI_SHOWN) max = ANI_UI_SHOWN;
    pthread_mutex_lock(&U.lock);
    expire(now_ms);
    int rows = U.count > max ? max - 1 : U.count;
    for (int k = 0; k < rows; k++) {
        int i = (U.head + U.count - 1 - k) % RING;
        uint64_t left = ANI_UI_TOAST_MS - (now_ms - U.ring[i].at);
        out[n] = U.ring[i].t;
        out[n].fade = left >= ANI_UI_FADE_MS ? 1.0f : (float)left / ANI_UI_FADE_MS;
        n++;
    }
    if (U.count > rows && n < max) {
        /* The newest of the hidden ones sets when the line goes. */
        int i = (U.head + U.count - 1 - rows) % RING;
        uint64_t left = ANI_UI_TOAST_MS - (now_ms - U.ring[i].at);
        memset(&out[n], 0, sizeof out[n]);
        out[n].kind = ANI_UI_INFO;
        out[n].fade = left >= ANI_UI_FADE_MS ? 1.0f : (float)left / ANI_UI_FADE_MS;
        snprintf(out[n].text, sizeof out[n].text, "+%d more", U.count - rows);
        n++;
    }
    pthread_mutex_unlock(&U.lock);
    return n;
}

void ani_ui_clear(void)
{
    pthread_mutex_lock(&U.lock);
    U.head = U.count = 0;
    pthread_mutex_unlock(&U.lock);
}

void ani_ui_set_status(const AniUiStatus *st)
{
    pthread_mutex_lock(&U.lock);
    U.status = *st;
    pthread_mutex_unlock(&U.lock);
}

void ani_ui_get_status(AniUiStatus *st)
{
    pthread_mutex_lock(&U.lock);
    *st = U.status;
    pthread_mutex_unlock(&U.lock);
}

int ani_ui_missing(int level, uint32_t kinds, AniUiFoundFn found, void *ctx,
                   const char **names, int max)
{
    int n = 0;
    for (int i = 0; i < ANI_AP_NAMES && n < max; i++) {
        int64_t id = ani_ap_location_names[i].id;
        int kind = ANI_AP_KIND_OF(id);
        if (ANI_UI_LEVEL_OF(id) != level || kind < 0 || kind > 31 || !(kinds >> kind & 1))
            continue;
        if (!found(id, ctx))
            names[n++] = ani_ap_location_names[i].name;
    }
    return n;
}
