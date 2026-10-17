# Archipelago randomizer

The recompiled game can join an [Archipelago](https://archipelago.gg) multiworld.
Every Edgar you pick up sends a check, the Edgars you receive are what opens the
movie sets, and (optionally) the abilities are shuffled too. It follows the design
of [crackdown-recomp](https://github.com/Unowa001/crackdown-recomp)'s randomizer: the
client is compiled into the executable, checks come from hooks on the game's own
functions, and items are granted by writing game state on the game thread. There is
no separate client program and no memory-poking sidecar.

**Status: first version, not yet played through.** On Austin's PC it builds, and a
bound session runs New Game into the hub and level 1 at 60 fps; no Edgar has been
picked up with it yet. The client, the world and the
protocol are tested against a real Archipelago 0.6.8 server (see Testing). The game
facts below come from static analysis of `default.xbe`; the ones marked
*provisional* still need a playthrough to confirm.

## Playing

1. Build the world: `python scripts/build_apworld.py` writes `build/animaniacs.apworld`.
   Install it in Archipelago (double-click, or copy it into `custom_worlds`).
2. Make a YAML with the Options Creator, generate, and host the room as usual.
3. Start the Vulkan build with the room and your slot:

   ```bash
   ./Animaniacs.exe --ap-server archipelago.gg:38281 --ap-slot YourName
   ```

   `ANI_AP_SERVER`, `ANI_AP_SLOT` and `ANI_AP_PASSWORD` work too; use the variable
   for a password so it stays off the command line. Without a scheme the client
   tries `wss://` first, then `ws://`.
4. Start a **New Game**. Each seed gets its own save directory
   (`<save dir>/archipelago/<seed>_<slot>/`), so saves from other seeds or from
   vanilla play are never mixed in. If the server can't be reached at start-up, the
   game plays the last seed used with that slot offline and sends the checks when
   it reconnects.

The log (stdout) shows what is sent and received: `[AP] check: Calamity Canyon Edgar 1`,
`[AP] received Snorkel`.

### Options

| Option | Default | |
|---|---|---|
| `edgars_required` | 30 | Edgars to receive to win (1-36) |
| `shuffle_abilities` | off | Abilities in the pool; the places the game hands them out become checks. **Experimental**: the logic for where each ability is needed is provisional |
| `starting_siblings` | start_with | With abilities shuffled: start with Wakko and Dot, or shuffle them too |

## Items and locations

All IDs live in [`archipelago/animaniacs/catalog.json`](../archipelago/animaniacs/catalog.json),
which the Python world loads and `scripts/gen_ap_catalog.py` turns into
`src/ap/ap_catalog.h` for the game (a CTest checks the header is current), so the
two can't disagree on an ID.

- **36 Edgar locations**, six per level: "Calamity Canyon Edgar 3" is the third Edgar
  you find in that level, whichever one it is. The game keeps a per-level count and
  not which statuette was taken, so the check is the count: reloading a save and
  picking the same Edgar up again sends nothing new.
- **11 ability locations** (with `shuffle_abilities`): "Snorkel Pickup" is where the
  game would have given you the Snorkel.
- **Items**: 36 Edgars, the 11 abilities, and "Applause" filler (does nothing).
- **Logic**: a level is open once you have received enough Edgars (`unlock_edgars`
  in the catalog). With abilities shuffled, a level's checks can also need abilities
  (`requires`, empty so far).
- **Goal**: receive `edgars_required` Edgars.

## How it works

`src/ap/`:

| File | Role |
|---|---|
| `ap_net.c` | Connection thread: reconnects with backoff, answers RoomInfo with Connect, queues packets. Never touches guest memory. Sends are tagged with a connection generation and dropped if that connection is gone |
| `ap_ws_winhttp.c` / `ap_ws_posix.c` | WebSocket transport: WinHTTP on Windows (ws and wss, system TLS and proxy); plain sockets elsewhere (ws only for now) |
| `ap_json.c` | Small JSON parser and builder |
| `ap_bridge.c` | Everything on the game thread: protocol, the sidecar, the hooks |
| `ap_game.c` | Guest addresses and layouts |

The sidecar `ap_state.json` (next to the seed's saves) holds the received items,
the checks found and the checks the server has acknowledged. A check is written there
before it is sent, and anything not acknowledged is sent again on every connect. The
server's `checked_locations` is authoritative, so a room restored from an older
save gets its forgotten checks back.

### Hooks (`src/recomp_manual.c`)

| Guest function | Evidence | Use |
|---|---|---|
| `0x000B09A0` state machine step | Called once per main-loop iteration (PC session) | Network, and forcing the ability word to the received abilities |
| `0x0009A9C0` level update | Top of the function: if byte `0x00308150` is set, `OscarPickupsCollected += 1`, run `"edgarsequence"` | Edgar handed out by a script |
| `0x00027E00` pickup update | Reached through the object type table at `0x001E363C`. Pickup type (`+0x118`) 3: `fld [*0x002ED388]; fadd 1.0; fstp`, then `"edgarsequence"` (`0x00027FBB`) | Edgar picked up |
| `0x0009F840` GiveAbility | `or [0x00311510], ax`. Callers: the `GiveAbility` script verb (`0x000FC8B0`) and pickup types 0xF/0x12/0x13/0x14 (`0x00028131`) | Shuffled abilities become checks and are not granted |
| `0x000FD450` GetAllEdgars | Script verb registered at `0x000FF13D`; sums bits 4-7 of each level record, returns 36 under the all-Edgars cheat (`0x00311512 & 0x10`) | Returns the Edgars received |

A hook that answers in place of the generated body (GetAllEdgars, and
GiveAbility when every bit is shuffled) pops the return address itself
(`g_esp += 4`), as the body's `ret` would; the host tests' fake bodies do the same
and check the stack balances. The two reached through function pointers are also returned from
`recomp_lookup_manual`, because the dispatch table maps a wrapped function to its
generated body.

### Guest data

| Address | Layout |
|---|---|
| `0x00313B54` | Game state; 3-8 are levels 0-5 |
| `0x003104B8` | Progress block, `0x41B` dwords, copied out for a save (`0x0009F850`) |
| `0x003104D8 + n*0x2B4` | Level record n. `+0x2A4` bits 4-7: Edgars found; `+0x25C`: collected-pickup bitfield; `+4..`: persistent script floats (written by `0x0009F370` on leaving a level) |
| `0x00311510` | Ability word. `GetAbility` (`0x000FCA30`) names the bits: `0x001` bomb, `0x002` shovel, `0x004` skirt, `0x008` magnifyglass, `0x010` wakko, `0x020` dot, `0x040` longattack, `0x080` snorkel, `0x100` suckers, `0x200` goggles, `0x400` redstardoor, `0x800` script (not shuffled) |
| `0x00308158` | The running level's script variable store; `0x0009C7A0` looks a name up (`ap_game.c` does the same) |

### Provisional, to confirm in a playthrough

Run with `ANI_AP_LOG=1` (and a room) and the log records what is needed:

1. **Edgar counter**: that `*0x002ED388` is the level's `OscarPickupsCollected`. The
   log line `edgar: level L count N (pickup), record R` should show N matching the
   in-game count.
2. **Edgars per level**: six each is inferred from the cheat's 36.
3. **Where each ability is granted**: `GiveAbility 0x080 in level 3` lines fill in
   `abilities[].level`, and which checks need which ability fills `levels[].requires`.
   Until then keep `shuffle_abilities` off for real games.
4. **What opens each level**: whether the hub's doors use `GetAllEdgars`, and their
   thresholds (`unlock_edgars`, a guess of 3/9/15/21/27). If the game asks for more
   than the logic, a seed can get stuck.
5. **Level names**: from the PC session's descriptions; the real ones are the
   `LEVELn_NAME` strings.
6. **Native ability pickups still show their item screen** (`0x000F3250`) even
   though the ability goes to the multiworld.

Not done yet: DeathLink (respawn verbs are at `0x000FD900`/`0x000FD940`), on-screen
messages (no HUD text function found yet), `wss://` off Windows, a launcher tab.

## Testing

```bash
cmake -S tests/ap -B build-aptest && cmake --build build-aptest
ctest --test-dir build-aptest --output-on-failure      # JSON, guest adapter, catalog header
python tests/ap/run_live.py build-aptest/test_ap --archipelago ~/Archipelago \
    --python ~/Archipelago/venv/bin/python
```

`run_live.py` builds the apworld, generates a one-player seed, hosts it with
`MultiServer`, and runs three cases against fake guest memory: a live session (an
ability grant and two Edgars become checks, items come back, the ability word follows
them), offline play with the server stopped, and the resend when it is back. The
host tests build with ASan and UBSan. The same harness cross-compiled with mingw
passes under Wine, which exercises the WinHTTP transport (including the
`wss://`-then-`ws://` fallback with `--no-scheme`).
