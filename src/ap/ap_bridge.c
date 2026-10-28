#include "ap_bridge.h"
#include "ap_catalog.h"
#include "ap_game.h"
#include "ap_json.h"
#include "ap_net.h"

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#if defined(_WIN32)
#include <direct.h>
#include <windows.h>
#define ani_mkdir(p) _mkdir(p)
#else
#include <unistd.h>
#define ani_mkdir(p) mkdir((p), 0755)
#endif

#if defined(_MSC_VER)
#  define ANI_TLS __declspec(thread)
#else
#  define ANI_TLS _Thread_local
#endif
extern ANI_TLS uint32_t g_eax, g_esp;
extern ptrdiff_t g_xbox_mem_offset;
#define G32(va) (*(volatile uint32_t *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))
#define GF(va)  (*(volatile float    *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))

#define SIDECAR_VERSION 2
#define MAX_ITEMS 4096
/* Every location ID is ANI_AP_BASE_ID plus less than this. */
#define LOC_SPAN (16u << 16)

/* ── State ─────────────────────────────────────────────────── */

/* A set of this game's locations, as a bitmap over the ID span. */
typedef struct { uint8_t bits[LOC_SPAN / 8]; int n; } LocSet;

enum { GOAL_EDGARS = 0, GOAL_CREDITS = 1 };

static struct {
    bool enabled;          /* --ap-server/--ap-slot given */
    bool bound;            /* a seed is known: the hooks act */
    bool log;              /* ANI_AP_LOG: capture details for the catalog */
    char server[256], slot[64], password[128];
    char seed[128];
    char dir[1024];        /* <save>/archipelago/<seed>_<slot> */
    char sidecar[1100];
    /* persisted */
    int64_t items[MAX_ITEMS];
    int item_count;
    LocSet checked;        /* observed in this game */
    LocSet acked;          /* the server has them */
    uint16_t shuffled_mask;    /* native grants of these become checks */
    uint16_t forced_mask;      /* ...and these follow the received items */
    int edgars_required;
    int goal;                  /* GOAL_* */
    uint32_t kinds;            /* bit per ANI_AP_KIND_* in this room */
    bool credits_reached;
    bool have_slot_data;
    /* session */
    uint64_t generation;   /* of the connection that sent Connected; 0 if none */
    bool goal_sent;
    bool dirty;
    bool refused;
    int our_slot;
    char players[64][40];  /* slot -> name, from Connected */
    uint16_t ap_bits;      /* abilities received */
    int edgars;            /* Edgars received */
} S;

#define LOG(...) do { printf("[AP] " __VA_ARGS__); putchar('\n'); fflush(stdout); } while (0)
#define DBG(...) do { if (S.log) LOG(__VA_ARGS__); } while (0)

static bool loc_ok(int64_t v) { return v >= ANI_AP_BASE_ID && v < ANI_AP_BASE_ID + LOC_SPAN; }

static bool set_has(const LocSet *s, int64_t v)
{
    uint32_t o = (uint32_t)(v - ANI_AP_BASE_ID);
    return loc_ok(v) && (s->bits[o >> 3] >> (o & 7) & 1);
}

static bool set_add(LocSet *s, int64_t v)
{
    uint32_t o = (uint32_t)(v - ANI_AP_BASE_ID);
    if (!loc_ok(v) || set_has(s, v)) return false;
    s->bits[o >> 3] |= (uint8_t)(1u << (o & 7));
    s->n++;
    return true;
}

static void set_clear(LocSet *s) { memset(s, 0, sizeof *s); }

/* Runs body with v bound to each member, in ID order. */
#define SET_EACH(s, v, body) \
    for (uint32_t o_ = 0; o_ < LOC_SPAN; o_ += 8) { \
        uint8_t b_ = (s)->bits[o_ >> 3]; \
        for (int k_ = 0; b_ && k_ < 8; k_++, b_ >>= 1) \
            if (b_ & 1) { int64_t v = ANI_AP_BASE_ID + o_ + k_; body } }

/* Checks of the kinds this room has; the rest are kept but never sent. */
static bool in_room(int64_t v)
{
    int kind = ANI_AP_KIND_OF(v);
    return kind >= 0 && kind < 32 && (S.kinds >> kind & 1);
}

static const AniApAbility *ability_by_item(int64_t item)
{
    for (int i = 0; i < ANI_AP_ABILITIES; i++)
        if (ani_ap_abilities[i].item == item) return &ani_ap_abilities[i];
    return NULL;
}

