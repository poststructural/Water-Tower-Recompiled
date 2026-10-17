# Launcher

A small Windows program (Python + tkinter) that sets the game up from your own
copy and keeps it up to date. Install it with `AnimaniacsLauncherSetup-<v>.exe`
from the [releases](https://github.com/Unowa001/AnimaniacsRecompiled/releases)
(tags `launcher-v*`), or run it from a checkout:

```bash
python launcher/run_launcher.py            # the window
python launcher/run_launcher.py --help     # the same steps from the command line
```

## What it does

1. **Game files.** Point it at an Xbox disc image (`.iso`, trimmed XISO or a
   full Redump dump), a `.zip`, or a folder with `default.xbe`. Images and
   zips are extracted; a folder is used where it is. It checks the XBE's
   title id (`494F0003`) and that `resource/`, `movies/` and
   `tkaXBoxDSPImage.bin` are there. US and EU copies both work.
2. **Build.** The recompiled code is generated from your `default.xbe`, so
   the launcher builds the game on your PC rather than downloading it: the
   README's Vulkan build steps, in a checkout it owns. The first build
   downloads llvm-mingw and the CLANG64 libraries (a few GB); later updates
   reuse them and rebuild incrementally.
3. **Updates.** "Releases" follows the newest GitHub release (and follows
   `main` until the repository has one); "Latest main" follows every commit.
   The last build is kept so you can switch back in Settings. Your
   `settings.ini` (window, fullscreen, render scale, skip intros) moves with
   you to each new build.
4. **Play.** Starts the current build on your game files and keeps its log in
   `logs/`. Saves stay in `%LOCALAPPDATA%\AnimaniacsRecompiled`.

The launcher also offers its own updates from `launcher-v*` releases.

## Needed on the PC

- [Git for Windows](https://git-scm.com/download/win) (git, and the bash the
  build scripts run in)
- Python 3.10+

The launcher offers to install both with `winget`. It puts the build's Python
tools (capstone, cmake, ninja, pkgconf) in its own venv. Ghidra is optional
(function names in crash logs; set its folder in Settings).

## Where things go

`%LOCALAPPDATA%\AnimaniacsRecompiled\launcher` (`ANI_LAUNCHER_HOME` overrides):
`settings.json`, `game/` (extracted game), `source/` (checkout),
`windeps/` (toolchain), `pyenv/`, `builds/<version>/`, `logs/`.
Uninstalling removes that folder and keeps your saves.

## Releasing

- Game: publish a GitHub release with a version tag (`v0.2.0`). Launchers on
  the Releases channel build it on their next update check.
- Launcher: bump `__version__` in `animaniacs_launcher/__init__.py` and push
  a `launcher-v<version>` tag. CI (`.github/workflows/launcher.yml`) builds
  the installer and attaches it to that release.

## Tests

```bash
python -m pytest launcher/tests
```

The tests build small synthetic disc images, so no game files are needed.
