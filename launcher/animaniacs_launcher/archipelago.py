"""Archipelago: how Play starts a session, the .apworld, and the session state.

The client is inside the game (src/ap); the launcher only passes the room and
slot (--ap-server / --ap-slot; the password through ANI_AP_PASSWORD, so it
stays off the command line) and reads back the state file the game keeps
next to each seed's saves (<save dir>/archipelago/<seed>_<slot>/ap_state.json).
"""

from __future__ import annotations

import json
import os
import re
import zipfile
from dataclasses import dataclass

from . import config


class ApError(Exception):
    pass


def args(settings: config.Settings) -> tuple[list[str], dict[str, str]]:
    """Extra command-line arguments and environment for a session, or none."""
    if not settings.ap_enabled:
        return [], {}
    server, slot = settings.ap_server.strip(), settings.ap_slot.strip()
    if not server or not slot:
        raise ApError("Archipelago is on but the server or slot name is empty")
    env = {"ANI_AP_PASSWORD": settings.ap_password} if settings.ap_password else {}
    return ["--ap-server", server, "--ap-slot", slot], env


def world_source() -> str:
    """The world in the launcher's source checkout (the build's own version)."""
    return config.sub("source", "archipelago", "animaniacs")


def write_apworld(out_path: str, src: str | None = None) -> str:
    """Package the world as an .apworld (scripts/build_apworld.py does the same)."""
    src = src or world_source()
    if not os.path.isfile(os.path.join(src, "__init__.py")):
        raise ApError("no Archipelago world in the game's source yet: run Update first")
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for d, dirs, names in os.walk(src):
            dirs[:] = [x for x in dirs if x != "__pycache__"]
            for n in sorted(names):
                p = os.path.join(d, n)
                z.write(p, os.path.join("animaniacs", os.path.relpath(p, src)))
    return out_path


@dataclass
class Session:
    seed: str
    folder: str
    checks: int
    edgars: int
    items: int
    goal_edgars: int


def _slot_file(slot: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", slot)


def last_session(slot: str, save_dir: str | None = None) -> Session | None:
    """The seed this slot last played, as the game left it."""
    base = os.path.join(save_dir or config.save_dir(), "archipelago")
    name = _slot_file(slot.strip())
    try:
        with open(os.path.join(base, f"last_seed_{name}.txt"), encoding="utf-8") as f:
            seed = f.read().strip()
        folder = os.path.join(base, f"{re.sub(r'[^A-Za-z0-9_-]', '_', seed)}_{name}")
        with open(os.path.join(folder, "ap_state.json"), encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        return None
    items = st.get("items", [])
    edgar = 1095630849   # catalog.json edgar_item
    return Session(seed, folder, len(st.get("checked", [])), items.count(edgar), len(items),
                   int(st.get("edgars_required", 0)))