static const char *item_name(int64_t item)
{
    const AniApAbility *a = ability_by_item(item);
    if (a) return a->name;
    if (item == ANI_AP_EDGAR_ITEM) return "Edgar";
    if (item == ANI_AP_FILLER_ITEM) return "Applause";
    return "an item";
}

static const char *location_name(int64_t loc)
{
    int lo = 0, hi = ANI_AP_NAMES - 1;
    while (lo <= hi) {
        int mid = (lo + hi) / 2;
        if (ani_ap_location_names[mid].id == loc) return ani_ap_location_names[mid].name;
        if (ani_ap_location_names[mid].id < loc) lo = mid + 1;
        else hi = mid - 1;
    }
    return NULL;
}

static void recount(void)
{
    S.ap_bits = 0;
    S.edgars = 0;
    for (int i = 0; i < S.item_count; i++) {
        const AniApAbility *a = ability_by_item(S.items[i]);
        if (a) S.ap_bits |= a->bit;
        else if (S.items[i] == ANI_AP_EDGAR_ITEM) S.edgars++;
    }
}

/* ── Sidecar ───────────────────────────────────────────────── */

static void write_set(AjBuf *b, const char *key, const LocSet *s)
{
    int n = 0;
    ajb_fmt(b, ",\"%s\":[", key);
    SET_EACH(s, v, ajb_fmt(b, "%s%lld", n++ ? "," : "", (long long)v);)
    ajb_raw(b, "]");
}

static bool replace_file(const char *tmp, const char *path)
{
#if defined(_WIN32)
    return MoveFileExA(tmp, path, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) != 0;
#else
    return rename(tmp, path) == 0;
#endif
}

static bool write_text(const char *path, const char *text, size_t len)
{
    char tmp[1200];
    FILE *f;
    bool ok;
    snprintf(tmp, sizeof tmp, "%s.tmp", path);
    if (!(f = fopen(tmp, "wb"))) return false;
    ok = fwrite(text, 1, len, f) == len;
    ok = fflush(f) == 0 && ok;
    ok = fclose(f) == 0 && ok;
    return ok && replace_file(tmp, path);
}

static char *read_text(const char *path)
{
    FILE *f = fopen(path, "rb");
    long n;
    char *t;
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    n = ftell(f);
    fseek(f, 0, SEEK_SET);
    t = n >= 0 ? malloc((size_t)n + 1) : NULL;
    if (t && fread(t, 1, (size_t)n, f) != (size_t)n) { free(t); t = NULL; }
    if (t) t[n] = 0;
    fclose(f);
    return t;
}

static void save_sidecar(void)
{
    AjBuf b = {0};
    ajb_fmt(&b, "{\"version\":%d,\"catalog_version\":%d,\"seed\":", SIDECAR_VERSION,
            ANI_AP_CATALOG_VERSION);
    ajb_str(&b, S.seed);
    ajb_raw(&b, ",\"slot\":");
    ajb_str(&b, S.slot);
    ajb_fmt(&b, ",\"have_slot_data\":%s,\"shuffled_mask\":%u,\"forced_mask\":%u,"
            "\"edgars_required\":%d,\"goal\":%d,\"kinds\":%u,\"credits_reached\":%s",
            S.have_slot_data ? "true" : "false", S.shuffled_mask, S.forced_mask,
            S.edgars_required, S.goal, S.kinds, S.credits_reached ? "true" : "false");
    ajb_raw(&b, ",\"items\":[");
    for (int i = 0; i < S.item_count; i++)
        ajb_fmt(&b, "%s%lld", i ? "," : "", (long long)S.items[i]);
    ajb_raw(&b, "]");
    write_set(&b, "checked", &S.checked);
    write_set(&b, "acked", &S.acked);
    ajb_raw(&b, "}\n");
    if (b.oom || !write_text(S.sidecar, b.buf, b.len)) {
        if (!S.dirty) LOG("could not write %s; retrying every frame", S.sidecar);
        S.dirty = true;
    } else {
        S.dirty = false;
    }
    ajb_free(&b);
}

static void read_set(const AjValue *arr, LocSet *s)
{
    set_clear(s);
    for (const AjValue *c = arr ? arr->child : NULL; c; c = c->next)
        set_add(s, aj_int(c, 0));
}

