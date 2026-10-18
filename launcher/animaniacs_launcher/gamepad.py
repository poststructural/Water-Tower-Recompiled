"""Controller navigation for the launcher window (Windows, XInput).

Polls the first connected pad and turns presses into launcher actions:
D-pad / left stick = move focus, A = activate, B = back, LB/RB = previous /
next tab. Elsewhere, or with no XInput DLL, it does nothing.
"""

from __future__ import annotations

import ctypes
import sys

UP, DOWN, LEFT, RIGHT = 0x0001, 0x0002, 0x0004, 0x0008
LB, RB, A, B = 0x0100, 0x0200, 0x1000, 0x2000
_STICK = 16000


class _Gamepad(ctypes.Structure):
    _fields_ = [("wButtons", ctypes.c_ushort), ("bLeftTrigger", ctypes.c_ubyte),
                ("bRightTrigger", ctypes.c_ubyte), ("sThumbLX", ctypes.c_short),
                ("sThumbLY", ctypes.c_short), ("sThumbRX", ctypes.c_short),
                ("sThumbRY", ctypes.c_short)]


class _State(ctypes.Structure):
    _fields_ = [("dwPacketNumber", ctypes.c_uint), ("Gamepad", _Gamepad)]


class Pad:
    def __init__(self):
        self.dll = None
        self.prev = 0
        if sys.platform == "win32":
            for name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
                try:
                    self.dll = ctypes.WinDLL(name)
                    break
                except OSError:
                    pass

    def buttons(self) -> int:
        """Buttons held now on the first connected pad (stick folded into the D-pad)."""
        if not self.dll:
            return 0
        st = _State()
        for i in range(4):
            if self.dll.XInputGetState(i, ctypes.byref(st)) == 0:
                g = st.Gamepad
                b = g.wButtons
                if g.sThumbLY > _STICK:
                    b |= UP
                elif g.sThumbLY < -_STICK:
                    b |= DOWN
                if g.sThumbLX > _STICK:
                    b |= RIGHT
                elif g.sThumbLX < -_STICK:
                    b |= LEFT
                return b
        return 0

    def pressed(self) -> int:
        """Buttons that went down since the last call."""
        now = self.buttons()
        new = now & ~self.prev
        self.prev = now
        return new
