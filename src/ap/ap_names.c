#include "ap_names.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#if defined(_WIN32)
#include <windows.h>
#else
#include <dirent.h>
#endif

typedef struct { int64_t id; char *name; } Entry;
typedef struct { Entry *e; int n; } Table;

typedef struct {
    char *game, *checksum;
    Table items, locations;
} Package;

#define MAX_GAMES 64
static Package P[MAX_GAMES];
static int P_n;

static void table_free(Table *t)
{
    for (int i = 0; i < t->n; i++) free(t->e[i].name);
    free(t->e);
    t->e = NULL;
    t->n = 0;
}

static int by_id(const void *a, const void *b)
{
    int64_t x = ((const Entry *)a)->id, y = ((const Entry *)b)->id;
    return x < y ? -1 : x > y;
}

/* name -> id object into a table sorted by id. */
static bool table_read(Table *t, const AjValue *obj)
{
    if (!obj || obj->type != AJ_OBJ) return false;
    t->e = calloc(obj->len ? obj->len : 1, sizeof *t->e);
    if (!t->e) return false;
    for (const AjValue *c = obj->child; c; c = c->next) {
        if (!c->key || c->type != AJ_NUM) continue;
        t->e[t->n].id = aj_int(c, 0);
        t->e[t->n].name = strdup(c->key);
        if (t->e[t->n].name) t->n++;
    }
    qsort(t->e, (size_t)t->n, sizeof *t->e, by_id);
    return true;
}

static const char *table_find(const Table *t, int64_t id)
{
    int lo = 0, hi = t->n - 1;
    while (lo <= hi) {
        int mid = (lo + hi) / 2;
        if (t->e[mid].id == id) return t->e[mid].name;
        if (t->e[mid].id < id) lo = mid + 1;
        else hi = mid - 1;
    }
    return NULL;
}

static Package *find(const char *game)
{
    for (int i = 0; i < P_n; i++)
        if (!strcmp(P[i].game, game)) return &P[i];
    return NULL;
}

static void package_free(Package *p)
{
    free(p->game);
    free(p->checksum);
    table_free(&p->items);
    table_free(&p->locations);
    memset(p, 0, sizeof *p);
}

void ani_names_reset(void)
{
    for (int i = 0; i < P_n; i++) package_free(&P[i]);
    P_n = 0;
}

bool ani_names_have(const char *game, const char *checksum)
{
    Package *p = find(game);
    return p && checksum && !strcmp(p->checksum, checksum);
}

/* A file name for a game: letters and digits kept, the rest '_'. */
static void file_for(char *out, size_t n, const char *dir, const char *game, const char *checksum)
{
    char safe[96];
    size_t i = 0;
    for (const char *s = game; *s && i + 1 < sizeof safe; s++)
        safe[i++] = ((*s >= 'a' && *s <= 'z') || (*s >= 'A' && *s <= 'Z') ||
                     (*s >= '0' && *s <= '9')) ? *s : '_';
    safe[i] = 0;
    snprintf(out, n, "%s/%s_%.64s.json", dir, safe, checksum);
}

static void write_cache(const char *dir, const char *game, const AjValue *pkg, const char *checksum)
{
    char path[1200], tmp[1210];
    AjBuf b = {0};
    ajb_raw(&b, "{\"game\":");
    ajb_str(&b, game);
    ajb_raw(&b, ",\"checksum\":");
    ajb_str(&b, checksum);
    static const char *keys[] = { "item_name_to_id", "location_name_to_id" };
    for (int k = 0; k < 2; k++) {
        int n = 0;
        ajb_fmt(&b, ",\"%s\":{", keys[k]);
        for (const AjValue *c = aj_get(pkg, keys[k])->child; c; c = c->next) {
            if (!c->key || c->type != AJ_NUM) continue;
            if (n++) ajb_raw(&b, ",");
            ajb_str(&b, c->key);
            ajb_fmt(&b, ":%lld", (long long)aj_int(c, 0));
        }
        ajb_raw(&b, "}");
    }
    ajb_raw(&b, "}\n");
    file_for(path, sizeof path, dir, game, checksum);
    snprintf(tmp, sizeof tmp, "%s.tmp", path);
    FILE *f = b.oom ? NULL : fopen(tmp, "wb");
    if (f) {
        bool ok = fwrite(b.buf, 1, b.len, f) == b.len;
        ok = fclose(f) == 0 && ok;
#if defined(_WIN32)
        if (ok) MoveFileExA(tmp, path, MOVEFILE_REPLACE_EXISTING);
#else
        if (ok) rename(tmp, path);
#endif
        if (!ok) remove(tmp);
    }
    ajb_free(&b);
}

bool ani_names_add(const char *game, const AjValue *pkg, const char *dir)
{
    const char *checksum = aj_str(aj_get(pkg, "checksum"), "");
    Package np = {0};
    if (!game || !*game || !table_read(&np.items, aj_get(pkg, "item_name_to_id")) ||
        !table_read(&np.locations, aj_get(pkg, "location_name_to_id"))) {
        package_free(&np);
        return false;
    }
    np.game = strdup(game);
    np.checksum = strdup(checksum);
    Package *old = find(game);
    if (old) {
        package_free(old);
        *old = np;
    } else if (P_n < MAX_GAMES) {
        P[P_n++] = np;
    } else {
        package_free(&np);
        return false;
    }
    if (dir && *checksum) write_cache(dir, game, pkg, checksum);
    return true;
}

static void load_file(const char *path)
{
    FILE *f = fopen(path, "rb");
    if (!f) return;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *t = n > 0 ? malloc((size_t)n + 1) : NULL;
    if (t && fread(t, 1, (size_t)n, f) == (size_t)n) {
        t[n] = 0;
        AjValue *v = aj_parse(t);
        const char *game = aj_str(aj_get(v, "game"), "");
        if (v && *game && !find(game)) ani_names_add(game, v, NULL);
        aj_free(v);
    }
    free(t);
    fclose(f);
}

void ani_names_load(const char *dir)
{
    char path[1200];
#if defined(_WIN32)
    WIN32_FIND_DATAA fd;
    snprintf(path, sizeof path, "%s/*.json", dir);
    HANDLE h = FindFirstFileA(path, &fd);
    if (h == INVALID_HANDLE_VALUE) return;
    do {
        snprintf(path, sizeof path, "%s/%s", dir, fd.cFileName);
        load_file(path);
    } while (FindNextFileA(h, &fd));
    FindClose(h);
#else
    DIR *d = opendir(dir);
    struct dirent *e;
    if (!d) return;
    while ((e = readdir(d))) {
        size_t n = strlen(e->d_name);
        if (n < 6 || strcmp(e->d_name + n - 5, ".json")) continue;
        snprintf(path, sizeof path, "%s/%s", dir, e->d_name);
        load_file(path);
    }
    closedir(d);
#endif
}

const char *ani_names_item(const char *game, int64_t id)
{
    Package *p = game ? find(game) : NULL;
    return p ? table_find(&p->items, id) : NULL;
}

const char *ani_names_location(const char *game, int64_t id)
{
    Package *p = game ? find(game) : NULL;
    return p ? table_find(&p->locations, id) : NULL;
}
