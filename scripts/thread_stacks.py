"""Print native call stacks of a running animaniacs_recomp.exe, by symbol.

Takes several snapshots and counts identical stacks per thread, so the
blocking or spinning call chain of each busy thread stands out.

    python scripts/thread_stacks.py [snapshots] [depth] [process-name]
"""
import collections
import ctypes
import ctypes.wintypes as wt
import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from sample_profile import (k32, dbg, SYMBOL_INFO, find_pid, threads_of,  # noqa: E402
                            THREAD_ALL, PROCESS_ALL)

CONTEXT_FULL = 0x0010000B
IMAGE_FILE_MACHINE_AMD64 = 0x8664


class ADDRESS64(ctypes.Structure):
    _fields_ = [("Offset", ctypes.c_uint64), ("Segment", wt.WORD), ("Mode", wt.DWORD)]


class STACKFRAME64(ctypes.Structure):
    _fields_ = [("AddrPC", ADDRESS64), ("AddrReturn", ADDRESS64),
                ("AddrFrame", ADDRESS64), ("AddrStack", ADDRESS64),
                ("AddrBStore", ADDRESS64), ("FuncTableEntry", ctypes.c_void_p),
                ("Params", ctypes.c_uint64 * 4), ("Far", wt.BOOL),
                ("Virtual", wt.BOOL), ("Reserved", ctypes.c_uint64 * 3),
                ("KdHelp", ctypes.c_byte * 160)]


def main():
    shots = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    depth = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    name = sys.argv[3] if len(sys.argv) > 3 else "animaniacs_recomp.exe"
    pid = find_pid(name)
    k32.OpenProcess.restype = wt.HANDLE
    k32.OpenThread.restype = wt.HANDLE
    hproc = k32.OpenProcess(PROCESS_ALL, False, pid)
    dbg.SymSetOptions(0x2 | 0x4)
    dbg.SymInitialize(wt.HANDLE(hproc), None, True)
    dbg.SymFunctionTableAccess64.restype = ctypes.c_void_p
    dbg.SymGetModuleBase64.restype = ctypes.c_uint64
    fta = ctypes.cast(dbg.SymFunctionTableAccess64, ctypes.c_void_p)
    gmb = ctypes.cast(dbg.SymGetModuleBase64, ctypes.c_void_p)
    sym = SYMBOL_INFO(SizeOfStruct=88, MaxNameLen=255)
    cache = {}

    def name_of(addr):
        if addr not in cache:
            disp = ctypes.c_uint64()
            cache[addr] = (sym.Name.decode() if dbg.SymFromAddr(
                wt.HANDLE(hproc), ctypes.c_uint64(addr), ctypes.byref(disp),
                ctypes.byref(sym)) else f"?{addr:x}")
        return cache[addr]

    handles = {tid: k32.OpenThread(THREAD_ALL, False, tid) for tid in threads_of(pid)}
    stacks = collections.defaultdict(collections.Counter)
    buf = (ctypes.c_byte * (1232 + 16))()
    base = (ctypes.addressof(buf) + 15) & ~15
    for _ in range(shots):
        for tid, h in handles.items():
            if not h or k32.SuspendThread(wt.HANDLE(h)) == 0xFFFFFFFF:
                continue
            try:
                ctypes.memset(base, 0, 1232)
                ctypes.c_uint32.from_address(base + 0x30).value = CONTEXT_FULL
                if not k32.GetThreadContext(wt.HANDLE(h), ctypes.c_void_p(base)):
                    continue
                rip = ctypes.c_uint64.from_address(base + 0xF8).value
                rsp = ctypes.c_uint64.from_address(base + 0x98).value
                rbp = ctypes.c_uint64.from_address(base + 0xA0).value
                sf = STACKFRAME64()
                sf.AddrPC = ADDRESS64(rip, 0, 3)
                sf.AddrStack = ADDRESS64(rsp, 0, 3)
                sf.AddrFrame = ADDRESS64(rbp, 0, 3)
                frames = []
                for _d in range(depth):
                    if not dbg.StackWalk64(IMAGE_FILE_MACHINE_AMD64, wt.HANDLE(hproc),
                                           wt.HANDLE(h), ctypes.byref(sf),
                                           ctypes.c_void_p(base), None, fta, gmb, None):
                        break
                    if not sf.AddrPC.Offset:
                        break
                    frames.append(name_of(sf.AddrPC.Offset))
                stacks[tid][" <- ".join(frames)] += 1
            finally:
                k32.ResumeThread(wt.HANDLE(h))
        time.sleep(0.05)
    for tid, ctr in stacks.items():
        top = ctr.most_common(3)
        if all(("WaitForMultiple" in s.split(" <- ")[0]) for s, _ in top):
            continue
        print(f"\n== thread {tid}")
        for s, c in top:
            print(f"  {c:3d}x {s}")


if __name__ == "__main__":
    main()