static bool load_sidecar(void)
{
    char *t = read_text(S.sidecar);
    AjValue *v = t ? aj_parse(t) : NULL;
    bool ok = v && aj_int(aj_get(v, "version"), 0) == SIDECAR_VERSION &&
              !strcmp(aj_str(aj_get(v, "seed"), ""), S.seed) &&
              !strcmp(aj_str(aj_get(v, "slot"), ""), S.slot);
    if (ok) {
        const AjValue *items = aj_get(v, "items");
        S.item_count = 0;
        for (const AjValue *c = items ? items->child : NULL; c && S.item_count < MAX_ITEMS; c = c->next)
            S.items[S.item_count++] = aj_int(c, 0);
        read_set(aj_get(v, "checked"), &S.checked);
        read_set(aj_get(v, "acked"), &S.acked);
        S.have_slot_data = aj_bool(aj_get(v, "have_slot_data"), false);
        S.shuffled_mask = (uint16_t)aj_int(aj_get(v, "shuffled_mask"), 0);
        S.forced_mask = (uint16_t)aj_int(aj_get(v, "forced_mask"), 0);
        S.edgars_required = (int)aj_int(aj_get(v, "edgars_required"), 0);
        S.goal = (int)aj_int(aj_get(v, "goal"), GOAL_EDGARS);
        S.kinds = (uint32_t)aj_int(aj_get(v, "kinds"), 0);
        S.credits_reached = aj_bool(aj_get(v, "credits_reached"), false);
        recount();
    } else if (t) {
        LOG("%s is unreadable or for another seed; starting it afresh", S.sidecar);
    }
    aj_free(v);
    free(t);
    return ok;
}

/* ── Protocol ──────────────────────────────────────────────── */

static void send_cmd(const char *json)
{
    if (S.generation) ani_net_send(S.generation, json);
}

static void send_pending(void)
{
    AjBuf b = {0};
    int n = 0;
    ajb_raw(&b, "[{\"cmd\":\"LocationChecks\",\"locations\":[");
    SET_EACH(&S.checked, v,
        if (in_room(v) && !set_has(&S.acked, v))
            ajb_fmt(&b, "%s%lld", n++ ? "," : "", (long long)v);)
    ajb_raw(&b, "]}]");
    if (n && !b.oom) send_cmd(b.buf);
    ajb_free(&b);
}

static void check_goal(void)
{
    if (S.goal_sent || !S.generation || !S.have_slot_data || S.edgars < S.edgars_required)
        return;
    if (S.goal == GOAL_CREDITS && !S.credits_reached)
        return;
    send_cmd("[{\"cmd\":\"StatusUpdate\",\"status\":30}]");
    S.goal_sent = true;
    if (S.goal == GOAL_CREDITS)
        LOG("goal: the credits, with %d Edgars received", S.edgars);
    else
        LOG("goal: %d Edgars received", S.edgars);
}

static void observe(int64_t location)
{
    const char *name;
    if (!set_add(&S.checked, location)) return;
    name = location_name(location);
    if (S.have_slot_data && !in_room(location))
        DBG("found %s (not a check in this room)", name ? name : "?");
    else
        LOG("check: %s", name ? name : "?");
    save_sidecar();
    send_pending();
}

static void on_received_items(const AjValue *p)
{
    int64_t index = aj_int(aj_get(p, "index"), -1);
    const AjValue *items = aj_get(p, "items");
    int before = S.item_count, old_edgars = S.edgars;
    uint16_t old_bits = S.ap_bits;

    if (index != 0 && index != S.item_count) {
        LOG("item index %lld, expected %d: resyncing", (long long)index, S.item_count);
        send_cmd("[{\"cmd\":\"Sync\"}]");
        send_pending();
        return;
    }
    if (index == 0) S.item_count = 0;
    for (const AjValue *it = items ? items->child : NULL; it; it = it->next) {
        if (S.item_count >= MAX_ITEMS) break;
        S.items[S.item_count++] = aj_int(aj_get(it, "item"), 0);
    }
    recount();
    if (S.item_count != before || S.edgars != old_edgars || S.ap_bits != old_bits)
        save_sidecar();
    if (index != 0)
        for (int i = before; i < S.item_count; i++)
            LOG("received %s", item_name(S.items[i]));
    else
        LOG("inventory: %d Edgars, abilities 0x%03X (%d items)", S.edgars, S.ap_bits, S.item_count);
    check_goal();
}

