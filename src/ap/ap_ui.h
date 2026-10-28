/**
 * What the Archipelago overlay shows: popups, the Edgar counter and the
 * tracker's counts. The bridge writes it on the game thread, the drawing
 * (ap_hud.c) reads it on the renderer's thread; every call takes the lock.
 * Nothing here knows about pixels.
 */
#pragma once
#include <stdbool.h>
#include <stdint.h>

#include "ap_catalog.h"

typedef enum { ANI_UI_RECEIVED, ANI_UI_SENT, ANI_UI_INFO, ANI_UI_HINT, ANI_UI_CHAT } AniUiKind;
typedef enum { ANI_UI_OFFLINE, ANI_UI_CONNECTING, ANI_UI_CONNECTED } AniUiConn;

#define ANI_UI_SHOWN 4          /* popups on screen at once */
#define ANI_UI_TOAST_MS 4000
#define ANI_UI_FADE_MS 500

typedef struct {
    AniUiKind kind;
    bool progression;
    char text[160];
    float fade;                 /* 1, then down to 0 over the last ANI_UI_FADE_MS */
} AniUiToast;

typedef struct { int found, total; } AniUiCount;

typedef struct {
    AniUiCount cell[ANI_AP_LEVELS][ANI_AP_KIND_ABILITY + 1];   /* [level][kind] */
    uint32_t kinds;             /* bit per kind the tracker shows */
    int edgars, required, goal;
    AniUiConn conn;
    bool active;                /* an AP session: anything draws at all */
} AniUiStatus;

void ani_ui_notify(AniUiKind kind, bool progression, const char *text, uint64_t now_ms);
/* Newest first, at most max (and ANI_UI_SHOWN); when more are waiting the
 * last one returned reads "+N more". */
int ani_ui_toasts(AniUiToast *out, int max, uint64_t now_ms);
void ani_ui_clear(void);

void ani_ui_set_status(const AniUiStatus *st);
void ani_ui_get_status(AniUiStatus *st);

/* The names of a level's checks of the given kinds that found() says are
 * not found yet, in catalog order. Returns how many were written. */
typedef bool (*AniUiFoundFn)(int64_t loc, void *ctx);
int ani_ui_missing(int level, uint32_t kinds, AniUiFoundFn found, void *ctx,
                   const char **names, int max);

/* Level and kind of one of this game's location IDs. */
#define ANI_UI_LEVEL_OF(id) ((int)((((id) - ANI_AP_BASE_ID) >> 12) & 0xF))

uint64_t ani_ui_now_ms(void);
