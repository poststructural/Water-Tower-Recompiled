# Bring-up notes

## Region comparison (2026-10-17)

- US `default.xbe` (3,036,504 bytes) and EU `default.xbe` (3,039,232 bytes):
  all 12 section payloads byte-identical. Headers differ: the US header is
  flagged Debug and its TLS directory parses as garbage; the EU header is a
  clean Retail header. Entry point and kernel thunk decode to the same VAs
  (`0x0010A26A`, `0x001D25E0`).
- Every `.hog`, `.xmv`, `version.txt` (`A6.4a`) and `tkaXBoxDSPImage.bin` is
  byte-identical between the two dumps.
- Conclusion: one build, one recomp. EU XBE is the reference input.

## Binary facts

- Debug path: `c:\Animaniacs\Projects\AnimaniacsXBox\animaniacs\fullrelease\animaniacs.exe`
- XDK 5849. Statically linked, non-LTCG libs in named sections: D3D, XGRPH,
  XMV, D3DX, DSOUND, XPP, plus DOLBY (data). Disassemble without
  `--text-only` so those get lifted.
- `tkaXBoxDSPImage.bin` is a DSP image the game loads for the MCPX GP DSP
  (audio), relevant once audio bring-up starts.

## Pipeline results

| Step | Result |
|---|---|
| disasm (all code sections) | 6,284 functions: .text 4,518, XGRPH 678, DSOUND 434, D3D 272, XPP 195, D3DX 119, XMV 68 |
| Ghidra 12.1.4 FidDb naming | 391 names, 133 applied to function starts |
| func_id | mostly vtable/XDK-caller heuristics; 4,385 unclassified |
| abi_analysis | 6,284 entries, 30 thiscall |
| recomp | 26 chunks of 250 functions, ~39 MB of C |

Lifter flagged privileged/rare instructions (`lldt`, `ltr`, `sgdt`, `ljmp`,
`verr`, `outsw`, `int1`, `aam`) at a handful of sites, mostly in XAPI/kernel
style startup code; these become stubs and only matter if reached.

## Tooling notes

- Ghidra 12 ships no Jython, so the toolkit's `ExportXbeNames.py` fails.
  `patches/xboxrecomp-0001-ghidra12-java-export.patch` adds a Java port.
- The rea MCP server's Ghidra provider needs `GHIDRA_INSTALL_DIR` set and a
  64-bit JDK 21 as its Java; on this machine it currently resolves the
  32-bit Java 8 runtime, so rea's Ghidra-backed tools are unavailable until
  its environment is configured.

## Bring-up log

### 2026-10-17

1. **Device creation hung** in D3D_BlockOnTime (`0x0014FA40`), spinning at
   `0x0014FB77` on the GPU semaphore at `*(device+0x30)`; device pointer at
   `0x0015A388`. Fix: `recomp_manual.c` wraps it and hands the semaphore to
   the pushbuffer executor (`nv2a_pb_set_semaphore_target`). Needs
   `RECOMP_PB_EXEC=1`. Result: Ignition splash plays at ~57 fps through the
   game's own lifted XMV decoder.
2. **Stuck after the first movie**: no controller. `main.c` now calls
   `xbox_OhciInit()`; run with `RECOMP_USB=1`. XAPI enumerates the pad.
