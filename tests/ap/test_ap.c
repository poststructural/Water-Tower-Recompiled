/**
 * Host tests for the Archipelago bridge, against fake guest memory.
 *
 *   test_ap json                 JSON parser and builder
 *   test_ap game                 guest-memory adapter
 *   test_ap live SAVE ADDR SLOT  a session against a running Archipelago
 *                                server (tests/ap/run_live.py drives it)
 *   test_ap offline SAVE ADDR SLOT   with the server down: pick up an Edgar
 *   test_ap resume SAVE ADDR SLOT    server back: the offline check is sent
 *
 * It includes ap_bridge.c to see the bridge's state.
 */
#include "../../src/ap/ap_bridge.c"

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

ptrdiff_t g_xbox_mem_offset;
_Thread_local uint32_t g_eax, g_esp;

#define FAIL(...) do { fprintf(stderr, "FAIL %s:%d: ", __FILE__, __LINE__); \
                       fprintf(stderr, __VA_ARGS__); fputc('\n', stderr); exit(1); } while (0)
#define CHECK(c) do { if (!(c)) FAIL("%s", #c); } while (0)

/* ── Fake guest ────────────────────────────────────────────── */

#define STORE   0x00500000u
#define TABLE   0x00501000u
#define ENTRIES 0x00502000u
#define NAMES   0x00503000u
#define VALUES  0x00504000u
#define STACK   0x00600000u

static void guest_init(void)
{
    uint8_t *mem = calloc(1, 0x04000000);
    const char *names[] = { "Objecttype", "OscarPickupsCollected" };
    uint32_t at = NAMES;
    CHECK(mem);
    g_xbox_mem_offset = (ptrdiff_t)(uintptr_t)mem;
    G32(ANI_G_SCRIPT_STORE) = STORE;
    G32(STORE + 0x1C) = TABLE;
    G32(STORE + 0x24) = VALUES;
    *(uint16_t *)((uintptr_t)mem + TABLE + 4) = 2;
    G32(TABLE + 8) = ENTRIES;
    for (int i = 0; i < 2; i++) {
        strcpy((char *)mem + at, names[i]);
        G32(ENTRIES + i * 0x18u) = at;
        *(uint16_t *)((uintptr_t)mem + ENTRIES + i * 0x18u + 4) = 2;
        at += 64;
    }
    /* The pickup code's counter is the same float (assumed; see the docs). */
    G32(ANI_G_EDGAR_COUNTER) = VALUES + 16;
    g_esp = STACK;
}

static void set_level(int lv) { G32(ANI_G_LEVEL_INDEX) = (uint32_t)(lv + ANI_G_LEVEL_BIAS); }
static float *edgar_var(void) { return (float *)((uintptr_t)g_xbox_mem_offset + VALUES + 16); }

/* Each fake body ends like a generated one: its ret pops the return address. */
#define RET() (g_esp += 4)

static void gen_frame(void)
{
    RET();
    if (*(uint8_t *)((uintptr_t)g_xbox_mem_offset + ANI_G_EDGAR_PENDING)) {
        *edgar_var() += 1.0f;
        *(uint8_t *)((uintptr_t)g_xbox_mem_offset + ANI_G_EDGAR_PENDING) = 0;
    }
}
static void gen_pickup_edgar(void) { *edgar_var() += 1.0f; RET(); }
static void gen_pickup_other(void) { RET(); }
static void gen_give(void)
{
    *(uint16_t *)((uintptr_t)g_xbox_mem_offset + ANI_G_ABILITIES) |= (uint16_t)G32(g_esp + 4);
    RET();
}
static void gen_get_all(void)
{
    GF(G32(G32(g_esp + 8) + 4)) = 99.0f;
    RET();
}

static void give(uint16_t bits)
{
    g_esp = STACK;
    G32(g_esp + 4) = bits;
    ani_ap_hook_give_ability(gen_give);
    CHECK(g_esp == STACK + 4);   /* the return address was popped exactly once */
}

