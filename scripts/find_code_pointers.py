"""Find code addresses the function detector missed, from the disassembly.

Every immediate operand (push imm, mov reg/mem, imm) whose value lands on an
instruction boundary in a code section but is not a detected function start,
and is not inside a detected function, is almost always a callback the title
stores and later calls indirectly. Each one the runtime meets is an
"[ICALL] Failed to resolve" and a skipped call -- usually a crash soon after.

    python scripts/find_code_pointers.py <disasm output dir> <seeds.json>

Merges the finds into <seeds.json> (keeping its entries) and prints them.
"""
import bisect
import glob
import json
import os
import re
import sys

out_dir, seeds_path = sys.argv[1], sys.argv[2]
funcs = json.load(open(os.path.join(out_dir, "functions.json")))
starts = {int(f["start"], 16) for f in funcs}
spans = sorted((int(f["start"], 16), int(f["end"], 16)) for f in funcs)
span_starts = [s for s, _ in spans]


def inside_function(a):
    i = bisect.bisect_right(span_starts, a) - 1
    return i >= 0 and spans[i][0] < a < spans[i][1]


INSN = re.compile(r"\s+0x([0-9A-F]{8})\s+[0-9a-f]+\s+(\S+)\s*(.*)")
IMM = re.compile(r"(?:^|[ ,])0x([0-9a-f]{5,8})\b(?!\])")
boundaries, uses, prev_mnem = set(), {}, {}
for path in glob.glob(os.path.join(out_dir, "asm", "*.asm")):
    last = None
    for line in open(path, encoding="utf-8", errors="replace"):
        m = INSN.match(line)
        if not m:
            continue
        here = int(m.group(1), 16)
        boundaries.add(here)
        prev_mnem[here] = last
        mnem, ops = m.group(2), m.group(3).split(";")[0]
        last = mnem
        if mnem not in ("push", "mov"):
            continue
        if "[" in ops and mnem == "push":
            continue
        for v in IMM.findall(ops):
            uses.setdefault(int(v, 16), int(m.group(1), 16))

# Only where a function can begin: right after the previous one ends (a
# ret, an unconditional jmp, or int3/nop padding). Data the disassembler
# decoded as instructions -- the tables after a library's code -- fails this,
# and seeding it as a function would clamp the real function before it.
ENDERS = {"ret", "retn", "jmp", "int3", "nop"}
found = sorted(a for a in uses
               if a in boundaries and a not in starts and not inside_function(a)
               and prev_mnem.get(a) in ENDERS)
seeds = json.load(open(seeds_path)) if os.path.exists(seeds_path) else []
have = {int(s["start"], 16) for s in seeds}
added = 0
for a in found:
    if a not in have:
        seeds.append({"start": "0x%08X" % a,
                      "note": "address taken as an immediate at 0x%08X "
                              "(scripts/find_code_pointers.py)" % uses[a]})
        added += 1
json.dump(seeds, open(seeds_path, "w"), indent=2)
open(seeds_path, "a").write("\n")
print(f"{len(found)} code pointers outside detected functions, {added} new")
for a in found:
    print("  0x%08X  (used at 0x%08X)" % (a, uses[a]))
