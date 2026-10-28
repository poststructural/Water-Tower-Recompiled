#include "ap_game.h"

#include <stddef.h>
#include <string.h>

extern ptrdiff_t g_xbox_mem_offset;

#define G8(va)  (*(volatile uint8_t  *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))
#define G16(va) (*(volatile uint16_t *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))
#define G32(va) (*(volatile uint32_t *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))
#define GF(va)  (*(volatile float    *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))

/* Guest pointers must land in the 64 MB of RAM, away from page zero. */
static bool guest_ptr_ok(uint32_t va) { return va >= 0x10000u && va < 0x04000000u; }

int ani_game_level(void)
{
    int32_t raw;
    if (!g_xbox_mem_offset) return -1;
    raw = (int32_t)G32(ANI_G_LEVEL_INDEX) - ANI_G_LEVEL_BIAS;
    return raw >= 0 && raw < ANI_G_LEVELS ? raw : -1;
}

int ani_game_record_edgars(int level)
{
    uint32_t rec = ANI_G_LEVEL_RECORDS + (uint32_t)level * ANI_G_LEVEL_RECORD;
    return (int)((G32(rec + ANI_G_RECORD_EDGARS) >> 4) & 0xF);
}

uint16_t ani_game_abilities(void) { return G16(ANI_G_ABILITIES); }
void ani_game_set_abilities(uint16_t bits) { G16(ANI_G_ABILITIES) = bits; }
bool ani_game_edgar_pending(void) { return G8(ANI_G_EDGAR_PENDING) != 0; }

uint32_t ani_game_pickup_state(uint32_t obj)
{
    return guest_ptr_ok(obj) ? G32(obj + ANI_G_PICKUP_STATE) : 0xFFFFu;
}

uint32_t ani_game_pickup_type(uint32_t obj)
{
    return guest_ptr_ok(obj) ? G32(obj + ANI_G_PICKUP_TYPE) : 0;
}

bool ani_game_object_name(uint32_t obj, char *out, size_t n)
{
    uint32_t s;
    size_t i;
    if (!guest_ptr_ok(obj) || !n) return false;
    s = G32(obj + ANI_G_OBJ_NAME);
    if (!guest_ptr_ok(s)) return false;
    for (i = 0; i + 1 < n && G8(s + i); i++) out[i] = (char)G8(s + i);
    out[i] = 0;
    return i > 0;
}

static int lower(int c) { return c >= 'A' && c <= 'Z' ? c - 'A' + 'a' : c; }

int ani_strnicmp(const char *a, const char *b, size_t n)
{
    for (; n; n--, a++, b++) {
        int d = lower((unsigned char)*a) - lower((unsigned char)*b);
        if (d || !*a) return d;
    }
    return 0;
}

int ani_stricmp(const char *a, const char *b) { return ani_strnicmp(a, b, (size_t)-1); }

/* 0x0009C7A0 for a plain name (no "object." prefix): the store's table at
 * +0x1C holds a count at +4 and 0x18-byte entries at +8 (name pointer, then
 * a type word); type-2 entries are floats, kept in 16-byte slots at +0x24 in
 * the order they appear in the table. */
bool ani_game_script_var(const char *name, float *out)
{
    uint32_t store, table, entries, values;
    unsigned count, floats = 0;
    size_t want = strlen(name);

    store = G32(ANI_G_SCRIPT_STORE);
    if (!guest_ptr_ok(store)) return false;
    table = G32(store + 0x1C);
    if (!guest_ptr_ok(table)) return false;
    count = G16(table + 4);
    entries = G32(table + 8);
    values = G32(store + 0x24);
    if (!guest_ptr_ok(entries) || !guest_ptr_ok(values) || count > 4096) return false;
    for (unsigned i = 0; i < count; i++) {
        uint32_t e = entries + i * 0x18u, s = G32(e);
        uint16_t type = G16(e + 4);
        if (guest_ptr_ok(s) &&
            !memcmp((const void *)((uintptr_t)g_xbox_mem_offset + s), name, want + 1)) {
            if (type != 2) return false;
            *out = GF(values + floats * 16u);
            return true;
        }
        if (type == 2) floats++;
    }
    return false;
}
