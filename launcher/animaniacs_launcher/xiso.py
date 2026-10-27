"""Read and extract Xbox disc images (XISO / XDVDFS).

An XDVDFS volume starts with a 2 KB volume descriptor at sector 32, framed by
the magic "MICROSOFT*XBOX*MEDIA" at both ends. It points at the root
directory, and every directory is a binary tree of entries:

    u16 left   offset of the left subtree, in 4-byte units (0 = none)
    u16 right  offset of the right subtree, in 4-byte units (0 = none)
    u32 sector first sector of the file or directory
    u32 size   bytes
    u8  attrs  0x10 = directory
    u8  len    name length
    name       len bytes, then padding to a 4-byte boundary

An entry never crosses a sector; the slack is filled with 0xFF.

A trimmed "game partition" image has the volume at offset 0. A full Redump
dump carries the video partition first, so the volume sits further in.
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field
from typing import BinaryIO, Callable, Iterator

SECTOR = 2048
MAGIC = b"MICROSOFT*XBOX*MEDIA"
DESCRIPTOR_SECTOR = 32
ATTR_DIRECTORY = 0x10

# Where the game partition starts: trimmed XISO, then the Redump layouts of
# XGD1, XGD2 and XGD3 discs.
PARTITION_OFFSETS = (0x0, 0x18300000, 0x0FD90000, 0x02080000)


class XisoError(Exception):
    pass


@dataclass
class Entry:
    name: str
    sector: int
    size: int
    is_dir: bool
    children: list["Entry"] = field(default_factory=list)


def find_partition(f: BinaryIO) -> int:
    """Byte offset of the XDVDFS volume in an image, or raise XisoError."""
    for base in PARTITION_OFFSETS:
        f.seek(base + DESCRIPTOR_SECTOR * SECTOR)
        head = f.read(SECTOR)
        if len(head) == SECTOR and head.startswith(MAGIC) and head[0x7EC:0x800] == MAGIC:
            return base
    raise XisoError("not an Xbox disc image (no XDVDFS volume found)")


def _safe_name(raw: bytes) -> str:
    name = raw.decode("latin-1")
    if not name or name in (".", "..") or any(c in name for c in '/\\:\0'):
        raise XisoError(f"refusing unsafe file name in image: {name!r}")
    return name


def _read_dir(f: BinaryIO, base: int, sector: int, size: int, depth: int) -> list[Entry]:
    if size == 0:
        return []
    if depth > 64:
        raise XisoError("directory nesting too deep")
    f.seek(base + sector * SECTOR)
    data = f.read(size)
    if len(data) < size:
        raise XisoError("image is truncated")

    entries: list[Entry] = []
    seen: set[int] = set()
    stack = [0]
    while stack:
        off = stack.pop()
        if off in seen or off + 14 > len(data):
            continue
        seen.add(off)
        left, right, start, length, attrs, nlen = struct.unpack_from("<HHIIBB", data, off)
        if left == 0xFFFF and right == 0xFFFF:
            continue  # sector slack
        name = _safe_name(data[off + 14:off + 14 + nlen])
        is_dir = bool(attrs & ATTR_DIRECTORY)
        e = Entry(name, start, length, is_dir)
        if is_dir:
            e.children = _read_dir(f, base, start, length, depth + 1)
        entries.append(e)
        if left:
            stack.append(left * 4)
        if right:
            stack.append(right * 4)
    entries.sort(key=lambda e: e.name.lower())
    return entries


def read_tree(f: BinaryIO) -> tuple[int, list[Entry]]:
    """(partition offset, root entries) of an opened image."""
    base = find_partition(f)
    f.seek(base + DESCRIPTOR_SECTOR * SECTOR + len(MAGIC))
    root_sector, root_size = struct.unpack("<II", f.read(8))
    return base, _read_dir(f, base, root_sector, root_size, 0)


def walk(entries: list[Entry], prefix: str = "") -> Iterator[tuple[str, Entry]]:
    for e in entries:
        path = f"{prefix}{e.name}"
        yield path, e
        if e.is_dir:
            yield from walk(e.children, path + "/")


def total_size(entries: list[Entry]) -> int:
    return sum(e.size for _, e in walk(entries) if not e.is_dir)


def is_xiso(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            find_partition(f)
        return True
    except (OSError, XisoError):
        return False


def list_files(path: str) -> list[str]:
    with open(path, "rb") as f:
        _, root = read_tree(f)
    return [p + ("/" if e.is_dir else "") for p, e in walk(root)]


def extract(path: str, dest: str,
            progress: Callable[[int, int, str], None] | None = None,
            cancelled: Callable[[], bool] | None = None) -> int:
    """Extract every file of the image at `path` into `dest`.

    progress(done_bytes, total_bytes, current_file) is called as data is
    copied. Returns the number of bytes written.
    """
    chunk = 4 << 20
    with open(path, "rb") as f:
        base, root = read_tree(f)
        total = total_size(root)
        done = 0
        os.makedirs(dest, exist_ok=True)
        for rel, e in walk(root):
            out = os.path.join(dest, *rel.split("/"))
            if e.is_dir:
                os.makedirs(out, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(out), exist_ok=True)
            f.seek(base + e.sector * SECTOR)
            left = e.size
            with open(out, "wb") as o:
                while left:
                    if cancelled and cancelled():
                        raise XisoError("cancelled")
                    buf = f.read(min(chunk, left))
                    if not buf:
                        raise XisoError(f"image is truncated inside {rel}")
                    o.write(buf)
                    left -= len(buf)
                    done += len(buf)
                    if progress:
                        progress(done, total, rel)
            if progress and e.size == 0:
                progress(done, total, rel)
        return done
