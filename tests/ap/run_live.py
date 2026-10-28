#!/usr/bin/env python3
"""Run the bridge against a real Archipelago server.

    python tests/ap/run_live.py build-aptest/test_ap \
        --archipelago ~/Archipelago [--python ~/Archipelago/venv/bin/python]

Builds animaniacs.apworld, generates a one-player seed with abilities
shuffled, hosts it with MultiServer on a free port, and runs test_ap's live,
offline (server stopped) and resume (server restarted) cases in order.
"""
import argparse
import os
import pathlib
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]

YAML = """name: Tester
game: "Animaniacs: The Great Edgar Hunt"
"Animaniacs: The Great Edgar Hunt":
  edgars_required: 10
  collectibles: every_one
  shuffle_abilities: true
  starting_siblings: start_with
"""

# Archipelago's scripts offer to pip-install missing requirements and wait on
# stdin; this runs them without that prompt.
LAUNCH = """import runpy, sys
sys.path.insert(0, sys.argv[1])
import ModuleUpdate
ModuleUpdate.update = lambda *a, **k: None
script = sys.argv[2]
sys.argv = [script] + sys.argv[3:]
runpy.run_path(script, run_name="__main__")
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("test_ap")
    ap.add_argument("--archipelago", required=True, type=pathlib.Path)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--no-scheme", action="store_true",
                    help="pass host:port, so the client tries wss:// before ws://")
    args = ap.parse_args()
    arch = args.archipelago.resolve()
    work = pathlib.Path(tempfile.mkdtemp(prefix="ani_ap_"))
    launch = work / "launch.py"
    launch.write_text(LAUNCH)
    (work / "players").mkdir()
    (work / "players" / "tester.yaml").write_text(YAML)
    worlds = arch / "custom_worlds"
    worlds.mkdir(exist_ok=True)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_apworld.py"), str(worlds)],
                   check=True)

    def run_ap(script, *extra, **kw):
        return subprocess.Popen([args.python, str(launch), str(arch), script, *extra],
                                cwd=arch, stdin=subprocess.DEVNULL, **kw)

    gen = run_ap("Generate.py", "--player_files_path", str(work / "players"),
                 "--outputpath", str(work / "out"))
    if gen.wait(300) != 0:
        print("generation failed", file=sys.stderr)
        return 1
    seed_zip = next((work / "out").glob("*.zip"))
    port = free_port()
    save = work / "save"
    addr = f"127.0.0.1:{port}" if args.no_scheme else f"ws://127.0.0.1:{port}"
    log = open(work / "server.log", "w")

    def start_server():
        p = run_ap("MultiServer.py", "--port", str(port), "--host", "127.0.0.1",
                   str(seed_zip), stdout=log, stderr=subprocess.STDOUT)
        for _ in range(200):
            try:
                socket.create_connection(("127.0.0.1", port), 0.2).close()
                return p
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("server did not start")

    def stop_server(p):
        if os.name == "nt":
            p.terminate()              # no SIGINT for a child on Windows
        else:
            p.send_signal(signal.SIGINT)   # MultiServer saves its .apsave on exit
        try:
            p.wait(20)
        except subprocess.TimeoutExpired:
            p.kill()

    def case(name):
        print(f"== {name}", flush=True)
        r = subprocess.run([args.test_ap, name, str(save), addr, "Tester"], timeout=120)
        if r.returncode:
            raise SystemExit(f"{name} failed (server log: {work / 'server.log'})")

    server = start_server()
    try:
        case("live")
    finally:
        stop_server(server)
    case("offline")
    server = start_server()
    try:
        case("resume")
    finally:
        stop_server(server)
    print("all live cases passed")
    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