static uint16_t bits_of(const AjValue *arr)
{
    uint16_t bits = 0;
    for (const AjValue *c = arr ? arr->child : NULL; c; c = c->next)
        bits |= (uint16_t)aj_int(c, 0);
    return bits;
}

static void on_connected(const AjValue *p, uint64_t generation)
{
    const AjValue *sd = aj_get(p, "slot_data");
    const AjValue *checked = aj_get(p, "checked_locations");
    int cat = (int)aj_int(aj_get(sd, "catalog_version"), -1);

    if (cat != ANI_AP_CATALOG_VERSION) {
        LOG("the room was generated with catalog %d but this game has %d: "
            "update the game or the apworld", cat, ANI_AP_CATALOG_VERSION);
        S.refused = true;
        ani_net_stop();
        return;
    }
    S.generation = generation;
    S.goal_sent = false;
    S.our_slot = (int)aj_int(aj_get(p, "slot"), 0);
    for (const AjValue *c = aj_get(p, "players") ? aj_get(p, "players")->child : NULL; c; c = c->next) {
        int64_t slot = aj_int(aj_get(c, "slot"), 0);
        if (slot > 0 && slot < 64)
            snprintf(S.players[slot], sizeof S.players[slot], "%s",
                     aj_str(aj_get(c, "alias"), aj_str(aj_get(c, "name"), "")));
    }
    S.edgars_required = (int)aj_int(aj_get(sd, "edgars_required"), 30);
    S.goal = (int)aj_int(aj_get(sd, "goal"), GOAL_EDGARS);
    S.kinds = 0;
    for (const AjValue *c = aj_get(sd, "location_kinds") ? aj_get(sd, "location_kinds")->child : NULL;
         c; c = c->next) {
        int64_t k = aj_int(c, -1);
        if (k >= 0 && k < 32) S.kinds |= 1u << k;
    }
    S.shuffled_mask = bits_of(aj_get(sd, "shuffled_abilities"));
    S.forced_mask = (uint16_t)(S.shuffled_mask | bits_of(aj_get(sd, "start_abilities")));
    S.have_slot_data = true;
    /* The server's list is authoritative: a room restored from an older
     * save may have forgotten checks, which then count as pending again. */
    read_set(checked, &S.acked);
    save_sidecar();
    LOG("connected as %s (slot %lld); goal %s with %d Edgars, shuffled abilities 0x%03X",
        S.slot, (long long)aj_int(aj_get(p, "slot"), 0),
        S.goal == GOAL_CREDITS ? "the credits" : "receiving", S.edgars_required, S.shuffled_mask);
    send_pending();
    check_goal();
}

static void on_room_update(const AjValue *p)
{
    const AjValue *checked = aj_get(p, "checked_locations");
    bool changed = false;
    for (const AjValue *c = checked ? checked->child : NULL; c; c = c->next)
        changed |= set_add(&S.acked, aj_int(c, 0));
    if (changed) save_sidecar();
}

/* PrintJSON parts carry IDs; names come from Connected (players) and the
 * catalog (this game's items and locations). Other games' names would need
 * their data packages, which this client does not fetch. */
static void on_print(const AjValue *p)
{
    const AjValue *data = aj_get(p, "data");
    AjBuf b = {0};
    for (const AjValue *c = data ? data->child : NULL; c; c = c->next) {
        const char *type = aj_str(aj_get(c, "type"), "text");
        const char *text = aj_str(aj_get(c, "text"), "");
        int64_t id = text[0] ? strtoll(text, NULL, 10) : 0;
        bool ours = aj_int(aj_get(c, "player"), -1) == S.our_slot;
        const char *name = NULL;
        if (!strcmp(type, "player_id") && id > 0 && id < 64 && S.players[id][0])
            name = S.players[id];
        else if (!strcmp(type, "item_id") && ours)
            name = item_name(id);
        else if (!strcmp(type, "location_id") && ours)
            name = location_name(id);
        else if (!strcmp(type, "item_id"))
            name = "an item";
        else if (!strcmp(type, "location_id"))
            name = "somewhere";
        ajb_raw(&b, name ? name : text);
    }
    if (b.buf && b.len) LOG("%s", b.buf);
    ajb_free(&b);
}

