"""One-shot actions and the admin tool launchers."""
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Optional

from .admin import CREATE_NO_WINDOW, powershell, run_elevated, run_hidden, shell_run


@dataclass
class ActionItem:
    id: str
    name: str
    desc: str
    category: str
    run: Optional[Callable[[], str]] = None
    admin: bool = False
    button: str = "Run"
    confirm: Optional[str] = None
    ui: Optional[str] = None           # special UI handler, e.g. "appx"
    kind: str = "action"


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def clean_temp() -> str:
    freed, skipped = 0, 0
    folders = {os.environ.get("TEMP"), os.environ.get("TMP"),
               os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Temp")}
    for folder in filter(None, folders):
        if not os.path.isdir(folder):
            continue
        for root, dirs, files in os.walk(folder, topdown=False):
            for f in files:
                p = os.path.join(root, f)
                try:
                    size = os.path.getsize(p)
                    os.remove(p)
                    freed += size
                except OSError:
                    skipped += 1
            for d in dirs:
                try:
                    os.rmdir(os.path.join(root, d))
                except OSError:
                    pass
    return f"Cleaned temporary files: freed {_fmt_bytes(freed)} ({skipped} in-use items skipped)."


def flush_dns() -> str:
    rc, out = run_hidden(["ipconfig.exe", "/flushdns"])
    if rc != 0:
        raise RuntimeError(out.strip() or "ipconfig failed")
    return "DNS cache flushed."


def restore_point() -> str:
    rc, out = powershell(
        'Checkpoint-Computer -Description "PC Tweaker" -RestorePointType MODIFY_SETTINGS '
        "-ErrorAction Stop", timeout=240)
    if rc != 0:
        raise RuntimeError(
            (out.strip() or "Unknown error") +
            "\n\nTip: System Protection must be switched on for your Windows drive "
            "(System Properties > System Protection).")
    return "Restore point created."


def sfc_scan() -> str:
    ok = run_elevated("cmd.exe", "/k sfc /scannow")
    if not ok:
        raise RuntimeError("Could not open an elevated console (was the UAC prompt declined?).")
    return "Opened an elevated console running System File Checker."


def dism_repair() -> str:
    ok = run_elevated("cmd.exe", "/k DISM /Online /Cleanup-Image /RestoreHealth")
    if not ok:
        raise RuntimeError("Could not open an elevated console (was the UAC prompt declined?).")
    return "Opened an elevated console running DISM RestoreHealth."


def restart_explorer() -> str:
    run_hidden(["taskkill.exe", "/f", "/im", "explorer.exe"])
    for _ in range(8):
        time.sleep(0.5)
        _, out = run_hidden(["tasklist.exe", "/fi", "imagename eq explorer.exe"])
        if "explorer.exe" in out.lower():
            return "Explorer restarted."
    subprocess.Popen(["explorer.exe"], creationflags=CREATE_NO_WINDOW)
    return "Explorer restarted."


# --------------------------------------------------------------------------- actions
ACTIONS = [
    ActionItem("clean_temp", "Clean temporary files",
               "Deletes files in your Temp folder and C:\\Windows\\Temp. Items in use are skipped. "
               "Run as administrator to clean the Windows Temp folder too.",
               "boost", clean_temp, button="Clean"),
    ActionItem("flush_dns", "Flush DNS cache",
               "Clears cached name lookups. Handy if sites or game servers fail to resolve.",
               "boost", flush_dns, admin=True, button="Flush"),
    ActionItem("remove_apps", "Remove built-in apps",
               "Pick which preinstalled apps (Clipchamp, News, Solitaire, Teams...) to uninstall. "
               "Everything can be reinstalled from the Microsoft Store.",
               "debloat", admin=True, button="Choose apps...", ui="appx"),
    ActionItem("restart_explorer", "Restart Explorer",
               "Reloads the taskbar and File Explorer so shell tweaks show up without signing out.",
               "customise", restart_explorer, button="Restart"),
    ActionItem("restore_point", "Create a restore point",
               "Recommended before applying tweaks. Lets you roll Windows back from System Restore.",
               "admin", restore_point, admin=True, button="Create",
               confirm="Create a system restore point now? This can take up to a minute."),
    ActionItem("sfc", "System File Checker (sfc /scannow)",
               "Scans Windows system files and repairs corrupted ones. Opens an admin console (UAC prompt).",
               "admin", sfc_scan, button="Open"),
    ActionItem("dism", "DISM RestoreHealth",
               "Repairs the Windows component store. Run it before SFC if SFC can't fix everything.",
               "admin", dism_repair, button="Open"),
]


def actions_for(cat: str):
    return [a for a in ACTIONS if a.category == cat]


# --------------------------------------------------------------------------- launchers
# (label, description, program, arguments, elevate)
LAUNCHERS = [
    ("Task Manager", "Processes, startup apps, performance", "taskmgr.exe", "", True),
    ("Services", "Start, stop and configure services", "mmc.exe", "services.msc", True),
    ("Registry Editor", "Browse and edit the registry", "regedit.exe", "", True),
    ("Device Manager", "Drivers and hardware", "mmc.exe", "devmgmt.msc", True),
    ("Disk Cleanup", "Windows' built-in cleaner", "cleanmgr.exe", "", True),
    ("Optimise Drives", "TRIM SSDs / defrag HDDs", "dfrgui.exe", "", True),
    ("Resource Monitor", "Live CPU, disk, network and memory", "resmon.exe", "", True),
    ("Performance Monitor", "Detailed performance counters", "perfmon.exe", "", True),
    ("Event Viewer", "System and application logs", "mmc.exe", "eventvwr.msc", True),
    ("Task Scheduler", "Scheduled and startup tasks", "mmc.exe", "taskschd.msc", True),
    ("System Configuration", "msconfig: boot and services", "msconfig.exe", "", True),
    ("Windows Features", "Turn Windows features on or off", "optionalfeatures.exe", "", True),
    ("Group Policy Editor", "Pro / Enterprise editions only", "mmc.exe", "gpedit.msc", True),
    ("Power Options", "Power plans and sleep settings", "control.exe", "powercfg.cpl", True),
    ("System Information", "Hardware and OS details", "msinfo32.exe", "", True),
    ("Startup Apps", "Settings page for startup programs", "ms-settings:startupapps", "", False),
    ("Command Prompt", "Opens elevated", "cmd.exe", "", True),
    ("PowerShell", "Opens elevated", "powershell.exe", "", True),
]


def launch(program: str, args: str, elevate: bool) -> str:
    ok = run_elevated(program, args) if elevate else shell_run(program, args)
    if not ok:
        raise RuntimeError("Could not launch it (the UAC prompt may have been declined).")
    return f"Launched {program}."
