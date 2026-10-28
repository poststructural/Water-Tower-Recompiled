/**
 * The Archipelago overlay on screen (docs/ARCHIPELAGO.md, "In game"):
 *   - popups for items sent and received, top right, while the game runs;
 *   - the Edgar counter with a connection light;
 *   - the tracker screen, over the held game (Tab, F1, or hold Back).
 * Popups and the counter are panels the presenter copies over each frame
 * (nv2a_hud_rects); the tracker is the presenter's held-game overlay. All of
 * it reads ap_ui.c and runs on the renderer's thread, apart from the key
 * events, which come from the window thread.
 */
#include "ap_bridge.h"
#include "ap_font.h"
#include "ap_hud.h"
#include "ap_ui.h"

#include "nv2a_window.h"

#include <SDL.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* xboxrecomp's pad state (src/input/xinput_xbox.h), mirrored to keep its
 * Windows types out of this file. */
typedef struct {
    uint32_t packet;
    uint16_t buttons;
    uint8_t analog[8];          /* A, B, X, Y, Black, White, LT, RT */
    int16_t lx, ly, rx, ry;
} PadState;
extern uint32_t xbox_InputGetState(uint32_t port, void *state);
#define PAD_UP 0x0001
#define PAD_DOWN 0x0002
#define PAD_LEFT 0x0004
#define PAD_RIGHT 0x0008
#define PAD_BACK 0x0020
#define PAD_A 0x1000            /* analog buttons folded in above the digital ones */
#define PAD_B 0x2000

#define HOLD_MS 500

static bool s_notify = true, s_tracker = true, s_counter = true, s_chat = true;

void ani_hud_configure(bool notifications, bool tracker, bool counter, bool chat)
{
    s_notify = notifications;
    s_tracker = tracker;
    s_counter = counter;
    s_chat = chat;
}

/* ── Colors (0xAARRGGBB) ───────────────────────────────────── */

#define C_PANEL   0xFF16182Au
#define C_TEXT    0xFFF4F1E8u
#define C_DIM     0xFFA9A6B8u
#define C_GOLD    0xFFFFC94Au
#define C_SKY     0xFF5AB4FFu
#define C_GREY    0xFF8C8C9Cu
#define C_GREEN   0xFF6BD66Bu
#define C_AMBER   0xFFFFB347u
#define C_RED     0xFFFF5C5Cu
#define C_ROW     0xFF2C3050u
#define C_VIOLET  0xFFC58CFFu
#define C_MINT    0xFF7FE0C8u

/* ── Input ─────────────────────────────────────────────────── */

/* Keys from the window thread for the renderer's thread. */
static SDL_atomic_t s_open_req;
static int s_keys[32];
static SDL_atomic_t s_key_w, s_key_r;
static SDL_atomic_t s_open;

void nv2a_window_event_hook(const void *sdl_event)
{
    const SDL_Event *ev = sdl_event;
    if (ev->type != SDL_KEYDOWN || !ani_ap_active() || !s_tracker) return;
    SDL_Keycode k = ev->key.keysym.sym;
    if (!SDL_AtomicGet(&s_open)) {
        if ((k == SDLK_TAB || k == SDLK_F1) && !ev->key.repeat) SDL_AtomicSet(&s_open_req, 1);
        return;
    }
    int w = SDL_AtomicGet(&s_key_w);
    if (w - SDL_AtomicGet(&s_key_r) < 32) {
        s_keys[w & 31] = k;
        SDL_AtomicSet(&s_key_w, w + 1);
    }
}

static int next_key(void)
{
    int r = SDL_AtomicGet(&s_key_r);
    if (r == SDL_AtomicGet(&s_key_w)) return 0;
    int k = s_keys[r & 31];
    SDL_AtomicSet(&s_key_r, r + 1);
    return k;
}

static uint16_t pad_buttons(void)
{
    PadState st;
    memset(&st, 0, sizeof st);
    if (xbox_InputGetState(0, &st) != 0) return 0;
    uint16_t b = st.buttons & 0x00FF;
    if (st.analog[0] > 30) b |= PAD_A;
    if (st.analog[1] > 30) b |= PAD_B;
    if (st.ly > 20000) b |= PAD_UP;
    if (st.ly < -20000) b |= PAD_DOWN;
    return b;
}

