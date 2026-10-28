# Archipelago 2.1 QOL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Item popups, a check tracker screen and an Edgar/goal counter drawn in game during Archipelago sessions.

**Architecture:** A platform-free UI model (`ap_ui.c`) is fed by the bridge on the game thread and read by the renderer thread under a mutex. A drawing module (`ap_hud.c`, game build only) turns it into pixels: popups and the counter through a new presenter hook (`nv2a_hud_rects`, patch 0007) that copies opaque panels onto each presented frame, and the tracker through the presenter's existing held-game overlay. Text comes from `ap_font.c`: a system TrueType font through stb_truetype, `stb_easy_font` if none is found.

**Tech Stack:** C11, SDL2, Vulkan presenter in `tools/ngbrecomp/xboxrecomp/src/nv2a_vk/host/present_sdl.c`, stb_truetype / stb_easy_font (already in `third_party/stb`), the existing `tests/ap` harness.

**Spec:** `docs/superpowers/specs/2026-10-28-archipelago-2-1-qol-design.md`

## Global Constraints

- With no AP session (`ani_ap_active()` false) nothing draws and no hook does work.
- Popups: top-right stack, newest on top, 4 s each, at most 4 visible.
- Connect backlog is one popup: `Received N items` (N = items beyond the sidecar's count), never N popups.
- Keys: Tab or F1 toggle the tracker; holding controller Back 0.5 s opens it. F9/F10/F11 stay the renderer's.
- settings.ini `[archipelago]`: `notifications`, `tracker`, `hud` (`on`/`off`, default `on`); the launcher's Archipelago tab gets the same three toggles.
- Screenshots for verification: game-rendered frames only (`NV2A_CAPTURE`/`RECOMP_FB_DUMP`), never screen grabs.
- Renderer changes go in `patches/ngbrecomp-0007-hud-layer.patch`, touching only `present_sdl.c` and `nv2a_window.h`.

## Review Focus

- Window resized or fullscreen toggled while popups show: panels must clip to the swapchain, never write out of bounds. (Task 4 test: draw at 320x240 with a panel wider than the window.)
- Names with non-ASCII characters (player aliases, other games' items): drawn as `?`, never crash. (Task 3 test.)
- Server never answers GetDataPackage, or the cache is corrupt: popups fall back to `an item`/`somewhere`. (Task 2 test.)
- Burst of 50 ItemSend in one packet (release/collect): queue keeps the newest 4 plus a `+46 more` line, no unbounded growth. (Task 1 test.)
- Tracker opened before slot data arrives (offline start): shows every kind, counts from the sidecar. (Task 1 test.)

---

### Task 1: UI model (`ap_ui.c`)

**Files:**
- Create: `src/ap/ap_ui.h`, `src/ap/ap_ui.c`
- Test: `tests/ap/test_ap.c` (new `ui` case), `tests/ap/CMakeLists.txt` (add `ap_ui.c`, `add_test(NAME ap_ui COMMAND test_ap ui)`)
- Modify: `vk/CMakeLists.txt` (add `ap_ui.c`)

**Interfaces (Produces):**
```c
typedef enum { ANI_UI_RECEIVED, ANI_UI_SENT, ANI_UI_INFO } AniUiKind;
typedef enum { ANI_UI_OFFLINE, ANI_UI_CONNECTING, ANI_UI_CONNECTED } AniUiConn;
typedef struct { AniUiKind kind; bool progression; char text[160]; float fade; } AniUiToast;
typedef struct { int found, total; } AniUiCount;
typedef struct {
    AniUiCount cell[ANI_AP_LEVELS][ANI_AP_KIND_ABILITY + 1];  /* [level][kind] */
    uint32_t kinds;            /* kinds shown */
    int edgars, required, goal; AniUiConn conn;
} AniUiStatus;
void ani_ui_notify(AniUiKind kind, bool progression, const char *text, uint64_t now_ms);
int  ani_ui_toasts(AniUiToast *out, int max, uint64_t now_ms);  /* newest first; fade 1..0 over last 0.5 s */
void ani_ui_set_status(const AniUiStatus *st);
void ani_ui_get_status(AniUiStatus *st);
/* Missing check names in a level, for the tracker's detail page. */
typedef bool (*AniUiFoundFn)(int64_t loc, void *ctx);
int  ani_ui_missing(int level, uint32_t kinds, AniUiFoundFn found, void *ctx,
                    const char **names, int max);
```
A queue of 16; overflow drops the oldest and the 4th visible line becomes `+N more`. Mutex: SDL-free (`CRITICAL_SECTION` / pthread), as `ap_net.c` does.

- [ ] Step 1: tests `ui_toasts_expire` (notify at t=0, visible at 3999 ms, gone at 4000), `ui_toasts_order_and_cap` (6 notifies -> 4 returned, newest first, last reads `+3 more`), `ui_burst_50`, `ui_status_roundtrip`, `ui_missing_lists_unfound` (level 1 Edgars with one found -> 7 names, none equal to the found one).
- [ ] Step 2: run `ctest --test-dir build-aptest -R ap_ui` -> fails to build.
- [ ] Step 3: implement.
- [ ] Step 4: ctest passes, ASan clean.
- [ ] Step 5: commit `Archipelago 2.1: UI model for popups, status and tracker`.

### Task 2: Bridge feeds the UI; other games' names

**Files:**
- Modify: `src/ap/ap_bridge.c` (on_connected, on_received_items, on_print, pump_network, check found path, handle_packet: `DataPackage`)
- Create: `src/ap/ap_names.c/.h` (data package cache)
- Test: `tests/ap/test_ap.c` (`names`, and `live` asserts on toasts), CMake lists as Task 1.

**Interfaces:**
- Consumes: Task 1.
- Produces:
```c
void ani_names_load(const char *cache_dir);                 /* reads <dir>/<game>_<checksum>.json */
bool ani_names_add_package(const char *game, const char *checksum, const AjValue *data, const char *cache_dir);
const char *ani_names_item(const char *game, int64_t id);   /* NULL if unknown */
const char *ani_names_location(const char *game, int64_t id);
```
- RoomInfo's `datapackage_checksums`: request `GetDataPackage` with the games whose checksum isn't cached. Cache dir `<save>/archipelago/datapackage/`. Slot -> game from Connected `slot_info`.
- PrintJSON `ItemSend`: `receiving == our_slot` -> `ANI_UI_RECEIVED` `"<item> from <sender>"` (`"<item>"` alone when sender is us); sender us, receiving other -> `ANI_UI_SENT` `"<item> for <player>"`. Progression = `item.flags & 1`.
- ReceivedItems index 0 with `item_count` above the sidecar's: `ANI_UI_INFO` `Received N items`.
- Status pushed on connect, disconnect, items, and found checks; tracker counts from `ani_ap_location_names` with `S.checked` (kinds from `S.kinds`, or all before slot data).
- Unknown names -> `an item` / `somewhere`; a malformed package is ignored, not cached.

- [ ] Step 1: tests `names_roundtrip` (add package, reload from cache dir, look up), `names_corrupt_cache_ignored`, `print_itemsend_text` (fed JSON -> toast text exact), `backlog_summary` (sidecar 3 items, index-0 packet with 10 -> one toast `Received 7 items`); extend `run_live.py` live case to assert one RECEIVED toast after an item comes back.
- [ ] Step 2: fail. Step 3: implement. Step 4: ctest + `run_live.py` pass.
- [ ] Step 5: commit `Archipelago 2.1: popups and tracker data from the client; other games' names`.

### Task 3: Font (`ap_font.c`)

**Files:** Create `src/ap/ap_font.c/.h`; test case `font` in test_ap.c; `vk/CMakeLists.txt` include `third_party/stb`.

**Interfaces (Produces):**
```c
bool ani_font_init(void);   /* false = easy_font fallback in use */
int  ani_font_width(int px, const char *utf8);
/* Draws into ARGB px (stride w), clipped to w x h, alpha-blended over what is there. Returns width. */
int  ani_font_draw(uint32_t *px, int w, int h, int x, int y, int size_px, uint32_t argb, const char *utf8);
```
Font search: Windows `%WINDIR%\Fonts\segoeui.ttf`, `arial.ttf`; Linux `DejaVuSans.ttf`/`NotoSans-Regular.ttf` under `/usr/share/fonts`; macOS `/System/Library/Fonts/Supplemental/Arial.ttf`, `/Library/Fonts/Arial.ttf`. Glyph cache per size. Code points outside Latin-1 draw `?`.

- [ ] Step 1: tests `font_draws_inside_box` (draw "Edgar" at 10,10 size 20 into 200x50: some pixel changed, none outside the clip), `font_clips_negative_and_overflow` (x=-30 and x=190 under ASan), `font_non_ascii` ("Zoë 日本" doesn't crash, width > 0).
- [ ] Steps 2-4: fail, implement, pass. Step 5: commit `Archipelago 2.1: text drawing`.

### Task 4: Presenter HUD hook (patch 0007)

**Files:** Modify `tools/ngbrecomp/xboxrecomp/src/nv2a_vk/host/present_sdl.c`, `nv2a_window.h`; create `patches/ngbrecomp-0007-hud-layer.patch` (`git -C tools/ngbrecomp diff -- <those two files>`).

**Interfaces (Produces):**
```c
typedef struct { int x, y, w, h; const uint32_t *argb; } NV2AHudRect;   /* opaque, window pixels */
/* Weak, default returns 0. Called on the renderer thread once per present. */
int nv2a_hud_rects(NV2AHudRect *rects, int max, int win_w, int win_h);
```
Presenter: per frame-in-flight 1024x1024x4 staging buffer; packs each rect (clipped to the swapchain, swizzled for `VK_FORMAT_R8G8B8A8_UNORM`), one `vkCmdCopyBufferToImage` region each, after the FPS box. Skipped entirely when 0 rects. Max 8 rects.

- [ ] Step 1: build `build-vk` with a temporary title-side `nv2a_hud_rects` returning one red 300x80 rect at the top-right; capture a game frame with `NV2A_CAPTURE` and check the rect is there; resize the window to 320x240 and confirm no validation errors (`NV2A_VK_VALIDATION=1` if available) or crash.
- [ ] Step 2: `scripts/setup_vk.sh` on a clean submodule applies 0001-0007 without conflicts.
- [ ] Step 3: commit `Renderer patch 0007: title HUD panels over each presented frame`.

### Task 5: HUD drawing, tracker screen, input, settings

**Files:**
- Create: `src/ap/ap_hud.c` (game build only)
- Modify: `src/settings.c/.h` (`[archipelago]` keys), `vk/CMakeLists.txt`, `launcher/animaniacs_launcher/archipelago.py` + `launcher/tests/test_archipelago.py`, `docs/ARCHIPELAGO.md` (2.1 section), `docs/SETTINGS.md`.

**Interfaces:** Consumes Tasks 1, 3, 4. Implements `nv2a_hud_rects`, `nv2a_overlay_wanted`, `nv2a_overlay_frame`, `nv2a_window_event_hook`.
- Popups: panel width 34% of window, line height window_h/24, dark `0xFF1A1A2E` panel with a 4 px kind stripe (received gold `0xFFFFC94A`, sent sky `0xFF5AB4FF`, info grey); progression items' text is drawn in the stripe color. Panels are opaque, so the fade slides the panel off to the right over its last 0.5 s.
- Counter: top-left under the game's HUD safe margin, `Edgars 12 / 30` and a dot (green connected, amber connecting, red offline). Hidden while the tracker is open.
- Tracker: dim the backdrop 60%, title `Archipelago tracker`, one row per set (Lot, Ye Old West, Spooky Movie, Once Upon A Time, King O'Sullivans Mines, The Epic) with `found/total` per shown kind; Up/Down (D-pad, arrows) picks a set, Right/Enter shows its missing names (scrolling), Left/Esc back, Tab/F1/B/Back closes.
- Input: keyboard from the event hook; pad by `xbox_InputGetState(0, &st)` each `nv2a_hud_rects` call (Back held >= 500 ms -> open) and each overlay frame.
- Settings: off switches gate each feature.

- [ ] Step 1: launcher test for the three toggles writing `[archipelago]` keys; run `pytest launcher/tests/test_archipelago.py` -> fail; implement; pass.
- [ ] Step 2: build `build-vk`; live run `ANI_LEVEL=1 ANI_AP_TEST_COLLECT=1` against the scratch server; capture game frames showing (a) a sent popup, (b) a received popup, (c) the counter, (d) the tracker main page and (e) a detail page; check each by eye.
- [ ] Step 3: run once with no AP session and confirm a captured frame has no panels.
- [ ] Step 4: commit `Archipelago 2.1: popups, Edgar counter and tracker screen in game`.

### Task 6 (after review with Austin): chat/hints popups, then DeathLink

Planned separately once 1-5 are in his hands: chat and hints reuse `ANI_UI_INFO` from PrintJSON `Chat`/`ServerChat`/`Hint`; DeathLink needs the game's death and kill functions found first.