static void handle_packet(const AjValue *p, uint64_t generation)
{
    const char *cmd = aj_str(aj_get(p, "cmd"), "");
    if (!strcmp(cmd, "RoomInfo")) {
        const char *seed = aj_str(aj_get(p, "seed_name"), "");
        if (strcmp(seed, S.seed)) {
            LOG("this server is hosting seed %s, but this game is bound to seed %s; "
                "restart the game to switch seeds", seed, S.seed);
            S.refused = true;
            ani_net_stop();
        }
    } else if (!strcmp(cmd, "Connected")) {
        on_connected(p, generation);
    } else if (!strcmp(cmd, "ConnectionRefused")) {
        AjBuf b = {0};
        const AjValue *errs = aj_get(p, "errors");
        for (const AjValue *c = errs ? errs->child : NULL; c; c = c->next) {
            ajb_raw(&b, b.len ? ", " : "");
            ajb_raw(&b, aj_str(c, "?"));
        }
        LOG("connection refused: %s", b.buf ? b.buf : "no reason given");
        ajb_free(&b);
        S.refused = true;
        ani_net_stop();
    } else if (!strcmp(cmd, "ReceivedItems")) {
        if (generation == S.generation) on_received_items(p);
    } else if (!strcmp(cmd, "RoomUpdate")) {
        if (generation == S.generation) on_room_update(p);
    } else if (!strcmp(cmd, "PrintJSON")) {
        on_print(p);
    }
}

static void pump_network(void)
{
    AniNetEvent ev[32];
    size_t n;
    while ((n = ani_net_drain(ev, 32)) > 0) {
        for (size_t i = 0; i < n; i++) {
            if (ev[i].kind == ANI_NET_PACKET) {
                AjValue *root = aj_parse(ev[i].text);
                if (!root || root->type != AJ_ARR)
                    LOG("unreadable packet from the server");
                for (const AjValue *p = root ? root->child : NULL; p; p = p->next)
                    handle_packet(p, ev[i].generation);
                aj_free(root);
            } else if (ev[i].kind == ANI_NET_DOWN) {
                if (ev[i].generation && ev[i].generation == S.generation) {
                    LOG("disconnected (%s); playing offline, checks will be sent on reconnect",
                        ev[i].text ? ev[i].text : "");
                    S.generation = 0;
                } else if (!S.generation) {
                    DBG("cannot reach the server: %s", ev[i].text ? ev[i].text : "");
                }
            }
            free(ev[i].text);
        }
    }
}

/* ── Init ──────────────────────────────────────────────────── */

static void take_arg(int *argc, char **argv, int i, int n)
{
    for (int j = i; j + n < *argc; j++) argv[j] = argv[j + n];
    *argc -= n;
    argv[*argc] = NULL;
}

static void sanitize(char *s)
{
    for (; *s; s++)
        if (!((*s >= 'a' && *s <= 'z') || (*s >= 'A' && *s <= 'Z') ||
              (*s >= '0' && *s <= '9') || *s == '-' || *s == '_'))
            *s = '_';
}

static void make_uuid(const char *base, char *out, size_t n)
{
    char path[1100];
    char *t;
    snprintf(path, sizeof path, "%s/uuid", base);
    t = read_text(path);
    if (t && strlen(t) >= 16) {
        snprintf(out, n, "%.32s", t);
        out[strcspn(out, "\r\n")] = 0;
    } else {
        unsigned seed = (unsigned)time(NULL) ^ (unsigned)(uintptr_t)out;
        srand(seed);
        for (int i = 0; i < 32 && (size_t)i + 1 < n; i++)
            out[i] = "0123456789abcdef"[rand() & 15];
        out[n < 33 ? n - 1 : 32] = 0;
        write_text(path, out, strlen(out));
    }
    free(t);
}

static void env_default(char *dst, size_t n, const char *name)
{
    const char *v = getenv(name);
    if (!dst[0] && v && *v) snprintf(dst, n, "%s", v);
}

