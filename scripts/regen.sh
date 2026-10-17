#!/usr/bin/env bash
# Regenerate the recompiled C for Animaniacs: The Great Edgar Hunt (Xbox).
#
# Runs the xboxrecomp pipeline end to end against your own copy of the game:
#   parse -> disassemble (all code sections) -> Ghidra naming -> func_id
#   -> abi_analysis -> recomp into src/recomp/gen/
#
# Usage (Git Bash on Windows, or bash on Linux/macOS):
#   XBE=game/default.xbe scripts/regen.sh
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
TK="$ROOT/tools/xboxrecomp"
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
echo "== disasm"; "$PY" -m tools.disasm "$XBE" --force
if [ -n "${GHIDRA_HOME:-}" ]; then
    echo "== ghidra naming"
    bash tools/ghidra_naming/run_ghidra.sh </dev/null
    "$PY" tools/ghidra_naming/merge_names.py --apply
else
    echo "== ghidra naming skipped (GHIDRA_HOME unset)"
fi
echo "== func_id"; "$PY" -m tools.func_id "$XBE"
echo "== abi";     "$PY" -m tools.abi_analysis "$XBE"
echo "== recomp"
rm -f "$ROOT"/src/recomp/gen/recomp_[0-9]*.c
"$PY" -m tools.recomp "$XBE" --all --split 250 \
    --game-name "Animaniacs: The Great Edgar Hunt" \
    --gen-dir "$ROOT/src/recomp/gen"
echo "done: $ROOT/src/recomp/gen"
