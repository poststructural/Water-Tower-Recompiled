# Bring-up notes

## Region comparison (2026-10-17)

- US `default.xbe` (3,036,504 bytes) and EU `default.xbe` (3,039,232 bytes):
  all 12 section payloads byte-identical. Headers differ: the US header is
  flagged Debug and its TLS directory parses as garbage; the EU header is a
  clean Retail header. Entry point and kernel thunk decode to the same VAs
  (`0x0010A26A`, `0x001D25E0`).
- Every `.hog`, `.xmv`, `version.txt` (`A6.4a`) and `tkaXBoxDSPImage.bin` is
  byte-identical between the two dumps.
- Conclusion: one build, one recomp. EU XBE is the reference input.

## Binary facts

- Debug path: `c:\Animaniacs\Projects\AnimaniacsXBox\animaniacs\fullrelease\animaniacs.exe`
- XDK 5849. Statically linked, non-LTCG libs in named sections: D3D, XGRPH,
  XMV, D3DX, DSOUND, XPP, plus DOLBY (data). Disassemble without
  `--text-only` so those get lifted.
- `tkaXBoxDSPImage.bin` is a DSP image the game loads for the MCPX GP DSP
  (audio), relevant once audio bring-up starts.

## Pipeline results

| Step | Result |
|---|---|
| disasm (all code sections) | 6,284 functions: .text 4,518, XGRPH 678, DSOUND 434, D3D 272, XPP 195, D3DX 119, XMV 68 |
| Ghidra 12.1.4 FidDb naming | 391 names, 133 applied to function starts |
| func_id | mostly vtable/XDK-caller heuristics; 4,385 unclassified |
| abi_analysis | 6,284 entries, 30 thiscall |
| recomp | 26 chunks of 250 functions, ~39 MB of C |

Lifter flagged privileged/rare instructions (`lldt`, `ltr`, `sgdt`, `ljmp`,
`verr`, `outsw`, `int1`, `aam`) at a handful of sites, mostly in XAPI/kernel
style startup code; these become stubs and only matter if reached.

## Tooling notes

- Ghidra 12 ships no Jython, so the toolkit's `ExportXbeNames.py` fails.
  `patches/xboxrecomp-0001-ghidra12-java-export.patch` adds a Java port.
- The rea MCP server's Ghidra provider needs `GHIDRA_INSTALL_DIR` set and a
  64-bit JDK 21 as its Java; on this machine it currently resolves the
  32-bit Java 8 runtime, so rea's Ghidra-backed tools are unavailable until
  its environment is configured.
