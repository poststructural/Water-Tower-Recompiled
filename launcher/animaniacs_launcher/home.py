"""The Home page: the studio-lot scene, the wordmark, a big Play button and a
glass status card, drawn on one tkinter Canvas.

The art is in assets/ui (drawn by launcher/tools/make_art.py, nothing from
the game). Canvas items are not widgets, so the page keeps its own focus:
arrows, Tab, Enter and Space move and press its buttons, and gui.py sends the
controller's D-pad and A here while Home has focus. The small classes below
answer the same config(text=..., state=...) calls gui.py makes on ttk
widgets, so the rest of the launcher doesn't care that Home is a canvas.
"""

from __future__ import annotations

import os
import sys
import tkinter as tk
import tkinter.font as tkfont

UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "ui")
FONT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts",
                         "LuckiestGuy-Regular.ttf")
DISPLAY_FAMILY = "Luckiest Guy"

INK = "#140c22"
TEXT = "#f6f1ff"
MUTED = "#b6aacd"
GOLD = "#f5b82e"
GREEN = "#5fcf80"
RED = "#ff7a66"
BLUE = "#7fb0ff"


def register_font() -> None:
    """Make the bundled display font usable by Tk, for this process only."""
    if sys.platform == "win32" and os.path.exists(FONT_FILE):
        try:
            import ctypes
            FR_PRIVATE = 0x10
            ctypes.windll.gdi32.AddFontResourceExW(FONT_FILE, FR_PRIVATE, 0)
        except (OSError, AttributeError):
            pass


def display_font(root: tk.Misc, size: int, fallback: str) -> tuple:
    """The display font if Tk can see it, else the UI font in bold."""
    try:
        have = DISPLAY_FAMILY in tkfont.families(root)
    except tk.TclError:
        have = False
    return (DISPLAY_FAMILY, size) if have else (fallback, max(9, size - 4), "bold")


def _image(name: str) -> tk.PhotoImage | None:
    try:
        return tk.PhotoImage(file=os.path.join(UI_DIR, name))
    except tk.TclError:
        return None


