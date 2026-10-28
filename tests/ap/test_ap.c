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
#include "../../src/ap/ap_ui.h"
#include "../../src/ap/ap_font.h"

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
#define OBJECTS 0x00520000u     /* fake pickup objects, 0x200 apart */
#define STACK   0x00600000u

static void guest_init(void)
{
    uint8_t *mem = calloc(1, 0x04000000);
    const char *names[] = { "Objecttype", "OscarPickupsCollected", "MajorPickupsCollected" };
    uint32_t at = NAMES;
    CHECK(mem);
    g_xbox_mem_offset = (ptrdiff_t)(uintptr_t)mem;
    G32(ANI_G_SCRIPT_STORE) = STORE;
    G32(STORE + 0x1C) = TABLE;
    G32(STORE + 0x24) = VALUES;
    *(uint16_t *)((uintptr_t)mem + TABLE + 4) = 3;
    G32(TABLE + 8) = ENTRIES;
    for (int i = 0; i < 3; i++) {
        strcpy((char *)mem + at, names[i]);
        G32(ENTRIES + i * 0x18u) = at;
        *(uint16_t *)((uintptr_t)mem + ENTRIES + i * 0x18u + 4) = 2;
        at += 64;
    }
    g_esp = STACK;
}

/* A pickup object as 0x00027E00 sees it: name, state 0 (waiting), type. */
static uint32_t make_pickup(int n, const char *name, uint32_t type)
{
    uint32_t obj = OBJECTS + (uint32_t)n * 0x200u;
    strcpy((char *)((uintptr_t)g_xbox_mem_offset + obj + 0x180), name);
    G32(obj + ANI_G_OBJ_NAME) = obj + 0x180;
    G32(obj + ANI_G_PICKUP_STATE) = 0;
    G32(obj + ANI_G_PICKUP_TYPE) = type;
    return obj;
}

static void set_level(int lv) { G32(ANI_G_LEVEL_INDEX) = (uint32_t)(lv + ANI_G_LEVEL_BIAS); }
static float *edgar_var(void) { return (float *)((uintptr_t)g_xbox_mem_offset + VALUES + 16); }
static float *major_var(void) { return (float *)((uintptr_t)g_xbox_mem_offset + VALUES + 32); }

/* Each fake body ends like a generated one: its ret pops the return address. */
#define RET() (g_esp += 4)

/* The level update clears the CC Deville flag as it hands the Edgar over. */
static void gen_frame(void)
{
    *(uint8_t *)((uintptr_t)g_xbox_mem_offset + ANI_G_EDGAR_PENDING) = 0;
    RET();
}
/* The pickup's own update: an Edgar goes straight to state 4, a counted
 * pickup (type 1) to state 3 once its counter is up; a waiting one stays. */
static void gen_pickup_collect(void)
{
    uint32_t obj = G32(g_esp + 4);
    if (G32(obj + ANI_G_PICKUP_TYPE) == 1) {
        *major_var() += 1.0f;
        G32(obj + ANI_G_PICKUP_STATE) = 3;
    } else {
        G32(obj + ANI_G_PICKUP_STATE) = 4;
    }
    RET();
}
static void gen_pickup_wait(void) { RET(); }

static void pickup(uint32_t obj, ani_gen_fn body)
{
    g_esp = STACK;
    G32(g_esp + 4) = obj;
    ani_ap_hook_pickup(body);
    CHECK(g_esp == STACK + 4);
}