/* ── Panels over the running game ──────────────────────────── */

typedef struct { uint32_t *px; int w, h, cap; } Panel;
static Panel s_panels[ANI_UI_SHOWN + 1];

static uint32_t *panel_size(Panel *p, int w, int h)
{
    if (w * h > p->cap) {
        free(p->px);
        p->cap = w * h;
        p->px = malloc((size_t)p->cap * 4);
        if (!p->px) p->cap = 0;
    }
    p->w = w;
    p->h = h;
    return p->px;
}

/* text cut to fit max_w pixels, with "..." when it doesn't. */
static void fit(char *out, size_t n, const char *text, int size, int max_w)
{
    snprintf(out, n, "%s", text);
    if (ani_font_width(size, out) <= max_w) return;
    size_t len = strlen(out);
    while (len > 0) {
        len--;
        while (len > 0 && ((unsigned char)out[len] & 0xC0) == 0x80) len--;
        snprintf(out + len, n - len, "...");
        if (ani_font_width(size, out) <= max_w) return;
    }
}

static uint32_t stripe_of(const AniUiToast *t)
{
    switch (t->kind) {
    case ANI_UI_RECEIVED: return C_GOLD;
    case ANI_UI_SENT: return C_SKY;
    case ANI_UI_HINT: return C_VIOLET;
    case ANI_UI_CHAT: return C_MINT;
    default: return C_GREY;
    }
}

static const char *tag_of(const AniUiToast *t)
{
    switch (t->kind) {
    case ANI_UI_RECEIVED: return "GOT";
    case ANI_UI_SENT: return "SENT";
    case ANI_UI_HINT: return "HINT";
    case ANI_UI_CHAT: return "CHAT";
    default: return "AP";
    }
}

static int draw_toast(Panel *p, const AniUiToast *t, int pw, int ph, int ts)
{
    uint32_t *px = panel_size(p, pw, ph);
    char line[200];
    if (!px) return 0;
    int stripe = ph / 10 > 3 ? ph / 10 : 3;
    int pad = ts / 2, tag_ts = ts * 3 / 4;
    for (int i = 0; i < pw * ph; i++) px[i] = C_PANEL;
    /* Panels are opaque, so a popup fades by its text and stripe fading
     * into the panel; then it is gone. */
    unsigned a = (unsigned)(t->fade * 255.0f);
#define FADED(c) (((c) & 0x00FFFFFFu) | (((c) >> 24) * a / 255u) << 24)
    ani_fill(px, pw, ph, 0, 0, stripe, ph, FADED(stripe_of(t)));
    int x = stripe + pad;
    x += ani_font_draw(px, pw, ph, x, (ph - tag_ts) / 2 - tag_ts / 10, tag_ts, FADED(stripe_of(t)), tag_of(t));
    x += pad;
    fit(line, sizeof line, t->text, ts, pw - x - pad);
    ani_font_draw(px, pw, ph, x, (ph - ts) / 2 - ts / 10, ts,
                  FADED(t->progression ? stripe_of(t) : C_TEXT), line);
#undef FADED
    return 1;
}

static void counter_text(char *out, size_t n, const AniUiStatus *st)
{
    if (st->required > 0)
        snprintf(out, n, "Edgars %d / %d", st->edgars, st->required);
    else
        snprintf(out, n, "Edgars %d", st->edgars);
}

static uint32_t conn_color(AniUiConn c)
{
    return c == ANI_UI_CONNECTED ? C_GREEN : c == ANI_UI_CONNECTING ? C_AMBER : C_RED;
}

static void fill_dot(uint32_t *px, int w, int h, int cx, int cy, int r, uint32_t c)
{
    for (int y = -r; y <= r; y++)
        for (int x = -r; x <= r; x++)
            if (x * x + y * y <= r * r) ani_fill(px, w, h, cx + x, cy + y, 1, 1, c);
}

