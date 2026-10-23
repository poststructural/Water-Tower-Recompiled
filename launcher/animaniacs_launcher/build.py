"""Build a version of the game from source, against the player's own XBE.

The steps are the README's "Building the Vulkan version (Windows)", run in a
checkout the launcher owns:

    git checkout <version>              source/
    scripts/setup_vk.sh                 llvm-mingw + CLANG64 libs into windeps/
    TK=tools/ngbrecomp/xboxrecomp scripts/regen.sh    C from the player's XBE
    cmake -S vk -B build-vk -G Ninja ...
    ninja -C build-vk
    copy Animaniacs.exe into builds/<version>/

What a player needs installed: Git for Windows (git and the bash the scripts
run in) and Python 3.10+. The launcher puts the Python tools the build uses
(capstone, cmake, ninja, pkgconf) in its own venv.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Callable

from . import REPO, config

PY_TOOLS = ("capstone", "cmake", "ninja", "pkgconf")
TK = "tools/ngbrecomp/xboxrecomp"
EXE = "Animaniacs.exe" if sys.platform == "win32" else "Animaniacs"
SETTINGS_INI = "settings.ini"

Log = Callable[[str], None]


class BuildError(Exception):
    pass


class Cancelled(BuildError):
    pass


# ── Finding tools ────────────────────────────────────────────────────────


def _which(*names: str) -> str | None:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def find_git() -> str | None:
    p = _which("git")
    if p or sys.platform != "win32":
        return p
    for root in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("LOCALAPPDATA", "") + r"\Programs"):
        c = os.path.join(root, "Git", "cmd", "git.exe")
        if os.path.isfile(c):
            return c
    return None


def find_bash() -> str | None:
    """Git for Windows' bash on Windows (never WSL's System32 bash)."""
    if sys.platform != "win32":
        return _which("bash")
    git = find_git()
    if git:
        root = os.path.dirname(os.path.dirname(os.path.realpath(git)))
        for c in ("bin/bash.exe", "usr/bin/bash.exe"):
            p = os.path.join(root, c)
            if os.path.isfile(p):
                return p
    p = _which("bash")
    if p and "system32" not in p.lower():
        return p
    return None


def _python_version(cmd: list[str]) -> tuple[int, int] | None:
    try:
        out = subprocess.run(cmd + ["-c", "import sys;print(*sys.version_info[:2])"],
                             capture_output=True, text=True, timeout=20,
                             creationflags=_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        major, minor = map(int, out.stdout.split())
        return major, minor
    except ValueError:
        return None


def find_python() -> list[str] | None:
    """A Python 3.10+ to make the venv with. Not sys.executable: frozen, that
    is the launcher itself."""
    cands = []
    if sys.platform == "win32":
        if _which("py"):
            cands.append([_which("py"), "-3"])
        cands += [[p] for p in filter(None, [_which("python"), _which("python3")])]
    else:
        cands += [[p] for p in filter(None, [_which("python3"), _which("python")])]
    if not getattr(sys, "frozen", False):
        cands.insert(0, [sys.executable])
    for c in cands:
        v = _python_version(c)
        if v and v >= (3, 10):
            return c
    return None


_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def venv_python() -> str:
    d = config.sub("pyenv")
    return os.path.join(d, "Scripts", "python.exe") if sys.platform == "win32" \
        else os.path.join(d, "bin", "python")


def venv_bin() -> str:
    return os.path.dirname(venv_python())


def venv_tool(name: str) -> str:
    return os.path.join(venv_bin(), name + (".exe" if sys.platform == "win32" else ""))


def pkgconf_exe() -> str | None:
    """The pkgconf binary the pkgconf wheel ships (site-packages/pkgconf/.bin)."""
    root = config.sub("pyenv")
    for d, _, names in os.walk(root):
        if os.path.basename(d) == ".bin" and ("pkgconf.exe" in names or "pkgconf" in names):
            return os.path.join(d, "pkgconf.exe" if "pkgconf.exe" in names else "pkgconf")
    return None


@dataclass
class Toolchain:
    git: str | None
    bash: str | None
    python: list[str] | None
    pyenv_ready: bool
    missing: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing


def detect() -> Toolchain:
    git, bash, py = find_git(), find_bash(), find_python()
    ready = os.path.isfile(venv_python()) and os.path.isfile(config.sub("pyenv", ".tools-ok"))
    missing = []
    if not git:
        missing.append("Git for Windows" if sys.platform == "win32" else "git")
    if not bash:
        missing.append("bash (comes with Git for Windows)" if sys.platform == "win32" else "bash")
    if not py and not ready:
        missing.append("Python 3.10 or newer")
    return Toolchain(git, bash, py, ready, missing)


# winget package ids for what detect() can report missing.
WINGET = {"Git for Windows": "Git.Git", "Python 3.10 or newer": "Python.Python.3.12"}


def supported() -> str | None:
    """None when this OS can build the game, else why not."""
    if sys.platform == "win32":
        return None
    return ("Building the game is Windows-only for now (the Linux port comes next). "
            "You can still point the launcher at a build you made yourself.")


# ── Running steps ────────────────────────────────────────────────────────


class Runner:
    def __init__(self, log: Log, cancelled: Callable[[], bool] = lambda: False):
        self.log = log
        self.cancelled = cancelled

    def run(self, cmd: list[str], cwd: str | None = None, env: dict | None = None) -> None:
        if self.cancelled():
            raise Cancelled("cancelled")
        self.log(f"$ {' '.join(cmd)}")
        full_env = dict(os.environ)
        full_env.update(env or {})
        try:
            p = subprocess.Popen(cmd, cwd=cwd, env=full_env, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                 text=True, encoding="utf-8", errors="replace",
                                 bufsize=1, creationflags=_NO_WINDOW)
        except OSError as e:
            raise BuildError(f"could not start {cmd[0]}: {e}")
        assert p.stdout
        for line in p.stdout:
            self.log(line.rstrip("\n"))
            if self.cancelled():
                p.kill()
                p.wait()
                raise Cancelled("cancelled")
        if p.wait() != 0:
            raise BuildError(f"{os.path.basename(cmd[0])} failed (exit code {p.returncode})")


def _fwd(p: str) -> str:
    """Forward slashes: what the bash scripts and CMake want on Windows."""
    return p.replace("\\", "/")


# ── The build ────────────────────────────────────────────────────────────


def ensure_pyenv(r: Runner, tc: Toolchain) -> None:
    marker = config.sub("pyenv", ".tools-ok")
    if os.path.isfile(venv_python()) and os.path.isfile(marker):
        return
    if not tc.python:
        raise BuildError("Python 3.10 or newer is needed to build the game")
    r.log("== Python tools")
    if not os.path.isfile(venv_python()):
        r.run(tc.python + ["-m", "venv", config.sub("pyenv")])
    r.run([venv_python(), "-m", "pip", "install", "--disable-pip-version-check",
           "--upgrade", *PY_TOOLS])
    with open(marker, "w") as f:
        f.write(" ".join(PY_TOOLS))


def checkout(r: Runner, git: str, ref: str) -> str:
    src = config.sub("source")
    if not os.path.isdir(os.path.join(src, ".git")):
        r.log("== Downloading the source")
        shutil.rmtree(src, ignore_errors=True)
        r.run([git, "clone", f"https://github.com/{REPO}.git", src])
    r.log(f"== Checking out {ref}")
    r.run([git, "-C", src, "fetch", "--force", "--tags", "origin",
           "+refs/heads/main:refs/remotes/origin/main"])
    if ref.startswith("refs/tags/"):
        r.run([git, "-C", src, "fetch", "--force", "origin", f"+{ref}:{ref}"])
    # setup_vk.sh and regen.sh patch the submodules in place: put them back
    # the way git has them so the new version's patches apply cleanly.
    r.run([git, "-C", src, "submodule", "foreach", "--recursive",
           "git reset -q --hard && git clean -qfd"])
    r.run([git, "-C", src, "checkout", "--force", "--detach", ref])
    r.run([git, "-C", src, "submodule", "sync", "--recursive"])
    r.run([git, "-C", src, "submodule", "update", "--init", "--force", "tools/ngbrecomp"])
    return src


def build_env(game_dir: str, settings: config.Settings) -> dict[str, str]:
    env = {
        "PATH": venv_bin() + os.pathsep + os.environ.get("PATH", ""),
        "ANI_WIN_DEPS": _fwd(config.sub("windeps")),
        "TK": TK,
        "XBE": _fwd(os.path.join(game_dir, "default.xbe")),
        "PY": _fwd(venv_python()),
        # Git Bash: do not rewrite /-prefixed arguments into Windows paths.
        "MSYS_NO_PATHCONV": "1",
    }
    if settings.ghidra_home:
        env["GHIDRA_HOME"] = _fwd(settings.ghidra_home)
    if settings.java_home:
        env["JAVA_HOME"] = _fwd(settings.java_home)
    return env


def dll_dirs() -> list[str]:
    """Where the exe's DLLs (SDL2, glib, the C++ runtime) live."""
    deps = config.sub("windeps")
    dirs = [os.path.join(deps, "sysroot", "clang64", "bin")]
    if os.path.isdir(deps):
        for n in sorted(os.listdir(deps)):
            if n.startswith("llvm-mingw-") and os.path.isdir(os.path.join(deps, n)):
                dirs.append(os.path.join(deps, n, "x86_64-w64-mingw32", "bin"))
    return dirs


