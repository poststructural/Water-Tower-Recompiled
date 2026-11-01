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
3. **Updates.** "Releases" follows the newest version (and follows `main`
   until there is one); "Latest main" follows every commit. Where versions
   come from is the update source (below), and "Install update from file"
   takes a source bundle or a launcher installer for updating offline.
   The last build is kept so you can switch back in Settings. Your
   `settings.ini` (window, fullscreen, render scale, skip intros) moves with
   you to each new build.
4. **Play.** Starts the current build on your game files and keeps its log in
   `logs/`. If the game crashes or closes during start-up, Home shows the end
   of its log and a Copy system info button for bug reports.

Home is a night scene of the studio lot with our water tower, the wordmark,
one big Play button (it reads Set up, Build or Play, whichever comes next),
Verify files, Game files, Updates and Settings, and a status card: the
installed version, renderer, save profile, controller, and whether the game
files are verified, with the progress of whatever is running. The other pages
are down the left:

| Tab | What it sets |
|---|---|
| Home | Play, verify game files, change the game files, updates, the status card |
| Display | Windowed or fullscreen (borderless, monitor resolution), window size (720p to 4K, ultrawide, native, or custom), aspect ratio (auto, 4:3, 16:9, 16:10, 21:9, 32:9), HUD and menu text (keep 4:3 or stretch), v-sync, frame rate counter |
| Graphics | Internal resolution (auto or 1x-8x), the auto limit, anti-aliasing, texture filtering |
| Gameplay | Skip intros, close the launcher on Play |
| Saves | Save profiles (each its own save folder), open or back up saves |
| Mods | Add mods from a .zip or folder, turn them on or off, load order, conflicts |
| Updates | Release or main channel, update source, build / update, install an update from a file, installed builds, build log |
| About | Logs, system info, Add to Steam, developer options |

Display, Graphics and Gameplay edit the game's own `settings.ini` beside the
exe, in place: comments and keys the launcher doesn't know are kept. The keys
are the ones in `docs/SETTINGS.md`; a file from the first version (width,
height, fullscreen, widescreen) is read, and each old key is replaced by its
new one when that setting is saved. Q / E switch pages and Esc goes
back; on Windows a controller works too (LB / RB pages, D-pad, A, B).

Add to Steam puts the launcher in your Steam library as a non-Steam game
(close Steam first; the old `shortcuts.vdf` is backed up beside it).

Save profiles are passed to the game as `ANI_SAVE_DIR`; the default profile
is the game's own `%LOCALAPPDATA%\AnimaniacsRecompiled`.

## Update source

One setting on the Updates tab says where updates come from:

- **Blank**: the project's home on GitLab
  (`https://gitlab.com/unowa001/animaniacs-remastered`). Game versions are
  its `v*` tags (or `main`) and launcher updates its `launcher-v*` releases.
- **Another GitLab project**: `https://gitlab.com/<owner>/<project>` (or a
  self-hosted GitLab), the same way.
- **A GitHub repository**: `https://github.com/<owner>/<repo>`. Game versions
  are its releases (or `main`) and launcher updates its `launcher-v*` releases.
- **An update file**: an `https://` address or a path ending in `.json`, so
  updates can be hosted anywhere:

  ```json
  {
    "source": "https://codeberg.org/someone/AnimaniacsRecompiled.git",
    "launcher": {
      "version": "1.0.0",
      "url": "https://example.org/AnimaniacsLauncherSetup-1.0.0.exe",
      "sha256": "<sha256 of the installer>",
      "notes": "What changed",
      "page": "https://example.org/releases"
    }
  }
  ```

  `source` is where the game's source is fetched from; game versions are its
  `v*` tags and `main`. A launcher download that doesn't match `sha256` is
  thrown away. Both keys are optional.
- **Any git repository**: a git address (Codeberg, GitLab, a server), a
  folder with a checkout, or a `.bundle` file. Game versions are its `v*`
  tags and `main`; there are no launcher updates from it.

For an offline update, make a bundle with
`git bundle create AnimaniacsRecompiled-v1.0.0.bundle --all` (or
`main --tags`) and use "Install update from file". A bundle needs the
submodule (`tools/ngbrecomp`) from its own address on the first build.

## Mods

A mod is a folder, or a `.zip` of one, holding `mod.json` and a `files/`
folder laid out like the game folder:

```
my-mod/
  mod.json     {"id": "my-mod", "name": "My mod", "version": "1.0",
                "author": "you", "description": "What it changes"}
  files/
    resource/...   replaces or adds these game files
```

`id` is lower-case letters, digits, `-`, `_` or `.`. Installing a mod with
the same id again upgrades it. The Mods tab sets which mods are on and their
order; lower in the list wins when two mods replace the same file. Names
match without regard to case, as on the Xbox.

The game files are never changed. When any mod is on, Play starts the game
on `game-modded/`: the game files with the mods laid over them, made of hard
links where the drive allows and copies elsewhere, and remade only when the
mods or the game files change. `default.xbe` can't be replaced, because the
game is built from it. Mods that change the game's code are not supported
yet.

## Needed on the PC

- [Git for Windows](https://git-scm.com/download/win) (git, and the bash the
  build scripts run in)
- Python 3.10+

The launcher offers to install both with `winget`. It puts the build's Python
tools (capstone, cmake, ninja, pkgconf) in its own venv. Ghidra is optional
(function names in crash logs; set its folder in Settings).

A first build needs about 4 GB free on the launcher's drive (it uses about
1.5 GB for the toolchain, checkout and build tree) and an update about 2 GB;
the launcher checks before it starts. A build takes a few minutes, most of it
the first toolchain download. Every build writes its whole output to `logs/build-*.txt`, and a
failed build names that file.

Windows SmartScreen may warn about the installer because it is not code
signed: choose More info, then Run anyway.

## Where things go

`%LOCALAPPDATA%\AnimaniacsRecompiled\launcher` (`ANI_LAUNCHER_HOME` overrides):
`settings.json`, `game/` (extracted game), `mods/`, `game-modded/`, `source/` (checkout),
`windeps/` (toolchain), `pyenv/`, `builds/<version>/`, `logs/`.
Uninstalling removes that folder and keeps your saves.

## Releasing

On GitLab (`.gitlab-ci.yml`):

- Game: push a version tag (`v1.0.0`; `v1.1.0-rc1` for a pre-release). The
  pipeline publishes a release, and launchers on the Releases channel build
  that tag on their next update check.
- Launcher: bump `__version__` in `animaniacs_launcher/__init__.py` and push
  a `launcher-v<version>` tag. The pipeline builds the installer on a
  Windows runner, uploads it to the project's package registry and publishes
  a release linking it; installed launchers offer it as an update.

The `.github/workflows` files do the same on GitHub.

## Art

Everything on Home is drawn from scratch by `tools/make_art.py` (Pillow) into
`animaniacs_launcher/assets/ui`; nothing comes from the game. Rerun it after
changing the art. The display font is Luckiest Guy (Apache-2.0), loaded for
the launcher only.

## Tests

```bash
python -m pytest launcher/tests
```

The tests build small synthetic disc images, so no game files are needed.