/* Held Back opens the tracker; a short press stays the game's. */
static void poll_hold(void)
{
    static uint64_t down_at;
    static bool fired;
    if (!s_tracker || SDL_AtomicGet(&s_open)) return;
    uint64_t now = ani_ui_now_ms();
    if (pad_buttons() & PAD_BACK) {
        if (!down_at) down_at = now;
        if (!fired && now - down_at >= HOLD_MS) {
            SDL_AtomicSet(&s_open_req, 1);
            fired = true;
        }
    } else {
        down_at = 0;
        fired = false;
    }
}

/* ANI_HUD_DUMP=<dir>: what the overlay draws, for checking it against the
 * game's own frames (NV2A_CAPTURE) without a screen grab: the panels with
 * their places (hud_<ms>_<i>.ppm and hud_<ms>.txt) once a second, and every
 * tracker screen as it is first drawn and after each input. */
static const char *dump_dir(void)
{
    static int read;
    static const char *dir;
    if (!read) { dir = getenv("ANI_HUD_DUMP"); read = 1; }
    return dir && *dir ? dir : NULL;
}

static void dump_ppm(const char *path, const uint32_t *px, int w, int h)
{
    FILE *f = fopen(path, "wb");
    if (!f) return;
    fprintf(f, "P6\n%d %d\n255\n", w, h);
    for (int i = 0; i < w * h; i++) {
        unsigned char rgb[3] = { px[i] >> 16 & 0xFF, px[i] >> 8 & 0xFF, px[i] & 0xFF };
        fwrite(rgb, 1, 3, f);
    }
    fclose(f);
}

static void dump_rects(const NV2AHudRect *r, int n, int win_w, int win_h)
{
    static uint64_t last;
    char path[1024];
    uint64_t now = ani_ui_now_ms();
    if (!dump_dir() || !n || now - last < 1000) return;
    last = now;
    snprintf(path, sizeof path, "%s/hud_%llu.txt", dump_dir(), (unsigned long long)now);
    FILE *f = fopen(path, "w");
    if (!f) return;
    fprintf(f, "%d %d\n", win_w, win_h);
    for (int i = 0; i < n; i++) {
        fprintf(f, "%d %d %d %d\n", r[i].x, r[i].y, r[i].w, r[i].h);
        snprintf(path, sizeof path, "%s/hud_%llu_%d.ppm", dump_dir(), (unsigned long long)now, i);
        dump_ppm(path, r[i].argb, r[i].w, r[i].h);
    }
    fclose(f);
}

/* ANI_HUD_TEST=<seconds>: a test switch that works the tracker without
 * anyone at the keyboard: that long after the first frame it opens, then
 * every two seconds shows a set's list, scrolls it, goes back, and closes. */
static uint64_t s_test_at;
static int s_test_step;

static void test_open(void)
{
    static int read;
    const char *e = getenv("ANI_HUD_TEST");
    if (!read) {
        read = 1;
        if (e && atoi(e) > 0) s_test_at = ani_ui_now_ms() + (uint64_t)atoi(e) * 1000u;
    }
    if (s_test_at && !s_test_step && ani_ui_now_ms() >= s_test_at) {
        s_test_step = 1;
        s_test_at = ani_ui_now_ms() + 2000;
        SDL_AtomicSet(&s_open_req, 1);
    }
}

static int test_key(void)
{
    static const int keys[] = { SDLK_DOWN, SDLK_RETURN, SDLK_DOWN, SDLK_LEFT, SDLK_TAB };
    if (!s_test_step || s_test_step > 5 || ani_ui_now_ms() < s_test_at) return 0;
    s_test_at = ani_ui_now_ms() + 2000;
    return keys[s_test_step++ - 1];
}

