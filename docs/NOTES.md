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
  host thread deadlocked D3D's fence wait (GET == PUT but the semaphore
  never reached the fence), so that was reverted. The real fix is likely a
  hardware render back end (`nv2a_backend.h`) so the walk stops being
  rasteriser-bound.
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