static int64_t loc_named(const char *name)
{
    for (int i = 0; i < ANI_AP_NAMES; i++)
        if (!strcmp(ani_ap_location_names[i].name, name)) return ani_ap_location_names[i].id;
    FAIL("no location %s", name);
}
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
    {
        char name[64];
        uint32_t obj = make_pickup(0, "Edgar_Bronco", 3);
        CHECK(ani_game_object_name(obj, name, sizeof name) && !strcmp(name, "Edgar_Bronco"));
        CHECK(ani_game_pickup_type(obj) == 3 && ani_game_pickup_state(obj) == 0);
        CHECK(ani_game_pickup_state(0) == 0xFFFFu);
        CHECK(!ani_stricmp("ACME_a", "acme_A") && ani_strnicmp("edgar_125_07", "Edgar_125_", 10) == 0);
    }
    /* Every location the catalog names has its own ID, inside the span. */
    for (int i = 1; i < ANI_AP_NAMES; i++)
        CHECK(ani_ap_location_names[i].id > ani_ap_location_names[i - 1].id &&
              loc_ok(ani_ap_location_names[i].id));
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
    bool all = true;
    SET_EACH(&S.checked, v, if (in_room(v) && !set_has(&S.acked, v)) all = false;)
    return all && S.checked.n > 0;
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
    CHECK(set_has(&S.checked, loc_named("King O'Sullivans Mines: Bomb")));
    frames_until(all_acked, 5000, "the Bomb check to be acknowledged");

    /* A pickup is the check its object is: the Rodeo Edgar in Ye Old West,
     * once it is collected and not while it waits. */
    set_level(1);
    {
        uint32_t bronco = make_pickup(1, "Edgar_Bronco", 3);
        uint32_t room125 = make_pickup(2, "edgar_125_33", 3);
        uint32_t nugget = make_pickup(3, "goldnuggets1", 1);
        pickup(bronco, gen_pickup_wait);
        CHECK(S.checked.n == 1);
        pickup(bronco, gen_pickup_collect);
        CHECK(set_has(&S.checked, loc_named("Ye Old West: Rodeo Edgar")));
        pickup(bronco, gen_pickup_collect);    /* stays collected: nothing new */
        CHECK(S.checked.n == 2);
        /* Any room's copy of the 125 Edgar is that Edgar. */
        pickup(room125, gen_pickup_collect);
        CHECK(set_has(&S.checked, loc_named("Ye Old West: 125 Gold Nuggets Edgar")));
        /* A collectible, and the milestone it completes. */
        *major_var() = 24.0f;
        pickup(nugget, gen_pickup_collect);
        CHECK(set_has(&S.checked, loc_named("Ye Old West: Gold Nugget 1")));
        CHECK(set_has(&S.checked, loc_named("Ye Old West: 25 Gold Nuggets")));
        CHECK(!set_has(&S.checked, loc_named("Ye Old West: 50 Gold Nuggets")));
        /* Objects are named per level: Spooky Movie's second C, and a name
         * from another level that is nothing here. */
        set_level(2);
        *major_var() = 0.0f;
        pickup(make_pickup(4, "acme_c01", 5), gen_pickup_collect);
        CHECK(set_has(&S.checked, loc_named("Spooky Movie: Letter C")));
        pickup(make_pickup(5, "Edgar_Bronco", 3), gen_pickup_collect);
        CHECK(S.checked.n == 6);
    }
    frames_until(all_acked, 5000, "the checks to be acknowledged");

    /* The room has every collectible as a check and so no milestones: the
     * milestone is kept but not sent. */
    CHECK(!in_room(loc_named("Ye Old West: 25 Gold Nuggets")));
    CHECK(in_room(loc_named("Ye Old West: Gold Nugget 1")));

    /* The world puts some item behind each check; with one player all of
     * them are ours. Start inventory (Wakko, Dot) arrives too. */
    want_items = 5 + 2;
    frames_until(have_items, 5000, "items for the five checks sent");
    /* Each came with a popup, and the counter knows them. */
    {
        AniUiToast t[8];
        AniUiStatus st;
        int n = ani_ui_toasts(t, 8, ani_ui_now_ms());
        CHECK(n >= 1 && t[0].kind != ANI_UI_SENT);
        ani_ui_get_status(&st);
        CHECK(st.active && st.conn == ANI_UI_CONNECTED && st.edgars == S.edgars);
        CHECK(st.cell[1][ANI_AP_KIND_EDGAR].found == 2 && st.cell[1][ANI_AP_KIND_EDGAR].total == 8);
    }
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
    CHECK(S.item_count >= 7 && S.checked.n == 6);
    set_level(2);
    pickup(make_pickup(0, "Edgar_Boss", 3), gen_pickup_collect);
    CHECK(set_has(&S.checked, loc_named("Spooky Movie: Bride Boss Edgar")));
    /* Beating CC Deville: the flag the next frame turns into the last Edgar
     * and the ending. */
    set_level(0);
    CHECK(!S.credits_reached);
    *(uint8_t *)((uintptr_t)g_xbox_mem_offset + ANI_G_EDGAR_PENDING) = 1;
    g_esp = STACK;
    ani_ap_hook_frame(gen_frame);
    CHECK(g_esp == STACK + 4);
    CHECK(set_has(&S.checked, ANI_AP_CC_DEVILLE_EDGAR) && S.credits_reached);
    CHECK(!all_acked());
    puts("offline ok");
}