# Free space a build needs: the first one also downloads the toolchain and
# libraries and generates ~40 MB of C; later ones rebuild in place.
FIRST_BUILD_GB = 15
UPDATE_GB = 4


def check_space(path: str | None = None) -> None:
    root = path or config.data_dir()
    os.makedirs(root, exist_ok=True)
    first = not os.path.isdir(os.path.join(config.sub("windeps"), "sysroot"))
    need = FIRST_BUILD_GB if first else UPDATE_GB
    free = shutil.disk_usage(root).free / 1e9
    if free < need:
        raise BuildError(f"the build needs about {need} GB free on {os.path.splitdrive(root)[0] or root}; "
                         f"there are {free:.1f} GB")


def build_log_path(version) -> str:
    os.makedirs(config.sub("logs"), exist_ok=True)
    return config.sub("logs", time.strftime(f"build-{version.name}-%Y%m%d-%H%M%S.txt"))


def build(version, game_dir: str, settings: config.Settings, log: Log,
          cancelled: Callable[[], bool] = lambda: False,
          step: Callable[[str], None] = lambda s: None) -> str:
    """Build `version` (an updates.GameVersion) and install it. Returns the
    installed build's folder. The whole log also goes to logs/build-*.txt."""
    why = supported()
    if why:
        raise BuildError(why)
    tc = detect()
    if not tc.git or not tc.bash:
        raise BuildError("missing: " + ", ".join(tc.missing))
    check_space()
    path = build_log_path(version)
    with open(path, "w", encoding="utf-8", errors="replace") as f:
        def both(line: str) -> None:
            f.write(line + "\n")
            f.flush()
            log(line)
        both(f"== Building {version.name} ({version.sha}) from {game_dir}")
        try:
            return _build(version, game_dir, settings, both, cancelled, step, tc)
        except Cancelled:
            both("== cancelled")
            raise
        except BuildError as e:
            both(f"error: {e}")
            raise BuildError(f"{e} (full log: {path})") from e


