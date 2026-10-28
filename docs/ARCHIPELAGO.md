# Archipelago randomizer

The recompiled game can join an [Archipelago](https://archipelago.gg) multiworld.
Every pickup the game places can be a check, the Edgars you receive are what open
the movie sets, and (optionally) the abilities are shuffled too. It follows the
design of [crackdown-recomp](https://github.com/Unowa001/crackdown-recomp)'s
randomizer: the client is compiled into the executable, checks come from hooks on
the game's own functions, and items are granted by writing game state on the game
thread. There is no separate client program and no memory-poking sidecar.

**Status: catalog 2, not yet played through.** The checks come from the game's own
level data. On Austin's PC a run into Ye Old West collected gold nuggets and the
letter A through the real pickup code and the server acknowledged them (the 25
nugget milestone fired at the 25th). The client and the world are tested against
a real Archipelago 0.6.8 server, and seeds generate for every option combination
tried. What still needs a playthrough is listed under Logic.

## Playing

1. Get the world: the launcher's Archipelago tab has **Save animaniacs.apworld**, or
   `python scripts/build_apworld.py` writes `build/animaniacs.apworld`. Install it in
   Archipelago (double-click, or copy it into `custom_worlds`).
2. Make a YAML with the Options Creator, generate, and host the room as usual.
3. In the launcher's Archipelago tab, turn the session on, fill in the server and
   slot (and password), and press Play. By hand:

   ```bash
   ./Animaniacs.exe --ap-server archipelago.gg:38281 --ap-slot YourName
   ```

   `ANI_AP_SERVER`, `ANI_AP_SLOT` and `ANI_AP_PASSWORD` work too; the launcher passes
   the password through the variable so it stays off the command line. Without a
   scheme the client tries `wss://` first, then `ws://`.
4. Start a **New Game**. Each seed gets its own save directory
   (`<save dir>/archipelago/<seed>_<slot>/`), so saves from other seeds or from
   vanilla play are never mixed in. If the server can't be reached at start-up, the
   game plays the last seed used with that slot offline and sends the checks when
   it reconnects.

The log (stdout, or the launcher's game log) shows what is sent and received:
`[AP] check: Ye Old West: Rodeo Edgar`, `[AP] received Edgar`.

### In game

- **Popups**, top right: `GOT` (gold) for an item you receive, with who sent it
  ("Hookshot from Sam", or where you found your own: "Edgar (Rodeo Edgar)"), and
  `SENT` (blue) for an item one of your checks sends someone else ("Bow for Sam").
  Progression items are in color. Each lasts four seconds; when more come at once
  than fit, the last line counts the rest. Items that arrived while the game was
  closed are one popup: "Received 14 items". Other games' names come from the room's
  data packages, cached in `<save dir>/archipelago/datapackage/`. `HINT` (violet) for
  a hint about one of your items or checks that isn't found yet, and `CHAT` (green) for
  chat, server messages and countdowns (these can be turned off on their own).
- **Edgar counter**, bottom left: Edgars received and the number the goal wants, with
  a light: green connected, amber reconnecting, red offline.
- **Tracker**: Tab or F1, or hold Back on the controller for half a second. The game
  holds still while it is open. One row per movie set with found/total for each kind of
  check the room has; Enter (or A) lists the checks still left in a set, Left (or B)
  goes back, Tab or B closes.

Each can be turned off in the launcher's Archipelago tab or in settings.ini
(`[archipelago]`, [SETTINGS.md](SETTINGS.md)).

### Options

| Option | Default | |
|---|---|---|
| `goal` | edgar_hunt | `edgar_hunt`: receive `edgars_required` Edgars. `credits`: beat CC Deville (his boss game wants 36 Edgars) with that many received |
| `edgars_required` | 30 | 1-45 |
| `collectibles` | milestones | `none`, `milestones` (every 25 of a level's 300: 72 checks), `every_one` (1800 checks) |
| `apples` | off | every placed apple is a check (253) |
| `shuffle_abilities` | off | abilities in the pool; where the game hands them out become checks. **Experimental** |
| `starting_siblings` | start_with | with abilities shuffled: start with Wakko and Dot, or shuffle them too |

## Checks

All IDs live in [`archipelago/animaniacs/catalog.json`](../archipelago/animaniacs/catalog.json).
`scripts/survey_ap_catalog.py` builds it from your game files (it reads the levels
out of `resource/levelN.hog` with [`tools/hog/hog.py`](../tools/hog/hog.py)), the
Python world loads it, and `scripts/gen_ap_catalog.py` turns it into
`src/ap/ap_catalog.h` for the game (a CTest checks the header is current), so the
three can't disagree on an ID. Location ID = base + kind × 0x10000 + level × 0x1000
+ index.

| Kind | Count | Where they come from |
|---|---|---|
| Edgars | 45 | Each set's `RegisterEdgar(slot, object, room)` calls: 8 per movie set, 4 on the lot (the 125 and 300 collectible Edgars have a copy in every room, `edgar_125_NN` / `edgar_300_NN`), and CC Deville's |
| ACME letters | 24 | Pickup types 4-7 (`APickupsCollected`... ), one each per level |
| Script pages | 6 | Pickup type 2 |
| Quest items | 30 | Types 8-13, 16, 22: Ye Old West's magnet, Spooky Movie's bones, Once Upon A Time's timber, the mines' key pieces, The Epic's feathers, dates, glue, blueprints and sticks |
| Collectibles | 1800 | Type 1, 300 per level: film reels, gold nuggets, pumpkins, crowns, emeralds, scarabs |
| Milestones | 72 | `MajorPickupsCollected` reaching 25, 50, ... 300 in a level |
| Apples | 253 | Type 14 |
| Abilities | 11 | With `shuffle_abilities`; the GiveAbility calls in the scripts and the four ability pickups (types 15, 18, 19, 20) |

Each check is a pickup object by name: object names are unique within a level, and
the pickup update hands the client the object it collected, so "Ye Old West: Rodeo
Edgar" is `Edgar_Bronco` in level 1 whichever order things happen in. Reloading a
save and collecting the same object again sends nothing new.

Not checks (yet): the puzzle buttons (type 21), level completion, and the boss
fights apart from the Edgars they award (most bosses and minigames end in one of
the named Edgars: the Bride, Wagroth, the totem pole, the chariot race, Pipe Mania...).

## Logic

- A movie set opens at the hub's Edgar door for it, read from `level0.lvl`:
  Ye Old West 0, Spooky Movie 4, Once Upon A Time 9, King O'Sullivans Mines 12,
  The Epic 25. The final boss, CC Deville, wants 36 (`EdgarsToPlayBoss`); the
  client's `GetAllEdgars` answers with the Edgars received, which is what all
  of these doors ask.
- Each set has one more Edgar door of its own (2, 6, 14, 20, 30). Which checks are
  behind it is not known, so every check in a set counts as needing it. This only
  over-restricts.
- Pickups hidden under a dig tile (the tile's `LinkedObject`) need the Shovel; a
  milestone past the collectibles that are out in the open needs it too.
- An ability that is not shuffled counts as had once its set's door can be passed.
  With abilities shuffled, a set's checks count as needing every ability the game
  hands out up to the end of that set, and an ability's own location only the ones
  a vanilla playthrough meets before it.

**To confirm in a playthrough:** the game has backtracking content gated by abilities
from later sets (dig tiles on the lot and in Ye Old West, bomb-able hydrants on the
lot, dark rooms that want the goggles). The dig tiles are handled; whether any
other check sits behind a later set's ability is not known from the data. If a seed
ever leaves a check you can't reach, note its name: the catalog takes a `requires`
list per location.

## How it works

`src/ap/`:

| File | Role |
|---|---|
| `ap_net.c` | Connection thread: reconnects with backoff, answers RoomInfo with Connect, queues packets. Never touches guest memory. Sends are tagged with a connection generation and dropped if that connection is gone |
| `ap_ws_winhttp.c` / `ap_ws_posix.c` | WebSocket transport: WinHTTP on Windows (ws and wss, system TLS and proxy); plain sockets elsewhere (ws only for now) |
| `ap_json.c` | Small JSON parser and builder |
| `ap_bridge.c` | Everything on the game thread: protocol, the sidecar, the hooks |
| `ap_game.c` | Guest addresses and layouts |
| `ap_names.c` | Other games' item and location names, from the room's data packages, cached on disk |
| `ap_ui.c` | What the overlay shows (popups, counter, tracker counts), written by the bridge and read by the renderer's thread under a lock |
| `ap_font.c` | Text: a system TrueType font (Segoe UI, Arial, DejaVu Sans...) through stb_truetype, `stb_easy_font` if none is found |
| `ap_hud.c` | The overlay on screen: popups and counter as panels the presenter copies over each frame (`nv2a_hud_rects`, `patches/ngbrecomp-0007`), the tracker over the held game (`nv2a_overlay_frame`), keys and pad |

The sidecar `ap_state.json` (next to the seed's saves) holds the received items,
the checks found and the checks the server has acknowledged. A check is written
there before it is sent, and anything not acknowledged is sent again on every
connect. The server's `checked_locations` is authoritative, so a room restored from
an older save gets its forgotten checks back. Checks of kinds the room doesn't have
(say, collectibles in a milestones room) are kept but never sent; the room's kinds
come in `slot_data.location_kinds`.

### Hooks (`src/recomp_manual.c`)

| Guest function | Use |
|---|---|
| `0x000B09A0` state machine step | Network, and forcing the ability word to the received abilities |
| `0x00027E00` pickup update (object type table `0x001E363C`) | The object it is given (`[esp+4]`) reaching state 3 (counted) or 4 (gone) is collected; its name says which check. Also the milestones |
| `0x0009A9C0` level update | Byte `0x00308150` set: CC Deville is beaten, the next frames hand over the last Edgar and play the ending (`GE2`) |
| `0x0009F840` GiveAbility | Shuffled abilities become checks and are not granted |
| `0x000FD450` GetAllEdgars | Returns the Edgars received |

A hook that answers in place of the generated body (GetAllEdgars, and GiveAbility
when every bit is shuffled) pops the return address itself (`g_esp += 4`), as the
body's `ret` would. The two reached through function pointers are also returned
from `recomp_lookup_manual`.

### Guest data

| Address | Layout |
|---|---|
| `0x00313B54` | Game state; 3-8 are levels 0-5 |
| `0x003104D8 + n*0x2B4` | Level record n (saved). `+0x25C` 64 bytes: collected pickups by their order among the level's pickup objects; `+0x29C`/`+0x29E` tasks revealed/done; `+0x2A0`: A letter (bit 0), script page (bit 1), Extra1-6 counts; `+0x2A4`: E, M, C (bits 1-3), Edgars (4-7), collectibles (8-16), Extra7 (17+); `+0x2A8` 9 bytes: Edgar slots spawned |
| `0x0030C630` | The level's objects in load order (count at `0x003104B4`); `0x00308160` the same sorted by name |
| Object | `+0x0C` name, `+0x2C` scene node (world matrix at `+0x40`/`+0x80`, byte `+0x23` picks), `+0x114` pickup state (`0xFFFF` new, 0 waiting, 3 counted, 4 gone, 6 hidden), `+0x118` PickupType |
| `0x00311510` | Ability word (`GetAbility`, `0x000FCA30`, names the bits) |
| `0x00308158` | The running level's script variable store; `0x0009C7A0` looks a name up |

Objects are allocated in the kernel's mirror of RAM (`0x8xxxxxxx`).

## Testing

```bash
cmake -S tests/ap -B build-aptest && cmake --build build-aptest
ctest --test-dir build-aptest --output-on-failure      # JSON, guest adapter, catalog header
python tests/ap/run_live.py build-aptest/test_ap --archipelago ~/Archipelago \
    --python ~/Archipelago/venv/bin/python
```

On Windows the same test builds with llvm-mingw (`ap_ws_winhttp.c`, `-lwinhttp
-lws2_32`). `run_live.py` builds the apworld, generates a one-player seed, hosts it
with `MultiServer`, and runs three cases against fake guest memory: a live session
(pickups by object name, a milestone, an ability grant, items coming back), offline
play with the server stopped (including beating CC Deville), and the resend when it
is back.

`ANI_HUD_DUMP=<dir>` writes what the overlay draws: the popup and counter panels with
their places once a second (`hud_<ms>.txt`, `hud_<ms>_<n>.ppm`) and each tracker screen,
to check against the game's own frames (`NV2A_CAPTURE`). `ANI_HUD_TEST=<seconds>` opens
the tracker that long after start and steps through it. `ANI_AP_LOG=1` logs every pickup state change; `ANI_AP_TEST_COLLECT=1` (a test
switch) brings one waiting pickup that is a check to the player every two seconds,
so a run collects them through the game's own code without anyone playing.
