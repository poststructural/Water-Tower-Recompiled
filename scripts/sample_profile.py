"""Sample where a running animaniacs_recomp.exe spends its time.

Suspends each thread, reads its RIP, and resolves it through the PDB with
dbghelp. Generated functions are named after the guest function they lift
(sub_XXXXXXXX), so this is a guest-level CPU profile of a live run.

    python scripts/sample_profile.py [seconds] [process-name]
"""
import collections
import ctypes
import ctypes.wintypes as wt
import sys
import time

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
dbg = ctypes.WinDLL("dbghelp", use_last_error=True)

TH32CS_SNAPTHREAD = 0x4
THREAD_ALL = 0x0002 | 0x0008 | 0x0010 | 0x0040   # suspend, get ctx, query
PROCESS_ALL = 0x0400 | 0x0010                     # query, vm read
CONTEXT_CONTROL = 0x00100001


class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD),
                ("th32ThreadID", wt.DWORD), ("th32OwnerProcessID", wt.DWORD),
                ("tpBasePri", wt.LONG), ("tpDeltaPri", wt.LONG),
                ("dwFlags", wt.DWORD)]


class CONTEXT(ctypes.Structure):
    # Only the prefix up to Rip matters; pad the rest of the 1232-byte struct.
    _pack_ = 16
    _fields_ = [("P", ctypes.c_uint64 * 6), ("ContextFlags", wt.DWORD),
                ("MxCsr", wt.DWORD), ("Seg", wt.WORD * 6), ("EFlags", wt.DWORD),
                ("Dr", ctypes.c_uint64 * 6), ("Gpr", ctypes.c_uint64 * 16),
                ("Rip", ctypes.c_uint64), ("rest", ctypes.c_byte * 976)]


class SYMBOL_INFO(ctypes.Structure):
    _fields_ = [("SizeOfStruct", wt.ULONG), ("TypeIndex", wt.ULONG),
                ("Reserved", ctypes.c_uint64 * 2), ("Index", wt.ULONG),
                ("Size", wt.ULONG), ("ModBase", ctypes.c_uint64),
                ("Flags", wt.ULONG), ("Value", ctypes.c_uint64),
                ("Address", ctypes.c_uint64), ("Register", wt.ULONG),
                ("Scope", wt.ULONG), ("Tag", wt.ULONG), ("NameLen", wt.ULONG),
                ("MaxNameLen", wt.ULONG), ("Name", ctypes.c_char * 256)]


def find_pid(name):
    import subprocess
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV",
                          "/NH"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = line.strip('"').split('","')
        if len(parts) > 1 and parts[0].lower() == name.lower():
            return int(parts[1])
    raise SystemExit(f"{name} is not running")


def threads_of(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    te = THREADENTRY32(dwSize=ctypes.sizeof(THREADENTRY32))
    ok = k32.Thread32First(snap, ctypes.byref(te))
    while ok:
        if te.th32OwnerProcessID == pid:
            yield te.th32ThreadID
        ok = k32.Thread32Next(snap, ctypes.byref(te))
    k32.CloseHandle(snap)


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 10
    name = sys.argv[2] if len(sys.argv) > 2 else "animaniacs_recomp.exe"
    pid = find_pid(name)
    hproc = k32.OpenProcess(PROCESS_ALL, False, pid)
    dbg.SymSetOptions(0x2 | 0x4)  # undname, deferred loads
    if not dbg.SymInitialize(hproc, None, True):
        raise SystemExit("SymInitialize failed")
    k32.OpenThread.restype = wt.HANDLE
    handles = {tid: k32.OpenThread(THREAD_ALL, False, tid) for tid in threads_of(pid)}
    per_thread = collections.defaultdict(collections.Counter)
    total = collections.Counter()
    sym = SYMBOL_INFO(SizeOfStruct=88, MaxNameLen=255)  # sizeof(SYMBOL_INFO) on x64
    cache = {}
    end = time.time() + secs
    n = 0
    while time.time() < end:
        for tid, h in handles.items():
            if not h or k32.SuspendThread(h) == 0xFFFFFFFF:
                continue
            ctx = CONTEXT(ContextFlags=CONTEXT_CONTROL)
            got = k32.GetThreadContext(h, ctypes.byref(ctx))
            k32.ResumeThread(h)
            if not got:
                continue
            rip = ctx.Rip
            if rip not in cache:
                disp = ctypes.c_uint64()
                cache[rip] = (sym.Name.decode() if dbg.SymFromAddr(
                    hproc, ctypes.c_uint64(rip), ctypes.byref(disp), ctypes.byref(sym))
                    else f"?{rip:x}")
            per_thread[tid][cache[rip]] += 1
            total[cache[rip]] += 1
        n += 1
        time.sleep(0.002)
    print(f"{n} sampling rounds over {secs:.0f}s, {len(handles)} threads")
    print("\n== hottest overall")
    for s, c in total.most_common(25):
        print(f"{c:7d}  {s}")
    for tid, ctr in per_thread.items():
        busy = sum(c for s, c in ctr.items() if "Wait" not in s and "NtDelay" not in s)
        if busy < n * 0.2:
            continue
        print(f"\n== thread {tid}")
        for s, c in ctr.most_common(8):
            print(f"{c:7d}  {s}")


if __name__ == "__main__":
    main()
