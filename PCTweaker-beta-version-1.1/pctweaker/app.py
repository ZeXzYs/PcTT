"""PC Tweaker main window (customtkinter)."""
import os
import platform
import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk
import psutil

from . import __version__, helpers
from .admin import is_admin, relaunch_as_admin, run_elevated
from .config import APP_NAME, TOOLS_DIR, Settings, resource_path
from .debloat import APPS, remove_apps
from .fps import PresentMonReader
from .overlay import Overlay
from .sensors import Sensors
from .tools import LAUNCHERS, actions_for, launch
from .tweaks import by_category

BG = "#0e1117"
SIDEBAR = "#131722"
CARD = "#181d2a"
CARD_HOVER = "#212840"
LINE = "#262d3f"
TEXT = "#e8ecf4"
MUTED = "#8891a7"
ACCENT = "#4f8cff"
ACCENT_SOFT = "#1d2943"
OK = "#34d399"
WARN = "#fbbf24"
BAD = "#f87171"

METRIC_LABELS = [
    ("fps", "FPS"), ("cpu_usage", "CPU usage"), ("cpu_temp", "CPU temperature"),
    ("gpu_usage", "GPU usage"), ("gpu_temp", "GPU temperature"), ("vram", "GPU memory"),
    ("ram", "RAM usage"), ("fans", "Fan speeds"), ("refresh", "Refresh rate"),
]


def windows_name() -> str:
    try:
        build = sys.getwindowsversion().build
        return "Windows 11" if build >= 22000 else "Windows 10"
    except Exception:
        return platform.system()


# ======================================================================= shared widgets
class ItemRow(ctk.CTkFrame):
    """One tweak (switch) or one action (button)."""

    def __init__(self, master, app, item):
        super().__init__(master, fg_color=CARD, corner_radius=10)
        self.app, self.item = app, item
        self.grid_columnconfigure(0, weight=1)
        text = ctk.CTkFrame(self, fg_color="transparent")
        text.grid(row=0, column=0, sticky="w", padx=(16, 8), pady=12)
        top = ctk.CTkFrame(text, fg_color="transparent")
        top.pack(anchor="w")
        ctk.CTkLabel(top, text=item.name, font=app.f_bold, text_color=TEXT).pack(side="left")
        if item.admin:
            self._badge(top, "ADMIN", WARN)
        if getattr(item, "reboot", False):
            self._badge(top, "REBOOT", MUTED)
        ctk.CTkLabel(text, text=item.desc, font=app.f_small, text_color=MUTED,
                     wraplength=540, justify="left").pack(anchor="w", pady=(3, 0))
        if item.kind == "toggle":
            self.switch = ctk.CTkSwitch(self, text="", width=44, command=self._toggled,
                                        progress_color=ACCENT, fg_color="#2c3447")
            self.switch.grid(row=0, column=1, padx=(8, 18))
        else:
            self.button = ctk.CTkButton(self, text=item.button, width=120, height=32,
                                        command=self._run, fg_color=ACCENT_SOFT,
                                        hover_color="#27365a", text_color=TEXT)
            self.button.grid(row=0, column=1, padx=(8, 16))

    @staticmethod
    def _badge(parent, text, color):
        ctk.CTkLabel(parent, text=f" {text} ", height=18, corner_radius=5, fg_color="#262d3d",
                     text_color=color, font=ctk.CTkFont("Segoe UI", 10, "bold")
                     ).pack(side="left", padx=(8, 0))

    def set_state(self, applied: bool):
        if applied:
            self.switch.select()
        else:
            self.switch.deselect()

    def _toggled(self):
        t, want = self.item, bool(self.switch.get())
        if t.admin and not is_admin():
            self.set_state(not want)
            self.app.need_admin(t.name)
            return
        self.switch.configure(state="disabled")

        def work():
            msg = t.apply() if want else t.revert()
            return msg, t.is_applied()

        def done(res, err):
            self.switch.configure(state="normal")
            if err:
                self.set_state(not want)
                self.app.say(f"{t.name}: {err}", "bad")
            else:
                self.set_state(res[1])
                self.app.say(res[0], "ok")

        self.app.run_bg(work, done)

    def _run(self):
        it = self.item
        if it.admin and not is_admin():
            self.app.need_admin(it.name)
            return
        if it.ui == "appx":
            AppxDialog(self.app)
            return
        if it.confirm and not messagebox.askyesno(APP_NAME, it.confirm, parent=self.app):
            return
        self.button.configure(state="disabled", text="Working...")

        def done(res, err):
            self.button.configure(state="normal", text=it.button)
            self.app.say(f"{it.name}: {err}" if err else res, "bad" if err else "ok")

        self.app.run_bg(it.run, done)