int nv2a_hud_rects(NV2AHudRect *rects, int max, int win_w, int win_h)
{
    AniUiStatus st;
    int n = 0;
    if (!ani_ap_active()) return 0;
    poll_hold();
    test_open();
    if (SDL_AtomicGet(&s_open)) return 0;
    ani_ui_get_status(&st);
    int ts = win_h / 40 > 12 ? win_h / 40 : 12;
    int margin = win_h / 36;

    if (s_notify && max > 0) {
        AniUiToast t[ANI_UI_SHOWN];
        int k = ani_ui_toasts(t, ANI_UI_SHOWN, ani_ui_now_ms());
        if (!s_chat) {
            int m = 0;
            for (int i = 0; i < k; i++)
                if (t[i].kind != ANI_UI_CHAT) t[m++] = t[i];
            k = m;
        }
        int maxw = win_w * 40 / 100, ph = ts * 2;
        int y = margin;
        if (maxw < ts * 12) maxw = ts * 12;
        for (int i = 0; i < k && n < max; i++) {
            /* As wide as the text, up to 40% of the window. */
            int pw = ts / 2 + ts + ani_font_width(ts * 3 / 4, tag_of(&t[i])) +
                     ani_font_width(ts, t[i].text) + ts;
            if (pw > maxw) pw = maxw;
            if (pw < ts * 8) pw = ts * 8;
            if (!draw_toast(&s_panels[i], &t[i], pw, ph, ts)) continue;
            rects[n++] = (NV2AHudRect){ win_w - margin - pw, y, pw, ph, s_panels[i].px };
            y += ph + ts / 3;
        }
    }

    if (s_counter && n < max) {
        char text[64];
        Panel *p = &s_panels[ANI_UI_SHOWN];
        counter_text(text, sizeof text, &st);
        int pad = ts / 2, dot = ts / 4;
        int pw = pad + dot * 2 + pad + ani_font_width(ts, text) + pad, ph = ts * 2;
        uint32_t *px = panel_size(p, pw, ph);
        if (px) {
            for (int i = 0; i < pw * ph; i++) px[i] = C_PANEL;
            fill_dot(px, pw, ph, pad + dot, ph / 2, dot, conn_color(st.conn));
            ani_font_draw(px, pw, ph, pad + dot * 2 + pad, (ph - ts) / 2 - ts / 10, ts, C_TEXT, text);
            rects[n++] = (NV2AHudRect){ margin, win_h - margin - ph, pw, ph, px };
        }
    }
    dump_rects(rects, n, win_w, win_h);
    return n;
}

/* ── Tracker screen ────────────────────────────────────────── */

static const struct { int kind; const char *title; } COLS[] = {
    { ANI_AP_KIND_EDGAR, "Edgars" },
    { ANI_AP_KIND_LETTER, "Letters" },
    { ANI_AP_KIND_SCRIPT_PAGE, "Pages" },
    { ANI_AP_KIND_QUEST, "Quest" },
    { ANI_AP_KIND_MILESTONE, "Milestones" },
    { ANI_AP_KIND_COLLECTIBLE, "Collectibles" },
    { ANI_AP_KIND_APPLE, "Apples" },
    { ANI_AP_KIND_ABILITY, "Abilities" },
};
#define NCOLS ((int)(sizeof COLS / sizeof *COLS))

static int s_row, s_detail = -1, s_scroll, s_dumped;
static uint16_t s_prev_pad;

static bool found_fn(int64_t loc, void *ctx) { (void)ctx; return ani_ap_checked(loc); }

bool nv2a_overlay_wanted(void)
{
    if (!ani_ap_active() || !s_tracker) return false;
    if (SDL_AtomicGet(&s_open_req)) {
        SDL_AtomicSet(&s_open_req, 0);
        SDL_AtomicSet(&s_key_r, SDL_AtomicGet(&s_key_w));   /* nothing stale */
        s_prev_pad = pad_buttons();      /* the Back that opened it is still down */
        s_detail = -1;
        s_dumped = 0;
        SDL_AtomicSet(&s_open, 1);
        return true;
    }
    return false;
}

static const char *short_name(const char *name)
{
    const char *c = strstr(name, ": ");
    return c ? c + 2 : name;
}

/* What the player pressed this frame, as one action. */
enum { A_NONE, A_UP, A_DOWN, A_IN, A_OUT, A_CLOSE };