const char *ani_ap_init(int *argc, char **argv, const char *save_dir)
{
    char base[1024], last[1100], uuid[40], slotfile[80];
    AjBuf connect = {0};
    char *t;

    for (int i = 1; i < *argc;) {
        char *dst = NULL;
        size_t n = 0;
        if (!strcmp(argv[i], "--ap-server")) { dst = S.server; n = sizeof S.server; }
        else if (!strcmp(argv[i], "--ap-slot")) { dst = S.slot; n = sizeof S.slot; }
        else if (!strcmp(argv[i], "--ap-password")) { dst = S.password; n = sizeof S.password; }
        if (dst && i + 1 < *argc) {
            snprintf(dst, n, "%s", argv[i + 1]);
            take_arg(argc, argv, i, 2);
        } else {
            i++;
        }
    }
    env_default(S.server, sizeof S.server, "ANI_AP_SERVER");
    env_default(S.slot, sizeof S.slot, "ANI_AP_SLOT");
    env_default(S.password, sizeof S.password, "ANI_AP_PASSWORD");
    S.log = getenv("ANI_AP_LOG") && *getenv("ANI_AP_LOG") && *getenv("ANI_AP_LOG") != '0';
    if (!S.server[0] || !S.slot[0]) return NULL;
    S.enabled = true;

    snprintf(base, sizeof base, "%s/archipelago", save_dir);
    ani_mkdir(save_dir);
    ani_mkdir(base);
    snprintf(slotfile, sizeof slotfile, "%s", S.slot);
    sanitize(slotfile);
    snprintf(last, sizeof last, "%s/last_seed_%s.txt", base, slotfile);
    make_uuid(base, uuid, sizeof uuid);

    ajb_raw(&connect, "{\"cmd\":\"Connect\",\"game\":");
    ajb_str(&connect, ANI_AP_GAME);
    ajb_raw(&connect, ",\"name\":");
    ajb_str(&connect, S.slot);
    ajb_raw(&connect, ",\"password\":");
    ajb_str(&connect, S.password);
    ajb_raw(&connect, ",\"uuid\":");
    ajb_str(&connect, uuid);
    ajb_raw(&connect, ",\"version\":{\"major\":0,\"minor\":6,\"build\":0,\"class\":\"Version\"},"
                      "\"items_handling\":7,\"tags\":[],\"slot_data\":true}");
    LOG("connecting to %s as %s", S.server, S.slot);
    ani_net_start(S.server, connect.buf);
    ajb_free(&connect);

    /* The seed picks the save directory, so wait for the room before boot. */
    if (!ani_net_wait_seed(8000, S.seed, sizeof S.seed)) {
        t = read_text(last);
        if (t) {
            snprintf(S.seed, sizeof S.seed, "%s", t);
            S.seed[strcspn(S.seed, "\r\n")] = 0;
            free(t);
        }
        if (!S.seed[0]) {
            LOG("cannot reach %s and no earlier seed for %s: playing without Archipelago",
                S.server, S.slot);
            ani_net_stop();
            S.enabled = false;
            return NULL;
        }
        LOG("cannot reach %s: playing seed %s offline", S.server, S.seed);
    }
    write_text(last, S.seed, strlen(S.seed));
    {
        char seedname[128];
        snprintf(seedname, sizeof seedname, "%s", S.seed);
        sanitize(seedname);
        snprintf(S.dir, sizeof S.dir, "%s/%s_%s", base, seedname, slotfile);
    }
    ani_mkdir(S.dir);
    snprintf(S.sidecar, sizeof S.sidecar, "%s/ap_state.json", S.dir);
    if (!load_sidecar()) save_sidecar();
    S.bound = true;
    LOG("seed %s: saves in %s", S.seed, S.dir);
    return S.dir;
}

bool ani_ap_active(void) { return S.bound; }

/* ── Hooks ─────────────────────────────────────────────────── */

/* A generated body ends with the guest's `ret`, which pops the return address
 * the caller pushed. A hook that answers in place of the body must pop it
 * itself, or the caller resumes with esp 4 bytes low. */

/* The check a pickup object is: its level and objectname, as the catalog
 * lists them (or a prefix, for the per-room copies of an Edgar). */
static int64_t pickup_location(int level, const char *name)
{
    for (int i = 0; i < ANI_AP_OBJECTS; i++)
        if (ani_ap_objects[i].level == level && !ani_stricmp(ani_ap_objects[i].object, name))
            return ani_ap_objects[i].location;
    for (int i = 0; i < ANI_AP_PREFIXES; i++) {
        const char *p = ani_ap_prefixes[i].prefix;
        if (ani_ap_prefixes[i].level == level && !ani_strnicmp(p, name, strlen(p)))
            return ani_ap_prefixes[i].location;
    }
    return 0;
}

/* Collectible milestones: the level's MajorPickupsCollected against each
 * step (25, 50, ... 300). */