def _build(version, game_dir: str, settings: config.Settings, log: Log,
           cancelled: Callable[[], bool], step: Callable[[str], None], tc: Toolchain) -> str:
    r = Runner(log, cancelled)
    started = time.time()

    step("Installing build tools")
    ensure_pyenv(r, tc)
    step("Downloading the source")
    src = checkout(r, tc.git, version.ref)
    env = build_env(game_dir, settings)
    bash = tc.bash

    step("Fetching compilers and libraries")
    r.log("== Compilers and libraries")
    r.run([bash, "scripts/setup_vk.sh"], cwd=src, env=env)

    step("Generating C from your default.xbe")
    r.log("== Recompiling the game binary")
    r.run([bash, "scripts/regen.sh"], cwd=src, env=env)

    step("Compiling")
    r.log("== Compiling")
    bdir = os.path.join(src, "build-vk")
    cfg = [venv_tool("cmake"), "-S", "vk", "-B", "build-vk", "-G", "Ninja",
           f"-DCMAKE_MAKE_PROGRAM={_fwd(venv_tool('ninja'))}",
           f"-DCMAKE_TOOLCHAIN_FILE={_fwd(os.path.join(src, 'cmake', 'toolchains', 'windows-llvm-mingw.cmake'))}",
           f"-DANI_WIN_DEPS={env['ANI_WIN_DEPS']}",
           f"-DANI_GUI={'OFF' if settings.show_console else 'ON'}"]
    pc = pkgconf_exe()
    if pc:
        cfg.append(f"-DPKG_CONFIG_EXECUTABLE={_fwd(pc)}")
    # vk/CMakeLists.txt copies the exe's DLLs beside it with a Python script.
    cfg.append(f"-DPython3_EXECUTABLE={_fwd(venv_python())}")
    r.run(cfg, cwd=src, env=env)
    r.run([venv_tool("ninja"), "-C", "build-vk"], cwd=src, env=env)

    step("Installing the build")
    exe = os.path.join(bdir, EXE)
    if not os.path.isfile(exe):
        raise BuildError(f"the build finished without producing {EXE}")
    dest = install(version, bdir, carry_from=settings.current_build)
    log(f"== Built {version.name} in {int(time.time() - started) // 60} min")
    return dest


