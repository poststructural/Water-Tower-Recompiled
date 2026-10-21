"""Read the running game's guest memory (bring-up aid).

    python scripts/guest_mem.py dump <out.bin> [lo hi]   (default the image data, 0x1E35A0..0x3862F8)
    python scripts/guest_mem.py diff <a.bin> <b.bin> [lo]   floats that changed

The guest window base is read from the run's log line
"xbox_MemoryLayoutInit: mapped ... at 0x...": pass it with ANI_MEM_BASE or the
script finds it in build-vk/vk_stderr.txt.
"""
import ctypes
import ctypes.wintypes as wt
import os
import re
import struct
import subprocess
import sys

LO, HI = 0x1E35A0, 0x3862F8


def base():
    if os.environ.get("ANI_MEM_BASE"):
        return int(os.environ["ANI_MEM_BASE"], 16)
    log = os.path.join(os.path.dirname(__file__), "..", "build-vk", "vk_stderr.txt")
    m = re.search(r"mapped \d+ KB at 0x([0-9A-Fa-f]+) \(offset", open(log, errors="replace").read())
    # The window is mapped at guest VA 0x10000 (the image base).
    return int(m.group(1), 16) - 0x10000


def pid():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Animaniacs.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return int(out.strip().split('","')[1])


def dump(path, lo=LO, hi=HI):
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wt.HANDLE
    h = k32.OpenProcess(0x0010 | 0x0400, False, pid())
    buf = (ctypes.c_char * (hi - lo))()
    got = ctypes.c_size_t()
    ok = k32.ReadProcessMemory(wt.HANDLE(h), ctypes.c_void_p(base() + lo), buf, hi - lo,
                               ctypes.byref(got))
    if not ok:
        raise SystemExit(f"ReadProcessMemory failed: {ctypes.get_last_error()}")
    open(path, "wb").write(buf.raw[:got.value])
    print(f"dumped {got.value} bytes from guest 0x{lo:08X}")


def diff(a, b, lo=LO):
    da, db = open(a, "rb").read(), open(b, "rb").read()
    for off in range(0, min(len(da), len(db)) - 3, 4):
        x, = struct.unpack_from("<f", da, off)
        y, = struct.unpack_from("<f", db, off)
        if x != y and abs(x) < 1e5 and abs(y) < 1e5 and (abs(x) > 1e-6 or abs(y) > 1e-6):
            print(f"0x{lo + off:08X}  {x:12.5f} -> {y:12.5f}")


if __name__ == "__main__":
    if sys.argv[1] == "dump":
        args = [int(v, 16) for v in sys.argv[3:5]]
        dump(sys.argv[2], *args)
    else:
        diff(sys.argv[2], sys.argv[3], *(int(v, 16) for v in sys.argv[4:5]))
