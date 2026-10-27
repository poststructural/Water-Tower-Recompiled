"""Save profiles and save backups.

The default profile is the game's own save folder, so existing saves stay
where they are. A named profile is <save folder>/profiles/<name>, handed to
the game as ANI_SAVE_DIR: its own saves, log.txt and (when the exe folder is
read-only) settings.ini.
"""

from __future__ import annotations

import os
import re
import time
import zipfile

from . import config

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,31}$")
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)),
             *(f"lpt{i}" for i in range(10))}


def valid_name(name: str) -> bool:
    return bool(_NAME.match(name)) and not name.endswith((" ", ".")) \
        and name.lower() not in _RESERVED


def root() -> str:
    return os.path.join(config.save_dir(), "profiles")


def folder(name: str) -> str:
    """The save folder of a profile ("" is the default profile)."""
    if not name:
        return config.save_dir()
    if not valid_name(name):
        raise ValueError(f"not a valid profile name: {name!r}")
    return os.path.join(root(), name)


def list_profiles() -> list[str]:
    try:
        return sorted((n for n in os.listdir(root())
                       if valid_name(n) and os.path.isdir(os.path.join(root(), n))),
                      key=str.lower)
    except OSError:
        return []


def create(name: str) -> str:
    if not valid_name(name):
        raise ValueError("Profile names are 1-32 letters, digits, spaces, '.', '_' or '-'")
    if name.lower() in (p.lower() for p in list_profiles()):
        raise ValueError(f"a profile named {name} already exists")
    d = folder(name)
    os.makedirs(d)
    return d


def env(name: str) -> dict[str, str]:
    return {"ANI_SAVE_DIR": folder(name)} if name else {}


def backup(name: str, dest_dir: str) -> str:
    """Zip a profile's saves (not its logs or other profiles) into dest_dir."""
    src = folder(name)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = os.path.join(dest_dir, f"Animaniacs-saves-{name or 'default'}-{stamp}.zip")
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for d, dirs, files in os.walk(src):
            if os.path.abspath(d) == os.path.abspath(src) and not name:
                dirs[:] = [x for x in dirs if x != "profiles"]
            for f in files:
                if f.lower() in ("log.txt",) or f.lower().endswith(".tmp"):
                    continue
                p = os.path.join(d, f)
                z.write(p, os.path.relpath(p, src))
                n += 1
    if not n:
        os.remove(out)
        raise ValueError("there are no saves in this profile yet")
    return out
