"""Freeze the launcher into dist/AnimaniacsLauncher.exe, then (on Windows,
with Inno Setup installed) wrap it in dist/AnimaniacsLauncherSetup-<v>.exe.

    python -m pip install pyinstaller
    python launcher/build_exe.py
"""

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from animaniacs_launcher import __version__  # noqa: E402


def main() -> int:
    os.chdir(HERE)
    subprocess.check_call([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
        "--windowed", "--name", "AnimaniacsLauncher", "run_launcher.py"])
    iscc = shutil.which("iscc") or r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if sys.platform == "win32" and os.path.isfile(iscc):
        subprocess.check_call([iscc, f"/DAppVersion={__version__}",
                               os.path.join("installer", "AnimaniacsLauncher.iss")])
    elif sys.platform == "win32":
        print("Inno Setup not found: built the launcher exe only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