def carry_settings(from_build: str, to_dir: str) -> None:
    """Copy the player's settings.ini (the game writes it beside the exe)
    from an installed build into another build's folder."""
    if not from_build:
        return
    ini = config.sub("builds", from_build, SETTINGS_INI)
    if os.path.isfile(ini) and os.path.abspath(os.path.dirname(ini)) != os.path.abspath(to_dir):
        shutil.copy2(ini, os.path.join(to_dir, SETTINGS_INI))


def install(version, bdir: str, carry_from: str = "") -> str:
    """Copy a finished build into builds/<version>, keeping the player's
    settings.ini from the build they were playing (carry_from)."""
    dest = config.sub("builds", version.name)
    tmp = dest + ".partial"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    for n in os.listdir(bdir):
        if n == EXE or n.lower().endswith((".pdb", ".dll")):
            shutil.copy2(os.path.join(bdir, n), tmp)
    carry_settings(carry_from, tmp)
    with open(os.path.join(tmp, "build.json"), "w", encoding="utf-8") as f:
        json.dump({"name": version.name, "sha": version.sha, "channel": version.channel,
                   "built": time.strftime("%Y-%m-%d %H:%M"), "dll_dirs": dll_dirs()}, f, indent=2)
    shutil.rmtree(dest, ignore_errors=True)
    os.replace(tmp, dest)
    return dest


# ── Installed builds ─────────────────────────────────────────────────────


def installed() -> list[dict]:
    """Installed builds, newest first."""
    root = config.sub("builds")
    out = []
    if os.path.isdir(root):
        for n in os.listdir(root):
            meta = os.path.join(root, n, "build.json")
            if os.path.isfile(meta):
                try:
                    with open(meta, encoding="utf-8") as f:
                        m = json.load(f)
                    m["path"] = os.path.join(root, n)
                    m["mtime"] = os.path.getmtime(meta)
                    out.append(m)
                except (OSError, ValueError):
                    pass
    out.sort(key=lambda m: m["mtime"], reverse=True)
    return out


def prune(current: str, keep: int) -> None:
    """Remove all but `current` and the `keep` newest other builds."""
    others = [b for b in installed() if b["name"] != current]
    for b in others[keep:]:
        shutil.rmtree(b["path"], ignore_errors=True)
