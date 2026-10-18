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
; Delete this file to get the defaults back. Reference: docs/SETTINGS.md

[display]
; windowed, fullscreen (borderless, at the monitor's resolution) or exclusive
; F11 or Alt+Enter switches between windowed and fullscreen in game.
mode = windowed
; Window size: 1280x720, 1920x1080, 2560x1440, 3840x2160 ... or native
; (the monitor's resolution). Fullscreen always uses the monitor's.
resolution = 1920x1080
; Picture shape: 4:3 (original), 16:9, 16:10, 21:9, 32:9, or auto (the
; monitor's). Wider shapes show more of the world at the sides.
aspect = auto
; on (no tearing), off, or adaptive
vsync = on
; on shows the frame rate (F10 toggles it in game)
show_fps = off

[graphics]
; Internal resolution as a multiple of the console's 640x480, 1 to 8, or
; auto: enough for the output resolution (3 at 1080p, 4 at 1440p, 6 at 4K).
render_scale = auto
; Upper limit for auto, to keep slower GPUs at 60 fps
max_render_scale = 6
; Multisample anti-aliasing: 1 (off), 2, 4 or 8
msaa = 1
; smooth (filtered, mipmapped) or console (as the Xbox drew it)
texture_filter = smooth

[game]
; on skips the publisher logos and intro movie at start-up
skip_intro = off
"""


@dataclass(frozen=True)
class Option:
    section: str
    key: str
    default: str
    label: str


# What the launcher shows, with the game's defaults (docs/SETTINGS.md). This
# table and the choice lists below are the only places that know the keys.
OPTIONS = {o.section + "." + o.key: o for o in [
    Option("display", "mode", "windowed", "Mode"),
    Option("display", "resolution", "1920x1080", "Resolution"),
    Option("display", "aspect", "auto", "Aspect ratio"),
    Option("display", "vsync", "on", "V-sync"),
    Option("display", "show_fps", "off", "Show frame rate"),
    Option("graphics", "render_scale", "auto", "Internal resolution"),
    Option("graphics", "max_render_scale", "6", "Auto limit"),
    Option("graphics", "msaa", "1", "Anti-aliasing"),
    Option("graphics", "texture_filter", "smooth", "Texture filtering"),
    Option("game", "skip_intro", "off", "Skip intro logos and movie"),
]}

# Keys from the first settings.ini. The game still reads them, and whichever
# of an old and a new key comes last in the file wins, so a save that writes
# a new key removes its old one.
LEGACY = {
    "display.resolution": ("width", "height"),
    "display.mode": ("fullscreen",),
    "display.aspect": ("widescreen",),
}

# Choices for the launcher's drop-downs: (value, label).
MODES = [("windowed", "Windowed"), ("fullscreen", "Fullscreen (borderless, monitor resolution)")]
RESOLUTIONS = [
    ("1280x720", "1280 x 720  (720p)"), ("1600x900", "1600 x 900"),
    ("1920x1080", "1920 x 1080  (1080p)"), ("2560x1440", "2560 x 1440  (1440p)"),
    ("3840x2160", "3840 x 2160  (4K)"), ("2560x1080", "2560 x 1080  (ultrawide)"),
    ("3440x1440", "3440 x 1440  (ultrawide)"), ("native", "Native (monitor resolution)"),
]
ASPECTS = [("auto", "Auto (window or monitor shape)"), ("4:3", "4:3  (original)"),
           ("16:9", "16:9"), ("16:10", "16:10"), ("21:9", "21:9"), ("32:9", "32:9")]
VSYNC = [("on", "On"), ("adaptive", "Adaptive"), ("off", "Off")]
RENDER_SCALES = [("auto", "Auto (matches the output resolution)")] + [
    (str(n), f"{n}x  ({640 * n} x {480 * n})") for n in range(1, 9)]
MAX_SCALES = [(str(n), f"{n}x  ({640 * n} x {480 * n})") for n in range(1, 9)]
MSAA = [("1", "Off"), ("2", "2x MSAA"), ("4", "4x MSAA"), ("8", "8x MSAA")]
TEXTURE_FILTERS = [("smooth", "Smooth (filtered)"), ("console", "Console (as on Xbox)")]
SWITCHES = ("display.show_fps", "game.skip_intro")


def is_on(v: str) -> bool:
    return v.strip().lower() in ("1", "on", "true", "yes")


def auto_scale(width: int, height: int, limit: int = 6) -> int:
    """What render_scale = auto picks (src/settings.c): the smallest multiple
    of 640x480 that covers the picture on both axes, up to the limit."""
    s = max(-(-width // 640), -(-height // 480), 1)
    return min(s, max(1, limit))


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

    def remove(self, section: str, key: str) -> None:
        while True:
            i, _ = self._find(section, key)
            if i < 0:
                return
            del self.lines[i]

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


def _legacy(ini: IniFile, name: str) -> str | None:
    """A new key's value from the first version's keys, when only those exist."""
    if name == "display.resolution":
        w, h = ini.get("display", "width"), ini.get("display", "height")
        return f"{w}x{h}" if w and h and w.isdigit() and h.isdigit() else None
    if name == "display.mode":
        v = ini.get("display", "fullscreen")
        return None if v is None else ("windowed" if v.strip() in ("0", "") else "fullscreen")
    if name == "display.aspect":
        v = ini.get("display", "widescreen")
        return None if v is None else ("16:9" if is_on(v) else "4:3")
    return None


def value(ini: IniFile, name: str) -> str:
    """The value the launcher shows: the file's, in the launcher's spelling."""
    o = OPTIONS[name]
    v = ini.get(o.section, o.key)
    if v is None:
        v = _legacy(ini, name)
    if v is None:
        return o.default
    v = v.strip().lower()
    if name in SWITCHES:
        return "on" if is_on(v) else "off"
    if name == "display.vsync":
        return {"1": "on", "true": "on", "yes": "on", "0": "off", "false": "off",
                "no": "off", "2": "adaptive"}.get(v, v)
    if name == "display.mode" and v == "exclusive":
        return "fullscreen"
    return v


def apply(ini: IniFile, changes: dict[str, str]) -> None:
    for name, v in changes.items():
        o = OPTIONS[name]
        ini.set(o.section, o.key, v)
        for old in LEGACY.get(name, ()):
            ini.remove(o.section, old)
