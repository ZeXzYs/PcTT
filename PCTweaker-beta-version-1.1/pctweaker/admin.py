"""Administrator helpers and a quiet subprocess runner."""
import ctypes
import os
import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def shell_run(file: str, params: str = "", verb: str = "open", show: int = 1) -> bool:
    """ShellExecute wrapper. Returns False if the launch failed or UAC was declined."""
    try:
        rc = ctypes.windll.shell32.ShellExecuteW(None, verb, file, params or None, None, show)
        return int(rc) > 32
    except Exception:
        return False


def run_elevated(file: str, params: str = "", show: int = 1) -> bool:
    if is_admin():
        return shell_run(file, params, "open", show)
    return shell_run(file, params, "runas", show)


def relaunch_as_admin() -> bool:
    """Start a new elevated copy of this program (caller should then exit)."""
    exe = sys.executable
    if getattr(sys, "frozen", False):
        params = " ".join(f'"{a}"' for a in sys.argv[1:])
    else:
        if exe.lower().endswith("python.exe"):
            pythonw = exe[:-10] + "pythonw.exe"
            if os.path.exists(pythonw):
                exe = pythonw
        params = " ".join(f'"{a}"' for a in sys.argv)
    try:
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, os.getcwd(), 1)
        return int(rc) > 32
    except Exception:
        return False


def run_hidden(args, timeout: int = 120):
    """Run a command without flashing a console window. Returns (returncode, output)."""
    try:
        p = subprocess.run(
            args, capture_output=True, text=True, errors="replace",
            timeout=timeout, creationflags=CREATE_NO_WINDOW,
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, "The command timed out."
    except OSError as e:
        return -1, str(e)


def powershell(script: str, timeout: int = 300):
    return run_hidden(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-Command", script],
        timeout=timeout,
    )
