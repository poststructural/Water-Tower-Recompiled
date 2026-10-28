#include "ap_font.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-function"
#endif
#define STB_TRUETYPE_IMPLEMENTATION
#define STBTT_STATIC
#include "stb_truetype.h"
#include "stb_easy_font.h"
#if defined(__GNUC__)
#pragma GCC diagnostic pop
#endif

static unsigned char *s_ttf;
static stbtt_fontinfo s_info;
static bool s_tried, s_have;

/* Glyphs rasterized once per size, for the few sizes a window uses. */
#define SIZES 6
typedef struct { unsigned char *bm; int w, h, xoff, yoff, adv; bool done; } Glyph;
static struct { int px; float scale; int ascent; Glyph g[256]; } s_cache[SIZES];
static int s_cache_next;

static unsigned char *read_file(const char *path)
{
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    unsigned char *b = n > 0 ? malloc((size_t)n) : NULL;
    if (b && fread(b, 1, (size_t)n, f) != (size_t)n) { free(b); b = NULL; }
    fclose(f);
    return b;
}

bool ani_font_init(void)
{
    char path[512];
    const char *win = getenv("WINDIR");
    const char *tries[] = {
        "segoeuib.ttf", "segoeui.ttf", "arialbd.ttf", "arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    };
    if (s_tried) return s_have;
    s_tried = true;
    for (size_t i = 0; i < sizeof tries / sizeof *tries && !s_have; i++) {
        if (tries[i][0] == '/') snprintf(path, sizeof path, "%s", tries[i]);
        else if (win) snprintf(path, sizeof path, "%s\\Fonts\\%s", win, tries[i]);
        else continue;
        s_ttf = read_file(path);
        if (s_ttf && stbtt_InitFont(&s_info, s_ttf, stbtt_GetFontOffsetForIndex(s_ttf, 0))) {
            s_have = true;
        } else {
            free(s_ttf);
            s_ttf = NULL;
        }
    }
    return s_have;
}

/* Next Latin-1 code point of a UTF-8 string ('?' for the rest). */
static int next_cp(const char **s)
{
    const unsigned char *p = (const unsigned char *)*s;
    int cp, n;
    if (p[0] < 0x80) { *s += 1; return p[0]; }
    if ((p[0] & 0xE0) == 0xC0) { cp = p[0] & 0x1F; n = 1; }
    else if ((p[0] & 0xF0) == 0xE0) { cp = p[0] & 0x0F; n = 2; }
    else if ((p[0] & 0xF8) == 0xF0) { cp = p[0] & 0x07; n = 3; }
    else { *s += 1; return '?'; }
    for (int i = 1; i <= n; i++) {
        if ((p[i] & 0xC0) != 0x80) { *s += i; return '?'; }
        cp = cp << 6 | (p[i] & 0x3F);
    }
    *s += n + 1;
    return cp < 256 ? cp : '?';
}

static int cache_for(int size_px)
{
    for (int i = 0; i < SIZES; i++)
        if (s_cache[i].px == size_px) return i;
    int i = s_cache_next++ % SIZES;
    for (int c = 0; c < 256; c++) free(s_cache[i].g[c].bm);
    memset(&s_cache[i], 0, sizeof s_cache[i]);
    s_cache[i].px = size_px;
    s_cache[i].scale = stbtt_ScaleForPixelHeight(&s_info, (float)size_px);
    int asc, desc, gap;
    stbtt_GetFontVMetrics(&s_info, &asc, &desc, &gap);
    s_cache[i].ascent = (int)(asc * s_cache[i].scale + 0.5f);
    return i;
}

static Glyph *glyph(int ci, int cp)
{
    Glyph *g = &s_cache[ci].g[cp];
    if (!g->done) {
        float sc = s_cache[ci].scale;
        int adv, lsb;
        if (!stbtt_FindGlyphIndex(&s_info, cp)) cp = '?';
        stbtt_GetCodepointHMetrics(&s_info, cp, &adv, &lsb);
        g->adv = (int)(adv * sc + 0.5f);
        g->bm = stbtt_GetCodepointBitmap(&s_info, sc, sc, cp, &g->w, &g->h, &g->xoff, &g->yoff);
        g->done = true;
    }
    return g;
}

static inline void blend(uint32_t *d, uint32_t argb, unsigned cover)
{
    unsigned a = (argb >> 24) * cover / 255;
    if (!a) return;
    uint32_t s = argb, o = *d;
    unsigned r = ((s >> 16 & 0xFF) * a + (o >> 16 & 0xFF) * (255 - a)) / 255;
    unsigned g = ((s >> 8 & 0xFF) * a + (o >> 8 & 0xFF) * (255 - a)) / 255;
    unsigned b = ((s & 0xFF) * a + (o & 0xFF) * (255 - a)) / 255;
    *d = 0xFF000000u | r << 16 | g << 8 | b;
}

void ani_fill(uint32_t *px, int w, int h, int x, int y, int rw, int rh, uint32_t argb)
{
    int x0 = x < 0 ? 0 : x, y0 = y < 0 ? 0 : y;
    int x1 = x + rw > w ? w : x + rw, y1 = y + rh > h ? h : y + rh;
    for (int j = y0; j < y1; j++)
        for (int i = x0; i < x1; i++)
            blend(&px[(size_t)j * w + i], argb, 255);
}

/* stb_easy_font's strokes, scaled: it lays text out about 12 units tall. */
static int easy_draw(uint32_t *px, int w, int h, int x, int y, int size_px, uint32_t argb,
                     const char *utf8, bool draw)
{
    char latin[256];
    static char quads[256 * 270];
    size_t n = 0;
    const char *s = utf8;
    while (*s && n + 1 < sizeof latin) {
        int cp = next_cp(&s);
        latin[n++] = (char)(cp < 128 ? cp : '?');
    }
    latin[n] = 0;
    float k = size_px / 12.0f;
    int width = (int)(stb_easy_font_width(latin) * k + 0.5f);
    if (!draw) return width;
    int nq = stb_easy_font_print(0, 0, latin, NULL, quads, sizeof quads);
    for (int q = 0; q < nq; q++) {
        float *v = (float *)(quads + q * 64);     /* 4 vertices of x, y, z, color */
        int qx0 = x + (int)(v[0] * k), qy0 = y + (int)(v[1] * k);
        int qx1 = x + (int)(v[8] * k + 0.999f), qy1 = y + (int)(v[9] * k + 0.999f);
        ani_fill(px, w, h, qx0, qy0, qx1 - qx0, qy1 - qy0, argb);
    }
    return width;
}

int ani_font_width(int size_px, const char *utf8)
{
    if (!utf8 || size_px <= 0) return 0;
    if (!ani_font_init()) return easy_draw(NULL, 0, 0, 0, 0, size_px, 0, utf8, false);
    int ci = cache_for(size_px), wsum = 0;
    for (const char *s = utf8; *s;) wsum += glyph(ci, next_cp(&s))->adv;
    return wsum;
}

int ani_font_draw(uint32_t *px, int w, int h, int x, int y, int size_px,
                  uint32_t argb, const char *utf8)
{
    if (!utf8 || size_px <= 0) return 0;
    if (!ani_font_init()) return easy_draw(px, w, h, x, y, size_px, argb, utf8, true);
    int ci = cache_for(size_px), pen = x;
    int base = y + s_cache[ci].ascent;
    for (const char *s = utf8; *s;) {
        Glyph *g = glyph(ci, next_cp(&s));
        int gx = pen + g->xoff, gy = base + g->yoff;
        for (int j = 0; j < g->h; j++) {
            int yy = gy + j;
            if (yy < 0 || yy >= h) continue;
            for (int i = 0; i < g->w; i++) {
                int xx = gx + i;
                if (xx < 0 || xx >= w) continue;
                unsigned c = g->bm[j * g->w + i];
                if (c) blend(&px[(size_t)yy * w + xx], argb, c);
            }
        }
        pen += g->adv;
    }
    return pen - x;
}
