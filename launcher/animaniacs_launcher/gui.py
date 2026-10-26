"""The launcher window (tkinter, so it runs wherever Python does).

Laid out like the Crackdown recomp's launcher: a tab bar (Home, Display,
Graphics, Gameplay, Saves, Updates, About), a page per tab, and a status
line. Display, graphics and gameplay options are the game's own
settings.ini, edited in place; nothing is written until Save settings (or
Play, which saves first). Keyboard: Q / E switch tabs, Esc goes back. A
controller works too on Windows: LB / RB tabs, D-pad moves, A selects,
B goes back.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from . import (HOME_URL, __version__, build, config, gamefiles, gamepad, gamesettings, mods, play,
               profiles, steam, updates)
from .gamesettings import (ASPECTS, HUDS, MAX_SCALES, MODES, MSAA, RENDER_SCALES, RESOLUTIONS,
                           TEXTURE_FILTERS, VSYNC)

CHANNELS = {"release": "Releases", "main": "Latest main (newest commit)"}
TABS = ["HOME", "DISPLAY", "GRAPHICS", "GAMEPLAY", "SAVES", "MODS", "UPDATES", "ABOUT"]
UPDATES_TAB = TABS.index("UPDATES")

# Warner Bros. water tower palette on a dark backdrop.
BG = "#0d1117"
PANEL = "#161d26"
FIELD = "#1f2833"
LINE = "#2b3644"
TEXT = "#e8edf2"
MUTED = "#93a1b0"
GOLD = "#f5b82e"
GOLD_HI = "#ffd166"
RED = "#e05a47"
GREEN = "#5fcf80"

UI = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"
MONO = "Consolas" if sys.platform == "win32" else "DejaVu Sans Mono"


def _open_folder(path: str) -> None:
    os.makedirs(path, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 - a folder the launcher owns
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def _style(root: tk.Tk) -> None:
    s = ttk.Style(root)
    s.theme_use("clam")
    root.configure(bg=BG)
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", GOLD)
    root.option_add("*TCombobox*Listbox.selectForeground", BG)
    root.option_add("*TCombobox*Listbox.font", (UI, 11))
    s.configure(".", background=BG, foreground=TEXT, fieldbackground=FIELD, bordercolor=LINE,
                lightcolor=LINE, darkcolor=LINE, troughcolor=FIELD, focuscolor=GOLD,
                font=(UI, 11), insertcolor=TEXT, selectbackground=GOLD, selectforeground=BG)
    s.configure("TFrame", background=BG)
    s.configure("Panel.TFrame", background=PANEL)
    s.configure("TLabel", background=BG, foreground=TEXT)
    s.configure("Panel.TLabel", background=PANEL)
    s.configure("Muted.TLabel", foreground=MUTED)
    s.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED)
    s.configure("Title.TLabel", font=(UI, 26, "bold"), foreground=GOLD)
    s.configure("Sub.TLabel", font=(UI, 12), foreground=MUTED)
    s.configure("H.TLabel", font=(UI, 14, "bold"), background=PANEL)
    s.configure("Status.TLabel", background=PANEL, foreground=MUTED, font=(UI, 10))
    s.configure("Good.TLabel", background=PANEL, foreground=GREEN)
    s.configure("Bad.TLabel", background=PANEL, foreground=RED)
    s.configure("TButton", background=FIELD, foreground=TEXT, borderwidth=1, padding=(14, 7),
                focusthickness=2, focuscolor=GOLD)
    s.map("TButton", background=[("disabled", PANEL), ("pressed", GOLD), ("active", LINE)],
          foreground=[("disabled", "#56616d"), ("pressed", BG)])
    s.configure("Gold.TButton", background=GOLD, foreground=BG, font=(UI, 11, "bold"))
    s.map("Gold.TButton", background=[("disabled", PANEL), ("active", GOLD_HI)],
          foreground=[("disabled", "#56616d")])
    s.configure("Tab.TButton", background=BG, foreground=MUTED, font=(UI, 11, "bold"),
                padding=(14, 8), borderwidth=0)
    s.map("Tab.TButton", background=[("active", PANEL)], foreground=[("active", TEXT)])
    s.configure("TabOn.TButton", background=PANEL, foreground=GOLD, font=(UI, 11, "bold"),
                padding=(14, 8), borderwidth=0)
    s.configure("Menu.TButton", background=PANEL, foreground=TEXT, font=(UI, 16, "bold"),
                anchor="w", padding=(18, 10), borderwidth=0)
    s.map("Menu.TButton", background=[("disabled", PANEL), ("focus", FIELD), ("active", FIELD)],
          foreground=[("disabled", "#4b5560"), ("focus", GOLD), ("active", GOLD_HI)])
    s.configure("TCheckbutton", background=PANEL, foreground=TEXT, indicatorbackground=FIELD,
                indicatorforeground=GOLD, padding=4)
    s.map("TCheckbutton", background=[("active", PANEL)],
          indicatorbackground=[("selected", GOLD), ("active", LINE)],
          foreground=[("disabled", "#56616d")])
    s.configure("TCombobox", fieldbackground=FIELD, background=FIELD, foreground=TEXT,
                arrowcolor=GOLD, padding=5)
    s.map("TCombobox", fieldbackground=[("readonly", FIELD), ("disabled", PANEL)],
          foreground=[("readonly", TEXT), ("disabled", "#56616d")],
          selectbackground=[("readonly", FIELD)], selectforeground=[("readonly", TEXT)])
    s.configure("TEntry", fieldbackground=FIELD, foreground=TEXT, padding=5)
    s.configure("TSpinbox", fieldbackground=FIELD, foreground=TEXT, arrowcolor=GOLD, padding=4)
    s.configure("Horizontal.TProgressbar", background=GOLD, troughcolor=FIELD, bordercolor=LINE)


class Choice:
    """A read-only combobox over (value, label) pairs."""

    def __init__(self, parent, pairs, width=28, command=None):
        self.pairs = list(pairs)
        self.var = tk.StringVar()
        self.box = ttk.Combobox(parent, textvariable=self.var, state="readonly", width=width,
                                values=[label for _, label in self.pairs])
        if command:
            self.box.bind("<<ComboboxSelected>>", lambda _e: command())

    def get(self) -> str:
        label = self.var.get()
        return next((v for v, lb in self.pairs if lb == label), "")

    def set(self, value: str) -> None:
        label = next((lb for v, lb in self.pairs if v == value), None)
        if label is None and self.pairs:
            label = self.pairs[0][1]
        self.var.set(label or "")


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.st = config.Settings.load()
        self.events: queue.Queue = queue.Queue()
        self.busy = False
        self.cancel = threading.Event()
        self.latest: updates.GameVersion | None = None
        self.launcher_release: updates.LauncherRelease | None = None
        self.game: subprocess.Popen | None = None
        self.game_log = ""
        self.game_started = 0.0
        self.changes: dict[str, str] = {}
        self.loading = False
        self.tab = 0
        self.pad = gamepad.Pad()

        root.title("Animaniacs: The Great Edgar Hunt — Recompiled")
        root.geometry("1100x720")
        root.minsize(940, 620)
        _style(root)
        self._build_ui()
        self.load_game_settings()
        self.refresh()
        self.show_tab(0)
        root.protocol("WM_DELETE_WINDOW", self.quit)
        root.bind("<KeyPress-q>", lambda e: self._tab_key(e, -1))
        root.bind("<KeyPress-e>", lambda e: self._tab_key(e, +1))
        root.bind("<Escape>", lambda _e: self.back())
        root.after(100, self._pump)
        if self.pad.dll:
            root.after(60, self._poll_pad)
        if self.st.check_updates_on_start:
            self.check_updates(quiet=True)

    # ── Layout ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        r = self.root
        head = ttk.Frame(r)
        head.pack(fill="x", padx=28, pady=(18, 6))
        ttk.Label(head, text="ANIMANIACS", style="Title.TLabel").pack(side="left")
        ttk.Label(head, text="  The Great Edgar Hunt  ·  Recompiled",
                  style="Sub.TLabel").pack(side="left", pady=(10, 0))
        ttk.Label(head, text=f"LAUNCHER {__version__}", style="Muted.TLabel").pack(side="right")

        bar = ttk.Frame(r)
        bar.pack(fill="x", padx=22)
        self.tab_buttons = []
        for i, name in enumerate(TABS):
            b = ttk.Button(bar, text=name, style="Tab.TButton", takefocus=False, width=1,
                           command=lambda i=i: self.show_tab(i))
            b.pack(side="left", expand=True, fill="x")
            self.tab_buttons.append(b)

        # The status line is packed first so a tall page never pushes it off.
        foot = ttk.Frame(r, style="Panel.TFrame")
        foot.pack(side="bottom", fill="x", padx=28, pady=(0, 16))
        self.status = ttk.Label(foot, style="Status.TLabel")
        self.status.pack(side="left", padx=14, pady=8)
        self.hints = ttk.Label(foot, style="Status.TLabel")
        self.hints.pack(side="right", padx=14)

        self.body = ttk.Frame(r, style="Panel.TFrame")
        self.body.pack(fill="both", expand=True, padx=28)
        self.pages = [self._home(), self._display(), self._graphics(), self._gameplay(),
                      self._saves(), self._mods(), self._updates(), self._about()]

    def _page(self) -> ttk.Frame:
        f = ttk.Frame(self.body, style="Panel.TFrame", padding=(28, 22))
        return f

    def _heading(self, parent, text: str, sub: str = "") -> None:
        ttk.Label(parent, text=text, style="H.TLabel").grid(sticky="w", columnspan=3)
        if sub:
            ttk.Label(parent, text=sub, style="PanelMuted.TLabel", wraplength=760,
                      justify="left").grid(sticky="w", columnspan=3, pady=(2, 12))

    def _row(self, parent, label: str, widget, note: str = "") -> ttk.Label:
        row = parent.grid_size()[1]
        lab = ttk.Label(parent, text=label, style="Panel.TLabel")
        lab.grid(row=row, column=0, sticky="w", pady=7, padx=(0, 24))
        widget.grid(row=row, column=1, sticky="w", pady=7)
        if note:
            ttk.Label(parent, text=note, style="PanelMuted.TLabel", wraplength=260,
                      justify="left").grid(row=row, column=2, sticky="w", padx=16)
        return lab

    def _save_row(self, parent) -> ttk.Button:
        f = ttk.Frame(parent, style="Panel.TFrame")
        f.grid(sticky="w", columnspan=3, pady=(18, 0))
        b = ttk.Button(f, text="Save settings", style="Gold.TButton", command=self.save_game_settings)
        b.pack(side="left")
        ttk.Button(f, text="Defaults", command=self.reset_page).pack(side="left", padx=8)
        ttk.Label(f, text="Game settings take effect on the next Play.",
                  style="PanelMuted.TLabel").pack(side="left", padx=8)
        self.save_buttons.append(b)
        return b

    # Pages

    def _home(self) -> ttk.Frame:
        self.save_buttons: list[ttk.Button] = []
        f = self._page()
        f.columnconfigure(1, weight=1)
        menu = ttk.Frame(f, style="Panel.TFrame")
        menu.grid(row=0, column=0, sticky="nw")
        self.m_play = ttk.Button(menu, style="Menu.TButton", width=22, command=self.play_or_setup)
        self.m_verify = ttk.Button(menu, text="VERIFY GAME FILES", style="Menu.TButton", width=22,
                                   command=self.verify)
        self.m_updates = ttk.Button(menu, text="CHECK FOR UPDATES", style="Menu.TButton", width=22,
                                    command=lambda: (self.show_tab(UPDATES_TAB), self.check_updates()))
        self.m_settings = ttk.Button(menu, text="SETTINGS", style="Menu.TButton", width=22,
                                     command=lambda: self.show_tab(1))
        self.m_quit = ttk.Button(menu, text="QUIT", style="Menu.TButton", width=22, command=self.quit)
        for b in (self.m_play, self.m_verify, self.m_updates, self.m_settings, self.m_quit):
            b.pack(anchor="w", pady=2)

        card = ttk.Frame(f, style="Panel.TFrame")
        card.grid(row=0, column=1, sticky="nw", padx=(40, 0))
        ttk.Label(card, text="GAME FILES", style="PanelMuted.TLabel").pack(anchor="w")
        self.h_game = ttk.Label(card, style="Panel.TLabel", wraplength=480, justify="left")
        self.h_game.pack(anchor="w", pady=(2, 6))
        src = ttk.Frame(card, style="Panel.TFrame")
        src.pack(anchor="w")
        self.b_image = ttk.Button(src, text="Disc image or .zip…", command=self.pick_image)
        self.b_image.pack(side="left")
        self.b_folder = ttk.Button(src, text="Game folder…", command=self.pick_folder)
        self.b_folder.pack(side="left", padx=6)
        ttk.Label(card, text="GAME BUILD", style="PanelMuted.TLabel").pack(anchor="w", pady=(18, 0))
        self.h_build = ttk.Label(card, style="Panel.TLabel", wraplength=480, justify="left")
        self.h_build.pack(anchor="w", pady=(2, 0))
        self.h_launcher = ttk.Label(card, style="Panel.TLabel", foreground=GOLD, cursor="hand2",
                                    wraplength=480)
        self.h_launcher.pack(anchor="w", pady=(10, 0))
        self.h_launcher.bind("<Button-1>", lambda _e: self.update_launcher())
        self.b_steam = ttk.Button(card, text="Add to Steam", command=self.add_to_steam)
        self.b_steam.pack(anchor="w", pady=(18, 0))

        prog = ttk.Frame(f, style="Panel.TFrame")
        prog.grid(row=1, column=0, columnspan=2, sticky="we", pady=(24, 0))
        self.step = ttk.Label(prog, style="Panel.TLabel")
        self.step.pack(anchor="w")
        row = ttk.Frame(prog, style="Panel.TFrame")
        row.pack(fill="x", pady=(4, 0))
        self.bar = ttk.Progressbar(row, mode="determinate")
        self.bar.pack(side="left", fill="x", expand=True)
        self.b_cancel = ttk.Button(row, text="Cancel", command=self.cancel.set)
        self.b_cancel.pack(side="left", padx=8)

        self.crash = ttk.Frame(f, style="Panel.TFrame")
        self.crash.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(16, 0))
        f.rowconfigure(2, weight=1)
        self.crash_label = ttk.Label(self.crash, style="Bad.TLabel")
        self.crash_label.pack(anchor="w")
        self.crash_text = tk.Text(self.crash, height=8, bg=FIELD, fg=TEXT, relief="flat",
                                  font=(MONO, 9), state="disabled")
        self.crash_text.pack(fill="both", expand=True, pady=4)
        cb = ttk.Frame(self.crash, style="Panel.TFrame")
        cb.pack(anchor="w")
        ttk.Button(cb, text="Open log", command=lambda: self.game_log and _open_folder_file(self.game_log)).pack(side="left")
        ttk.Button(cb, text="Copy system info", command=self.copy_info).pack(side="left", padx=6)
        ttk.Button(cb, text="Dismiss", command=self.crash.grid_remove).pack(side="left")
        self.crash.grid_remove()
        return f

    def _display(self) -> ttk.Frame:
        f = self._page()
        self._heading(f, "Display", "Fullscreen uses your monitor's resolution. A wider aspect "
                                    "ratio shows more of the world at the sides; the main menus "
                                    "and movies stay 4:3.")
        self.mode = Choice(f, MODES, command=lambda: (self._set("display.mode", self.mode.get()),
                                                      self._mode_shown()))
        self._row(f, "Mode", self.mode.box, "F11 / Alt+Enter")
        self.res = Choice(f, RESOLUTIONS + [("custom", "Custom…")], command=self._res_changed)
        self.res_label = self._row(f, "Window size", self.res.box)
        cust = ttk.Frame(f, style="Panel.TFrame")
        self.width = tk.StringVar()
        self.height = tk.StringVar()
        ttk.Spinbox(cust, from_=320, to=7680, increment=16, width=7, textvariable=self.width,
                    command=self._custom_changed).pack(side="left")
        ttk.Label(cust, text=" x ", style="Panel.TLabel").pack(side="left")
        ttk.Spinbox(cust, from_=240, to=4320, increment=16, width=7, textvariable=self.height,
                    command=self._custom_changed).pack(side="left")
        for v in (self.width, self.height):
            v.trace_add("write", lambda *_: self._custom_changed())
        self.cust = (cust, self._row(f, "Custom size", cust))
        self.aspect = Choice(f, ASPECTS, command=lambda: self._set("display.aspect", self.aspect.get()))
        self._row(f, "Aspect ratio", self.aspect.box)
        self.hud = Choice(f, HUDS, command=lambda: self._set("display.hud", self.hud.get()))
        self._row(f, "HUD and menu text", self.hud.box, "on wide pictures")
        self.vsync = Choice(f, VSYNC, command=lambda: self._set("display.vsync", self.vsync.get()))
        self._row(f, "V-sync", self.vsync.box)
        self.fps = tk.BooleanVar()
        self._row(f, "Frame rate counter", ttk.Checkbutton(
            f, text="Show", variable=self.fps,
            command=lambda: self._set("display.show_fps", "on" if self.fps.get() else "off")),
            "F10 in game")
        self._save_row(f)
        self.ini_label = ttk.Label(f, style="PanelMuted.TLabel", cursor="hand2")
        self.ini_label.grid(sticky="w", columnspan=3, pady=(14, 0))
        self.ini_label.bind("<Button-1>", lambda _e: self.open_ini())
        return f

    def _graphics(self) -> ttk.Frame:
        f = self._page()
        self._heading(f, "Graphics", "The internal resolution is what the GPU draws at, as a "
                                     "multiple of the Xbox's 640 x 480, before the picture is "
                                     "scaled to the screen. Auto picks enough for your output "
                                     "resolution.")
        self.scale = Choice(f, RENDER_SCALES, width=36,
                            command=lambda: self._set("graphics.render_scale", self.scale.get()))
        self._row(f, "Internal resolution", self.scale.box)
        self.max_scale = Choice(f, MAX_SCALES, width=36,
                                command=lambda: self._set("graphics.max_render_scale", self.max_scale.get()))
        self._row(f, "Auto limit", self.max_scale.box, "lower it if a slower GPU drops below 60 fps")
        self.msaa = Choice(f, MSAA, width=36, command=lambda: self._set("graphics.msaa", self.msaa.get()))
        self._row(f, "Anti-aliasing", self.msaa.box)
        self.filt = Choice(f, TEXTURE_FILTERS, width=36,
                           command=lambda: self._set("graphics.texture_filter", self.filt.get()))
        self._row(f, "Texture filtering", self.filt.box)
        self.scale_hint = ttk.Label(f, style="PanelMuted.TLabel", wraplength=760, justify="left")
        self.scale_hint.grid(sticky="w", columnspan=3, pady=(8, 0))
        self._save_row(f)
        return f

    def _gameplay(self) -> ttk.Frame:
        f = self._page()
        self._heading(f, "Gameplay")
        self.skip = tk.BooleanVar()
        self._row(f, "Start-up", ttk.Checkbutton(
            f, text="Skip the publisher logos and intro movie", variable=self.skip,
            command=lambda: self._set("game.skip_intro", "on" if self.skip.get() else "off")))
        self.close_play = tk.BooleanVar(value=self.st.close_on_play)
        self._row(f, "Launcher", ttk.Checkbutton(
            f, text="Close the launcher when the game starts", variable=self.close_play,
            command=self._close_play_changed))
        self._save_row(f)
        ttk.Label(f, text="Controls: an Xbox-style controller works as on the console. "
                          "F10 shows the frame rate, F11 or Alt+Enter toggles fullscreen.",
                  style="PanelMuted.TLabel", wraplength=760, justify="left").grid(
            sticky="w", columnspan=3, pady=(18, 0))
        return f

    def _saves(self) -> ttk.Frame:
        f = self._page()
        self._heading(f, "Saves", "A profile is a separate set of saves. The default profile is "
                                  "the game's own save folder, so existing saves stay where they are.")
        self.profile = ttk.Combobox(f, state="readonly", width=30)
        self.profile.bind("<<ComboboxSelected>>", lambda _e: self._profile_changed())
        self._row(f, "Profile", self.profile)
        new = ttk.Frame(f, style="Panel.TFrame")
        self.new_profile = tk.StringVar()
        ttk.Entry(new, textvariable=self.new_profile, width=22).pack(side="left")
        ttk.Button(new, text="Create profile", command=self.create_profile).pack(side="left", padx=8)
        self._row(f, "New profile", new)
        acts = ttk.Frame(f, style="Panel.TFrame")
        acts.grid(sticky="w", columnspan=3, pady=(12, 0))
        ttk.Button(acts, text="Open saves folder",
                   command=lambda: _open_folder(profiles.folder(self.st.profile))).pack(side="left")
        ttk.Button(acts, text="Back up saves…", command=self.backup_saves).pack(side="left", padx=8)
        self.saves_label = ttk.Label(f, style="PanelMuted.TLabel", wraplength=760, justify="left")
        self.saves_label.grid(sticky="w", columnspan=3, pady=(14, 0))
        return f

    def _mods(self) -> ttk.Frame:
        f = self._page()
        f.columnconfigure(0, weight=1)
        self._heading(f, "Mods", "Mods replace or add game files, such as textures, sounds and "
                                 "levels. Your game files are never changed: Play lays the mods "
                                 "that are on over a copy. Lower in the list wins when two mods "
                                 "replace the same file.")
        box = ttk.Frame(f, style="Panel.TFrame")
        box.grid(sticky="we", columnspan=3)
        self.mod_list = tk.Listbox(box, height=8, bg=FIELD, fg=TEXT, selectbackground=GOLD,
                                   selectforeground=BG, relief="flat", highlightthickness=0,
                                   font=(UI, 10), activestyle="none", exportselection=False)
        self.mod_list.pack(side="left", fill="both", expand=True)
        self.mod_list.bind("<<ListboxSelect>>", lambda _e: self._mod_selected())
        self.mod_list.bind("<space>", lambda _e: self.toggle_mod())
        side = ttk.Frame(box, style="Panel.TFrame")
        side.pack(side="left", fill="y", padx=(8, 0))
        for text, fn in (("Turn on / off", self.toggle_mod), ("Move up", lambda: self.move_mod(-1)),
                         ("Move down", lambda: self.move_mod(1)), ("Remove", self.remove_mod)):
            ttk.Button(side, text=text, command=fn).pack(fill="x", pady=(0, 6))
        acts = ttk.Frame(f, style="Panel.TFrame")
        acts.grid(sticky="w", columnspan=3, pady=(12, 0))
        ttk.Button(acts, text="Add mod (.zip)…", style="Gold.TButton",
                   command=lambda: self.add_mod(False)).pack(side="left")
        ttk.Button(acts, text="Add mod folder…", command=lambda: self.add_mod(True)).pack(side="left", padx=8)
        ttk.Button(acts, text="Open mods folder",
                   command=lambda: (os.makedirs(mods.root(), exist_ok=True),
                                    _open_folder(mods.root()))).pack(side="left")
        self.mod_info = ttk.Label(f, style="PanelMuted.TLabel", wraplength=760, justify="left")
        self.mod_info.grid(sticky="w", columnspan=3, pady=(14, 0))
        self.mod_items: list[mods.Mod] = []
        return f

    def _updates(self) -> ttk.Frame:
        f = self._page()
        f.columnconfigure(1, weight=1)
        self._heading(f, "Updates", "The game is rebuilt on this PC from your own default.xbe "
                                    "whenever a new version comes out; nothing from the game is downloaded.")
        self.channel = Choice(f, list(CHANNELS.items()), command=self._channel_changed)
        self.channel.set(self.st.channel)
        self._row(f, "Follow", self.channel.box)
        opts = ttk.Frame(f, style="Panel.TFrame")
        self.pre = tk.BooleanVar(value=self.st.include_prereleases)
        self.auto = tk.BooleanVar(value=self.st.check_updates_on_start)
        ttk.Checkbutton(opts, text="Include pre-releases", variable=self.pre,
                        command=self._update_prefs).pack(side="left")
        ttk.Checkbutton(opts, text="Check when the launcher opens", variable=self.auto,
                        command=self._update_prefs).pack(side="left", padx=16)
        self._row(f, "Options", opts)
        srow = ttk.Frame(f, style="Panel.TFrame")
        self.source = tk.StringVar(value=self.st.update_source)
        e = ttk.Entry(srow, textvariable=self.source, width=46)
        e.pack(side="left")
        e.bind("<Return>", lambda _e: self._source_changed())
        ttk.Button(srow, text="Use", command=self._source_changed).pack(side="left", padx=6)
        self._row(f, "Update source", srow, "Blank for the project's GitLab; or an update "
                                            "file (.json), git address or folder")
        self.u_status = ttk.Label(f, style="Panel.TLabel", wraplength=760, justify="left")
        self.u_status.grid(sticky="w", columnspan=3, pady=(8, 4))
        acts = ttk.Frame(f, style="Panel.TFrame")
        acts.grid(sticky="w", columnspan=3)
        self.b_check = ttk.Button(acts, text="Check for updates", command=self.check_updates)
        self.b_check.pack(side="left")
        self.b_update = ttk.Button(acts, text="Update", style="Gold.TButton", command=self.update)
        self.b_update.pack(side="left", padx=8)
        self.b_file = ttk.Button(acts, text="Install update from file…", command=self.update_from_file)
        self.b_file.pack(side="left")
        self.b_tools = ttk.Button(acts, text="Install missing tools", command=self.install_tools)
        self.tools_label = ttk.Label(f, style="PanelMuted.TLabel", wraplength=760, justify="left")
        self.tools_label.grid(sticky="w", columnspan=3, pady=(6, 0))

        ttk.Label(f, text="INSTALLED BUILDS", style="PanelMuted.TLabel").grid(sticky="w", columnspan=3, pady=(16, 2))
        bl = ttk.Frame(f, style="Panel.TFrame")
        bl.grid(sticky="we", columnspan=3)
        self.builds = tk.Listbox(bl, height=2, bg=FIELD, fg=TEXT, selectbackground=GOLD,
                                 selectforeground=BG, relief="flat", highlightthickness=0,
                                 font=(UI, 10), activestyle="none")
        self.builds.pack(side="left", fill="x", expand=True)
        ttk.Button(bl, text="Play this build", command=self.switch_build).pack(side="left", padx=8)

        ttk.Label(f, text="BUILD LOG", style="PanelMuted.TLabel").grid(sticky="w", columnspan=3, pady=(16, 2))
        self.log = ScrolledText(f, height=5, state="disabled", font=(MONO, 9), bg=FIELD, fg=TEXT,
                                relief="flat", insertbackground=TEXT)
        self.log.grid(sticky="nsew", columnspan=3)
        f.rowconfigure(f.grid_size()[1] - 1, weight=1)
        return f

    def _about(self) -> ttk.Frame:
        f = self._page()
        self._heading(f, f"Animaniacs Recompiled · Launcher {__version__}",
                      "A static recompilation of Animaniacs: The Great Edgar Hunt (Xbox, 2005). "
                      "Bring your own copy of the game.")
        acts = ttk.Frame(f, style="Panel.TFrame")
        acts.grid(sticky="w", columnspan=3, pady=(0, 12))
        ttk.Button(acts, text="Project page",
                   command=lambda: webbrowser.open(HOME_URL)).pack(side="left")
        ttk.Button(acts, text="Open logs folder",
                   command=lambda: _open_folder(config.sub("logs"))).pack(side="left", padx=8)
        ttk.Button(acts, text="Copy system info", command=self.copy_info).pack(side="left")
        ttk.Button(acts, text="Launcher data folder",
                   command=lambda: _open_folder(config.data_dir())).pack(side="left", padx=8)

        ttk.Label(f, text="DEVELOPER", style="PanelMuted.TLabel").grid(sticky="w", columnspan=3, pady=(10, 4))
        self.console = tk.BooleanVar(value=self.st.show_console)
        self._row(f, "Console", ttk.Checkbutton(f, text="Build the game with a console window",
                                                variable=self.console, command=self._dev_changed),
                  "next build")
        self.custom_exe = tk.StringVar(value=self.st.custom_exe)
        self.ghidra = tk.StringVar(value=self.st.ghidra_home)
        self.java = tk.StringVar(value=self.st.java_home)
        self._path_row(f, "Play this exe instead", self.custom_exe, file=True)
        self._path_row(f, "Ghidra 12 folder", self.ghidra)
        self._path_row(f, "JDK 21 folder", self.java)
        kb = ttk.Frame(f, style="Panel.TFrame")
        kb.grid(sticky="w", columnspan=3, pady=(8, 0))
        ttk.Label(kb, text="Older builds to keep:", style="Panel.TLabel").pack(side="left")
        self.keep = tk.IntVar(value=self.st.keep_builds)
        ttk.Spinbox(kb, from_=0, to=5, width=4, textvariable=self.keep,
                    command=self._dev_changed).pack(side="left", padx=8)
        ttk.Label(f, text="Launcher: Python, tkinter. No game data or code is included; the game "
                          "is built from your files.", style="PanelMuted.TLabel", wraplength=760,
                  justify="left").grid(sticky="w", columnspan=3, pady=(18, 0))
        return f

    def _path_row(self, f, label: str, var: tk.StringVar, file: bool = False) -> None:
        row = ttk.Frame(f, style="Panel.TFrame")
        e = ttk.Entry(row, textvariable=var, width=52)
        e.pack(side="left")
        e.bind("<FocusOut>", lambda _e: self._dev_changed())

        def pick():
            p = (filedialog.askopenfilename(filetypes=[("Programs", "*.exe"), ("All", "*")])
                 if file else filedialog.askdirectory())
            if p:
                var.set(p)
                self._dev_changed()
        ttk.Button(row, text="…", width=3, command=pick).pack(side="left", padx=4)
        ttk.Button(row, text="Clear", command=lambda: (var.set(""), self._dev_changed())).pack(side="left")
        self._row(f, label, row)

    # ── Tabs, keyboard and controller ───────────────────────────────────

    def show_tab(self, i: int) -> None:
        self.pages[self.tab].pack_forget()
        self.tab = i % len(TABS)
        self.pages[self.tab].pack(fill="both", expand=True)
        for j, b in enumerate(self.tab_buttons):
            b.configure(style="TabOn.TButton" if j == self.tab else "Tab.TButton")
        if TABS[self.tab] == "SAVES":
            self._fill_profiles()
        if TABS[self.tab] == "MODS":
            self._fill_mods()
        if TABS[self.tab] == "UPDATES":
            self._fill_builds()
        self.root.after_idle(self._focus_first)

    def _focus_first(self) -> None:
        def first(w):
            for c in w.winfo_children():
                try:
                    if str(c.cget("takefocus")) != "0" and "disabled" not in c.state() \
                            and isinstance(c, (ttk.Button, ttk.Checkbutton, ttk.Combobox, ttk.Entry, ttk.Spinbox)):
                        return c
                except (tk.TclError, AttributeError):
                    pass
                f = first(c)
                if f:
                    return f
            return None
        w = first(self.pages[self.tab])
        if w:
            w.focus_set()

    def _tab_key(self, e, d: int) -> None:
        if isinstance(e.widget, (ttk.Entry, tk.Entry, ttk.Spinbox, tk.Text)):
            return
        self.show_tab(self.tab + d)

    def back(self) -> None:
        if self.tab:
            self.show_tab(0)
        elif self.busy:
            self.cancel.set()

    def _poll_pad(self) -> None:
        try:
            b = self.pad.pressed()
        except OSError:
            b = 0
        if b:
            self._pad_seen = True
            focus = self.root.focus_get()
            if b & gamepad.LB:
                self.show_tab(self.tab - 1)
            elif b & gamepad.RB:
                self.show_tab(self.tab + 1)
            elif b & gamepad.B:
                self.back()
            elif b & (gamepad.DOWN | gamepad.UP):
                nxt = (focus.tk_focusNext() if b & gamepad.DOWN else focus.tk_focusPrev()) if focus else None
                (nxt or self.root).focus_set()
            elif b & (gamepad.LEFT | gamepad.RIGHT) and isinstance(focus, ttk.Combobox):
                vals = list(focus.cget("values"))
                if vals:
                    i = vals.index(focus.get()) if focus.get() in vals else 0
                    focus.set(vals[(i + (1 if b & gamepad.RIGHT else -1)) % len(vals)])
                    focus.event_generate("<<ComboboxSelected>>")
            elif b & gamepad.A and focus is not None and hasattr(focus, "invoke"):
                focus.invoke()
            self._hints()
        self.root.after(60, self._poll_pad)

    def _hints(self) -> None:
        if getattr(self, "_pad_seen", False):
            self.hints.config(text="LB/RB tabs   D-pad move   ◀▶ change   A select   B back")
        else:
            self.hints.config(text="Q/E tabs   Tab move   Space select   Esc back")

    # ── Game settings (settings.ini) ────────────────────────────────────

    def ini_path(self) -> str | None:
        try:
            exe, _ = play.current_exe(self.st)
        except play.PlayError:
            return None
        return gamesettings.location(exe)

    def load_game_settings(self) -> None:
        path = self.ini_path()
        self.ini = gamesettings.load(path) if path else gamesettings.IniFile(
            gamesettings.template_from_source() or gamesettings.FALLBACK_TEMPLATE)
        self.changes.clear()
        self._fill_game_settings()

    def _v(self, name: str) -> str:
        return self.changes.get(name, gamesettings.value(self.ini, name))

    def _fill_game_settings(self) -> None:
        self.loading = True
        res = self._v("display.resolution")
        self.res.set(res if any(v == res for v, _ in self.res.pairs) else "custom")
        w, _, h = res.partition("x")
        self.width.set(w if w.isdigit() else "1920")
        self.height.set(h if h.isdigit() else "1080")
        self.mode.set(self._v("display.mode"))
        self.aspect.set(self._v("display.aspect"))
        self.hud.set(self._v("display.hud"))
        self.vsync.set(self._v("display.vsync"))
        self.fps.set(self._v("display.show_fps") == "on")
        self.scale.set(self._v("graphics.render_scale"))
        self.max_scale.set(self._v("graphics.max_render_scale"))
        self.msaa.set(self._v("graphics.msaa"))
        self.filt.set(self._v("graphics.texture_filter"))
        self.skip.set(self._v("game.skip_intro") == "on")
        self.loading = False
        self._mode_shown()
        self._scale_hint()
        self._dirty()

    def _set(self, name: str, value: str) -> None:
        if self.loading:
            return
        if gamesettings.value(self.ini, name) == value:
            self.changes.pop(name, None)
        else:
            self.changes[name] = value
        self._scale_hint()
        self._dirty()

    def _dirty(self) -> None:
        for b in self.save_buttons:
            b.config(text="Save settings *" if self.changes else "Save settings")
        path = self.ini_path()
        self.ini_label.config(text=f"settings.ini: {path}" if path else
                              "settings.ini is created once a build is installed.")

    def _mode_shown(self) -> None:
        """Window size only matters windowed; custom size only for Custom."""
        windowed = self.mode.get() != "fullscreen"
        for w in (self.res.box, self.res_label):
            w.grid() if windowed else w.grid_remove()
        for w in self.cust:
            w.grid() if windowed and self.res.get() == "custom" else w.grid_remove()

    def _res_changed(self) -> None:
        self._mode_shown()
        v = self.res.get()
        if v == "custom":
            self._custom_changed()
        else:
            self._set("display.resolution", v)

    def _custom_changed(self) -> None:
        if self.loading:
            return
        w, h = self.width.get().strip(), self.height.get().strip()
        if w.isdigit() and h.isdigit() and int(w) >= 320 and int(h) >= 240:
            self._set("display.resolution", f"{w}x{h}")

    def _output_size(self) -> tuple[int, int, str]:
        """The output picture the game will draw for: (width, height, what)."""
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        res = self._v("display.resolution")
        if self._v("display.mode") == "fullscreen" or res == "native":
            w, h, what = sw, sh, "your monitor"
        else:
            try:
                w, h = (int(x) for x in res.split("x"))
            except ValueError:
                w, h = 1920, 1080
            what = f"a {w} x {h} window"
        aspect = self._v("display.aspect")
        if aspect != "auto":
            # The picture's shape inside the output: width follows the aspect.
            try:
                aw, ah = (float(x) for x in aspect.split(":"))
                w = min(w, round(h * aw / ah)) if aw / ah >= 4 / 3 else round(h * 4 / 3)
            except ValueError:
                pass
        return w, h, what

    def _scale_hint(self) -> None:
        w, h, what = self._output_size()
        try:
            limit = int(self._v("graphics.max_render_scale"))
        except ValueError:
            limit = 6
        v = self._v("graphics.render_scale")
        if v == "auto":
            n = gamesettings.auto_scale(w, h, limit)
            tip = f"Auto draws at {n}x ({640 * n} x {480 * n}) for {what}."
            if gamesettings.auto_scale(w, h, 8) > limit:
                tip += f" That is the auto limit; {what} would get {gamesettings.auto_scale(w, h, 8)}x without it."
        else:
            n = int(v) if v.isdigit() else 2
            need = gamesettings.auto_scale(w, h, 8)
            tip = f"Draws at {n}x ({640 * n} x {480 * n}) for {what}."
            if n < need:
                tip += f" {need}x would match it; lower looks softer."
            elif n > need + 1:
                tip += f" {need}x already matches it and runs lighter."
        self.scale_hint.config(text=tip)

    def save_game_settings(self) -> bool:
        path = self.ini_path()
        if not path:
            messagebox.showinfo("Settings", "Build the game first; its settings.ini lives beside it.")
            return False
        if not self.changes:
            return True
        try:
            # Re-read: the game may have written the file since (F11 and so on).
            self.ini = gamesettings.load(path)
            gamesettings.apply(self.ini, self.changes)
            self.ini.save(path)
        except OSError as e:
            messagebox.showerror("Settings", f"Could not save {path}: {e}")
            return False
        self.changes.clear()
        self._dirty()
        self._log(f"Saved {path}")
        return True

    def reset_page(self) -> None:
        page = {1: "display.", 2: "graphics.", 3: "game."}.get(self.tab, "")
        for name, o in gamesettings.OPTIONS.items():
            if name.startswith(page):
                self._set(name, o.default)
        self._fill_game_settings()

    def open_ini(self) -> None:
        p = self.ini_path()
        if p and os.path.isfile(p):
            _open_folder_file(p)

    # ── Launcher preferences ────────────────────────────────────────────

    def _close_play_changed(self) -> None:
        self.st.close_on_play = self.close_play.get()
        self.st.save()

    def _update_prefs(self) -> None:
        self.st.include_prereleases = self.pre.get()
        self.st.check_updates_on_start = self.auto.get()
        self.st.save()

    def _dev_changed(self) -> None:
        self.st.show_console = self.console.get()
        self.st.custom_exe = self.custom_exe.get().strip()
        self.st.ghidra_home = self.ghidra.get().strip()
        self.st.java_home = self.java.get().strip()
        try:
            self.st.keep_builds = max(0, min(5, int(self.keep.get())))
        except (tk.TclError, ValueError):
            pass
        self.st.save()
        self.load_game_settings()
        self.refresh()

    def _source_changed(self) -> None:
        text = self.source.get().strip()
        if text == self.st.update_source:
            return
        self.st.update_source = text
        self.st.save()
        self.latest = None
        self.launcher_release = None
        self.check_updates()

    def _channel_changed(self) -> None:
        self.st.channel = self.channel.get() or "release"
        self.st.save()
        self.latest = None
        self.check_updates()

    # ── Mods ────────────────────────────────────────────────────────────

    def _fill_mods(self, select: int | None = None) -> None:
        self.mod_items = mods.load()
        self.mod_list.delete(0, "end")
        for m in self.mod_items:
            mark = "✓" if m.enabled else "  ·"
            by = f"   by {m.author}" if m.author else ""
            self.mod_list.insert("end", f"  {mark}  {m.name}  {m.version}{by}"
                                        + ("" if m.enabled else "   (off)"))
        if self.mod_items:
            i = min(select if select is not None else 0, len(self.mod_items) - 1)
            self.mod_list.selection_set(i)
            self.mod_list.see(i)
        self._mod_selected()

    def _mod_index(self) -> int | None:
        sel = self.mod_list.curselection()
        return sel[0] if sel else None

    def _mod_selected(self) -> None:
        if not self.mod_items:
            self.mod_info.config(text="No mods yet. A mod is a .zip or folder with a mod.json "
                                      "and a files/ folder laid out like the game folder.")
            return
        lines = []
        i = self._mod_index()
        if i is not None:
            m = self.mod_items[i]
            n = len(m.files())
            lines.append(f"{m.name}: {m.description or 'no description'} "
                         f"({n} file{'s' if n != 1 else ''})")
        clash = mods.conflicts(self.mod_items)
        if clash:
            lines.append(f"{len(clash)} file{' is' if len(clash) == 1 else 's are'} replaced by "
                         "more than one mod that is on; the lowest in the list wins.")
        on = sum(m.enabled for m in self.mod_items)
        lines.append(f"{on} of {len(self.mod_items)} mods on.")
        self.mod_info.config(text="\n".join(lines))

    def toggle_mod(self) -> None:
        i = self._mod_index()
        if i is None:
            return
        self.mod_items[i].enabled = not self.mod_items[i].enabled
        mods.save(self.mod_items)
        self._fill_mods(i)

    def move_mod(self, d: int) -> None:
        i = self._mod_index()
        if i is None or not 0 <= i + d < len(self.mod_items):
            return
        items = self.mod_items
        items[i], items[i + d] = items[i + d], items[i]
        mods.save(items)
        self._fill_mods(i + d)

    def remove_mod(self) -> None:
        i = self._mod_index()
        if i is None:
            return
        m = self.mod_items[i]
        if messagebox.askyesno("Remove mod", f"Remove {m.name}? Its files are deleted from "
                                             "the mods folder."):
            mods.remove(m.id)
            self._fill_mods(i)

    def add_mod(self, folder: bool) -> None:
        path = (filedialog.askdirectory(title="The mod's folder") if folder else
                filedialog.askopenfilename(title="A mod", filetypes=[("Mod", "*.zip"),
                                                                     ("All files", "*.*")]))
        if not path:
            return

        def done(m):
            self._log(f"Installed mod {m.name} {m.version}")
            self._fill_mods(next((i for i, x in enumerate(mods.load()) if x.id == m.id), 0))
        self._run("Installing mod", lambda: mods.install(path), done, pulse=True)

    # ── Profiles ────────────────────────────────────────────────────────

    def _fill_profiles(self) -> None:
        names = ["Default (existing saves)"] + profiles.list_profiles()
        self.profile.config(values=names)
        self.profile.set(self.st.profile if self.st.profile in names else names[0])
        self.saves_label.config(text=f"Saves for this profile: {profiles.folder(self.st.profile)}")

    def _profile_changed(self) -> None:
        v = self.profile.get()
        self.st.profile = "" if v.startswith("Default") else v
        self.st.save()
        self._fill_profiles()
        self.refresh()

    def create_profile(self) -> None:
        name = self.new_profile.get().strip()
        try:
            profiles.create(name)
        except (ValueError, OSError) as e:
            messagebox.showerror("Profiles", str(e))
            return
        self.new_profile.set("")
        self.st.profile = name
        self.st.save()
        self._fill_profiles()
        self.refresh()

    def backup_saves(self) -> None:
        d = filedialog.askdirectory(title="Where to put the backup")
        if not d:
            return
        try:
            out = profiles.backup(self.st.profile, d)
        except (ValueError, OSError) as e:
            messagebox.showerror("Back up saves", str(e))
            return
        messagebox.showinfo("Back up saves", f"Saved {out}")

    # ── State ───────────────────────────────────────────────────────────

    def refresh(self) -> None:
        st = self.st
        if st.game_dir:
            chk = gamefiles.check_dir(st.game_dir)
            self.game_ok = chk.ok
            self.h_game.config(text=f"✓ {chk.summary()}\n{st.game_dir}" if chk.ok
                               else f"✗ {st.game_dir}\n{chk.summary()}",
                               foreground=TEXT if chk.ok else RED)
        else:
            self.game_ok = False
            self.h_game.config(text="Point the launcher at your own copy of the game: an Xbox disc "
                                    "image (.iso), a .zip, or a folder with default.xbe.",
                               foreground=TEXT)

        why = build.supported()
        tc = build.detect()
        self.tools = tc
        installed = st.custom_exe or st.current_build
        line = f"Installed: {installed or 'nothing yet'}"
        avail = ""
        if self.latest:
            note = " (no releases yet, following main)" if self.latest.fell_back else ""
            if self.latest.name == st.current_build:
                line += f"  ·  up to date{note}"
            else:
                avail = f"Available: {self.latest.name}{note}"
                if self.latest.notes:
                    avail += f"\n{self.latest.notes.strip().splitlines()[0][:110]}"
                line += "\n" + avail
        self.h_build.config(text=line)
        self.u_status.config(text=line)
        if why:
            self.tools_label.config(text=why)
        elif tc.ok:
            self.tools_label.config(text="Build tools: ready")
        else:
            self.tools_label.config(text="Needed to build: " + ", ".join(tc.missing))
        if not why and not tc.ok and sys.platform == "win32":
            self.b_tools.pack(side="left")
        else:
            self.b_tools.pack_forget()
        if self.launcher_release:
            self.h_launcher.config(text=f"Launcher {self.launcher_release.version} is available. Click to install.")

        running = bool(self.game and self.game.poll() is None)
        idle = "disabled" if self.busy else "normal"
        for b in (self.b_image, self.b_folder, self.b_check, self.b_file):
            b.config(state=idle)
        can_build = not self.busy and self.game_ok and not why and bool(tc.git and tc.bash)
        self.b_update.config(state="normal" if can_build else "disabled",
                             text="Build" if not st.current_build else "Update")
        if running:
            self.m_play.config(text="PLAYING…", state="disabled")
        elif not self.game_ok:
            self.m_play.config(text="SET UP GAME FILES", state=idle)
        elif not installed:
            self.m_play.config(text="BUILD THE GAME", state="normal" if can_build else "disabled")
        else:
            self.m_play.config(text="PLAY", state=idle)
        self.m_verify.config(state="normal" if st.game_dir and not self.busy else "disabled")
        self.b_cancel.config(state="normal" if self.busy else "disabled")

        game = "Playing" if running else "Ready" if self.game_ok and installed else \
            "Needs a build" if self.game_ok else "Not set up"
        self.status.config(text=f"GAME  {game}      BUILD  {installed or '—'}      "
                                f"PROFILE  {st.profile or 'Default'}      "
                                f"FOLLOW  {CHANNELS[st.channel].split(' (')[0]}")
        self._hints()

    def _fill_builds(self) -> None:
        self.builds.delete(0, "end")
        self._build_names = []
        for b in build.installed():
            mark = "   ← playing" if b["name"] == self.st.current_build else ""
            self.builds.insert("end", f"  {b['name']}    built {b.get('built', '?')}{mark}")
            self._build_names.append(b["name"])

    def switch_build(self) -> None:
        sel = self.builds.curselection()
        if not sel:
            return
        name = self._build_names[sel[0]]
        build.carry_settings(self.st.current_build, config.sub("builds", name))
        self.st.current_build = name
        self.st.save()
        self._fill_builds()
        self.load_game_settings()
        self.refresh()

    # ── Background work ─────────────────────────────────────────────────

    def _pump(self) -> None:
        try:
            while True:
                kind, *a = self.events.get_nowait()
                if kind == "log":
                    self.log.config(state="normal")
                    self.log.insert("end", a[0] + "\n")
                    lines = int(self.log.index("end-1c").split(".")[0])
                    if lines > 5000:
                        self.log.delete("1.0", f"{lines - 5000}.0")
                    self.log.see("end")
                    self.log.config(state="disabled")
                elif kind == "step":
                    self.step.config(text=a[0])
                elif kind == "progress":
                    done, total = a
                    if total:
                        self.bar.stop()
                        self.bar.config(mode="determinate", maximum=total, value=done)
                elif kind == "pulse" and self.busy:
                    self.bar.config(mode="indeterminate")
                    self.bar.start(15)
                elif kind == "call":
                    a[0]()
        except queue.Empty:
            pass
        if self.game and self.game.poll() is not None:
            self._game_exited()
        self.root.after(100, self._pump)

    def _game_exited(self) -> None:
        code = self.game.returncode
        ran = time.time() - self.game_started
        self.game = None
        self._log(f"Game exited (code {code})")
        if code != 0 or ran < 10:
            what = "crashed" if code != 0 else "closed during start-up"
            self.crash_label.config(text=f"The game {what} (exit code {code & 0xFFFFFFFF:#010x}). "
                                         "The end of its log:")
            self.crash_text.config(state="normal")
            self.crash_text.delete("1.0", "end")
            self.crash_text.insert("end", play.log_tail(self.game_log) or "(the log is empty)")
            self.crash_text.config(state="disabled")
            self.crash.grid()
            self.show_tab(0)
        self.refresh()

    def _log(self, s: str) -> None:
        self.events.put(("log", s))

    def _run(self, title: str, fn, done=None, pulse: bool = False, quiet: bool = False) -> None:
        if self.busy:
            return
        self.busy = True
        self.cancel.clear()
        self.events.put(("step", title))
        self.events.put(("progress", 0, 1))
        if pulse:
            self.events.put(("pulse", True))
        self.refresh()

        def work():
            err = None
            result = None
            try:
                result = fn()
            except Exception as e:  # shown to the player, never fatal
                err = e
            self.events.put(("call", lambda: finish(result, err)))

        def finish(result, err):
            self.busy = False
            self.bar.stop()
            self.bar.config(mode="determinate", value=0)
            if err:
                cancelled = isinstance(err, build.Cancelled) or str(err) == "cancelled"
                self.step.config(text="Cancelled" if cancelled else f"{title} failed: {err}")
                if not cancelled:
                    self._log(f"error: {err}")
                    if not quiet:
                        messagebox.showerror(title, str(err))
            else:
                self.step.config(text=f"{title}: done")
                if done:
                    done(result)
            self.refresh()

        threading.Thread(target=work, daemon=True).start()

    def _progress(self, done: int, total: int, name: str) -> None:
        self.events.put(("progress", done, total))

    # ── Actions ─────────────────────────────────────────────────────────

    def play_or_setup(self) -> None:
        if not self.game_ok:
            self.pick_image()
        elif not (self.st.current_build or self.st.custom_exe):
            self.show_tab(UPDATES_TAB)
            self.update()
        else:
            self.play()

    def pick_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Your Animaniacs disc image or zip",
            filetypes=[("Xbox disc image or zip", "*.iso *.xiso *.zip"), ("All files", "*.*")])
        if path:
            self._import(path, "Extracting the game files")

    def pick_folder(self) -> None:
        path = filedialog.askdirectory(title="Folder with default.xbe, resource and movies")
        if path:
            self._import(path, "Checking the game files")

    def _import(self, path: str, title: str) -> None:
        def work():
            return gamefiles.import_game(path, config.sub("game"), progress=self._progress,
                                         cancelled=self.cancel.is_set)

        def done(game_dir):
            self.st.game_dir = game_dir
            self.st.save()
            self._log(f"Game files: {game_dir}")
            if not self.st.current_build and not self.st.custom_exe:
                self.check_updates(quiet=True)
        self._run(title, work, done)

    def verify(self) -> None:
        chk = gamefiles.check_dir(self.st.game_dir)
        if chk.ok:
            messagebox.showinfo("Verify game files", f"Your game files look complete: {chk.summary()}.")
        else:
            messagebox.showerror("Verify game files", chk.summary())
        self.refresh()

    def check_updates(self, quiet: bool = False) -> None:
        def work():
            v = updates.latest_game(self.st.channel, self.st.include_prereleases,
                                    self.st.update_source)
            try:
                lr = updates.latest_launcher(self.st.update_source)
            except updates.UpdateError:
                lr = None
            return v, lr

        def done(res):
            v, lr = res
            self.latest = v
            self.launcher_release = lr
            self._log(f"Newest version: {v.name}" + (" (no releases yet, using main)" if v.fell_back else ""))
        if quiet and self.busy:
            return
        self._run("Checking for updates", work, done, pulse=True, quiet=quiet)

    def update_from_file(self) -> None:
        path = filedialog.askopenfilename(
            title="An update file",
            filetypes=[("Game source bundle or launcher installer", "*.bundle *.exe"),
                       ("All files", "*.*")])
        if not path:
            return
        if path.lower().endswith(".exe"):
            if messagebox.askokcancel("Update the launcher",
                                      f"Run {os.path.basename(path)} to update the launcher? "
                                      "The launcher closes while it installs."):
                subprocess.Popen([path, "/SILENT"])
                self.root.destroy()
            return

        def done(v):
            self.update(v)
        self._run("Reading the update file",
                  lambda: updates.from_bundle(path, self.st.channel, True), done, pulse=True)

    def update(self, version: updates.GameVersion | None = None) -> None:
        if version is None and not self.latest:
            def work():
                return updates.latest_game(self.st.channel, self.st.include_prereleases,
                                           self.st.update_source)

            def done(v):
                self.latest = v
                self.update()
            self._run("Checking for updates", work, done, pulse=True)
            return
        v = version or self.latest
        if v.name == self.st.current_build and not messagebox.askyesno(
                "Rebuild", f"{v.name} is already installed. Build it again?"):
            return
        if not self.st.current_build and not messagebox.askokcancel(
                "Build the game",
                "The launcher builds the game from source on this PC, using your "
                "default.xbe. The first build downloads compilers and libraries "
                "(a few GB) and takes a while; later updates are faster.\n\nStart now?"):
            return

        def work():
            build.build(v, self.st.game_dir, self.st, log=self._log,
                        cancelled=self.cancel.is_set,
                        step=lambda s: self.events.put(("step", s)))
            return v

        def done(v):
            self.st.current_build = v.name
            self.st.save()
            build.prune(v.name, self.st.keep_builds)
            self._log(f"Installed {v.name}")
            self._fill_builds()
            self.load_game_settings()
        self._run(f"Building {v.name}", work, done, pulse=True)

    def install_tools(self) -> None:
        ids = [build.WINGET[m] for m in self.tools.missing if m in build.WINGET]
        if not ids:
            webbrowser.open("https://git-scm.com/download/win")
            return
        if not messagebox.askokcancel(
                "Install build tools",
                "Install " + ", ".join(self.tools.missing) + " with winget?\n\n"
                "Windows may ask for permission. Restart the launcher afterwards."):
            return

        def work():
            r = build.Runner(self._log, self.cancel.is_set)
            for pkg in ids:
                r.run(["winget", "install", "--id", pkg, "-e", "--source", "winget",
                       "--accept-package-agreements", "--accept-source-agreements"])
        self._run("Installing build tools", work, pulse=True)

    def update_launcher(self) -> None:
        lr = self.launcher_release
        if not lr:
            return
        if not lr.installer_url:
            webbrowser.open(lr.page_url)
            return

        def work():
            dest = config.sub(f"AnimaniacsLauncherSetup-{lr.version}.exe")
            return updates.download(lr.installer_url, dest, self._progress, lr.sha256)

        def done(path):
            subprocess.Popen([path, "/SILENT"])
            self.root.destroy()
        self._run(f"Downloading launcher {lr.version}", work, done)

    def play(self) -> None:
        if self.changes and not self.save_game_settings():
            return
        if self.busy:
            return
        if any(m.enabled for m in mods.load()):
            self._run("Applying mods", lambda: mods.prepare(self.st.game_dir, log=self._log),
                      self._start_game, pulse=True)
        else:
            self._start_game(self.st.game_dir)

    def _start_game(self, game_dir: str) -> None:
        try:
            self.game, self.game_log = play.launch(self.st, game_dir)
        except (play.PlayError, ValueError) as e:
            messagebox.showerror("Play", str(e))
            return
        self.game_started = time.time()
        self.crash.grid_remove()
        self._log(f"Game started (log: {self.game_log})")
        if self.st.close_on_play:
            self.root.destroy()
            return
        self.refresh()

    def add_to_steam(self) -> None:
        if not getattr(sys, "frozen", False):
            messagebox.showinfo("Add to Steam", "Add to Steam works from the installed launcher "
                                                "(AnimaniacsLauncher.exe).")
            return
        try:
            msg = steam.add_to_steam(sys.executable)
        except (steam.SteamError, OSError) as e:
            messagebox.showerror("Add to Steam", str(e))
            return
        messagebox.showinfo("Add to Steam", msg)

    def copy_info(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(play.system_info(self.st))
        messagebox.showinfo("System info", "Copied. Paste it into your bug report.")

    def quit(self) -> None:
        if self.changes:
            ans = messagebox.askyesnocancel("Quit", "Save your game settings before quitting?")
            if ans is None:
                return
            if ans and not self.save_game_settings():
                return
        if self.busy and not messagebox.askokcancel("Quit", "Stop what the launcher is doing and quit?"):
            return
        self.cancel.set()
        self.root.destroy()


def _open_folder_file(path: str) -> None:
    """Open a file with its default program (the log, settings.ini)."""
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606
    else:
        subprocess.Popen(["xdg-open" if sys.platform != "darwin" else "open", path])


def run(smoke: bool = False) -> int:
    """smoke: show every tab, then close (a check that the window builds)."""
    root = tk.Tk()
    try:
        icon = tk.PhotoImage(file=os.path.join(os.path.dirname(__file__), "assets", "icon.png"))
        root.iconphoto(True, icon)
    except tk.TclError:
        pass
    app = App(root)
    if smoke:
        app.st.check_updates_on_start = False

        def step(i: int = 0) -> None:
            if i < len(TABS):
                app.show_tab(i)
                root.after(150, step, i + 1)
            else:
                root.destroy()
        root.after(300, step)
    root.mainloop()
    return 0
