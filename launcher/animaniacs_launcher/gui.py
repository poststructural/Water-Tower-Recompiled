"""The launcher window (tkinter, so it runs wherever Python does)."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from . import REPO, __version__, build, config, gamefiles, play, updates

CHANNELS = {"release": "Releases", "main": "Latest main (newest commit)"}


def _open_folder(path: str) -> None:
    os.makedirs(path, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 - a folder the launcher owns
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.st = config.Settings.load()
        self.events: queue.Queue = queue.Queue()
        self.busy = False
        self.cancel = threading.Event()
        self.latest: updates.GameVersion | None = None
        self.game: subprocess.Popen | None = None

        root.title("Animaniacs: The Great Edgar Hunt — Recompiled")
        root.minsize(640, 520)
        self._build_ui()
        self.refresh()
        root.after(100, self._pump)
        if self.st.check_updates_on_start:
            self.check_updates(quiet=True)

    # ── Layout ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        r = self.root
        pad = {"padx": 12, "pady": 6}
        head = ttk.Frame(r)
        head.pack(fill="x", **pad)
        ttk.Label(head, text="Animaniacs: The Great Edgar Hunt",
                  font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(head, text=f"Recompiled launcher {__version__}").pack(anchor="w")
        self.launcher_banner = ttk.Label(head, foreground="#0a58ca", cursor="hand2")
        self.launcher_banner.pack(anchor="w")

        g = ttk.LabelFrame(r, text="Game files")
        g.pack(fill="x", **pad)
        self.game_label = ttk.Label(g, wraplength=580, justify="left")
        self.game_label.pack(anchor="w", padx=8, pady=4)
        gb = ttk.Frame(g)
        gb.pack(anchor="w", padx=8, pady=(0, 8))
        self.btn_image = ttk.Button(gb, text="Use a disc image or .zip…", command=self.pick_image)
        self.btn_image.pack(side="left")
        self.btn_folder = ttk.Button(gb, text="Use a game folder…", command=self.pick_folder)
        self.btn_folder.pack(side="left", padx=6)

        b = ttk.LabelFrame(r, text="Game build")
        b.pack(fill="x", **pad)
        self.build_label = ttk.Label(b, wraplength=580, justify="left")
        self.build_label.pack(anchor="w", padx=8, pady=4)
        self.tools_label = ttk.Label(b, wraplength=580, justify="left")
        self.tools_label.pack(anchor="w", padx=8)
        bb = ttk.Frame(b)
        bb.pack(fill="x", padx=8, pady=(4, 8))
        ttk.Label(bb, text="Follow:").pack(side="left")
        self.channel = tk.StringVar(value=CHANNELS.get(self.st.channel, CHANNELS["release"]))
        cb = ttk.Combobox(bb, textvariable=self.channel, values=list(CHANNELS.values()),
                          state="readonly", width=28)
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", self._channel_changed)
        self.btn_check = ttk.Button(bb, text="Check for updates", command=self.check_updates)
        self.btn_check.pack(side="left", padx=6)
        self.btn_update = ttk.Button(bb, text="Update", command=self.update)
        self.btn_update.pack(side="left")
        self.btn_tools = ttk.Button(bb, text="Install missing tools", command=self.install_tools)

        p = ttk.Frame(r)
        p.pack(fill="x", **pad)
        self.btn_play = ttk.Button(p, text="▶  Play", command=self.play)
        self.btn_play.pack(side="left", ipadx=24, ipady=8)
        side = ttk.Frame(p)
        side.pack(side="right")
        ttk.Button(side, text="Saves", command=lambda: _open_folder(config.save_dir())).pack(side="left")
        ttk.Button(side, text="Logs", command=lambda: _open_folder(config.sub("logs"))).pack(side="left", padx=4)
        ttk.Button(side, text="Settings", command=self.settings).pack(side="left")

        prog = ttk.Frame(r)
        prog.pack(fill="x", **pad)
        self.step = ttk.Label(prog, text="")
        self.step.pack(anchor="w")
        row = ttk.Frame(prog)
        row.pack(fill="x")
        self.bar = ttk.Progressbar(row, mode="determinate")
        self.bar.pack(side="left", fill="x", expand=True)
        self.btn_cancel = ttk.Button(row, text="Cancel", command=self.cancel.set, state="disabled")
        self.btn_cancel.pack(side="left", padx=6)

        self.log = ScrolledText(r, height=10, state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, **pad)

    # ── State ───────────────────────────────────────────────────────────

    def refresh(self) -> None:
        st = self.st
        if st.game_dir:
            chk = gamefiles.check_dir(st.game_dir)
            self.game_ok = chk.ok
            self.game_label.config(
                text=f"✓ {chk.summary()}\n{st.game_dir}" if chk.ok
                else f"✗ {st.game_dir}: {chk.summary()}")
        else:
            self.game_ok = False
            self.game_label.config(text="Point the launcher at your own copy of the game: an Xbox "
                                        "disc image (.iso), a .zip, or a folder with default.xbe. "
                                        "Nothing is downloaded; the game is built from your files.")

        why = build.supported()
        installed = st.custom_exe or st.current_build or "nothing yet"
        line = f"Installed: {installed}"
        if self.latest:
            note = " (no releases yet, following main)" if self.latest.fell_back else ""
            if self.latest.name == st.current_build:
                line += f" — up to date{note}"
            else:
                line += f"\nAvailable: {self.latest.name}{note}"
                if self.latest.notes:
                    line += f" — {self.latest.notes.strip().splitlines()[0][:90]}"
        self.build_label.config(text=line)

        tc = build.detect()
        self.tools = tc
        if why:
            self.tools_label.config(text=why)
        elif tc.ok:
            self.tools_label.config(text="Build tools: ready")
        else:
            self.tools_label.config(text="Needed to build: " + ", ".join(tc.missing))
        if not why and not tc.ok and sys.platform == "win32":
            self.btn_tools.pack(side="left", padx=6)
        else:
            self.btn_tools.pack_forget()

        idle = "disabled" if self.busy else "normal"
        for btn in (self.btn_image, self.btn_folder, self.btn_check):
            btn.config(state=idle)
        can_build = not self.busy and self.game_ok and not why and tc.git and tc.bash
        self.btn_update.config(state="normal" if can_build else "disabled",
                               text="Build" if not st.current_build else "Update")
        can_play = not self.busy and self.game_ok and (st.current_build or st.custom_exe) \
            and not (self.game and self.game.poll() is None)
        self.btn_play.config(state="normal" if can_play else "disabled")
        self.btn_cancel.config(state="normal" if self.busy else "disabled")

    def _channel_changed(self, _e=None) -> None:
        inv = {v: k for k, v in CHANNELS.items()}
        self.st.channel = inv[self.channel.get()]
        self.st.save()
        self.latest = None
        self.check_updates()

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
                        self.bar.config(mode="determinate", maximum=total, value=done)
                elif kind == "pulse" and self.busy:
                    self.bar.config(mode="indeterminate")
                    self.bar.start(15)
                elif kind == "call":
                    a[0]()
        except queue.Empty:
            pass
        if self.game and self.game.poll() is not None:
            code = self.game.returncode
            self.game = None
            self._log(f"Game exited (code {code})")
            self.refresh()
        self.root.after(100, self._pump)

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
                self.step.config(text="Cancelled" if cancelled else f"{title} failed")
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

    def check_updates(self, quiet: bool = False) -> None:
        def work():
            v = updates.latest_game(self.st.channel, self.st.include_prereleases)
            try:
                lr = updates.latest_launcher()
            except updates.UpdateError:
                lr = None
            return v, lr

        def done(res):
            v, lr = res
            self.latest = v
            self._log(f"Newest version: {v.name}"
                      + (" (no releases yet, using main)" if v.fell_back else ""))
            if lr:
                self.launcher_banner.config(
                    text=f"Launcher {lr.version} is available — click to install")
                self.launcher_banner.bind("<Button-1>", lambda _e: self.update_launcher(lr))
        if quiet and self.busy:
            return
        self._run("Checking for updates", work, done, pulse=True, quiet=quiet)

    def update(self) -> None:
        if not self.latest:
            # Check first, then build what the check found.
            def work():
                return updates.latest_game(self.st.channel, self.st.include_prereleases)

            def done(v):
                self.latest = v
                self.update()
            self._run("Checking for updates", work, done, pulse=True)
            return
        v = self.latest
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

    def update_launcher(self, lr: updates.LauncherRelease) -> None:
        if not lr.installer_url:
            webbrowser.open(lr.page_url)
            return

        def work():
            dest = config.sub(f"AnimaniacsLauncherSetup-{lr.version}.exe")
            return updates.download(lr.installer_url, dest, self._progress)

        def done(path):
            subprocess.Popen([path, "/SILENT"])
            self.root.destroy()
        self._run(f"Downloading launcher {lr.version}", work, done)

    def play(self) -> None:
        try:
            self.game, log = play.launch(self.st)
        except play.PlayError as e:
            messagebox.showerror("Play", str(e))
            return
        self._log(f"Game started (log: {log})")
        self.refresh()

    def settings(self) -> None:
        SettingsDialog(self)


class SettingsDialog:
    def __init__(self, app: App):
        self.app = app
        st = app.st
        w = self.w = tk.Toplevel(app.root)
        w.title("Settings")
        w.transient(app.root)
        w.resizable(False, False)
        f = ttk.Frame(w, padding=12)
        f.pack(fill="both")

        self.vars = {
            "check_updates_on_start": tk.BooleanVar(value=st.check_updates_on_start),
            "include_prereleases": tk.BooleanVar(value=st.include_prereleases),
            "show_console": tk.BooleanVar(value=st.show_console),
            "keep_builds": tk.IntVar(value=st.keep_builds),
            "ghidra_home": tk.StringVar(value=st.ghidra_home),
            "java_home": tk.StringVar(value=st.java_home),
            "custom_exe": tk.StringVar(value=st.custom_exe),
        }
        ttk.Checkbutton(f, text="Check for updates when the launcher opens",
                        variable=self.vars["check_updates_on_start"]).grid(sticky="w", columnspan=3)
        ttk.Checkbutton(f, text="Include pre-releases",
                        variable=self.vars["include_prereleases"]).grid(sticky="w", columnspan=3)
        ttk.Checkbutton(f, text="Show the game's console (applies to the next build)",
                        variable=self.vars["show_console"]).grid(sticky="w", columnspan=3)
        row = ttk.Frame(f)
        row.grid(sticky="w", columnspan=3, pady=4)
        ttk.Label(row, text="Older builds to keep for rolling back:").pack(side="left")
        ttk.Spinbox(row, from_=0, to=5, width=4, textvariable=self.vars["keep_builds"]).pack(side="left", padx=6)

        def path_row(label, key, pick):
            ttk.Label(f, text=label).grid(sticky="w", columnspan=3, pady=(8, 0))
            r = f.grid_size()[1]
            ttk.Entry(f, textvariable=self.vars[key], width=50).grid(row=r, column=0, columnspan=2, sticky="we")
            ttk.Button(f, text="…", width=3, command=pick).grid(row=r, column=2, padx=4)

        path_row("Ghidra 12 folder (optional: function names in crash logs)", "ghidra_home",
                 lambda: self._dir("ghidra_home"))
        path_row("JDK 21 folder (for Ghidra)", "java_home", lambda: self._dir("java_home"))
        path_row("Play this executable instead of the launcher's build (developers)", "custom_exe",
                 self._exe)

        builds = build.installed()
        if builds:
            ttk.Label(f, text="Installed builds (double-click to switch):").grid(sticky="w", columnspan=3, pady=(8, 0))
            lb = tk.Listbox(f, height=min(5, len(builds)))
            for b in builds:
                mark = "  (current)" if b["name"] == st.current_build else ""
                lb.insert("end", f"{b['name']}  —  built {b.get('built', '?')}{mark}")
            lb.grid(sticky="we", columnspan=3)
            lb.bind("<Double-Button-1>", lambda _e: self._switch(builds[lb.curselection()[0]]["name"]))

        bb = ttk.Frame(f)
        bb.grid(sticky="e", columnspan=3, pady=(12, 0))
        ttk.Button(bb, text="Project page",
                   command=lambda: webbrowser.open(f"https://github.com/{REPO}")).pack(side="left")
        ttk.Button(bb, text="Cancel", command=w.destroy).pack(side="left", padx=6)
        ttk.Button(bb, text="Save", command=self.save).pack(side="left")

    def _dir(self, key: str) -> None:
        p = filedialog.askdirectory(parent=self.w)
        if p:
            self.vars[key].set(p)

    def _exe(self) -> None:
        p = filedialog.askopenfilename(parent=self.w, filetypes=[("Programs", "*.exe"), ("All", "*")])
        if p:
            self.vars["custom_exe"].set(p)

    def _switch(self, name: str) -> None:
        build.carry_settings(self.app.st.current_build, config.sub("builds", name))
        self.app.st.current_build = name
        self.app.st.save()
        self.app.refresh()
        self.w.destroy()

    def save(self) -> None:
        st = self.app.st
        for k, v in self.vars.items():
            setattr(st, k, v.get())
        st.save()
        self.app.refresh()
        self.w.destroy()


def run() -> int:
    root = tk.Tk()
    try:
        ttk.Style(root).theme_use("vista" if sys.platform == "win32" else "clam")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()
    return 0
