#!/usr/bin/env bash
# Regenerate the recompiled C for Animaniacs: The Great Edgar Hunt (Xbox).
#
# Runs the xboxrecomp pipeline end to end against your own copy of the game:
#   parse -> disassemble (all code sections) -> Ghidra naming -> func_id
#   -> abi_analysis -> recomp into src/recomp/gen/
#
# Usage (Git Bash on Windows, or bash on Linux/macOS):
#   XBE=game/default.xbe scripts/regen.sh
#   TK=tools/ngbrecomp/xboxrecomp scripts/regen.sh   # for the Vulkan build (vk/)
#
# The generated code belongs to the toolkit that made it: regenerate when
# switching between the MSVC build (tools/xboxrecomp) and the Vulkan build.
#
# Env:
#   XBE          path to default.xbe (default: game/default.xbe)
#   GHIDRA_HOME  Ghidra 12.x install; Ghidra naming is skipped when unset
#   JAVA_HOME    64-bit JDK 21 for Ghidra
#   PY           python interpreter (default: python, or python3 off Windows)
#
# US and EU XBEs carry byte-identical code and data sections; either works.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# TK: the toolkit whose pipeline and runtime this build uses.
TK="${TK:-$ROOT/tools/xboxrecomp}"
XBE="${XBE:-$ROOT/game/default.xbe}"
XBE="$(cd "$(dirname "$XBE")" && pwd)/$(basename "$XBE")"
if command -v python >/dev/null 2>&1; then PY="${PY:-python}"; else PY="${PY:-python3}"; fi

[ -f "$XBE" ] || { echo "XBE not found: $XBE" >&2; exit 1; }
[ -f "$TK/tools/recomp/__main__.py" ] || [ -d "$TK/tools/recomp" ] || {
    echo "toolkit missing: run 'git submodule update --init'" >&2; exit 1; }

# Ghidra 12 dropped Jython; apply the Java export script if not yet applied.
if [ ! -f "$TK/tools/ghidra_naming/ghidra_scripts/ExportXbeNames.java" ]; then
    git -C "$TK" apply "$ROOT/patches/xboxrecomp-0001-ghidra12-java-export.patch"
fi

cd "$TK"
echo "== parse";  "$PY" -m tools.xbe_parser "$XBE" --json "$(dirname "$XBE")/animaniacs_analysis.json" >/dev/null
# Not --text-only: the D3D8/XGRAPH/XMV/DSOUND/XPP code is statically linked in
# its own sections and must be lifted too.
# config/seed_functions.json: entry points the detector misses, found at runtime.
echo "== disasm"; "$PY" -m tools.disasm "$XBE" --force \
    --seed-functions "$ROOT/config/seed_functions.json"
# Ghidra's export does not depend on the disassembly, so it is reused once it
# exists. FORCE_GHIDRA=1 re-runs the analysis.
GEXPORT=tools/ghidra_naming/export/functions.json
if [ -n "${GHIDRA_HOME:-}" ] && { [ ! -f "$GEXPORT" ] || [ "${FORCE_GHIDRA:-0}" = 1 ]; }; then
    echo "== ghidra analysis"
    XBE="$XBE" bash tools/ghidra_naming/run_ghidra.sh </dev/null
fi
if [ -f "$GEXPORT" ]; then
    echo "== ghidra naming"
    "$PY" tools/ghidra_naming/merge_names.py --apply
else
    echo "== ghidra naming skipped (set GHIDRA_HOME to run it)"
fi
# Recovered names that collide with host C runtime declarations (mingw).
"$PY" "$ROOT/scripts/apply_name_denylist.py" tools/disasm/output/functions.json \
    "$ROOT/config/name_denylist.txt"
echo "== func_id"; "$PY" -m tools.func_id "$XBE"
echo "== abi";     "$PY" -m tools.abi_analysis "$XBE"
echo "== recomp"
# recomp_types.h is the register model of the toolkit that generates the code,
# and the pipeline never overwrites an existing one: remove it so switching TK
# cannot pair one toolkit's header with the other's runtime.
rm -f "$ROOT"/src/recomp/gen/recomp_[0-9]*.c "$ROOT/src/recomp/gen/recomp_types.h"
"$PY" -m tools.recomp "$XBE" --all --split 250 \
    --game-name "Animaniacs: The Great Edgar Hunt" \
    --exclude-manual "$ROOT/src/recomp_manual.c" \
    --gen-dir "$ROOT/src/recomp/gen"
echo "done: $ROOT/src/recomp/gen"
