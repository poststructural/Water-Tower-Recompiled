"""Where the launcher keeps things, and its settings file.

Everything lives under one data folder:

    %LOCALAPPDATA%\\AnimaniacsRecompiled\\launcher   (Windows)
    ~/.local/share/AnimaniacsRecompiled/launcher    (Linux, XDG_DATA_HOME)
    ~/Library/Application Support/AnimaniacsRecompiled/launcher  (macOS)

        settings.json
        game/        the extracted game, when it came from a disc image or zip
        mods/        installed mods, and mods.json (their order); see mods.py
        game-modded/ the game with the enabled mods' files laid over it
        source/      git checkout the game is built from
        windeps/     llvm-mingw and the CLANG64 libraries (shared by builds)
        pyenv/       Python venv with the build's Python tools
        builds/<v>/  each installed build; "current" names the one to play
        logs/

ANI_LAUNCHER_HOME overrides the data folder. Game saves stay where the game
puts them (%LOCALAPPDATA%\\AnimaniacsRecompiled).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field


def data_dir() -> str:
    env = os.environ.get("ANI_LAUNCHER_HOME")
    if env:
        return env
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "AnimaniacsRecompiled", "launcher")


def save_dir() -> str:
    """The game's own save folder (src/main_vk.c save_dir_path)."""
    if os.environ.get("ANI_SAVE_DIR"):
        return os.environ["ANI_SAVE_DIR"]
    if sys.platform == "win32":
        return os.path.join(os.environ.get("LOCALAPPDATA", ""), "AnimaniacsRecompiled")
    return os.path.join(os.path.expanduser("~"), ".local", "share", "AnimaniacsRecompiled")


@dataclass
class Settings:
    game_dir: str = ""
    # Where updates come from (updates.py): a GitLab or GitHub project, an
    # update file (.json), or any git address, folder or bundle. "" = the
    # project's home (HOME_URL, on GitLab).
    update_source: str = ""
    # "release": the newest version; "main": the newest commit on main.
    channel: str = "release"
    include_prereleases: bool = False
    current_build: str = ""
    # Builds kept besides the current one, for rolling back.
    keep_builds: int = 1
    show_console: bool = False
    close_on_play: bool = False
    # Save profile ("" = the game's own save folder); see profiles.py.
    profile: str = ""
    check_updates_on_start: bool = True
    # Optional: Ghidra 12 install and JDK 21, for function names in crash logs.
    ghidra_home: str = ""
    java_home: str = ""
    # Play an exe built elsewhere (a developer checkout) instead of a managed build.
    custom_exe: str = ""
    extra_env: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def path() -> str:
        return os.path.join(data_dir(), "settings.json")

    @classmethod
    def load(cls) -> "Settings":
        try:
            with open(cls.path(), encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            return cls()
        known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def save(self) -> None:
        os.makedirs(data_dir(), exist_ok=True)
        tmp = self.path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
        os.replace(tmp, self.path())


def sub(*parts: str) -> str:
    return os.path.join(data_dir(), *parts)