static float get_all_edgars(void)
{
    g_esp = STACK;
    G32(g_esp + 8) = 0x00610000u;
    G32(0x00610004u) = 0x00610100u;
    GF(0x00610100u) = -1.0f;
    ani_ap_hook_get_all_edgars(gen_get_all);
    CHECK(g_esp == STACK + 4);
    return GF(0x00610100u);
}

static void frames_until(bool (*cond)(void), int ms, const char *what)
{
    for (int t = 0; t < ms; t += 10) {
        ani_ap_main_loop();
        ani_ap_hook_frame(gen_frame);
        if (cond()) return;
        usleep(10000);
    }
    FAIL("timed out waiting for %s", what);
}

/* ── Unit tests ────────────────────────────────────────────── */

static void test_json(void)
{
    AjValue *v = aj_parse("[{\"cmd\":\"ReceivedItems\",\"index\":0,\"items\":"
                          "[{\"item\":1095630849,\"location\":-2,\"player\":0,\"flags\":1}],"
                          "\"s\":\"a\\\"b\\u00e9\\ud83d\\ude00\",\"f\":1.5,\"t\":true,\"n\":null}]");
    AjBuf b = {0};
    CHECK(v && v->type == AJ_ARR && v->len == 1);
    CHECK(!strcmp(aj_str(aj_get(aj_at(v, 0), "cmd"), ""), "ReceivedItems"));
    CHECK(aj_int(aj_get(aj_at(aj_get(aj_at(v, 0), "items"), 0), "item"), 0) == 1095630849LL);
    CHECK(aj_int(aj_get(aj_at(aj_get(aj_at(v, 0), "items"), 0), "location"), 0) == -2);
    CHECK(!strcmp(aj_str(aj_get(aj_at(v, 0), "s"), ""), "a\"b\xC3\xA9\xF0\x9F\x98\x80"));
    CHECK(aj_get(aj_at(v, 0), "f")->num == 1.5 && !aj_get(aj_at(v, 0), "f")->is_int);
    CHECK(aj_bool(aj_get(aj_at(v, 0), "t"), false));
    CHECK(aj_get(aj_at(v, 0), "n")->type == AJ_NULL);
    aj_free(v);
    CHECK(!aj_parse("[1,]") && !aj_parse("{\"a\" 1}") && !aj_parse("\"open") && !aj_parse("[] x"));
    ajb_str(&b, "q\"\\\n");
    CHECK(!strcmp(b.buf, "\"q\\\"\\\\\\u000a\""));
    ajb_free(&b);
    puts("json ok");
}

static void test_game(void)
{
    float v = 0;
    guest_init();
    CHECK(ani_game_level() == -1);
    set_level(2);
    CHECK(ani_game_level() == 2);
    *edgar_var() = 3.0f;
    CHECK(ani_game_script_var("OscarPickupsCollected", &v) && v == 3.0f);
    CHECK(!ani_game_script_var("Nope", &v));
    CHECK(ani_game_edgar_counter(&v) && v == 3.0f);
    G32(ANI_G_LEVEL_RECORDS + 2 * ANI_G_LEVEL_RECORD + ANI_G_RECORD_EDGARS) = 5u << 4;
    CHECK(ani_game_record_edgars(2) == 5);
    /* Without a session the hooks are the game's own code. */
    give(0x80);
    CHECK(ani_game_abilities() == 0x80);
    CHECK(get_all_edgars() == 99.0f);
    puts("game ok");
}

/* ── Live tests ────────────────────────────────────────────── */

static bool connected(void) { return S.generation != 0; }
static bool all_acked(void)
{
    for (int i = 0; i < S.checked.n; i++)
        if (!set_has(&S.acked, S.checked.v[i])) return false;
    return S.checked.n > 0;
}
static int want_items;
static bool have_items(void) { return S.item_count >= want_items; }