static void check_milestones(void)
{
    int level = ani_game_level();
    float v;
    if (level < 0 || level >= ANI_AP_LEVELS || !ani_game_script_var("MajorPickupsCollected", &v))
        return;
    for (int k = 0; k < ani_ap_levels[level].milestones; k++)
        if (v + 0.5f >= (float)((k + 1) * ani_ap_levels[level].milestone_step))
            observe(ani_ap_levels[level].milestone[k]);
}

void ani_ap_main_loop(void)
{
    if (!S.bound) return;
    pump_network();
    /* Abilities the session owns follow what was received, whatever a save
     * or the game's own grants put there. */
    if (S.forced_mask) {
        uint16_t w = ani_game_abilities();
        uint16_t want = (uint16_t)((w & ~S.forced_mask) | (S.ap_bits & S.forced_mask));
        if (w != want) ani_game_set_abilities(want);
    }
    if (S.dirty) save_sidecar();
}

void ani_ap_hook_frame(ani_gen_fn gen)
{
    static unsigned frames;
    bool script_edgar;
    if (!S.bound) { gen(); return; }
    script_edgar = ani_game_edgar_pending();
    gen();
    /* A script can hand an Edgar over without a pickup object (0x0009A9EE);
     * none of the levels' scripts are known to, so it is only logged. */
    if (script_edgar)
        LOG("an Edgar was handed out by a script in level %d; please report this",
            ani_game_level());
    /* Collectibles from before the session (or a save) count too. */
    if (++frames % 60 == 0) check_milestones();
}

void ani_ap_hook_pickup(ani_gen_fn gen)
{
    uint32_t obj, before, after;
    if (!S.bound) { gen(); return; }
    obj = G32(g_esp + 4);           /* cdecl: the pickup object */
    before = ani_game_pickup_state(obj);
    gen();
    after = ani_game_pickup_state(obj);
    /* Collected: the pickup reaches state 3 (a counted pickup, after its
     * counter goes up) or 4 (gone; 0x00027C80), which is also what a save
     * keeps (0x0009F370). 0xFFFF is a pickup not yet set up. */
    if (after != before && (after == 3 || after == 4) && before != 0xFFFFu) {
        int level = ani_game_level();
        char name[64];
        int64_t loc;
        if (level < 0 || !ani_game_object_name(obj, name, sizeof name)) return;
        loc = pickup_location(level, name);
        DBG("pickup %s (type %u) in level %d: %s", name, ani_game_pickup_type(obj), level,
            loc ? location_name(loc) : "not a check");
        if (loc) observe(loc);
        if (ani_game_pickup_type(obj) == 1) check_milestones();
    }
}

void ani_ap_hook_give_ability(ani_gen_fn gen)
{
    uint32_t arg = g_esp + 4;
    uint16_t bits = (uint16_t)G32(arg), taken;

    DBG("GiveAbility 0x%03X in level %d", bits, ani_game_level());
    if (!S.bound || !(taken = bits & S.shuffled_mask)) { gen(); return; }
    for (int i = 0; i < ANI_AP_ABILITIES; i++)
        if (taken & ani_ap_abilities[i].bit)
            observe(ani_ap_abilities[i].location);
    /* Abilities that stay vanilla still go through the game's own code. */
    if (bits & ~taken) {
        uint32_t saved = G32(arg);
        G32(arg) = (saved & 0xFFFF0000u) | (uint16_t)(bits & ~taken);
        gen();
        G32(arg) = saved;
    } else {
        g_esp += 4;   /* the generated body's ret: pop the return address */
    }
    g_eax = (g_eax & 0xFFFF0000u) | bits;
}

void ani_ap_hook_get_all_edgars(ani_gen_fn gen)
{
    uint32_t args, out;
    if (!S.bound) { gen(); return; }
    /* Script binding: arg 2 is the call's argument block, whose +4 holds the
     * address of the result (0x000FD45C, the all-Edgars cheat path). */
    args = G32(g_esp + 8);
    out = G32(args + 4);
    GF(out) = (float)S.edgars;
    g_eax = (g_eax & 0xFFFFFF00u) | 1;
    g_esp += 4;       /* the generated body's ret: pop the return address */
}

/* SetReadyForCredits (0x000FC730), the script verb the ending calls. */
void ani_ap_hook_credits(ani_gen_fn gen)
{
    if (S.bound && !S.credits_reached) {
        S.credits_reached = true;
        LOG("reached the credits");
        save_sidecar();
        check_goal();
    }
    gen();
}
