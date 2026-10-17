# Animaniacs: The Great Edgar Hunt — Static Recompilation

A static recompilation of the original Xbox release of *Animaniacs: The Great
Edgar Hunt* (Ignition / Warthog, 2005) into a native executable, built on
[xboxrecomp](https://github.com/sp00nznet/xboxrecomp). Windows (MSVC + D3D11)
is the primary target; Linux and macOS go through xboxrecomp's SDL2/OpenGL
back end.

**No game files are included.** You need your own copy of the game.

## Status

Boots and plays on Windows: splash movies, intro, the 3D frontend, saving
and loading, and the first level (the Warner lot) with Yakko under control.
See [docs/NOTES.md](docs/NOTES.md) for the bring-up log.

Two builds of the same recompiled game:

| | MSVC build (`CMakeLists.txt`) | Vulkan build (`vk/`) |
|---|---|---|
| Runtime | [xboxrecomp](https://github.com/sp00nznet/xboxrecomp) upstream | [ngbrecomp](https://github.com/gamboozino/ngbrecomp)'s xboxrecomp fork |
| GPU | CPU pushbuffer rasteriser | xemu's NV2A model on Vulkan |
| Speed | menus ~7-10 fps, level load ~12 min | 60 fps menus, ~40 fps in level, load under a minute |
| Compiler | MSVC | llvm-mingw (clang) |

The Vulkan build is the one to play.

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

## Building the Vulkan version (Windows)

Needs a GPU with Vulkan 1.3 drivers.

```bash
scripts/setup_vk.sh                                  # once: fork, patches, llvm-mingw, libraries
TK=tools/ngbrecomp/xboxrecomp XBE=game/default.xbe scripts/regen.sh
cmake -S vk -B build-vk -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE=cmake/toolchains/windows-llvm-mingw.cmake
ninja -C build-vk
# The build folder is a runnable game folder: the DLLs are copied beside the
# exe. Put (or link) your game files in build-vk/game, then:
build-vk/Animaniacs.exe
```

Saves and `log.txt` go to `%LOCALAPPDATA%\AnimaniacsRecompiled` (`ANI_SAVE_DIR`
overrides). `settings.ini` is written beside the exe on first run: window size,
fullscreen (F11 / Alt+Enter in game), vsync, render scale (1-4, default 2 =
1280x960), MSAA, texture filtering, and `skip_intro`. F10 shows the frame rate.

Test switches: `ANI_LEVEL=N` (1-5) loads level N instead of the hub;
`RECOMP_AUDIO_WAV=out.wav` records the audio output.

## Layout

```
src/main.c              host entry (MSVC build): loads the XBE, boots the kernel layer, calls the guest
src/main_vk.c           host entry (Vulkan build): window, GPU model, virtual CPU
src/recomp_manual.c     hand-written overrides for lifted functions
src/recomp/gen/         generated C (not committed; produced by scripts/regen.sh)
tools/xboxrecomp/       the toolkit (git submodule)
tools/ngbrecomp/        ngbrecomp, for its xboxrecomp fork (git submodule)
vk/                     the Vulkan build
cmake/toolchains/       llvm-mingw toolchain for the Vulkan build
patches/                local patches applied to the toolkit
scripts/regen.sh        the full XBE -> C pipeline
```

## Toolkit patches

- `xboxrecomp-0001-ghidra12-java-export.patch` — Ghidra 12 no longer ships
  Jython, so the toolkit's `ExportXbeNames.py` post-script aborts. This adds a
  Java port (functions + symbols export) and makes it the default.
  `scripts/regen.sh` applies it automatically.