3. **Missed functions** reached by indirect calls: XPP USB callbacks after
   `ret` with no padding, and `.text` callbacks whose address is taken as an
   immediate (one was the save-name screen's, failing 11k times). Listed in
   `config/seed_functions.json`.
4. Result: all splash movies, intro, 3D frontend, New Game, name entry,
   save write ("Game saved successfully"), Continue Game listing saves, and
   the level0 (Warner lot) loading screen.

### Open issues

- **Level load crawls** (~200 KB/s of `level0.hog`, 64 KB sequential reads).
  The game's render thread spends ~90% of its time in KickOff
  (`sub_0014F860`) spinning on the PFB write-combine flush bit
  (0x100410 bit 16), which the runtime only clears between commands of the
  pushbuffer walk -- and the walker is also the CPU rasteriser. Loader
  workers wait on events behind it. Answering the flush instantly from a
  host thread (`ANI_FAST_FLUSH=1`, off by default) lets D3D run more than
  0x2400 bytes ahead of GET, and BlockOnTime then takes its wake-me path
  (0x0014FAEA), waiting at 0x0014F7D0 for PGRAPH 0x400B10's fence bits to
  match the semaphore. The executor never latches 0x400B10 in this title
  (it reads 0), so that wait never ends. The real fix is likely a
  hardware render back end (`nv2a_backend.h`) so the walk stops being
  rasteriser-bound.
- **BlockOnTime's wake-me path** (fence 0x2000+ bytes ahead of the GPU)
  sleeps on the event at device+0x1DCC, signalled by a GPU software-method
  interrupt nothing raises; KeWaitForSingleObject on it fails at once and
  the title spun at 0x0014FB94 (seen in gi1.xmv under `RECOMP_PB_WALK=dma`).
  `recomp_manual.c` now makes 0x0014F4C0 report "close", so BlockOnTime
  always uses its semaphore spin. Proper fix: raise the interrupt from the
  executor on the software method.
- **Frame rate is rasteriser-bound**: ~57-65 fps for movies, ~7-10 fps for
  the 3D frontend and the loading screen. The loader is paced by frames, so
  level0 streams at ~200 KB/s in every mode tried (scan or dma walk, with or
  without `ANI_FAST_FLUSH`). A hardware back end (`nv2a_backend.h`) is the
  fix for both.
- The Continue Game confirm dialog draws the whole font atlas full-screen
  for a frame or two (executor bug, probably a quad's UVs/coords).

## Driving a run without a pad

```
RECOMP_USB=1 RECOMP_PAD_LIVE=live.txt RECOMP_FB_DUMP=frames/f \
RECOMP_PB_REPORT_MS=1500 RECOMP_PB_EXEC=1 RECOMP_VBLANK=1 RECOMP_AC97_READY=1 \
    build/Release/animaniacs_recomp.exe 2>stderr.txt
echo start >> live.txt     # each appended line is a press: a, b, up, start ...
```

`scripts/sample_profile.py` and `scripts/thread_stacks.py` sample a live run
by symbol (the Release build now writes a PDB).

### Vulkan runtime (ngbrecomp's xboxrecomp fork)

- `vk/` builds the same lifted code against ngbrecomp's fork: xemu's NV2A
  model with its Vulkan renderer, one virtual CPU for guest threads, SDL2
  audio and input. Windows needs llvm-mingw; `scripts/setup_vk.sh`.
- The fork's checkout has a git symlink (`nv2a_vk/shim/hw/xbox/nv2a ->
  ../../../xemu`) that a Windows checkout turns into a text file;
  `vk/CMakeLists.txt` makes a junction in the build tree instead.
- mingw declares `fpclass` and `_abnormal_termination`; Ghidra's FidDb gave
  two lifted functions those names. `config/name_denylist.txt` turns them
  back into `sub_` names.
- DirectSound's GP DSP doorbell: the fork has only fixed addresses.
  `patches/ngbrecomp-0001` backports upstream's `RECOMP_APU_DSP_ACK=auto`
  (doorbell = GPSADDR SGE[0] + 0x810), on by default in `main_vk.c`.
- Four more functions seeded (0x0003F990, 0x00073A20, 0x000FAB60,
  0x00107690): level0 code reached by ICALL, which crashed the first
  Vulkan-speed load.
- Result: 60 fps menus and movies, ~40 fps in the Warner lot, level0 loads
  in well under a minute (vs ~12 min on the CPU rasteriser). The font-atlas
  flash on the Continue Game dialog does not happen here.
- CPU-executor shims in `recomp_manual.c` (semaphore registration, the
  BlockOnTime "close" answer) are compiled out under `ANI_NV2A_VK`: the
  NV2A model writes the semaphore and raises the interrupts itself.

### Windows polish (2026-10-17, afternoon)

- **Sound** works: `RECOMP_AUDIO_WAV=<file>` (patches/ngbrecomp-0002) records
  what the APU hands SDL; movies and menu music come through.
- **Warner lot 40 -> 60 fps.** The GPU thread spent ~60% of its time in
  `lru_visit_active`: every texture bound on a written page walked all 1024
  texture-cache entries to mark overlapping ones possibly dirty, per draw.
  patches/ngbrecomp-0003 replaces the walk with per-page write generations
  (a texture is possibly dirty when a page it spans is newer than its last
  hash) and clears the flag once a bound texture is re-hashed (xemu left it
  set, re-hashing on every bind). Measured: steady 60 fps, jitter < 1 ms.
- Profiling the Vulkan build: it writes `Animaniacs.pdb`; the GPU model has
  line tables; `-DANI_PROFILE_NOINLINE=ON` keeps its helpers out of line;
  `python scripts/sample_profile.py 10 --lines` while the game runs.

### Cutscenes in widescreen (2026-10-20)

- In-engine cutscene letterbox: sub_000A7C00 (per frame from sub_0009ABD0)
  draws two black quads through the 2D quad routine 0x0011E4A0 (0..60 and
  360..480 of 640x480) while 0x00312D84 is non-zero, sliding them by
  0x00312D80. recomp_manual.c skips those two quads when the picture is wider
  than 4:3; the state still advances. (sub_00109830 is the separate
  WipeOn/WipeOff fade, not the bars.)
- FMVs: the movie player 0x000ECF20 plays the movie inside the call, and all
  33 movies are 640x480 4:3, so the presenter is switched to 4:3 for the call
  (pillarbox instead of stretch).
- Finding draw calls: ANI_QUAD_LOG=1 lists every 2D quad call site once with
  its rectangle; RECOMP_COVER_SNAP=<prefix> plus creating <prefix>.req writes
  a coverage snapshot (patches/ngbrecomp-0005); scripts/guest_mem.py dumps
  and diffs guest memory of a running game.

### 2D and the frontend in widescreen (2026-10-23)

- Menus, text and HUD go through an immediate-mode layer: 0x001378E0 begins a
  primitive (types >= 5 load a 640x480 orthographic projection), vertices go
  to the pushbuffer as SetVertexData4f(VERTEX) (method 0x1518), D3D End is
  0x0014DD80. At End the primitive's vertices are still unsubmitted, so the
  x values are squeezed by 4:3/aspect in place, anchored by which third of
  the screen the primitive sits in; full-width primitives are left alone.
- The frontend stage is a full-screen 4:3 backdrop with 3D characters on it
  (their cameras set scales through 0x00122A50); widening the view moves the
  characters off their marks. States below 3 (boot, frontend) are shown at
  4:3 with side bars; levels at the picture's shape.
- getenv in a per-draw hook cost ~half the frame rate: debug switches in
  recomp_manual.c are read once (ANI_ENV).
- scripts/guest_mem.py read 0x10000 too low; it now uses the logged offset.

### Rumble stalls (2026-10-23)

- The game's rumble call (0x0013CB60) creates an event, passes it to
  XInputSetState and waits for the emulated USB transfer to signal it, on the
  main thread. That wait cost a poll interval per call (30-45 fps in fights)
  and could be lost, freezing the game (seen in level 4 at 6x render scale).
  recomp_manual.c now sets the host controller's motors directly and returns.
- Still open: level 4's busy areas dip to 30-45 fps at times at any scale. The
  main thread waits in BlockOnTime on the GPU thread, which spends its time in
  surface ownership (VirtualProtect) and surface downloads, not in drawing.
  ANI_BLOCK_SPIN=1 (BlockOnTime polls the semaphore instead of sleeping on the
  GPU interrupt) did not change it.