static void test_resume(int argc, char **argv)
{
    boot(argc, argv);
    CHECK(S.checked.n == 8 && S.credits_reached && !all_acked());
    frames_until(connected, 10000, "Connected");
    frames_until(all_acked, 5000, "the offline check to be acknowledged");
    puts("resume ok");
}

/* ── Overlay model ─────────────────────────────────────────── */

static bool found_one(int64_t loc, void *ctx) { return loc == *(int64_t *)ctx; }

static void test_ui(void)
{
    AniUiToast t[8];
    char buf[32];
    ani_ui_clear();
    /* A popup lasts ANI_UI_TOAST_MS and fades over its last ANI_UI_FADE_MS. */
    ani_ui_notify(ANI_UI_RECEIVED, true, "Edgar from Sam", 1000);
    CHECK(ani_ui_toasts(t, 8, 1000) == 1 && !strcmp(t[0].text, "Edgar from Sam"));
    CHECK(t[0].kind == ANI_UI_RECEIVED && t[0].progression && t[0].fade == 1.0f);
    CHECK(ani_ui_toasts(t, 8, 1000 + 3750) == 1 && t[0].fade > 0.4f && t[0].fade < 0.6f);
    CHECK(ani_ui_toasts(t, 8, 1000 + 3999) == 1);
    CHECK(ani_ui_toasts(t, 8, 1000 + 4000) == 0);

    /* Newest first, ANI_UI_SHOWN at most, the last line counts the rest. */
    ani_ui_clear();
    for (int i = 0; i < 6; i++) {
        snprintf(buf, sizeof buf, "item %d", i);
        ani_ui_notify(ANI_UI_SENT, false, buf, 100 + i);
    }
    CHECK(ani_ui_toasts(t, 8, 200) == ANI_UI_SHOWN);
    CHECK(!strcmp(t[0].text, "item 5") && !strcmp(t[2].text, "item 3"));
    CHECK(!strcmp(t[3].text, "+3 more") && t[3].kind == ANI_UI_INFO);
    /* A burst goes away together: the hidden ones are summed up, not queued. */
    CHECK(ani_ui_toasts(t, 8, 100 + 4005) == 0);

    /* A release of 50 items: bounded, and the count says so. */
    ani_ui_clear();
    for (int i = 0; i < 50; i++) ani_ui_notify(ANI_UI_RECEIVED, false, "Applause", 10);
    CHECK(ani_ui_toasts(t, 8, 10) == ANI_UI_SHOWN);
    CHECK(!strncmp(t[3].text, "+", 1) && atoi(t[3].text + 1) == 47);

    /* Status round trip. */
    AniUiStatus st = {0}, back;
    st.edgars = 12; st.required = 30; st.conn = ANI_UI_CONNECTED; st.active = true;
    st.cell[1][ANI_AP_KIND_EDGAR].found = 3;
    ani_ui_set_status(&st);
    ani_ui_get_status(&back);
    CHECK(!memcmp(&st, &back, sizeof st));

    /* Ye Old West has 8 Edgars; with one found, 7 names are left. */
    const char *names[64];
    int64_t rodeo = loc_named("Ye Old West: Rodeo Edgar");
    int n = ani_ui_missing(1, 1u << ANI_AP_KIND_EDGAR, found_one, &rodeo, names, 64);
    CHECK(n == 7);
    for (int i = 0; i < n; i++) CHECK(strcmp(names[i], "Ye Old West: Rodeo Edgar"));
    CHECK(ani_ui_missing(1, 1u << ANI_AP_KIND_EDGAR, found_one, &rodeo, names, 3) == 3);
    puts("ui ok");
}

static void feed(const char *json)
{
    AjValue *root = aj_parse(json);
    CHECK(root && root->type == AJ_ARR);
    for (const AjValue *p = root->child; p; p = p->next) handle_packet(p, S.generation);
    aj_free(root);
}

