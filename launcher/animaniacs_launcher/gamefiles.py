"""Find, check and import the player's own copy of the game.

The recompiled game reads its data from one directory (src/main_vk.c):
default.xbe, resource/ (.hog archives), movies/ (.xmv) and
tkaXBoxDSPImage.bin. The player can hand us that directory, a .zip of it, or
a disc image (XISO, trimmed or a full Redump dump).
"""

from __future__ import annotations

import os
import shutil
import struct
import zipfile
from dataclasses import dataclass, field
from typing import Callable

from . import xiso

TITLE_ID = 0x494F0003
REQUIRED = ("default.xbe", "resource/", "movies/", "tkaXBoxDSPImage.bin")

REGIONS = {1: "US", 2: "Japan", 4: "EU"}

Progress = Callable[[int, int, str], None]


@dataclass
class XbeInfo:
    title_id: int
    title: str
    region: str


@dataclass
class Check:
    ok: bool
    problems: list[str] = field(default_factory=list)
    xbe: XbeInfo | None = None

    def summary(self) -> str:
        if self.ok and self.xbe:
            return f"{self.xbe.title} ({self.xbe.region})"
        return "; ".join(self.problems)


def parse_xbe(data: bytes) -> XbeInfo:
    """Title id, title and region from an XBE header."""
    if len(data) < 0x178 or data[:4] != b"XBEH":
        raise ValueError("default.xbe is not an Xbox executable")
    base, = struct.unpack_from("<I", data, 0x104)
    cert_addr, = struct.unpack_from("<I", data, 0x118)
    cert = cert_addr - base
    if cert < 0 or cert + 0xA4 > len(data):
        raise ValueError("default.xbe has no readable certificate")
    title_id, = struct.unpack_from("<I", data, cert + 0x08)
    title = data[cert + 0x0C:cert + 0x5C].decode("utf-16-le", "replace").split("\0")[0]
    region_bits, = struct.unpack_from("<I", data, cert + 0xA0)
    regions = [n for bit, n in REGIONS.items() if region_bits & bit]
    return XbeInfo(title_id, title, "/".join(regions) or f"region {region_bits:#x}")


def check_dir(path: str) -> Check:
    """Is `path` a usable game directory?"""
    problems = []
    if not os.path.isdir(path):
        return Check(False, [f"{path} is not a folder"])
    for req in REQUIRED:
        p = os.path.join(path, req.rstrip("/"))
        if req.endswith("/") and not os.path.isdir(p):
            problems.append(f"missing folder {req}")
        elif not req.endswith("/") and not os.path.isfile(p):
            problems.append(f"missing {req}")
    info = None
    xbe = os.path.join(path, "default.xbe")
    if os.path.isfile(xbe):
        with open(xbe, "rb") as f:
            head = f.read(64 << 10)
        try:
            info = parse_xbe(head)
            if info.title_id != TITLE_ID:
                problems.append(
                    f"default.xbe is {info.title or 'another game'} "
                    f"(title id {info.title_id:08X}), not Animaniacs: The Great Edgar Hunt")
        except ValueError as e:
            problems.append(str(e))
    res = os.path.join(path, "resource")
    if os.path.isdir(res) and not any(n.lower().endswith(".hog") for n in os.listdir(res)):
        problems.append("resource/ has no .hog archives")
    return Check(not problems, problems, info)


def find_game_root(path: str) -> str | None:
    """The folder holding default.xbe: `path` itself or one level below it
    (zips and copied discs often wrap everything in a top folder)."""
    if os.path.isfile(os.path.join(path, "default.xbe")):
        return path
    try:
        subs = [os.path.join(path, n) for n in os.listdir(path)]
    except OSError:
        return None
    for s in subs:
        if os.path.isfile(os.path.join(s, "default.xbe")):
            return s
    return None


def source_kind(path: str) -> str:
    """'folder', 'iso', 'zip', or 'xbe' (the default.xbe inside a folder)."""
    if os.path.isdir(path):
        return "folder"
    low = path.lower()
    if low.endswith(".xbe"):
        return "xbe"
    if zipfile.is_zipfile(path):
        return "zip"
    if xiso.is_xiso(path):
        return "iso"
    raise ValueError(f"{os.path.basename(path)} is not a game folder, .zip or Xbox disc image "
                     "(.7z and .rar archives need extracting first)")


def _extract_zip(path: str, dest: str, progress: Progress | None,
                 cancelled: Callable[[], bool] | None) -> None:
    with zipfile.ZipFile(path) as z:
        members = [m for m in z.infolist() if not m.is_dir()]
        total = sum(m.file_size for m in members)
        done = 0
        root = os.path.realpath(dest)
        for m in members:
            out = os.path.realpath(os.path.join(dest, m.filename))
            if not out.startswith(root + os.sep):
                raise ValueError(f"refusing unsafe path in zip: {m.filename}")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with z.open(m) as src, open(out, "wb") as dst:
                while buf := src.read(4 << 20):
                    if cancelled and cancelled():
                        raise xiso.XisoError("cancelled")
                    dst.write(buf)
                    done += len(buf)
                    if progress:
                        progress(done, total, m.filename)


def _copy_tree(src: str, dest: str, progress: Progress | None,
               cancelled: Callable[[], bool] | None) -> None:
    files = []
    for d, _, names in os.walk(src):
        files += [os.path.join(d, n) for n in names]
    total = sum(os.path.getsize(p) for p in files)
    done = 0
    for p in files:
        rel = os.path.relpath(p, src)
        out = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(p, "rb") as i, open(out, "wb") as o:
            while buf := i.read(4 << 20):
                if cancelled and cancelled():
                    raise xiso.XisoError("cancelled")
                o.write(buf)
                done += len(buf)
                if progress:
                    progress(done, total, rel)


def import_game(source: str, dest: str, copy_folder: bool = False,
                progress: Progress | None = None,
                cancelled: Callable[[], bool] | None = None) -> str:
    """Make the game available and return the game directory to use.

    A folder is used where it is, unless copy_folder is set. A disc image or
    zip is extracted into `dest`. The result is checked before it is returned.
    """
    kind = source_kind(source)
    if kind == "xbe":
        source, kind = os.path.dirname(source), "folder"

    if kind == "folder" and not copy_folder:
        root = find_game_root(source) or source
        chk = check_dir(root)
        if not chk.ok:
            raise ValueError(chk.summary())
        return os.path.abspath(root)

    tmp = dest + ".partial"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    try:
        if kind == "iso":
            xiso.extract(source, tmp, progress, cancelled)
        elif kind == "zip":
            _extract_zip(source, tmp, progress, cancelled)
        else:
            _copy_tree(find_game_root(source) or source, tmp, progress, cancelled)
        root = find_game_root(tmp) or tmp
        chk = check_dir(root)
        if not chk.ok:
            raise ValueError(chk.summary())
        shutil.rmtree(dest, ignore_errors=True)
        os.replace(root, dest) if root != tmp else os.replace(tmp, dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return os.path.abspath(dest)
