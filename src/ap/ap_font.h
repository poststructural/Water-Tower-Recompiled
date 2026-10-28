/**
 * Text for the Archipelago overlay: a TrueType font from the system (Segoe UI,
 * Arial, DejaVu Sans...) through stb_truetype, or stb_easy_font's built-in
 * strokes when none is found. Latin-1 is drawn; anything else is '?'.
 * Renderer thread only.
 */
#pragma once
#include <stdbool.h>
#include <stdint.h>

/* False when no font file was found and the fallback is in use. */
bool ani_font_init(void);
/* Width in pixels of utf8 at a line height of size_px. */
int ani_font_width(int size_px, const char *utf8);
/* Draws utf8 with its top-left at x, y into px (w x h ARGB, rows top-down),
 * blended over what is there and clipped to the buffer. Returns its width. */
int ani_font_draw(uint32_t *px, int w, int h, int x, int y, int size_px,
                  uint32_t argb, const char *utf8);
/* Fills a rectangle, blended by argb's alpha, clipped. */
void ani_fill(uint32_t *px, int w, int h, int x, int y, int rw, int rh, uint32_t argb);
