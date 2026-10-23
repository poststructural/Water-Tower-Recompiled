# Animaniacs: The Great Edgar Hunt — Static Recompilation

A static recompilation of the original Xbox release of *Animaniacs: The Great
Edgar Hunt* (Ignition / Warthog, 2005) into a native executable, built on
[xboxrecomp](https://github.com/sp00nznet/xboxrecomp). Windows is the
first target; Linux and macOS follow.

**No game files are included.** You need your own copy of the game.

## Status: 1.0 (Windows)

The whole game plays on Windows through the Vulkan build: the intro movies,
the frontend, saving and loading, the Warner lot hub and all five levels, at
60 fps.

- Any output resolution up to 4K, windowed or fullscreen, with an internal
  render scale chosen to match (up to 6x the console's 640x480).
- Widescreen (Hor+) from 16:10 to 32:9 in the levels; the HUD and menu text
  keep their shape; in-engine cutscenes without letterbox bars; the movies and
  the frontend's painted 4:3 stage shown at 4:3.
- Controllers through SDL (Xbox, PlayStation, Switch and others) with rumble,
  and the keyboard.
- `settings.ini` for everything ([docs/SETTINGS.md](docs/SETTINGS.md)); a
  crash writes `crash.txt` beside `log.txt`.

Linux and macOS are next.

Two builds of the same recompiled game exist:

| | MSVC build (`CMakeLists.txt`) | Vulkan build (`vk/`) |
|---|---|---|
| Runtime | [xboxrecomp](https://github.com/sp00nznet/xboxrecomp) upstream | [ngbrecomp](https://github.com/gamboozino/ngbrecomp)'s xboxrecomp fork |
| GPU | CPU pushbuffer rasteriser | xemu's NV2A model on Vulkan |
| Speed | menus ~7-10 fps, level load ~12 min | 60 fps |
| Compiler | MSVC | llvm-mingw (clang) |

The Vulkan build is the one to play; the MSVC build is kept as a reference.

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

Requirements: Python 3.10+ with `capstone`, CMake 3.20+. The Vulkan build
needs llvm-mingw (fetched by `scripts/setup_vk.sh`); the MSVC build needs
Visual Studio 2022+. Optional: Ghidra 12.x and a 64-bit JDK 21 for function
naming (the game builds and plays the same without it).

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
overrides). `settings.ini` is written beside the exe on first run: windowed or fullscreen,
output resolution (1080p, 1440p, 4K, ultrawide), aspect ratio (4:3 to 32:9,
or auto), render scale (auto matches the output), MSAA, texture filtering and
`skip_intro`. Every key is listed in [docs/SETTINGS.md](docs/SETTINGS.md).
F11 / Alt+Enter toggles fullscreen and F10 shows the frame rate. Controller
and keyboard keys are in [docs/CONTROLS.md](docs/CONTROLS.md).

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

## Licenses

Third-party parts and their licenses are listed in
[THIRD_PARTY.md](THIRD_PARTY.md); a built game folder carries it with the
license texts. *Animaniacs: The Great Edgar Hunt* belongs to its rights
holders; no game data is included here.
