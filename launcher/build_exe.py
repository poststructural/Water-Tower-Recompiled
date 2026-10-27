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
        "--windowed", "--name", "AnimaniacsLauncher",
        "--icon", os.path.join("animaniacs_launcher", "assets", "icon.ico"),
        "--add-data", os.pathsep.join([os.path.join("animaniacs_launcher", "assets")] * 2),
        "run_launcher.py"])
    # On PATH, or where Inno Setup installs for all users or (winget) just you.
    iscc = shutil.which("iscc") or next((
        p for p in (r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
                    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"))
        if os.path.isfile(p)), "")
    if sys.platform == "win32" and os.path.isfile(iscc):
        subprocess.check_call([iscc, f"/DAppVersion={__version__}",
                               os.path.join("installer", "AnimaniacsLauncher.iss")])
    elif sys.platform == "win32":
        print("Inno Setup not found: built the launcher exe only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
