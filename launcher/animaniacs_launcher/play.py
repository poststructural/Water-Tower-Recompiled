"""Start the game."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

from . import build, config


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


def launch(settings: config.Settings) -> tuple[subprocess.Popen, str]:
    """Start the game; returns the process and the log file it writes to."""
    if not settings.game_dir:
        raise PlayError("no game files set up yet")
    exe, dirs = current_exe(settings)
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([*dirs, env.get("PATH", "")])
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
        p = subprocess.Popen([exe, settings.game_dir], cwd=os.path.dirname(exe), env=env,
                             stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                             creationflags=flags)
    except OSError as e:
        log.close()
        raise PlayError(f"could not start the game: {e}")
    log.close()  # the child holds its own handle
    return p, log_path


def _prune_logs(keep: int) -> None:
    d = config.sub("logs")
    logs = sorted((n for n in os.listdir(d) if n.startswith("game-")), reverse=True)
    for n in logs[keep:]:
        try:
            os.remove(os.path.join(d, n))
        except OSError:
            pass
