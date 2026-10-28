"""List and extract the game's .hog archives ("WART3.00").

Layout (from the loader at 0x00148220 and the reader at 0x00148800):
  0x00  "WART3.00"
  0x08  u32 entry count
  0x0C  u32 offset of the name table (NUL-separated, directories first)
  0x10  u32 size of the name table
  0x14  u32 where the file names start in the name table (directories first)
  0x18  entries, 24 bytes each: u32 offset, u32 stored size, u32 size,
        u32 name hash, u32 name (from the file names' start), u32 directory
        (a name-table offset).
A stored size below the size means the data is compressed, in blocks of up
to 128 KB: a u32 length, then RefPack (the decoder is 0x001480C0).

  python tools/hog/hog.py list game/resource/level1.hog
  python tools/hog/hog.py extract game/resource/level1.hog out/ [substring]
"""
import os
import struct
import sys


def refpack(src, size):
    out = bytearray()
    i = 0
    while i < len(src) and len(out) < size:
        b = src[i]
        if b < 0x80:
            b1 = src[i + 1]; i += 2
            lit, off, n = b & 3, ((b & 0x60) << 3) + b1 + 1, ((b >> 2) & 7) + 3
        elif b < 0xC0:
            b1, b2 = src[i + 1], src[i + 2]; i += 3
            lit, off, n = b1 >> 6, ((b1 & 0x3F) << 8) + b2 + 1, (b & 0x3F) + 4
        elif b < 0xE0:
            b1, b2, b3 = src[i + 1], src[i + 2], src[i + 3]; i += 4
            lit, off = b & 3, ((b & 0x10) << 12) + (b1 << 8) + b2 + 1
            n = b3 + ((b & 0x0C) << 6) + 5
        else:
            i += 1
            lit = ((b & 0x1F) << 2) + 4
            if lit > 0x70:
                lit = b & 3
                out += src[i:i + lit]
                break
            out += src[i:i + lit]; i += lit
            continue
        out += src[i:i + lit]; i += lit
        for _ in range(n):
            out.append(out[-off])
    return bytes(out)


def entries(d):
    assert d[:8] == b"WART3.00", "not a hog"
    count, names, _size, files = struct.unpack_from("<4I", d, 8)

    def name(o):
        return d[names + o:d.index(b"\0", names + o)].decode("latin1")

    for k in range(count):
        off, stored, size, _hash, nm, dr = struct.unpack_from("<6I", d, 0x18 + 24 * k)
        yield name(dr) + name(files + nm), off, stored, size


def read(d, off, stored, size):
    raw = d[off:off + stored]
    if stored >= size:
        return raw
    # Compressed in blocks of up to 128 KB, each a u32 length and RefPack.
    out, i = bytearray(), 0
    while len(out) < size and i + 4 <= len(raw):
        n = struct.unpack_from("<I", raw, i)[0]
        out += refpack(raw[i + 4:i + 4 + n], min(0x20000, size - len(out)))
        i += 4 + n
    return bytes(out)


def main(argv):
    d = open(argv[2], "rb").read()
    if argv[1] == "list":
        for nm, off, stored, size in entries(d):
            print(f"{size:10d} {stored:10d}  {nm}")
    elif argv[1] == "extract":
        sub = argv[4] if len(argv) > 4 else ""
        for nm, off, stored, size in entries(d):
            if sub not in nm:
                continue
            data = read(d, off, stored, size)
            path = os.path.join(argv[3], nm.replace("\\", "/"))
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            open(path, "wb").write(data)


if __name__ == "__main__":
    main(sys.argv)
