"""FPS counter powered by Intel's PresentMon (ETW based, works for DX9-12/Vulkan/OpenGL)."""
import subprocess
import threading
import time
from collections import deque

from . import winapi
from .admin import CREATE_NO_WINDOW, is_admin
from .config import data_dir
from .helpers import presentmon_path

IGNORED = {"dwm.exe", "explorer.exe", "searchhost.exe", "shellexperiencehost.exe"}


def parse_header(line: str):
    cols = [c.strip().lower() for c in line.split(",")]
    if "application" in cols and "processid" in cols and "msbetweenpresents" in cols:
        return {c: i for i, c in enumerate(cols)}
    return None


def parse_row(header: dict, line: str):
    """-> (app, pid, frame_ms) or None."""
    parts = line.split(",")
    try:
        app = parts[header["application"]].strip()
        pid = int(parts[header["processid"]])
        ms = float(parts[header["msbetweenpresents"]])
    except (KeyError, ValueError, IndexError):
        return None
    return (app, pid, ms) if ms > 0 else None


class PresentMonReader:
    def __init__(self):
        self.proc = None
        self.frames = {}          # pid -> deque[(arrival, ms)]
        self.names = {}
        self.lock = threading.Lock()
        self.last_error = ""
        self.current_app = ""

    @property
    def available(self) -> bool:
        return presentmon_path() is not None

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self):
        """Returns (ok, message)."""
        if self.running:
            return True, "FPS counter running."
        exe = presentmon_path()
        if not exe:
            self.last_error = "PresentMon not found in the tools folder."
            return False, self.last_error
        if not is_admin():
            self.last_error = "The FPS counter needs PC Tweaker to run as administrator."
            return False, self.last_error
        log = open(data_dir() / "presentmon.log", "w", encoding="utf-8", errors="replace")
        try:
            self.proc = subprocess.Popen(
                [str(exe), "--output_stdout", "--stop_existing_session",
                 "--no_console_stats", "--v1_metrics"],
                stdout=subprocess.PIPE, stderr=log, stdin=subprocess.DEVNULL,
                text=True, bufsize=1, errors="replace", creationflags=CREATE_NO_WINDOW)
        except OSError as e:
            self.last_error = f"Could not start PresentMon: {e}"
            return False, self.last_error
        time.sleep(0.8)
        if self.proc.poll() is not None:
            log.flush()
            try:
                msg = (data_dir() / "presentmon.log").read_text(errors="replace").strip()
            except OSError:
                msg = ""
            self.last_error = msg.splitlines()[-1] if msg else "PresentMon exited immediately."
            self.proc = None
            return False, self.last_error
        self.last_error = ""
        threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()
        return True, "FPS counter started."

    def stop(self):
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            try:
                p.terminate()
            except OSError:
                pass
        with self.lock:
            self.frames.clear()

    def _read(self, proc):
        header = None
        for raw in proc.stdout:
            line = raw.strip()
            if not line:
                continue
            if header is None:
                header = parse_header(line)
                continue
            row = parse_row(header, line)
            if not row:
                continue
            app, pid, ms = row
            if app.lower() in IGNORED:
                continue
            now = time.monotonic()
            with self.lock:
                dq = self.frames.setdefault(pid, deque(maxlen=120))
                dq.append((now, ms))
                self.names[pid] = app

    def current_fps(self):
        """FPS of the foreground game if it is presenting frames, else the busiest app."""
        if not self.running:
            return None
        now = time.monotonic()
        with self.lock:
            live = {pid: dq for pid, dq in self.frames.items() if dq and now - dq[-1][0] < 2.0}
            for pid in [p for p, dq in self.frames.items() if not dq or now - dq[-1][0] > 15]:
                self.frames.pop(pid, None)
            if not live:
                self.current_app = ""
                return None
            fg = winapi.foreground_pid()
            pid = fg if fg in live else max(
                live, key=lambda p: sum(1 for t, _ in live[p] if now - t <= 1.0))
            recent = list(live[pid])[-60:]
            total = sum(ms for _, ms in recent)
            self.current_app = self.names.get(pid, "")
            return 1000.0 * len(recent) / total if total > 0 else None