static int action(void)
{
    int k = test_key();
    for (; k || (k = next_key()); k = 0) {
        switch (k) {
        case SDLK_UP: case SDLK_w: return A_UP;
        case SDLK_DOWN: case SDLK_s: return A_DOWN;
        case SDLK_RIGHT: case SDLK_RETURN: case SDLK_d: return A_IN;
        case SDLK_LEFT: case SDLK_BACKSPACE: case SDLK_a: return A_OUT;
        case SDLK_ESCAPE: return s_detail >= 0 ? A_OUT : A_CLOSE;
        case SDLK_TAB: case SDLK_F1: return A_CLOSE;
        default: break;
        }
    }
    uint16_t b = pad_buttons(), pressed = b & ~s_prev_pad;
    s_prev_pad = b;
    if (pressed & PAD_UP) return A_UP;
    if (pressed & PAD_DOWN) return A_DOWN;
    if (pressed & (PAD_RIGHT | PAD_A)) return A_IN;
    if (pressed & PAD_LEFT) return A_OUT;
    if (pressed & PAD_B) return s_detail >= 0 ? A_OUT : A_CLOSE;
    if (pressed & PAD_BACK) return A_CLOSE;
    return A_NONE;
}

static void draw_cell(uint32_t *px, int w, int h, int x, int y, int ts, AniUiCount c)
{
    char t[24];
    if (!c.total) {
        ani_font_draw(px, w, h, x, y, ts, C_DIM, "-");
        return;
    }
    snprintf(t, sizeof t, "%d/%d", c.found, c.total);
    ani_font_draw(px, w, h, x, y, ts, c.found == c.total ? C_GREEN : C_TEXT, t);
}

static void draw_main(uint32_t *px, int w, int h, const AniUiStatus *st, int ts)
{
    int cols[NCOLS], nc = 0;
    for (int i = 0; i < NCOLS; i++) {
        int total = 0;
        for (int l = 0; l < ANI_AP_LEVELS; l++) total += st->cell[l][COLS[i].kind].total;
        if ((st->kinds >> COLS[i].kind & 1) && total) cols[nc++] = i;
    }
    int x0 = w / 12, name_w = w * 30 / 100;
    int colw = nc ? (w - 2 * x0 - name_w) / nc : 0;
    int y = h / 5, rowh = ts * 2;

    for (int c = 0; c < nc; c++)
        ani_font_draw(px, w, h, x0 + name_w + c * colw, y, ts * 4 / 5, C_DIM, COLS[cols[c]].title);
    y += rowh;
    for (int l = 0; l < ANI_AP_LEVELS; l++) {
        if (l == s_row) ani_fill(px, w, h, x0 - ts / 2, y - ts / 2, w - 2 * x0 + ts, rowh, C_ROW);
        ani_font_draw(px, w, h, x0, y, ts, l == s_row ? C_GOLD : C_TEXT, ani_ap_levels[l].name);
        for (int c = 0; c < nc; c++)
            draw_cell(px, w, h, x0 + name_w + c * colw, y, ts, st->cell[l][COLS[cols[c]].kind]);
        y += rowh;
    }
    /* Totals. */
    y += ts / 2;
    ani_font_draw(px, w, h, x0, y, ts, C_DIM, "All sets");
    for (int c = 0; c < nc; c++) {
        AniUiCount t = { 0, 0 };
        for (int l = 0; l < ANI_AP_LEVELS; l++) {
            t.found += st->cell[l][COLS[cols[c]].kind].found;
            t.total += st->cell[l][COLS[cols[c]].kind].total;
        }
        draw_cell(px, w, h, x0 + name_w + c * colw, y, ts, t);
    }
    ani_font_draw(px, w, h, x0, h - ts * 3, ts * 4 / 5, C_DIM,
                  "Up/Down: choose    Enter or A: what's left    Tab or B: close");
}