class CanvasButton:
    """An image button on the Home canvas: normal, focus and disabled art, a label."""

    def __init__(self, page: "HomeCanvas", kind: str, text: str, command, font, fg: str):
        self.page, self.kind, self.command = page, kind, command
        self.state = "normal"
        self.focused = False
        self.imgs = {s: page.img(f"{kind}_{s}.png") for s in ("normal", "focus", "disabled")}
        c = page.canvas
        self.bg = c.create_image(0, 0, anchor="nw", image=self.imgs["normal"])
        self.label = c.create_text(0, 0, text=text, font=font, fill=fg, anchor="w" if kind == "play" else "center")
        self.fg = fg
        for item in (self.bg, self.label):
            c.tag_bind(item, "<Enter>", lambda _e: page.set_focus(self))
            c.tag_bind(item, "<Button-1>", lambda _e: self.invoke())
            c.tag_bind(item, "<Enter>", lambda _e: c.config(cursor="hand2"), add="+")
            c.tag_bind(item, "<Leave>", lambda _e: c.config(cursor=""), add="+")

    def size(self) -> tuple[int, int]:
        im = self.imgs["normal"]
        return (im.width(), im.height()) if im else (200, 60)

    def place(self, x: int, y: int) -> None:
        c = self.page.canvas
        c.coords(self.bg, x, y)
        w, h = self.size()
        if self.kind == "play":
            c.coords(self.label, x + 100, y + h // 2 - 3)
        else:
            c.coords(self.label, x + w // 2, y + h // 2 + 1)

    def _draw(self) -> None:
        c = self.page.canvas
        art = "disabled" if self.state == "disabled" else "focus" if self.focused else "normal"
        if self.imgs[art]:
            c.itemconfig(self.bg, image=self.imgs[art])
        fg = "#8e84a3" if self.state == "disabled" else (INK if self.kind == "play" else
                                                         GOLD if self.focused else self.fg)
        c.itemconfig(self.label, fill=fg)

    def config(self, text: str | None = None, state: str | None = None, **_ignored) -> None:
        if text is not None:
            self.page.canvas.itemconfig(self.label, text=text)
        if state is not None:
            self.state = state
            if state == "disabled" and self.focused:
                self.page.move(1)
        self._draw()

    configure = config

    def invoke(self) -> None:
        if self.state != "disabled" and self.command:
            self.command()


class CanvasText:
    """A text item that takes config(text=..., foreground=...) like a ttk.Label."""

    def __init__(self, page: "HomeCanvas", font, fill: str = TEXT, anchor: str = "nw", width: int = 0):
        self.page = page
        self.item = page.canvas.create_text(0, 0, text="", font=font, fill=fill, anchor=anchor, width=width)
        self.text = ""

    def place(self, x: int, y: int) -> None:
        self.page.canvas.coords(self.item, x, y)

    def config(self, text: str | None = None, foreground: str | None = None, **_ignored) -> None:
        if text is not None:
            self.text = text
            self.page.canvas.itemconfig(self.item, text=text)
        if foreground is not None:
            self.page.canvas.itemconfig(self.item, fill=foreground)

    configure = config

    def cget(self, key: str):
        return self.text if key == "text" else self.page.canvas.itemcget(self.item, key)


class CanvasBar:
    """A thin progress bar with the parts of ttk.Progressbar gui.py uses."""

    def __init__(self, page: "HomeCanvas", width: int):
        c = page.canvas
        self.page, self.width = page, width
        self.trough = c.create_rectangle(0, 0, 0, 0, fill="#2a2240", outline="")
        self.fill = c.create_rectangle(0, 0, 0, 0, fill=GREEN, outline="")
        self.mode, self.maximum, self.value = "determinate", 1, 0
        self.x = self.y = 0
        self._job = None
        self._phase = 0

    def place(self, x: int, y: int) -> None:
        self.x, self.y = x, y
        self.page.canvas.coords(self.trough, x, y, x + self.width, y + 8)
        self._draw()

    def _draw(self) -> None:
        c = self.page.canvas
        x, y, w = self.x, self.y, self.width
        if self.mode == "indeterminate":
            seg = w // 4
            start = (self._phase % (w + seg)) - seg
            c.coords(self.fill, x + max(0, start), y, x + min(w, start + seg), y + 8)
        else:
            frac = 0 if not self.maximum else max(0.0, min(1.0, float(self.value) / float(self.maximum)))
            c.coords(self.fill, x, y, x + int(w * frac), y + 8)

    def config(self, mode=None, maximum=None, value=None, **_ignored) -> None:
        if mode is not None:
            self.mode = mode
        if maximum is not None:
            self.maximum = maximum
        if value is not None:
            self.value = value
        self._draw()

    configure = config

    def start(self, interval: int = 15) -> None:
        self.stop()

        def tick():
            self._phase += 6
            self._draw()
            self._job = self.page.canvas.after(interval, tick)
        tick()

    def stop(self) -> None:
        if self._job:
            self.page.canvas.after_cancel(self._job)
            self._job = None
        self._draw()

    def set_colour(self, colour: str) -> None:
        self.page.canvas.itemconfig(self.fill, fill=colour)


class HomeCanvas:
    """The scene and everything drawn on it. gui.App fills in the commands."""

    def __init__(self, parent: tk.Misc, ui_font: str):
        self.images: dict[str, tk.PhotoImage | None] = {}
        self.canvas = c = tk.Canvas(parent, highlightthickness=0, bd=0, bg="#0b0814", takefocus=1)
        self.ui = ui_font
        self.big = display_font(c, 30, ui_font)
        self.mid = display_font(c, 15, ui_font)
        self.small = display_font(c, 12, ui_font)
        self.buttons: list[CanvasButton] = []
        self.current: CanvasButton | None = None

        self.hero = c.create_image(0, 0, anchor="se", image=self.img("hero.png"))
        self.wordmark = c.create_image(0, 0, anchor="nw", image=self.img("wordmark.png"))
        self.card = c.create_image(0, 0, anchor="nw", image=self.img("card.png"))
        self.icon = c.create_image(0, 0, anchor="nw", image=self.img("status_warn.png"))
        self.footer = c.create_text(0, 0, anchor="se", fill="#8f84a8", font=(ui_font, 9),
                                    text="Fan project, not affiliated with Warner Bros. "
                                         "Play with your own copy of the game.")
        self.hint = c.create_text(0, 0, anchor="sw", fill="#8f84a8", font=(ui_font, 9), text="")

        c.bind("<Configure>", lambda _e: self.layout())
        for key, d in (("<Down>", 1), ("<Right>", 1), ("<Tab>", 1), ("<Up>", -1), ("<Left>", -1),
                       ("<Shift-Tab>", -1), ("<ISO_Left_Tab>", -1)):
            c.bind(key, lambda _e, d=d: (self.move(d), "break")[1])
        c.bind("<Return>", lambda _e: self.invoke())
        c.bind("<space>", lambda _e: self.invoke())
        c.bind("<FocusIn>", lambda _e: self._focus_in())
        c.bind("<FocusOut>", lambda _e: self._focus_out())

    def img(self, name: str) -> tk.PhotoImage | None:
        if name not in self.images:
            self.images[name] = _image(name)
        return self.images[name]

    # buttons and focus

    def button(self, kind: str, text: str, command) -> CanvasButton:
        font = self.big if kind == "play" else self.small
        b = CanvasButton(self, kind, text, command, font, INK if kind == "play" else TEXT)
        self.buttons.append(b)
        return b

    def set_focus(self, b: CanvasButton | None) -> None:
        if self.current is b:
            return
        if self.current:
            self.current.focused = False
            self.current._draw()
        self.current = b
        if b:
            b.focused = True
            b._draw()

    def move(self, d: int) -> None:
        live = [b for b in self.buttons if b.state != "disabled"]
        if not live:
            self.set_focus(None)
            return
        i = live.index(self.current) if self.current in live else (-1 if d > 0 else 0)
        self.set_focus(live[(i + d) % len(live)])

    def invoke(self) -> None:
        if self.current:
            self.current.invoke()

    def _focus_in(self) -> None:
        if not self.current or self.current.state == "disabled":
            self.set_focus(None)
            self.move(1)

    def _focus_out(self) -> None:
        pass

    # layout

    def layout(self) -> None:
        c = self.canvas
        w, h = c.winfo_width(), c.winfo_height()
        if w < 10:
            return
        c.coords(self.hero, w, h + 40)
        x = 44
        c.coords(self.wordmark, x - 4, 30)
        wm = self.img("wordmark.png")
        y = 30 + (wm.height() if wm else 160) + 26
        play = self.buttons[0]
        play.place(x - 14, y)
        y += play.size()[1] + 2
        bx = x - 8
        for b in self.buttons[1:]:
            b.place(bx, y)
            bx += b.size()[0] - 8
        card = self.img("card.png")
        cw, ch = (card.width(), card.height()) if card else (840, 132)
        cx = max(24, min(x, w - cw - 24)) if w > cw + 48 else 24
        cy = h - ch - 34
        c.coords(self.card, cx, cy)
        self.layout_card(cx, cy, cw, ch)
        c.coords(self.footer, w - 24, h - 10)
        c.coords(self.hint, cx + 4, h - 10)

    def layout_card(self, x: int, y: int, w: int, h: int) -> None:
        """gui.App places the card's text through these hooks."""
        for fn in getattr(self, "card_layout", []):
            fn(x, y, w, h)

    def set_icon(self, kind: str) -> None:
        im = self.img(f"status_{kind}.png")
        if im:
            self.canvas.itemconfig(self.icon, image=im)
