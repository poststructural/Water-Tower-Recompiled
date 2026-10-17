#!/usr/bin/env python3
"""Package archipelago/animaniacs into animaniacs.apworld (a zip Archipelago loads).

    python scripts/build_apworld.py [out_dir]     # default: build/
"""
import pathlib
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "archipelago" / "animaniacs"


def main() -> int:
    out_dir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "animaniacs.apworld"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(SRC.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                z.write(path, pathlib.Path("animaniacs") / path.relative_to(SRC))
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
