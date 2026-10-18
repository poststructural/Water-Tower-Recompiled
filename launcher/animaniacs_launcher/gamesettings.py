"""The game's settings.ini, read and written the way src/settings.c reads it.

The game reads settings.ini beside its exe (or, when that folder is not
writable, in the save folder), and writes a commented default file on first
run. The launcher edits that same file in place: it changes only the values
it shows, and keeps every comment, blank line and key it does not know, so
options the game gains later survive a save from an older launcher.

Format (src/settings.c): "[section]" lines, "key = value" lines, and
comments starting with ";" or "#".
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from . import config

FILENAME = "settings.ini"

# The game's defaults (src/settings.c DEFAULT_INI); used when there is no
# file yet and the source checkout is not around to read them from.
FALLBACK_TEMPLATE = """\
; Animaniacs: The Great Edgar Hunt (static recompilation) settings.
; Delete this file to get the defaults back.

[display]
; Window size in pixels at start-up (F11 or Alt+Enter toggles fullscreen).
width = 1280
height = 960
; 0 windowed, 1 fullscreen, 2 borderless fullscreen
fullscreen = 0
; 1 sync to the display (no tearing), 0 off, 2 adaptive
vsync = 1
; 1 shows the frame rate (F10 toggles it in game)
show_fps = 0

[graphics]
; Internal render resolution: 1 is the console's 640x480, 2 is 1280x960, up to 4
render_scale = 2
; Multisample anti-aliasing: 1 (off), 2, 4 or 8
msaa = 1
; smooth (filtered, mipmapped) or console (as the Xbox drew it)
texture_filter = smooth

[game]
; 1 skips the publisher logos and intro movie at start-up
skip_intro = 0
"""


@dataclass(frozen=True)
class Option:
    section: str
    key: str
    default: str
    label: str


# What the launcher shows, with the game's defaults.
OPTIONS = {o.section + "." + o.key: o for o in [
    Option("display", "width", "1280", "Width"),
    Option("display", "height", "960", "Height"),
    Option("display", "fullscreen", "0", "Window mode"),
    Option("display", "vsync", "1", "V-sync"),
    Option("display", "widescreen", "0", "Widescreen (16:9)"),
    Option("display", "show_fps", "0", "Show frame rate"),
    Option("graphics", "render_scale", "2", "Internal resolution"),
    Option("graphics", "msaa", "1", "Anti-aliasing"),
    Option("graphics", "texture_filter", "smooth", "Texture filtering"),
    Option("game", "skip_intro", "0", "Skip intro logos and movie"),
]}

# Choices for the launcher's drop-downs: (value, label).
WINDOW_MODES = [("0", "Windowed"), ("1", "Fullscreen"), ("2", "Borderless fullscreen")]
VSYNC = [("1", "On"), ("2", "Adaptive"), ("0", "Off")]
RENDER_SCALES = [("1", "1x  (640 x 480, original)"), ("2", "2x  (1280 x 960)"),
                 ("3", "3x  (1920 x 1440)"), ("4", "4x  (2560 x 1920)")]
MSAA = [("1", "Off"), ("2", "2x MSAA"), ("4", "4x MSAA"), ("8", "8x MSAA")]
TEXTURE_FILTERS = [("smooth", "Smooth (filtered)"), ("console", "Console (as on Xbox)")]
# (width, height, widescreen, label); widescreen sizes turn on the Hor+ view.
RESOLUTIONS = [
    (1280, 960, False, "1280 x 960  (4:3, original)"),
    (1440, 1080, False, "1440 x 1080  (4:3)"),
    (1920, 1440, False, "1920 x 1440  (4:3)"),
    (1280, 720, True, "1280 x 720  (16:9)"),
    (1920, 1080, True, "1920 x 1080  (16:9)"),
    (2560, 1440, True, "2560 x 1440  (16:9)"),
    (3840, 2160, True, "3840 x 2160  (16:9)"),
]

_SECTION = re.compile(r"^\s*\[([^\]]*)\]\s*$")
_KEY = re.compile(r"^(\s*)([^=;#\s][^=]*?)(\s*=\s*)(.*?)(\s*)$")


class IniFile:
    """A settings.ini kept as its lines, so a save changes only values."""

    def __init__(self, text: str = ""):
        self.lines = text.splitlines()

    @classmethod
    def load(cls, path: str) -> "IniFile":
        with open(path, encoding="utf-8", errors="replace") as f:
            return cls(f.read())

    def _find(self, section: str, key: str) -> tuple[int, int]:
        """(index of the key's line or -1, index after the section's last
        line or -1 when the section is missing)."""
        current, end, found = "", -1, -1
        for i, line in enumerate(self.lines):
            m = _SECTION.match(line)
            if m:
                current = m.group(1).strip()
                if current == section:
                    end = i + 1
                continue
            if current != section:
                continue
            if line.strip() and not line.lstrip().startswith((";", "#")):
                end = i + 1
            km = _KEY.match(line)
            if km and km.group(2).strip() == key:
                found = i
        return found, end

    def get(self, section: str, key: str, default: str | None = None) -> str | None:
        i, _ = self._find(section, key)
        if i < 0:
            return default
        return _KEY.match(self.lines[i]).group(4)

    def set(self, section: str, key: str, value: str) -> None:
        i, end = self._find(section, key)
        if i >= 0:
            m = _KEY.match(self.lines[i])
            self.lines[i] = f"{m.group(1)}{m.group(2)}{m.group(3)}{value}"
            return
        if end < 0:
            if self.lines and self.lines[-1].strip():
                self.lines.append("")
            self.lines += [f"[{section}]", f"{key} = {value}"]
        else:
            self.lines.insert(end, f"{key} = {value}")

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"

    def save(self, path: str) -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\r\n" if os.name == "nt" else "\n") as f:
            f.write(self.text())
        os.replace(tmp, path)


def template_from_source(src: str | None = None) -> str | None:
    """DEFAULT_INI from src/settings.c in the launcher's checkout, so a new
    file has the comments and keys of the version being played."""
    path = os.path.join(src or config.sub("source"), "src", "settings.c")
    try:
        with open(path, encoding="utf-8") as f:
            c = f.read()
    except OSError:
        return None
    m = re.search(r"DEFAULT_INI\[\]\s*=\s*((?:\s*\"(?:[^\"\\]|\\.)*\")+)\s*;", c)
    if not m:
        return None
    parts = re.findall(r"\"((?:[^\"\\]|\\.)*)\"", m.group(1))
    text = "".join(parts)
    return text.encode("latin-1", "backslashreplace").decode("unicode_escape")


def location(exe: str) -> str:
    """Where the game reads settings.ini for this exe: beside it, or the save
    folder when the game would find that one instead (read-only exe folder)."""
    beside = os.path.join(os.path.dirname(exe), FILENAME)
    if os.path.isfile(beside) or os.access(os.path.dirname(exe) or ".", os.W_OK):
        return beside
    return os.path.join(config.save_dir(), FILENAME)


def load(path: str) -> IniFile:
    if os.path.isfile(path):
        return IniFile.load(path)
    return IniFile(template_from_source() or FALLBACK_TEMPLATE)


def value(ini: IniFile, name: str) -> str:
    o = OPTIONS[name]
    return ini.get(o.section, o.key, o.default)


def apply(ini: IniFile, changes: dict[str, str]) -> None:
    for name, v in changes.items():
        o = OPTIONS[name]
        ini.set(o.section, o.key, v)
