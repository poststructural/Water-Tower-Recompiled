"""Mods: files that replace or add to the game's own files.

A mod is a folder (or a .zip of one) with a mod.json and a files/ folder
laid out like the game folder:

    mod.json      {"id": "hd-textures", "name": "HD textures", "version": "1.0",
                   "author": "...", "description": "..."}
    files/        resource/..., movies/... as in the game folder

Installed mods live in mods/<id>/ under the launcher's data folder, and
mods.json there keeps their load order and which are on. When any mod is on,
Play starts the game on game-modded/: the game files with each enabled mod's
files laid over them in load order, so a later mod wins where two replace
the same file. The game files themselves are never changed. game-modded/ is
made of hard links where the drive allows (no extra space) and copies
elsewhere, and is only remade when the mods or the game files change.

default.xbe cannot be replaced: the game is built from it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass

from . import config

MANIFEST = "mod.json"
FILES = "files"
PROTECTED = {"default.xbe"}
_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")


class ModError(Exception):
    pass


@dataclass
class Mod:
    id: str
    name: str
    version: str = ""
    author: str = ""
    description: str = ""
    enabled: bool = True

    @property
    def path(self) -> str:
        return os.path.join(root(), self.id)

    def files(self) -> list[str]:
        """The game paths the mod provides, with "/" separators."""
        base = os.path.join(self.path, FILES)
        out = []
        for d, _, names in os.walk(base):
            for n in names:
                out.append(os.path.relpath(os.path.join(d, n), base).replace(os.sep, "/"))
        return sorted(out)


def root() -> str:
    return config.sub("mods")


def _order_path() -> str:
    return os.path.join(root(), "mods.json")


def _read_manifest(folder: str) -> dict:
    try:
        with open(os.path.join(folder, MANIFEST), encoding="utf-8") as f:
            data = json.load(f)
    except OSError:
        raise ModError(f"no {MANIFEST} in the mod")
    except ValueError:
        raise ModError(f"{MANIFEST} is not valid JSON")
    if not isinstance(data, dict):
        raise ModError(f"{MANIFEST} should hold a JSON object")
    mid = str(data.get("id", "")).strip().lower()
    if not _ID.match(mid):
        raise ModError(f"{MANIFEST} needs an \"id\" of lower-case letters, digits, '-', '_' or '.'")
    data["id"] = mid
    return data


def _mod(data: dict, enabled: bool) -> Mod:
    return Mod(data["id"], str(data.get("name") or data["id"]), str(data.get("version", "")),
               str(data.get("author", "")), str(data.get("description", "")), enabled)


def load() -> list[Mod]:
    """Installed mods in load order (first loads first, last wins)."""
    try:
        with open(_order_path(), encoding="utf-8") as f:
            order = json.load(f)
    except (OSError, ValueError):
        order = []
    state = {e["id"]: bool(e.get("enabled", True)) for e in order
             if isinstance(e, dict) and isinstance(e.get("id"), str)}
    ids = [e["id"] for e in order if isinstance(e, dict) and e.get("id") in state]
    if os.path.isdir(root()):
        for n in sorted(os.listdir(root())):
            if n not in ids and os.path.isfile(os.path.join(root(), n, MANIFEST)):
                ids.append(n)
    mods = []
    for mid in dict.fromkeys(ids):
        folder = os.path.join(root(), mid)
        try:
            data = _read_manifest(folder)
        except ModError:
            continue
        if data["id"] == mid:
            mods.append(_mod(data, state.get(mid, True)))
    return mods


def save(mods: list[Mod]) -> None:
    os.makedirs(root(), exist_ok=True)
    tmp = _order_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump([{"id": m.id, "enabled": m.enabled} for m in mods], f, indent=2)
    os.replace(tmp, _order_path())


def _safe(name: str) -> bool:
    parts = name.replace("\\", "/").split("/")
    return not (name.startswith(("/", "\\")) or ":" in name or ".." in parts)


def _find_mod_root(folder: str) -> str:
    if os.path.isfile(os.path.join(folder, MANIFEST)):
        return folder
    subs = [os.path.join(folder, n) for n in os.listdir(folder)
            if os.path.isdir(os.path.join(folder, n))]
    if len(subs) == 1 and os.path.isfile(os.path.join(subs[0], MANIFEST)):
        return subs[0]
    raise ModError(f"no {MANIFEST} found (at the top, or in the one folder inside)")


def install(path: str) -> Mod:
    """Install (or upgrade) a mod from a .zip or a folder."""
    os.makedirs(root(), exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root(), prefix=".install-") as tmp:
        if os.path.isdir(path):
            src = _find_mod_root(path)
        elif zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as z:
                for info in z.infolist():
                    if not _safe(info.filename):
                        raise ModError(f"unsafe path in the zip: {info.filename}")
                z.extractall(tmp)
            src = _find_mod_root(tmp)
        else:
            raise ModError("choose a mod's .zip or its folder")
        data = _read_manifest(src)
        files = os.path.join(src, FILES)
        if not os.path.isdir(files):
            raise ModError(f"the mod has no {FILES}/ folder")
        for n in os.listdir(files):
            if n.lower() in PROTECTED:
                raise ModError(f"mods cannot replace {n}: the game is built from it")
        staged = os.path.join(tmp, ".staged")
        shutil.copytree(src, staged)
        dest = os.path.join(root(), data["id"])
        mods = load()
        existing = next((m for m in mods if m.id == data["id"]), None)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        os.replace(staged, dest)
    mod = _mod(data, existing.enabled if existing else True)
    if existing:
        mods = [mod if m.id == mod.id else m for m in mods]
    else:
        mods.append(mod)
    save(mods)
    return mod


def remove(mod_id: str) -> None:
    mods = [m for m in load() if m.id != mod_id]
    shutil.rmtree(os.path.join(root(), mod_id), ignore_errors=True)
    save(mods)


def conflicts(mods: list[Mod]) -> dict[str, list[str]]:
    """{game path: [mod ids, in load order]} where enabled mods overlap."""
    seen: dict[str, list[str]] = {}
    for m in mods:
        if m.enabled:
            for f in m.files():
                seen.setdefault(f.lower(), []).append(m.id)
    return {f: ids for f, ids in seen.items() if len(ids) > 1}


def _place(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.lexists(dst):
        os.remove(dst)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _stamp(game_dir: str, mods: list[Mod]) -> dict:
    def tree(folder: str) -> list:
        out = []
        for d, _, names in os.walk(folder):
            for n in names:
                st = os.stat(os.path.join(d, n))
                out.append([os.path.relpath(os.path.join(d, n), folder), st.st_size,
                            int(st.st_mtime)])
        return sorted(out)
    return {"game": os.path.abspath(game_dir), "game_files": len(tree(game_dir)),
            "mods": [[m.id, m.version, tree(os.path.join(m.path, FILES))] for m in mods]}


def prepare(game_dir: str, mods: list[Mod] | None = None, log=print) -> str:
    """The folder to start the game on: game_dir itself when no mod is on,
    else game-modded/ with the enabled mods laid over the game files."""
    on = [m for m in (load() if mods is None else mods) if m.enabled]
    if not on:
        return game_dir
    out = config.sub("game-modded")
    stamp_path = os.path.join(out, ".launcher-mods.json")
    stamp = _stamp(game_dir, on)
    try:
        with open(stamp_path, encoding="utf-8") as f:
            if json.load(f) == stamp:
                return out
    except (OSError, ValueError):
        pass
    log("Applying mods: " + ", ".join(m.name for m in on))
    shutil.rmtree(out, ignore_errors=True)
    # Game paths by lower-case name: the Xbox's file system ignores case, so
    # a mod's Resource/X.bin replaces the game's resource/x.bin.
    paths: dict[str, str] = {}
    for d, _, names in os.walk(game_dir):
        for n in names:
            rel = os.path.relpath(os.path.join(d, n), game_dir)
            paths[rel.lower().replace(os.sep, "/")] = rel
            _place(os.path.join(d, n), os.path.join(out, rel))
    for m in on:
        base = os.path.join(m.path, FILES)
        for f in m.files():
            if f.lower() in PROTECTED:
                continue
            rel = paths.setdefault(f.lower(), f.replace("/", os.sep))
            _place(os.path.join(base, f.replace("/", os.sep)), os.path.join(out, rel))
    with open(stamp_path, "w", encoding="utf-8") as f:
        json.dump(stamp, f)
    return out