static void test_names(const char *dir)
{
    AniUiToast t[8];
    char cache[1100];
    snprintf(cache, sizeof cache, "%s/datapackage", dir);
    ani_mkdir(dir);
    ani_mkdir(cache);
    snprintf(S.names_dir, sizeof S.names_dir, "%s", cache);

    /* A package is kept, cached and read back. */
    ani_names_reset();
    S.generation = 0;
    feed("[{\"cmd\":\"DataPackage\",\"data\":{\"games\":{\"A Link to the Past\":"
         "{\"checksum\":\"abc123\",\"item_name_to_id\":{\"Hookshot\":10,\"Bow\":11},"
         "\"location_name_to_id\":{\"Link's House\":100}}}}}]");
    CHECK(!strcmp(ani_names_item("A Link to the Past", 10), "Hookshot"));
    ani_names_reset();
    CHECK(!ani_names_item("A Link to the Past", 10));
    ani_names_load(cache);
    CHECK(!strcmp(ani_names_item("A Link to the Past", 11), "Bow"));
    CHECK(!strcmp(ani_names_location("A Link to the Past", 100), "Link's House"));
    CHECK(ani_names_have("A Link to the Past", "abc123") && !ani_names_have("A Link to the Past", "x"));

    /* A broken cache file is skipped. */
    {
        char p[1200];
        snprintf(p, sizeof p, "%s/Broken_zzz.json", cache);
        FILE *f = fopen(p, "wb");
        fputs("{\"game\":\"Broken\",\"item_name_to_id\":{", f);
        fclose(f);
        ani_names_reset();
        ani_names_load(cache);
        CHECK(!ani_names_item("Broken", 1) && ani_names_item("A Link to the Past", 10));
    }

    /* ItemSend popups, by who found it and who gets it. */
    S.our_slot = 1;
    snprintf(S.players[1], sizeof S.players[1], "Me");
    snprintf(S.players[2], sizeof S.players[2], "Sam");
    snprintf(S.games[1], sizeof S.games[1], "%s", ANI_AP_GAME);
    snprintf(S.games[2], sizeof S.games[2], "A Link to the Past");
    ani_ui_clear();
    char pkt[512];
    snprintf(pkt, sizeof pkt, "[{\"cmd\":\"PrintJSON\",\"type\":\"ItemSend\",\"receiving\":1,"
             "\"item\":{\"item\":%lld,\"location\":100,\"player\":2,\"flags\":1},\"data\":[]}]",
             (long long)ANI_AP_EDGAR_ITEM);
    feed(pkt);
    CHECK(ani_ui_toasts(t, 8, ani_ui_now_ms()) == 1);
    CHECK(!strcmp(t[0].text, "Edgar from Sam") && t[0].kind == ANI_UI_RECEIVED && t[0].progression);
    ani_ui_clear();
    feed("[{\"cmd\":\"PrintJSON\",\"type\":\"ItemSend\",\"receiving\":2,"
         "\"item\":{\"item\":10,\"location\":1095630848,\"player\":1,\"flags\":0},\"data\":[]}]");
    CHECK(ani_ui_toasts(t, 8, ani_ui_now_ms()) == 1);
    CHECK(!strcmp(t[0].text, "Hookshot for Sam") && t[0].kind == ANI_UI_SENT && !t[0].progression);
    ani_ui_clear();
    feed("[{\"cmd\":\"PrintJSON\",\"type\":\"ItemSend\",\"receiving\":2,"
         "\"item\":{\"item\":99,\"location\":5,\"player\":3,\"flags\":0},\"data\":[]}]");
    CHECK(ani_ui_toasts(t, 8, ani_ui_now_ms()) == 0);   /* not ours either way */
    feed("[{\"cmd\":\"PrintJSON\",\"type\":\"ItemSend\",\"receiving\":2,"
         "\"item\":{\"item\":12345,\"location\":5,\"player\":1,\"flags\":0},\"data\":[]}]");
    CHECK(ani_ui_toasts(t, 8, ani_ui_now_ms()) == 1 && !strcmp(t[0].text, "an item for Sam"));
    ani_ui_clear();
    snprintf(pkt, sizeof pkt, "[{\"cmd\":\"PrintJSON\",\"type\":\"ItemSend\",\"receiving\":1,"
             "\"item\":{\"item\":%lld,\"location\":%lld,\"player\":1,\"flags\":1},\"data\":[]}]",
             (long long)ANI_AP_EDGAR_ITEM, (long long)loc_named("Ye Old West: Rodeo Edgar"));
    feed(pkt);
    CHECK(ani_ui_toasts(t, 8, ani_ui_now_ms()) == 1 && !strcmp(t[0].text, "Edgar (Rodeo Edgar)"));

    /* Items that came while away: one popup with the count. */
    ani_ui_clear();
    S.generation = 1;
    S.item_count = 3;
    for (int i = 0; i < 3; i++) S.items[i] = ANI_AP_FILLER_ITEM;
    snprintf(S.sidecar, sizeof S.sidecar, "%s/ap_state.json", dir);
    {
        AjBuf b = {0};
        ajb_raw(&b, "[{\"cmd\":\"ReceivedItems\",\"index\":0,\"items\":[");
        for (int i = 0; i < 10; i++)
            ajb_fmt(&b, "%s{\"item\":%lld,\"location\":0,\"player\":2,\"flags\":0}",
                    i ? "," : "", (long long)ANI_AP_FILLER_ITEM);
        ajb_raw(&b, "]}]");
        feed(b.buf);
        ajb_free(&b);
    }
    CHECK(ani_ui_toasts(t, 8, ani_ui_now_ms()) == 1 && !strcmp(t[0].text, "Received 7 items"));
    /* The first item a fresh slot gets while playing also comes at index 0:
     * that one is PrintJSON's to announce, not a summary. */
    ani_ui_clear();
    S.item_count = 0;
    feed("[{\"cmd\":\"ReceivedItems\",\"index\":0,\"items\":[{\"item\":1095630849,\"location\":0,\"player\":2,\"flags\":1}]}]");
    CHECK(S.item_count == 1 && ani_ui_toasts(t, 8, ani_ui_now_ms()) == 0);
    S.generation = 0;
    puts("names ok");
}