static void draw_detail(uint32_t *px, int w, int h, const AniUiStatus *st, int ts)
{
    static const char *names[ANI_AP_NAMES];
    uint32_t kinds = st->kinds & ~(1u << ANI_AP_KIND_COLLECTIBLE);
    char t[160];
    int n = ani_ui_missing(s_detail, kinds, found_fn, NULL, names, ANI_AP_NAMES);
    int x0 = w / 12, rowh = ts * 3 / 2, y0 = h / 5 + rowh / 2;
    int per_col = (h - y0 - ts * 4) / rowh, ncol = 2;
    if (per_col < 1) per_col = 1;
    int page = per_col * ncol;
    if (s_scroll > n - page) s_scroll = n - page;
    if (s_scroll < 0) s_scroll = 0;

    snprintf(t, sizeof t, "%s: %d left", ani_ap_levels[s_detail].name, n);
    ani_font_draw(px, w, h, x0, y0 - rowh, ts, C_GOLD, t);
    if (!n)
        ani_font_draw(px, w, h, x0, y0 + rowh, ts, C_GREEN, "Everything here is found.");
    for (int i = 0; i < page && s_scroll + i < n; i++) {
        int col = i / per_col, row = i % per_col;
        char line[160];
        fit(line, sizeof line, short_name(names[s_scroll + i]), ts, (w - 2 * x0) / ncol - ts);
        ani_font_draw(px, w, h, x0 + col * (w - 2 * x0) / ncol, y0 + row * rowh + ts / 2, ts, C_TEXT, line);
    }
    if (st->kinds >> ANI_AP_KIND_COLLECTIBLE & 1) {
        AniUiCount c = st->cell[s_detail][ANI_AP_KIND_COLLECTIBLE];
        snprintf(t, sizeof t, "Collectibles: %d of %d found (not listed one by one)", c.found, c.total);
        ani_font_draw(px, w, h, x0, h - ts * 4, ts * 4 / 5, C_DIM, t);
    }
    ani_font_draw(px, w, h, x0, h - ts * 3, ts * 4 / 5, C_DIM,
                  n > page ? "Up/Down: scroll    Left or B: back    Tab: close"
                           : "Left or B: back    Tab: close");
}

bool nv2a_overlay_frame(uint32_t *px, int w, int h, const uint32_t *backdrop)
{
    AniUiStatus st;
    char t[96];
    int ts = h / 32 > 12 ? h / 32 : 12;
    int act = action();
    if (act != A_NONE) s_dumped = 0;

    switch (act) {
    case A_UP:
        if (s_detail >= 0) s_scroll -= 2;
        else s_row = (s_row + ANI_AP_LEVELS - 1) % ANI_AP_LEVELS;
        break;
    case A_DOWN:
        if (s_detail >= 0) s_scroll += 2;
        else s_row = (s_row + 1) % ANI_AP_LEVELS;
        break;
    case A_IN:
        if (s_detail < 0) { s_detail = s_row; s_scroll = 0; }
        break;
    case A_OUT:
        s_detail = -1;
        break;
    case A_CLOSE:
        SDL_AtomicSet(&s_open, 0);
        return false;
    default:
        break;
    }

    /* The held frame, darkened. */
    for (int i = 0; i < w * h; i++) {
        uint32_t c = backdrop[i];
        px[i] = 0xFF000000u | ((c >> 16 & 0xFF) * 3 / 10) << 16 |
                ((c >> 8 & 0xFF) * 3 / 10) << 8 | (c & 0xFF) * 3 / 10;
    }
    ani_ui_get_status(&st);
    int x0 = w / 12;
    ani_font_draw(px, w, h, x0, h / 14, ts * 3 / 2, C_TEXT, "Archipelago tracker");
    counter_text(t, sizeof t, &st);
    snprintf(t + strlen(t), sizeof t - strlen(t), "      %s",
             st.conn == ANI_UI_CONNECTED ? "connected" :
             st.conn == ANI_UI_CONNECTING ? "reconnecting" : "offline");
    fill_dot(px, w, h, x0 + ts / 3, h / 14 + ts * 2 + ts / 2, ts / 3, conn_color(st.conn));
    ani_font_draw(px, w, h, x0 + ts, h / 14 + ts * 2, ts, C_DIM, t);

    if (s_detail >= 0) draw_detail(px, w, h, &st, ts);
    else draw_main(px, w, h, &st, ts);
    if (dump_dir() && s_dumped++ == 1) {
        char path[1024];
        snprintf(path, sizeof path, "%s/tracker_%llu.ppm", dump_dir(),
                 (unsigned long long)ani_ui_now_ms());
        dump_ppm(path, px, w, h);
    }
    return true;
}
