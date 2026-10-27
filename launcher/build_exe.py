"""Freeze the launcher into dist/AnimaniacsLauncher.exe, then (on Windows,
with Inno Setup installed) wrap it in dist/AnimaniacsLauncherSetup-<v>.exe.

    python -m pip install pyinstaller
    python launcher/build_exe.py
"""

import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from animaniacs_launcher import __version__  # noqa: E402


VERSION_FILE = """VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Animaniacs Recompiled'),
      StringStruct('FileDescription', 'Animaniacs Recompiled Launcher'),
      StringStruct('FileVersion', '{s}'),
      StringStruct('InternalName', 'AnimaniacsLauncher'),
      StringStruct('OriginalFilename', 'AnimaniacsLauncher.exe'),
      StringStruct('ProductName', 'Animaniacs Recompiled'),
      StringStruct('ProductVersion', '{s}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def write_version_file() -> str:
    """build/version_info.txt: the exe's Properties > Details, from
    __version__ padded to four numbers (0.2.0 -> 0.2.0.0)."""
    nums = [int(n) for n in re.findall(r"\d+", __version__)[:4]]
    nums += [0] * (4 - len(nums))
    path = os.path.join("build", "version_info.txt")
    os.makedirs("build", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(VERSION_FILE.format(v=tuple(nums), s=".".join(map(str, nums))))
    return path


def main() -> int:
    os.chdir(HERE)
    version_file = write_version_file()
    subprocess.check_call([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
        "--windowed", "--name", "AnimaniacsLauncher",
        "--icon", os.path.join("animaniacs_launcher", "assets", "icon.ico"),
        "--version-file", version_file,
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