/* ── Text ──────────────────────────────────────────────────── */

/* A buffer with a guard band around it, to catch writes outside the clip. */
#define FW 200
#define FH 50
#define GUARD 4096
static uint32_t fbuf[GUARD + FW * FH + GUARD];

static void font_case(bool truetype)
{
    uint32_t *px = fbuf + GUARD;
    int changed = 0;
    memset(fbuf, 0x11, sizeof fbuf);
    for (int i = 0; i < FW * FH; i++) px[i] = 0xFF000000u;
    int wdt = ani_font_draw(px, FW, FH, 10, 10, 20, 0xFFFFFFFFu, "Edgar");
    CHECK(wdt > 20 && wdt == ani_font_width(20, "Edgar"));
    for (int y = 0; y < FH; y++)
        for (int x = 0; x < FW; x++)
            if (px[y * FW + x] != 0xFF000000u) {
                changed++;
                CHECK(x >= 8 && x < 10 + wdt + 4 && y >= 6 && y < 40);
            }
    CHECK(changed > 40);
    /* Clipped at every edge. */
    ani_font_draw(px, FW, FH, -30, -8, 30, 0xFFFFFFFFu, "Clip me");
    ani_font_draw(px, FW, FH, 190, 40, 30, 0xFFFFFFFFu, "Clip me");
    ani_fill(px, FW, FH, -10, -10, FW + 20, FH + 20, 0x80FF0000u);
    for (int i = 0; i < GUARD; i++) CHECK(fbuf[i] == 0x11111111u && fbuf[GUARD + FW * FH + i] == 0x11111111u);
    /* Names from other games: drawn, never a crash. */
    CHECK(ani_font_width(20, "Zo\xc3\xab \xe6\x97\xa5\xe6\x9c\xac \xf0\x9f\x98\x80") > 0);
    CHECK(ani_font_width(20, "bad \xc3") > 0);
    printf("font ok (%s)\n", truetype ? "TrueType" : "built-in strokes");
}

static void test_font(void)
{
    font_case(ani_font_init());
}

int main(int argc, char **argv)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc >= 2 && !strcmp(argv[1], "json")) test_json();
    else if (argc >= 2 && !strcmp(argv[1], "game")) test_game();
    else if (argc >= 2 && !strcmp(argv[1], "ui")) test_ui();
    else if (argc >= 3 && !strcmp(argv[1], "names")) test_names(argv[2]);
    else if (argc >= 2 && !strcmp(argv[1], "font")) test_font();
    else if (argc >= 5 && !strcmp(argv[1], "live")) test_live(argc, argv);
    else if (argc >= 5 && !strcmp(argv[1], "offline")) test_offline(argc, argv);
    else if (argc >= 5 && !strcmp(argv[1], "resume")) test_resume(argc, argv);
    else { fprintf(stderr, "usage: see the top of test_ap.c\n"); return 2; }
    _exit(0);
}
