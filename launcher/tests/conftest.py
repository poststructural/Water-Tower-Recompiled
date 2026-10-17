import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from animaniacs_launcher import gamefiles, xiso  # noqa: E402

SECTOR = xiso.SECTOR


def make_xbe(title_id=gamefiles.TITLE_ID, title="Animaniacs", region=4) -> bytes:
    base = 0x10000
    data = bytearray(0x1000)
    data[:4] = b"XBEH"
    struct.pack_into("<I", data, 0x104, base)
    struct.pack_into("<I", data, 0x118, base + 0x200)
    struct.pack_into("<I", data, 0x200 + 0x08, title_id)
    name = title.encode("utf-16-le")
    data[0x200 + 0x0C:0x200 + 0x0C + len(name)] = name
    struct.pack_into("<I", data, 0x200 + 0xA0, region)
    return bytes(data)


def game_tree(xbe=None) -> dict:
    """path -> bytes; a path ending in / is an empty directory."""
    return {
        "default.xbe": xbe or make_xbe(),
        "tkaXBoxDSPImage.bin": b"\x01" * 3000,
        "resource/level1.hog": os.urandom(5000),
        "resource/front.hog": b"hog" * 100,
        "movies/intro.xmv": os.urandom(SECTOR * 2 + 17),
        "version.txt": b"A6.4a",
    }


def make_xiso(files: dict, offset: int = 0) -> bytes:
    """A minimal XDVDFS image: each directory's entries chained through the
    right-subtree pointer."""
    # Build a nested dict.
    root: dict = {}
    for path, data in files.items():
        parts = path.split("/")
        d = root
        for p in parts[:-1]:
            d = d.setdefault(p, {})
        if parts[-1]:
            d[parts[-1]] = data

    DESC = xiso.DESCRIPTOR_SECTOR
    sectors: list[tuple[int, bytes]] = []
    next_sector = [DESC + 1]

    def alloc(data: bytes) -> int:
        start = next_sector[0]
        n = max(1, -(-len(data) // SECTOR))
        sectors.append((start, data))
        next_sector[0] += n
        return start

    def write_dir(d: dict) -> tuple[int, int]:
        items = sorted(d.items())
        placed = []
        for name, val in items:
            if isinstance(val, dict):
                s, size = write_dir(val)
                placed.append((name, s, size, 0x10))
            else:
                placed.append((name, alloc(val) if val else 0, len(val), 0x20))
        buf = bytearray()
        offs = []
        for name, *_ in placed:
            n = 14 + len(name)
            n += -n % 4
            offs.append(len(buf))
            buf += b"\0" * n
        for i, (name, s, size, attrs) in enumerate(placed):
            right = offs[i + 1] // 4 if i + 1 < len(placed) else 0
            struct.pack_into("<HHIIBB", buf, offs[i], 0, right, s, size, attrs, len(name))
            buf[offs[i] + 14:offs[i] + 14 + len(name)] = name.encode()
        buf += b"\xff" * (-len(buf) % SECTOR)
        return alloc(bytes(buf)), len(buf)

    root_sector, root_size = write_dir(root)
    img = bytearray(next_sector[0] * SECTOR)
    desc = bytearray(SECTOR)
    desc[:20] = xiso.MAGIC
    struct.pack_into("<II", desc, 20, root_sector, root_size)
    desc[0x7EC:0x800] = xiso.MAGIC
    img[DESC * SECTOR:(DESC + 1) * SECTOR] = desc
    for start, data in sectors:
        img[start * SECTOR:start * SECTOR + len(data)] = data
    return b"\0" * offset + bytes(img)


def write_tree(root: str, files: dict) -> None:
    for path, data in files.items():
        if path.endswith("/"):
            os.makedirs(os.path.join(root, path), exist_ok=True)
            continue
        p = os.path.join(root, *path.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)


@pytest.fixture(autouse=True)
def launcher_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("ANI_LAUNCHER_HOME", str(home))
    return home