class ListPage(ctk.CTkFrame):
    def __init__(self, app, title, subtitle, sections, banner=None):
        super().__init__(app.content, fg_color="transparent")
        self.rows = []
        ctk.CTkLabel(self, text=title, font=app.f_title, text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(self, text=subtitle, font=app.f_small, text_color=MUTED).pack(anchor="w", pady=(2, 10))
        if banner:
            bar = ctk.CTkFrame(self, fg_color=ACCENT_SOFT, corner_radius=10)
            bar.pack(fill="x", pady=(0, 6))
            ctk.CTkLabel(bar, text=banner[0], font=app.f_small, text_color=TEXT,
                         wraplength=560, justify="left").pack(side="left", padx=16, pady=10)
            ctk.CTkButton(bar, text=banner[1], width=150, height=30, command=banner[2],
                          fg_color=ACCENT, hover_color="#3d79e8").pack(side="right", padx=12)
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        for heading, items in sections:
            if heading:
                ctk.CTkLabel(scroll, text=heading.upper(), font=ctk.CTkFont("Segoe UI", 11, "bold"),
                             text_color=MUTED).pack(anchor="w", pady=(14, 4))
            for it in items:
                row = ItemRow(scroll, app, it)
                row.pack(fill="x", pady=3)
                if it.kind == "toggle":
                    self.rows.append(row)


class AppxDialog(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Remove built-in apps")
        self.geometry("470x640")
        self.configure(fg_color=BG)
        self.transient(app)
        self.after(200, self._modal)
        ctk.CTkLabel(self, text="Remove built-in apps", font=app.f_title, text_color=TEXT
                     ).pack(anchor="w", padx=20, pady=(18, 0))
        ctk.CTkLabel(self, text="Ticked apps will be uninstalled for all users. You can reinstall "
                     "any of them from the Microsoft Store.", font=app.f_small, text_color=MUTED,
                     wraplength=420, justify="left").pack(anchor="w", padx=20, pady=(2, 8))
        box = ctk.CTkScrollableFrame(self, fg_color=CARD)
        box.pack(fill="both", expand=True, padx=20, pady=6)
        self.checks = []
        for pkg, label, default in APPS:
            cb = ctk.CTkCheckBox(box, text=label, checkbox_width=20, checkbox_height=20,
                                 fg_color=ACCENT, hover_color="#3d79e8")
            cb.pack(anchor="w", pady=5, padx=8)
            if default:
                cb.select()
            self.checks.append((pkg, default, cb))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(6, 14))
        ctk.CTkButton(row, text="Recommended", width=110, fg_color=ACCENT_SOFT, hover_color="#27365a",
                      command=lambda: self._set(lambda d: d)).pack(side="left")
        ctk.CTkButton(row, text="None", width=70, fg_color=ACCENT_SOFT, hover_color="#27365a",
                      command=lambda: self._set(lambda d: False)).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Remove selected", width=140, fg_color="#c0392b", hover_color="#a93226",
                      command=self._go).pack(side="right")
        ctk.CTkButton(row, text="Cancel", width=80, fg_color="transparent", border_width=1,
                      border_color=LINE, command=self.destroy).pack(side="right", padx=6)

    def _modal(self):
        try:
            self.grab_set()
            self.focus()
        except tk.TclError:
            pass

    def _set(self, fn):
        for _, default, cb in self.checks:
            cb.select() if fn(default) else cb.deselect()

    def _go(self):
        names = [pkg for pkg, _, cb in self.checks if cb.get()]
        if not names:
            return
        if not messagebox.askyesno(APP_NAME, f"Remove {len(names)} app(s)?", parent=self):
            return
        self.destroy()
        app = self.app
        app.say("Removing apps - this can take a minute...", "warn")

        def done(res, err):
            if err:
                app.say(f"Remove apps: {err}", "bad")
            else:
                msg = f"Removed {len(res['removed'])} app(s)"
                if res["absent"]:
                    msg += f", {len(res['absent'])} weren't installed"
                if res["kept"]:
                    msg += f", {len(res['kept'])} couldn't be removed"
                app.say(msg + ".", "ok")

        app.run_bg(lambda: remove_apps(names), done)


