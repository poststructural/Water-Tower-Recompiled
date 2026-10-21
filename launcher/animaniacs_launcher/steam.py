"""Add the launcher to Steam as a non-Steam game (Windows).

Steam keeps non-Steam shortcuts in userdata/<account>/config/shortcuts.vdf,
a binary KeyValues file. Each entry is kept byte for byte, fields the
launcher does not know included; only a new entry is appended. Steam
rewrites the file from memory while it runs, so it has to be closed first.
A backup of the old file is left beside it.

Binary KeyValues: a field is a type byte, a NUL-terminated key, then the
value: 0x00 a nested object (ended by 0x08), 0x01 a NUL-terminated string,
0x02 a 32-bit integer; 0x03 float, 0x04 pointer, 0x06 color (4 bytes) and
0x07 / 0x0A 64-bit values are carried through as raw bytes.
"""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
import time
import zlib
from dataclasses import dataclass, field

APP_NAME = "Animaniacs: The Great Edgar Hunt"

_SIZES = {2: 4, 3: 4, 4: 4, 6: 4, 7: 8, 10: 8}


class SteamError(Exception):
    pass


@dataclass
class Node:
    type: int
    key: str
    value: bytes = b""
    children: list["Node"] = field(default_factory=list)

    def get(self, key: str) -> str | None:
        for c in self.children:
            if c.key == key and c.type == 1:
                return c.value.decode("utf-8", "replace")
        return None


def _z(b: bytes, p: int) -> tuple[bytes, int]:
    end = b.find(b"\0", p)
    if end < 0:
        raise SteamError("truncated string in shortcuts.vdf")
    return b[p:end], end + 1


def _parse(b: bytes, p: int, depth: int) -> tuple[list[Node], int]:
    if depth > 32:
        raise SteamError("shortcuts.vdf nests too deep")
    nodes = []
    while p < len(b):
        t = b[p]
        p += 1
        if t == 8:
            return nodes, p
        key, p = _z(b, p)
        n = Node(t, key.decode("utf-8", "replace"))
        if t == 0:
            n.children, p = _parse(b, p, depth + 1)
        elif t == 1:
            n.value, p = _z(b, p)
        elif t in _SIZES and p + _SIZES[t] <= len(b):
            n.value, p = b[p:p + _SIZES[t]], p + _SIZES[t]
        else:
            raise SteamError(f"unsupported or truncated field type {t} in shortcuts.vdf")
        nodes.append(n)
    raise SteamError("shortcuts.vdf ends inside an object")


def read_vdf(data: bytes) -> list[Node]:
    if not data:
        return [Node(0, "shortcuts")]
    nodes, p = _parse(data, 0, 0)
    if p != len(data):
        raise SteamError("unexpected bytes after the end of shortcuts.vdf")
    return nodes


def write_vdf(nodes: list[Node]) -> bytes:
    out = bytearray()

    def emit(ns: list[Node]) -> None:
        for n in ns:
            key = n.key.encode("utf-8")
            if b"\0" in key:
                raise SteamError("NUL in a key")
            out.append(n.type)
            out.extend(key + b"\0")
            if n.type == 0:
                emit(n.children)
            elif n.type == 1:
                out.extend(n.value + b"\0")
            else:
                if len(n.value) != _SIZES.get(n.type, -1):
                    raise SteamError("bad field size")
                out.extend(n.value)
        out.append(8)

    emit(nodes)
    return bytes(out)


def shortcut_appid(exe: str, name: str = APP_NAME) -> int:
    """Steam's id for a non-Steam shortcut: CRC32 of the quoted exe and the
    name, with the top bit set."""
    return (zlib.crc32((exe + name).encode("utf-8")) & 0xFFFFFFFF) | 0x80000000


def append_shortcut(nodes: list[Node], exe_path: str, name: str = APP_NAME) -> bool:
    """Add a shortcut for exe_path; False when one is already there."""
    roots = [n for n in nodes if n.key.lower() == "shortcuts"]
    if len(roots) != 1 or roots[0].type != 0:
        raise SteamError("shortcuts.vdf has no single shortcuts list")
    root = roots[0]
    exe = f'"{os.path.abspath(exe_path)}"'
    start = f'"{os.path.dirname(os.path.abspath(exe_path))}"'
    used = set()
    for n in root.children:
        if (n.get("Exe") or n.get("exe")) == exe:
            return False
        if n.type != 0 or not n.key.isdigit():
            raise SteamError("unexpected entry in the shortcuts list")
        used.add(int(n.key))
    index = max(used) + 1 if used else 0

    def s(k, v):
        return Node(1, k, v.encode("utf-8"))

    def i(k, v):
        return Node(2, k, struct.pack("<I", v))

    root.children.append(Node(0, str(index), children=[
        i("appid", shortcut_appid(exe, name)), s("AppName", name), s("Exe", exe),
        s("StartDir", start), s("icon", os.path.abspath(exe_path)), s("ShortcutPath", ""),
        s("LaunchOptions", ""), i("IsHidden", 0), i("AllowDesktopConfig", 1),
        i("AllowOverlay", 1), i("OpenVR", 0), i("Devkit", 0), s("DevkitGameID", ""),
        i("DevkitOverrideAppID", 0), i("LastPlayTime", 0), s("FlatpakAppID", ""),
        Node(0, "tags", children=[s("0", "Recompiled")]),
    ]))
    return True


def _steam_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq steam.exe", "/NH"],
                             capture_output=True, text=True, timeout=15,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        raise SteamError("could not check whether Steam is running")
    return "steam.exe" in out.lower()


def steam_dir() -> str:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            return winreg.QueryValueEx(k, "SteamPath")[0]
    except OSError:
        raise SteamError("Steam is not installed for this Windows user")


def add_to_steam(exe_path: str, userdata: str | None = None) -> str:
    """Add exe_path to every Steam account on this PC; returns a summary."""
    if userdata is None:
        if sys.platform != "win32":
            raise SteamError("Add to Steam works on Windows")
        if _steam_running():
            raise SteamError("Close Steam first (Steam > Exit), then try again")
        userdata = os.path.join(steam_dir(), "userdata")
    if not os.path.isdir(userdata):
        raise SteamError("Steam has no accounts on this PC yet: sign in to Steam once first")
    added = present = 0
    for acct in sorted(os.listdir(userdata)):
        if not acct.isdigit() or not os.path.isdir(os.path.join(userdata, acct)):
            continue
        cfg = os.path.join(userdata, acct, "config")
        os.makedirs(cfg, exist_ok=True)
        path = os.path.join(cfg, "shortcuts.vdf")
        original = b""
        if os.path.isfile(path):
            with open(path, "rb") as f:
                original = f.read()
        nodes = read_vdf(original)
        if not append_shortcut(nodes, exe_path):
            present += 1
            continue
        data = write_vdf(nodes)
        read_vdf(data)  # what we write must read back
        if original:
            shutil.copy2(path, f"{path}.launcher-backup.{int(time.time())}")
        tmp = path + ".launcher-tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        added += 1
    if not added and not present:
        raise SteamError("Steam has no accounts on this PC yet: sign in to Steam once first")
    if not added:
        return "It is already in your Steam library."
    return "Added to your Steam library. Start Steam and look under Non-Steam games."