static void boot(int argc, char **argv)
{
    char *args[8] = { "test_ap", "--ap-server", argv[3], "--ap-slot", argv[4], "game", NULL };
    int n = 6;
    const char *dir;
    guest_init();
    dir = ani_ap_init(&n, args, argv[2]);
    (void)argc;
    CHECK(dir && ani_ap_active());
    CHECK(n == 2 && !strcmp(args[1], "game"));   /* --ap-* consumed */
    printf("save dir %s\n", dir);
}

static void test_live(int argc, char **argv)
{
    int edgar_items;
    boot(argc, argv);
    frames_until(connected, 10000, "Connected");
    CHECK(S.have_slot_data && S.shuffled_mask != 0);

    /* Native ability grants become checks and give nothing. */
    give(0x001);
    CHECK(set_has(&S.checked, ani_ap_abilities[0].location));
    frames_until(all_acked, 5000, "the Bomb check to be acknowledged");

    /* An Edgar picked up in level 1 is "Level 1 Edgar 1". */
    set_level(1);
    *edgar_var() = 0;
    ani_ap_hook_pickup(gen_pickup_other);
    CHECK(S.checked.n == 1);
    ani_ap_hook_pickup(gen_pickup_edgar);
    CHECK(set_has(&S.checked, ani_ap_levels[1].edgar_location[0]));
    /* A script-given Edgar arrives through the frame. */
    *(uint8_t *)((uintptr_t)g_xbox_mem_offset + ANI_G_EDGAR_PENDING) = 1;
    ani_ap_hook_frame(gen_frame);
    CHECK(set_has(&S.checked, ani_ap_levels[1].edgar_location[1]));
    frames_until(all_acked, 5000, "the Edgar checks to be acknowledged");

    /* The world puts some item behind each check; with one player all of
     * them are ours. Start inventory (Wakko, Dot) arrives too. */
    want_items = 3 + 2;
    frames_until(have_items, 5000, "items for the three checks");
    edgar_items = S.edgars;
    CHECK(get_all_edgars() == (float)edgar_items);
    /* The abilities the session owns follow what was received; Wakko and
     * Dot are start inventory and so on from the start. */
    ani_ap_main_loop();
    CHECK(S.forced_mask == 0x7FF);
    CHECK((ani_game_abilities() & S.forced_mask) == S.ap_bits);
    CHECK((ani_game_abilities() & 0x30) == 0x30);
    /* A save that brings its own ability bits is overridden. */
    ani_game_set_abilities(0x7FF);
    ani_ap_main_loop();
    CHECK(ani_game_abilities() == S.ap_bits);
    printf("live ok: %d checks, %d items, %d Edgars, abilities 0x%03X\n",
           S.checked.n, S.item_count, S.edgars, S.ap_bits);
}

static void test_offline(int argc, char **argv)
{
    boot(argc, argv);   /* the server is down: the last seed is used */
    CHECK(S.item_count >= 5 && S.checked.n == 3);
    set_level(2);
    *edgar_var() = 0;
    ani_ap_hook_pickup(gen_pickup_edgar);
    CHECK(set_has(&S.checked, ani_ap_levels[2].edgar_location[0]));
    CHECK(!all_acked());
    puts("offline ok");
}

static void test_resume(int argc, char **argv)
{
    boot(argc, argv);
    CHECK(S.checked.n == 4 && !all_acked());
    frames_until(connected, 10000, "Connected");
    frames_until(all_acked, 5000, "the offline check to be acknowledged");
    puts("resume ok");
}

int main(int argc, char **argv)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc >= 2 && !strcmp(argv[1], "json")) test_json();
    else if (argc >= 2 && !strcmp(argv[1], "game")) test_game();
    else if (argc >= 5 && !strcmp(argv[1], "live")) test_live(argc, argv);
    else if (argc >= 5 && !strcmp(argv[1], "offline")) test_offline(argc, argv);
    else if (argc >= 5 && !strcmp(argv[1], "resume")) test_resume(argc, argv);
    else { fprintf(stderr, "usage: see the top of test_ap.c\n"); return 2; }
    _exit(0);
}
