"""Command line: the GUI by default, plus the same steps as subcommands.

    AnimaniacsLauncher                     the launcher window
    AnimaniacsLauncher setup <iso|zip|dir> import your game files
    AnimaniacsLauncher check               check the game files and build tools
    AnimaniacsLauncher update [--main]     build the newest version
    AnimaniacsLauncher play                start the game
"""

from __future__ import annotations

import argparse
import sys

from . import __version__, build, config, gamefiles, play, updates


def _progress(done: int, total: int, name: str) -> None:
    pct = 100 * done // total if total else 100
    print(f"\r{pct:3d}%  {name[-60:]:<60}", end="", flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="AnimaniacsLauncher",
                                 description="Animaniacs: The Great Edgar Hunt recomp launcher")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("setup", help="import your game files (folder, .iso or .zip)")
    s.add_argument("source")
    s.add_argument("--copy", action="store_true", help="copy a folder instead of using it in place")
    sub.add_parser("check", help="check the game files and build tools")
    u = sub.add_parser("update", help="build the newest version")
    u.add_argument("--main", action="store_true", help="follow main instead of releases")
    u.add_argument("--force", action="store_true", help="rebuild even if up to date")
    sub.add_parser("play", help="start the game")
    args = ap.parse_args(argv)

    if not args.cmd:
        from . import gui
        return gui.run()

    st = config.Settings.load()
    try:
        if args.cmd == "setup":
            st.game_dir = gamefiles.import_game(args.source, config.sub("game"),
                                                copy_folder=args.copy, progress=_progress)
            st.save()
            print(f"\nGame files: {st.game_dir} ({gamefiles.check_dir(st.game_dir).summary()})")
        elif args.cmd == "check":
            chk = gamefiles.check_dir(st.game_dir) if st.game_dir else None
            print("Game files:", f"{st.game_dir}: {chk.summary()}" if chk else "not set up")
            tc = build.detect()
            print("Build tools:", "ready" if tc.ok else "missing " + ", ".join(tc.missing))
            print("Installed build:", st.current_build or st.custom_exe or "none")
            return 0 if chk and chk.ok and tc.ok else 1
        elif args.cmd == "update":
            v = updates.latest_game("main" if args.main else st.channel, st.include_prereleases)
            if v.name == st.current_build and not args.force:
                print(f"Up to date: {v.name}")
                return 0
            print(f"Building {v.name}" + (" (no releases yet, using main)" if v.fell_back else ""))
            build.build(v, st.game_dir, st, log=print)
            st.current_build = v.name
            st.save()
            build.prune(v.name, st.keep_builds)
        elif args.cmd == "play":
            p, log = play.launch(st)
            print(f"Started (log: {log})")
            return p.wait()
    except (ValueError, build.BuildError, updates.UpdateError, play.PlayError, OSError) as e:
        print(f"\nerror: {e}", file=sys.stderr)
        return 1
    return 0
