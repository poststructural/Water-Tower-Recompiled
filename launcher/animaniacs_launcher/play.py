"""Start the game."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

from . import build, config, mods, profiles


class PlayError(Exception):
    pass


def current_exe(settings: config.Settings) -> tuple[str, list[str]]:
    """(exe, extra DLL folders) of the build to play."""
    if settings.custom_exe:
        if not os.path.isfile(settings.custom_exe):
            raise PlayError(f"custom executable not found: {settings.custom_exe}")
        return settings.custom_exe, []
    if not settings.current_build:
        raise PlayError("no build installed yet: run Update first")
    d = config.sub("builds", settings.current_build)
    exe = os.path.join(d, build.EXE)
    if not os.path.isfile(exe):
        raise PlayError(f"build {settings.current_build} is missing its {build.EXE}")
    try:
        with open(os.path.join(d, "build.json"), encoding="utf-8") as f:
            dirs = json.load(f).get("dll_dirs", [])
    except (OSError, ValueError):
        dirs = []
    return exe, dirs or build.dll_dirs()


def launch(settings: config.Settings, game_dir: str | None = None) -> tuple[subprocess.Popen, str]:
    """Start the game; returns the process and the log file it writes to.
    game_dir: the folder to start it on, when not the game files themselves
    (mods.prepare)."""
    if not settings.game_dir:
        raise PlayError("no game files set up yet")
    if game_dir is None:
        try:
            game_dir = mods.prepare(settings.game_dir)
        except (mods.ModError, OSError) as e:
            raise PlayError(f"could not apply the mods: {e}")
    exe, dirs = current_exe(settings)
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([*dirs, env.get("PATH", "")])
    env.update(profiles.env(settings.profile))
    env.update(settings.extra_env)
    os.makedirs(config.sub("logs"), exist_ok=True)
    log_path = config.sub("logs", time.strftime("game-%Y%m%d-%H%M%S.txt"))
    _prune_logs(keep=10)
    log = open(log_path, "w", encoding="utf-8", errors="replace")
    if sys.platform == "win32" and settings.show_console:
        # The game's own console shows its log live.
        out, err, flags = None, None, subprocess.CREATE_NEW_CONSOLE
    else:
        out, err, flags = log, subprocess.STDOUT, 0
    try:
        p = subprocess.Popen([exe, game_dir], cwd=os.path.dirname(exe), env=env,
                             stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                             creationflags=flags)
    except OSError as e:
        log.close()
        raise PlayError(f"could not start the game: {e}")
    log.close()  # the child holds its own handle
    return p, log_path


def log_tail(path: str, lines: int = 25) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-lines:])
    except OSError:
        return ""


def system_info(settings: config.Settings) -> str:
    """Text for a bug report: versions, OS, build and settings.ini."""
    import platform

    from . import __version__, gamefiles, gamesettings
    lines = [f"Launcher: {__version__}",
             f"OS: {platform.platform()} ({platform.machine()})",
             f"Build: {settings.custom_exe or settings.current_build or 'none'}"]
    try:
        with open(config.sub("builds", settings.current_build, "build.json"), encoding="utf-8") as f:
            meta = json.load(f)
        lines.append(f"Commit: {meta.get('sha', '?')} ({meta.get('channel', '?')}, built {meta.get('built', '?')})")
    except (OSError, ValueError):
        pass
    if settings.game_dir:
        lines.append(f"Game files: {gamefiles.check_dir(settings.game_dir).summary()}")
    lines.append(f"Profile: {settings.profile or 'default'}")
    on = [f"{m.id} {m.version}".strip() for m in mods.load() if m.enabled]
    lines.append("Mods: " + (", ".join(on) if on else "none"))
    lines.append(f"Update source: {settings.update_source or 'default (GitLab)'}")
    try:
        exe, _ = current_exe(settings)
        ini = gamesettings.location(exe)
        with open(ini, encoding="utf-8", errors="replace") as f:
            body = [ln for ln in f.read().splitlines() if ln.strip() and not ln.lstrip().startswith((";", "#"))]
        lines.append("settings.ini:")
        lines += ["  " + ln for ln in body]
    except (OSError, PlayError):
        pass
    return "\n".join(lines) + "\n"


def _prune_logs(keep: int) -> None:
    d = config.sub("logs")
    logs = sorted((n for n in os.listdir(d) if n.startswith("game-")), reverse=True)
    for n in logs[keep:]:
        try:
            os.remove(os.path.join(d, n))
        except OSError:
            pass