# ======================================================================= dashboard
class Dashboard(ctk.CTkFrame):
    def __init__(self, app):
        super().__init__(app.content, fg_color="transparent")
        self.app = app
        ctk.CTkLabel(self, text="Dashboard", font=app.f_title, text_color=TEXT).pack(anchor="w")
        info = (f"{windows_name()}  ·  {psutil.cpu_count(logical=True)} threads  ·  "
                f"{psutil.virtual_memory().total / 2 ** 30:.0f} GB RAM")
        ctk.CTkLabel(self, text=info, font=app.f_small, text_color=MUTED).pack(anchor="w", pady=(2, 12))

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure((0, 1), weight=1, uniform="c")
        self.cards = {}
        for i, (key, title) in enumerate([("cpu", "CPU"), ("gpu", "GPU"), ("ram", "Memory"), ("disp", "Display")]):
            card = ctk.CTkFrame(grid, fg_color=CARD, corner_radius=12)
            card.grid(row=i // 2, column=i % 2, sticky="nsew", padx=6, pady=6)
            ctk.CTkLabel(card, text=title.upper(), font=ctk.CTkFont("Segoe UI", 11, "bold"),
                         text_color=MUTED).pack(anchor="w", padx=18, pady=(14, 0))
            value = ctk.CTkLabel(card, text="--", font=ctk.CTkFont("Segoe UI", 30, "bold"), text_color=TEXT)
            value.pack(anchor="w", padx=18)
            bar = None
            if key != "disp":
                bar = ctk.CTkProgressBar(card, height=6, progress_color=ACCENT, fg_color=LINE)
                bar.set(0)
                bar.pack(fill="x", padx=18, pady=(2, 6))
            sub = ctk.CTkLabel(card, text="", font=app.f_small, text_color=MUTED)
            sub.pack(anchor="w", padx=18, pady=(0, 14))
            self.cards[key] = (value, sub, bar)

        quick = ctk.CTkFrame(self, fg_color=CARD, corner_radius=12)
        quick.pack(fill="x", padx=6, pady=(10, 0))
        left = ctk.CTkFrame(quick, fg_color="transparent")
        left.pack(side="left", padx=18, pady=14)
        ctk.CTkLabel(left, text="Performance overlay", font=app.f_bold, text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(left, text="Floating FPS, temperatures, fan speeds and usage readout.",
                     font=app.f_small, text_color=MUTED).pack(anchor="w")
        sw = ctk.CTkSwitch(quick, text="", width=44, progress_color=ACCENT, fg_color="#2c3447")
        sw.configure(command=lambda: app.set_overlay(bool(sw.get())))
        sw.pack(side="right", padx=18)
        app.overlay_switches.append(sw)

        acts = ctk.CTkFrame(self, fg_color="transparent")
        acts.pack(fill="x", padx=6, pady=10)
        for action in [a for a in actions_for("admin") if a.id == "restore_point"] + \
                      [a for a in actions_for("boost") if a.id == "clean_temp"]:
            btn = ctk.CTkButton(acts, text=action.name, height=36, fg_color=ACCENT_SOFT,
                                hover_color="#27365a", text_color=TEXT)
            btn.configure(command=lambda a=action, b=btn: self._act(a, b))
            btn.pack(side="left", padx=(0, 8))

    def _act(self, action, btn):
        if action.admin and not is_admin():
            self.app.need_admin(action.name)
            return
        if action.confirm and not messagebox.askyesno(APP_NAME, action.confirm, parent=self.app):
            return
        btn.configure(state="disabled")

        def done(res, err):
            btn.configure(state="normal")
            self.app.say(f"{action.name}: {err}" if err else res, "bad" if err else "ok")

        self.app.run_bg(action.run, done)

    def update_stats(self, s):
        def pct(v):
            return "--" if v is None else f"{v:.0f}%"

        def deg(v):
            return None if v is None else f"{v:.0f} °C"

        v, sub, bar = self.cards["cpu"]
        v.configure(text=pct(s.get("cpu_usage")))
        bar.set((s.get("cpu_usage") or 0) / 100)
        sub.configure(text=deg(s.get("cpu_temp")) or "temperature: needs LibreHardwareMonitor")

        v, sub, bar = self.cards["gpu"]
        v.configure(text=pct(s.get("gpu_usage")))
        bar.set((s.get("gpu_usage") or 0) / 100)
        parts = [deg(s.get("gpu_temp"))]
        if s.get("vram_total"):
            parts.append(f"{s.get('vram_used', 0) / 1024:.1f}/{s['vram_total'] / 1024:.0f} GB VRAM")
        sub.configure(text="  ·  ".join(p for p in parts if p) or "no GPU sensor data")

        v, sub, bar = self.cards["ram"]
        v.configure(text=pct(s.get("ram_percent")))
        bar.set((s.get("ram_percent") or 0) / 100)
        sub.configure(text=f"{s.get('ram_used', 0):.1f} / {s.get('ram_total', 0):.1f} GB")

        v, sub, _ = self.cards["disp"]
        hz = s.get("refresh")
        v.configure(text="--" if not hz else f"{hz} Hz")
        fps = s.get("fps")
        sub.configure(text=(f"{fps:.0f} FPS  ·  {s.get('fps_app', '')}" if fps else "FPS: start the overlay to measure"))


# ======================================================================= admin tools page
class AdminPage(ctk.CTkFrame):
    def __init__(self, app):
        super().__init__(app.content, fg_color="transparent")
        ctk.CTkLabel(self, text="Admin Tools", font=app.f_title, text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(self, text="Launch Windows' own power tools on demand - each one opens elevated and "
                     "nothing runs until you click it.", font=app.f_small, text_color=MUTED
                     ).pack(anchor="w", pady=(2, 10))
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        ctk.CTkLabel(scroll, text="LAUNCH", font=ctk.CTkFont("Segoe UI", 11, "bold"),
                     text_color=MUTED).pack(anchor="w", pady=(4, 6))
        grid = ctk.CTkFrame(scroll, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure((0, 1, 2), weight=1, uniform="t")
        for i, (label, desc, prog, args, elev) in enumerate(LAUNCHERS):
            b = ctk.CTkButton(grid, text=f"{label}\n{desc}", anchor="w", height=58, corner_radius=10,
                              fg_color=CARD, hover_color=CARD_HOVER, text_color=TEXT,
                              font=ctk.CTkFont("Segoe UI", 12))
            b.configure(command=lambda p=prog, a=args, e=elev, l=label: self._launch(app, l, p, a, e))
            b.grid(row=i // 3, column=i % 3, sticky="nsew", padx=4, pady=4)
        ctk.CTkLabel(scroll, text="MAINTENANCE", font=ctk.CTkFont("Segoe UI", 11, "bold"),
                     text_color=MUTED).pack(anchor="w", pady=(18, 4))
        for a in actions_for("admin"):
            ItemRow(scroll, app, a).pack(fill="x", pady=3)

    @staticmethod
    def _launch(app, label, prog, args, elev):
        try:
            launch(prog, args, elev)
            app.say(f"Opened {label}.", "ok")
        except Exception as e:
            app.say(f"{label}: {e}", "bad")


# ======================================================================= overlay page
class OverlayPage(ctk.CTkFrame):
    def __init__(self, app):
        super().__init__(app.content, fg_color="transparent")
        self.app = app
        cfg = app.settings.overlay
        ctk.CTkLabel(self, text="Performance Overlay", font=app.f_title, text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(self, text="A small always-on-top readout. Drag it anywhere; right-click it to close.",
                     font=app.f_small, text_color=MUTED).pack(anchor="w", pady=(2, 10))
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        card = self._card(scroll)
        left = ctk.CTkFrame(card, fg_color="transparent")
        left.pack(side="left", padx=18, pady=14)
        ctk.CTkLabel(left, text="Show overlay", font=app.f_bold, text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(left, text="Works over windowed and borderless games. Exclusive-fullscreen "
                     "games hide it - switch them to borderless.", font=app.f_small, text_color=MUTED,
                     wraplength=520, justify="left").pack(anchor="w")
        sw = ctk.CTkSwitch(card, text="", width=44, progress_color=ACCENT, fg_color="#2c3447")
        sw.configure(command=lambda: app.set_overlay(bool(sw.get())))
        sw.pack(side="right", padx=18)
        app.overlay_switches.append(sw)

        card = self._card(scroll, vertical=True)
        ctk.CTkLabel(card, text="Metrics", font=app.f_bold, text_color=TEXT).pack(anchor="w", padx=18, pady=(14, 6))
        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.pack(fill="x", padx=18, pady=(0, 14))
        grid.grid_columnconfigure((0, 1, 2), weight=1, uniform="m")
        for i, (key, label) in enumerate(METRIC_LABELS):
            cb = ctk.CTkCheckBox(grid, text=label, checkbox_width=20, checkbox_height=20,
                                 fg_color=ACCENT, hover_color="#3d79e8")
            cb.configure(command=lambda k=key, c=cb: app.set_metric(k, bool(c.get())))
            if cfg["metrics"].get(key):
                cb.select()
            cb.grid(row=i // 3, column=i % 3, sticky="w", pady=5)

        card = self._card(scroll, vertical=True)
        ctk.CTkLabel(card, text="Appearance", font=app.f_bold, text_color=TEXT).pack(anchor="w", padx=18, pady=(14, 6))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=4)
        ctk.CTkLabel(row, text="Opacity", width=120, anchor="w", text_color=MUTED, font=app.f_small).pack(side="left")
        slider = ctk.CTkSlider(row, from_=0.3, to=1.0, number_of_steps=14, width=220, progress_color=ACCENT,
                               button_color=ACCENT, button_hover_color="#3d79e8",
                               command=lambda v: app.set_overlay_value("opacity", round(float(v), 2)))
        slider.set(cfg["opacity"])
        slider.pack(side="left")
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=4)
        ctk.CTkLabel(row, text="Update rate", width=120, anchor="w", text_color=MUTED, font=app.f_small).pack(side="left")
        seg = ctk.CTkSegmentedButton(row, values=["0.5 s", "1 s", "2 s"], selected_color=ACCENT,
                                     command=lambda v: app.set_interval(float(v.split()[0])))
        seg.set(f"{cfg['interval']:g} s" if f"{cfg['interval']:g} s" in ("0.5 s", "1 s", "2 s") else "1 s")
        seg.pack(side="left")
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(4, 14))
        ctk.CTkLabel(row, text="Click-through", width=120, anchor="w", text_color=MUTED, font=app.f_small).pack(side="left")
        ct = ctk.CTkSwitch(row, text="mouse clicks pass through (can't drag while on)", width=44,
                           progress_color=ACCENT, fg_color="#2c3447", font=app.f_small, text_color=MUTED)
        ct.configure(command=lambda: app.set_overlay_value("click_through", bool(ct.get())))
        if cfg["click_through"]:
            ct.select()
        ct.pack(side="left")
        ctk.CTkButton(row, text="Reset position", width=120, height=28, fg_color=ACCENT_SOFT,
                      hover_color="#27365a", command=app.overlay.reset_position).pack(side="right")

        card = self._card(scroll, vertical=True)
        ctk.CTkLabel(card, text="Data sources", font=app.f_bold, text_color=TEXT).pack(anchor="w", padx=18, pady=(14, 6))
        self.status = {}
        for key, title in (("gpu", "GPU (NVIDIA / Windows counters)"),
                           ("lhm", "CPU temperature & fan speeds"),
                           ("fps", "FPS counter (PresentMon)")):
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=2)
            dot = ctk.CTkLabel(row, text="●", width=18, text_color=MUTED)
            dot.pack(side="left")
            ctk.CTkLabel(row, text=title, width=250, anchor="w", font=app.f_small, text_color=TEXT).pack(side="left")
            msg = ctk.CTkLabel(row, text="", anchor="w", font=app.f_small, text_color=MUTED, wraplength=360, justify="left")
            msg.pack(side="left", fill="x")
            self.status[key] = (dot, msg)
        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(fill="x", padx=18, pady=(10, 14))
        self.dl_btn = ctk.CTkButton(btns, text="Download helper tools", height=32, fg_color=ACCENT,
                                    hover_color="#3d79e8", command=self._download)
        self.dl_btn.pack(side="left")
        ctk.CTkButton(btns, text="Start sensor service", height=32, fg_color=ACCENT_SOFT, hover_color="#27365a",
                      command=self._start_lhm).pack(side="left", padx=8)
        ctk.CTkButton(btns, text="Open tools folder", height=32, fg_color=ACCENT_SOFT, hover_color="#27365a",
                      command=self._open_tools).pack(side="left")
        ctk.CTkLabel(card, text="NVIDIA GPU data works out of the box. CPU temperature and fan RPM need "
                     "LibreHardwareMonitor running as administrator; the FPS counter needs PresentMon and "
                     "PC Tweaker running as administrator. Both helpers are free and downloaded from GitHub.",
                     font=app.f_small, text_color=MUTED, wraplength=640, justify="left"
                     ).pack(anchor="w", padx=18, pady=(0, 14))

    @staticmethod
    def _card(parent, vertical=False):
        c = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=12)
        c.pack(fill="x", pady=5)
        return c

    def _download(self):
        self.dl_btn.configure(state="disabled", text="Downloading...")
        self.app.say("Downloading PresentMon and LibreHardwareMonitor from GitHub...", "warn")

        def done(res, err):
            self.dl_btn.configure(state="normal", text="Download helper tools")
            self.app.say(f"Download failed: {err}" if err else res, "bad" if err else "ok")
            self.app.ensure_fps()

        self.app.run_bg(helpers.download_all, done)

    def _start_lhm(self):
        exe = helpers.lhm_path()
        if not exe:
            self.app.say("LibreHardwareMonitor isn't downloaded yet - click 'Download helper tools'.", "warn")
            return
        ok = run_elevated(str(exe), "", 1)
        self.app.say("Started LibreHardwareMonitor. Keep it running (minimise it) for temperatures and fan "
                     "speeds." if ok else "Could not start it (UAC declined?).", "ok" if ok else "bad")

    def _open_tools(self):
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(TOOLS_DIR))

    def update_status(self, st, fps):
        def put(key, ok, text):
            dot, msg = self.status[key]
            dot.configure(text_color=OK if ok else WARN)
            msg.configure(text=text)

        put("gpu", st.get("nvml") or st.get("gpu_counters") or st.get("lhm"),
            "NVIDIA sensors active" if st.get("nvml") else
            "Using Windows GPU counters" if st.get("gpu_counters") else
            "Active via LibreHardwareMonitor" if st.get("lhm") else "No GPU data yet")
        put("lhm", st.get("lhm"), "Active" if st.get("lhm") else "Not running - start LibreHardwareMonitor")
        if fps.running:
            put("fps", True, "Active" + (f" - {fps.current_app}" if fps.current_app else " - waiting for a game"))
        elif not fps.available:
            put("fps", False, "PresentMon not downloaded")
        elif not is_admin():
            put("fps", False, "Restart PC Tweaker as administrator")
        else:
            put("fps", False, fps.last_error or "Stopped (turns on with the overlay)")


# ======================================================================= main window
class App(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("dark")
        super().__init__()
        self.title(f"{APP_NAME} {__version__}")
        self.geometry("1080x720")
        self.minsize(960, 620)
        self.configure(fg_color=BG)
        self.after(250, self._set_icon)

        self.f_title = ctk.CTkFont("Segoe UI", 24, "bold")
        self.f_bold = ctk.CTkFont("Segoe UI", 14, "bold")
        self.f_small = ctk.CTkFont("Segoe UI", 12)

        self.settings = Settings()
        self.fps = PresentMonReader()
        self.sensors = Sensors(self.fps)
        self.sensors.interval = float(self.settings.overlay["interval"])
        self.overlay = Overlay(self, self.sensors, self.settings)
        self.overlay.on_hidden = self._overlay_hidden
        self.overlay_switches = []
        self.uiq = queue.Queue()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=1)
        self.content = ctk.CTkFrame(main, fg_color="transparent")
        self.content.grid(row=0, column=0, sticky="nsew", padx=26, pady=(22, 0))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        bar = ctk.CTkFrame(main, fg_color=SIDEBAR, corner_radius=0, height=34)
        bar.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.status_label = ctk.CTkLabel(bar, text="Ready.", font=self.f_small, text_color=MUTED, anchor="w")
        self.status_label.pack(side="left", padx=18, pady=6)

        self.dashboard = Dashboard(self)
        self.overlay_page = OverlayPage(self)
        self.pages = {
            "Dashboard": self.dashboard,
            "FPS & Boost": ListPage(self, "FPS & Boost", "Performance tweaks. Every switch can be turned back off "
                                    "to restore your previous setting.",
                                    [("Tweaks", by_category("boost")), ("Quick actions", actions_for("boost"))]),
            "Debloat": ListPage(self, "Debloat & Privacy", "Cut background noise, telemetry and preinstalled clutter.",
                                [("Privacy & services", by_category("debloat")), ("Apps", actions_for("debloat"))],
                                banner=("Tip: create a restore point before making system-wide changes.",
                                        "Create restore point", self._restore_point)),
            "Customise": ListPage(self, "Customise", "Make Windows look and behave the way you like.",
                                  [("Look & feel", by_category("customise")), ("Apply", actions_for("customise"))]),
            "Admin Tools": AdminPage(self),
            "Overlay": self.overlay_page,
        }
        self.show("Dashboard")
        self.after(80, self._drain)
        self.after(500, self._tick_ui)
        self.sensors.start()
        self.refresh_states()
        if self.settings.overlay["enabled"]:
            self.after(700, lambda: self.set_overlay(True))
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------------------------------------------------------- layout
    def _set_icon(self):
        try:
            self.iconbitmap(str(resource_path("assets/icon.ico")))
        except Exception:
            pass

    def _build_sidebar(self):
        side = ctk.CTkFrame(self, width=210, corner_radius=0, fg_color=SIDEBAR)
        side.grid(row=0, column=0, sticky="nsw")
        side.grid_propagate(False)
        side.grid_rowconfigure(10, weight=1)
        ctk.CTkLabel(side, text="PC Tweaker", font=ctk.CTkFont("Segoe UI", 21, "bold"), text_color=TEXT
                     ).grid(row=0, column=0, sticky="w", padx=22, pady=(24, 0))
        ctk.CTkLabel(side, text=f"v{__version__}  ·  Windows", font=self.f_small, text_color=MUTED
                     ).grid(row=1, column=0, sticky="w", padx=22, pady=(0, 18))
        self.nav = {}
        for i, name in enumerate(["Dashboard", "FPS & Boost", "Debloat", "Customise", "Admin Tools", "Overlay"]):
            b = ctk.CTkButton(side, text=name, anchor="w", height=40, corner_radius=8, width=176,
                              font=ctk.CTkFont("Segoe UI", 13, "bold"), fg_color="transparent",
                              hover_color="#1b2130", text_color=MUTED, command=lambda n=name: self.show(n))
            b.grid(row=2 + i, column=0, padx=17, pady=2)
            self.nav[name] = b
        box = ctk.CTkFrame(side, fg_color=CARD, corner_radius=10)
        box.grid(row=11, column=0, padx=14, pady=16, sticky="ew")
        admin = is_admin()
        ctk.CTkLabel(box, text="● Administrator" if admin else "● Standard user", font=self.f_small,
                     text_color=OK if admin else WARN).pack(anchor="w", padx=14, pady=(10, 2))
        if not admin:
            ctk.CTkLabel(box, text="Some tweaks need admin rights.", font=ctk.CTkFont("Segoe UI", 11),
                         text_color=MUTED, wraplength=150, justify="left").pack(anchor="w", padx=14)
            ctk.CTkButton(box, text="Restart as admin", height=30, fg_color=ACCENT, hover_color="#3d79e8",
                          command=lambda: self.need_admin("PC Tweaker", ask=False)).pack(padx=12, pady=10, fill="x")
        else:
            ctk.CTkLabel(box, text="All tools unlocked.", font=ctk.CTkFont("Segoe UI", 11),
                         text_color=MUTED).pack(anchor="w", padx=14, pady=(0, 10))

    def show(self, name):
        for n, page in self.pages.items():
            if n == name:
                page.grid(row=0, column=0, sticky="nsew")
            else:
                page.grid_remove()
        for n, b in self.nav.items():
            b.configure(fg_color=ACCENT_SOFT if n == name else "transparent",
                        text_color=TEXT if n == name else MUTED)

    # ---------------------------------------------------------------- helpers
    def say(self, text, kind="info"):
        color = {"ok": OK, "bad": BAD, "warn": WARN}.get(kind, MUTED)
        self.status_label.configure(text=" ".join(str(text).split())[:220], text_color=color)

    def run_bg(self, fn, done=None):
        def work():
            try:
                res, err = fn(), None
            except Exception as e:  # shown to the user in the status bar
                res, err = None, e
            if done:
                self.uiq.put(lambda: done(res, err))
        threading.Thread(target=work, daemon=True).start()

    def _drain(self):
        try:
            while True:
                self.uiq.get_nowait()()
        except queue.Empty:
            pass
        self.after(80, self._drain)

    def need_admin(self, what, ask=True):
        if ask and not messagebox.askyesno(
                "Administrator needed",
                f"'{what}' changes system-wide settings and needs administrator rights.\n\n"
                "Restart PC Tweaker as administrator now?", parent=self):
            return
        if relaunch_as_admin():
            self.on_close()
        else:
            self.say("Elevation was cancelled.", "warn")

    def _restore_point(self):
        action = next(a for a in actions_for("admin") if a.id == "restore_point")
        if not is_admin():
            self.need_admin(action.name)
            return
        self.say("Creating restore point...", "warn")
        self.run_bg(action.run, lambda r, e: self.say(f"{action.name}: {e}" if e else r, "bad" if e else "ok"))

    def refresh_states(self):
        rows = [r for p in self.pages.values() if isinstance(p, ListPage) for r in p.rows]

        def work():
            out = []
            for r in rows:
                try:
                    out.append((r, r.item.is_applied()))
                except Exception:
                    out.append((r, False))
            return out

        def done(res, err):
            for r, ok in res or []:
                r.set_state(ok)

        self.run_bg(work, done)

    # ---------------------------------------------------------------- overlay control
    def set_overlay(self, on: bool):
        if on and not self.overlay.visible:
            self.overlay.show()
            self.ensure_fps()
        elif not on and self.overlay.visible:
            self.overlay.hide()
        self._sync_switches()

    def _overlay_hidden(self):
        self.fps.stop()
        self._sync_switches()

    def _sync_switches(self):
        for sw in self.overlay_switches:
            sw.select() if self.overlay.visible else sw.deselect()

    def set_metric(self, key, on):
        self.settings.overlay["metrics"][key] = on
        self.settings.save()
        self.overlay.refresh()
        if key == "fps":
            self.ensure_fps() if on else self.fps.stop()

    def set_overlay_value(self, key, value):
        self.settings.overlay[key] = value
        self.settings.save()
        self.overlay.apply_settings()

    def set_interval(self, seconds):
        self.settings.overlay["interval"] = seconds
        self.sensors.interval = seconds
        self.settings.save()

    def ensure_fps(self):
        """Start PresentMon when the overlay wants FPS and everything needed is present."""
        if not (self.overlay.visible and self.settings.overlay["metrics"].get("fps")):
            return
        if self.fps.running or not self.fps.available:
            return
        if not is_admin():
            self.say("FPS counter needs PC Tweaker running as administrator (sidebar > Restart as admin).", "warn")
            return
        self.run_bg(self.fps.start, lambda r, e: self.say(
            r[1] if r and r[0] else f"FPS counter: {(r[1] if r else e)}", "ok" if r and r[0] else "warn"))

    # ---------------------------------------------------------------- periodic UI refresh
    def _tick_ui(self):
        try:
            self.dashboard.update_stats(self.sensors.snapshot())
            self.overlay_page.update_status(self.sensors.status, self.fps)
        except Exception:
            pass
        self.after(1000, self._tick_ui)

    def on_close(self):
        try:
            if self.overlay.visible:
                keep = self.settings.overlay["enabled"]
                self.overlay.hide()
                self.settings.overlay["enabled"] = keep
            self.settings.save()
            self.fps.stop()
            self.sensors.stop()
        finally:
            self.destroy()
