# Animaniacs: The Great Edgar Hunt — Static Recompilation

A static recompilation of the original Xbox release of *Animaniacs: The Great
Edgar Hunt* (Ignition / Warthog, 2005) into a native executable, built on
[xboxrecomp](https://github.com/sp00nznet/xboxrecomp). Windows (MSVC + D3D11)
is the primary target; Linux and macOS go through xboxrecomp's SDL2/OpenGL
back end.

**No game files are included.** You need your own copy of the game.

## Status

Early bring-up. The full pipeline runs and the lifted C compiles into
`animaniacs_recomp.exe`; booting it is the work in progress. See
[docs/NOTES.md](docs/NOTES.md) for findings and the bring-up log.

## The game binary

| | |
|---|---|
| Title ID | `0x494F0003` |
| Build | 2004-11-08, XDK 5849, internal version `A6.4a` |
| Entry point | `0x0010A26A` |
| Code | `.text` 1.25 MB + statically linked D3D8, XGRAPHICS, XMV, D3DX8, DSOUND, XPP sections |
| Functions | 6,284 detected (4,518 game, 1,766 XDK) |
| Kernel imports | 106 |

The US and PAL ("EURPOE") dumps are the same build: every XBE section, every
`.hog` archive and every `.xmv` movie is byte-identical. Only the XBE header
differs (the US dump's header is re-flagged as a debug XBE). The EU retail XBE
is used as the reference input, and either region's data runs.

## Building

Requirements: Python 3.10+ with `capstone`, CMake 3.20+, Visual Studio 2022+
(C workload) on Windows. Optional: Ghidra 12.x and a 64-bit JDK 21 for
function naming.

```bash
git clone --recursive https://github.com/Unowa001/AnimaniacsRecompiled.git
cd AnimaniacsRecompiled
pip install capstone

# 1. Put your game files in game/ (default.xbe, resource/, movies/,
#    tkaXBoxDSPImage.bin)

# 2. Generate the C from your XBE
GHIDRA_HOME=/path/to/ghidra_12.1.4_PUBLIC JAVA_HOME=/path/to/jdk-21 \
    XBE=game/default.xbe scripts/regen.sh

# 3. Build
cmake -S . -B build -A x64
cmake --build build --config Release --parallel

# 4. Run with game/ next to the exe
cp -r game build/Release/game     # or a junction/symlink
build/Release/animaniacs_recomp.exe 2>stderr.txt
```

## Layout

```
src/main.c              host entry: loads the XBE, boots the kernel layer, calls the guest
src/recomp_manual.c     hand-written overrides for lifted functions
src/recomp/gen/         generated C (not committed; produced by scripts/regen.sh)
tools/xboxrecomp/       the toolkit (git submodule)
patches/                local patches applied to the toolkit
scripts/regen.sh        the full XBE -> C pipeline
```

## Toolkit patches

- `xboxrecomp-0001-ghidra12-java-export.patch` — Ghidra 12 no longer ships
  Jython, so the toolkit's `ExportXbeNames.py` post-script aborts. This adds a
  Java port (functions + symbols export) and makes it the default.
  `scripts/regen.sh` applies it automatically.
