"""Always-on-top performance overlay (borderless tkinter window)."""
import tkinter as tk

from . import winapi

BG = "#0b0e14"
COLORS = {
    "label": "#7d879c", "value": "#f1f4fa", "accent": "#5b9dff",
    "ok": "#3ddc97", "warn": "#ffc857", "hot": "#ff6b6b", "dim": "#586073",
}


def _temp_tag(t):
    return "ok" if t < 70 else "warn" if t < 85 else "hot"


def _num(v, fmt):
    return "--" if v is None else fmt.format(v)


def build_lines(s: dict, m: dict):
    """Turn a sensor snapshot into [(label, [(text, tag), ...]), ...] using the enabled metrics."""
    rows = []
    if m.get("fps"):
        fps = s.get("fps")
        rows.append(("FPS", [(_num(fps, "{:.0f}"), "accent" if fps else "dim")]))

    def usage_temp(label, u_key, t_key, mem=False):
        seg = []
        if m.get(u_key):
            seg.append((_num(s.get(u_key), "{:.0f}%"), "value"))
        if m.get(t_key):
            t = s.get(t_key)
            if seg:
                seg.append(("  ", "value"))
            seg.append((_num(t, "{:.0f}°C"), _temp_tag(t) if t is not None else "dim"))
        if mem and m.get("vram") and s.get("vram_total"):
            if seg:
                seg.append(("  ", "value"))
            seg.append((f"{s.get('vram_used', 0) / 1024:.1f}/{s['vram_total'] / 1024:.0f} GB", "label"))
        if seg:
            rows.append((label, seg))

    usage_temp("CPU", "cpu_usage", "cpu_temp")
    usage_temp("GPU", "gpu_usage", "gpu_temp", mem=True)
    if m.get("ram"):
        seg = [(_num(s.get("ram_percent"), "{:.0f}%"), "value")]
        if s.get("ram_total"):
            seg += [("  ", "value"), (f"{s.get('ram_used', 0):.1f}/{s['ram_total']:.0f} GB", "label")]
        rows.append(("RAM", seg))
    if m.get("refresh"):
        rows.append(("DISP", [(_num(s.get("refresh"), "{:.0f} Hz"), "value")]))
    if m.get("fans"):
        shown = [f for f in s.get("fans", []) if f[1] and f[1] > 0][:4]
        if shown:
            for name, val, unit in shown:
                label = name.replace("Fan", "").replace("fan", "").strip() or "FAN"
                label = ("FAN " + label if label.startswith("#") else label)[:11]
                rows.append((label, [(f"{val:.0f} {unit}", "value")]))
        else:
            rows.append(("FANS", [("--", "dim")]))
    return rows


class Overlay:
    def __init__(self, root, sensors, settings):
        self.root, self.sensors, self.settings = root, sensors, settings
        self.win = None
        self.text = None
        self._drag = (0, 0)
        self._job = None
        self.on_hidden = None

    @property
    def visible(self) -> bool:
        return self.win is not None

    def show(self):
        if self.win:
            return
        cfg = self.settings.overlay
        cfg["enabled"] = True
        self.settings.save()
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.configure(bg=BG)
        w.attributes("-topmost", True)
        w.attributes("-alpha", cfg["opacity"])
        w.geometry(f"+{int(cfg['x'])}+{int(cfg['y'])}")
        t = tk.Text(w, bg=BG, fg=COLORS["value"], bd=0, highlightthickness=0, padx=14, pady=10,
                    font=("Consolas", 11), wrap="none", cursor="fleur", takefocus=0,
                    spacing1=1, spacing3=1, state="disabled")
        t.pack()
        for tag, color in COLORS.items():
            t.tag_configure(tag, foreground=color)
        t.tag_configure("accent", foreground=COLORS["accent"], font=("Consolas", 11, "bold"))
        for widget in (w, t):
            widget.bind("<ButtonPress-1>", self._press)
            widget.bind("<B1-Motion>", self._motion)
            widget.bind("<ButtonRelease-1>", self._release)
            widget.bind("<Button-3>", lambda e: self.hide())
        self.win, self.text = w, t
        w.update_idletasks()
        self._style()
        self._tick()

    def hide(self):
        if self._job and self.win:
            try:
                self.win.after_cancel(self._job)
            except Exception:
                pass
        self._job = None
        if self.win:
            self.win.destroy()
        self.win = self.text = None
        self.settings.overlay["enabled"] = False
        self.settings.save()
        if self.on_hidden:
            self.on_hidden()

    def _style(self):
        try:
            winapi.set_overlay_style(winapi.toplevel_hwnd(self.win),
                                     bool(self.settings.overlay["click_through"]))
        except Exception:
            pass

    def apply_settings(self):
        if not self.win:
            return
        self.win.attributes("-alpha", self.settings.overlay["opacity"])
        self._style()
        self.text.configure(cursor="arrow" if self.settings.overlay["click_through"] else "fleur")
        self.refresh()

    def reset_position(self):
        self.settings.overlay.update(x=30, y=30)
        self.settings.save()
        if self.win:
            self.win.geometry("+30+30")

    # ---- dragging
    def _press(self, e):
        self._drag = (e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y())

    def _motion(self, e):
        self.win.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    def _release(self, _):
        self.settings.overlay.update(x=self.win.winfo_x(), y=self.win.winfo_y())
        self.settings.save()

    # ---- drawing
    def refresh(self):
        if not self.win:
            return
        rows = build_lines(self.sensors.snapshot(), self.settings.overlay["metrics"])
        width = max([len(lbl) for lbl, _ in rows] + [4]) + 2
        t = self.text
        t.configure(state="normal")
        t.delete("1.0", "end")
        for i, (label, segs) in enumerate(rows):
            t.insert("end", label.ljust(width), "label")
            for txt, tag in segs:
                t.insert("end", txt, tag)
            if i < len(rows) - 1:
                t.insert("end", "\n")
        if not rows:
            t.insert("end", "No metrics selected", "dim")
        t.configure(state="disabled", width=max(
            (width + sum(len(x) for x, _ in segs) for _, segs in rows), default=20),
            height=max(len(rows), 1))

    def _tick(self):
        if not self.win:
            return
        self.refresh()
        try:
            self.win.attributes("-topmost", True)
            self.win.lift()
        except Exception:
            pass
        ms = int(max(0.25, float(self.settings.overlay["interval"])) * 1000)
        self._job = self.win.after(ms, self._tick)
