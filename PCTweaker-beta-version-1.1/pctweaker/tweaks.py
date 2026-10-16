"""Catalogue of toggle-able tweaks, grouped by page."""
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from . import winapi
from .registry import (BACKUP, DWORD, SZ, PowerPlan, RegKey, RegValue, Service,
                       read_value)


@dataclass
class Tweak:
    id: str
    name: str
    desc: str
    category: str                      # "boost" | "debloat" | "customise"
    parts: List = field(default_factory=list)
    admin: bool = False
    reboot: bool = False
    explorer: bool = False
    hook: Optional[Callable[[], None]] = None
    kind: str = "toggle"

    def is_applied(self) -> bool:
        store = BACKUP.peek(self.id)
        return all(p.is_applied(store) for p in self.parts)

    def _finish(self):
        if self.hook:
            try:
                self.hook()
            except Exception:
                pass

    def apply(self) -> str:
        store = BACKUP.get(self.id)
        try:
            for p in self.parts:
                p.apply(store)
        finally:
            BACKUP.save()
        self._finish()
        return f"{self.name}: enabled." + self._hint()

    def revert(self) -> str:
        store = BACKUP.get(self.id)
        for p in self.parts:
            p.revert(store)
        BACKUP.drop(self.id)
        self._finish()
        return f"{self.name}: restored to previous setting." + self._hint()

    def _hint(self) -> str:
        if self.reboot:
            return " Restart your PC for it to take effect."
        if self.explorer:
            return " Use 'Restart Explorer' on the Customise page to see it now."
        return ""


# ----------------------------------------------------------------------- hooks
def _mouse_hook():
    vals = []
    for name, dflt in (("MouseSpeed", 1), ("MouseThreshold1", 6), ("MouseThreshold2", 10)):
        cur = read_value("HKCU", r"Control Panel\Mouse", name)
        try:
            vals.append(int(cur["data"]) if cur["exists"] else dflt)
        except (TypeError, ValueError):
            vals.append(dflt)
    winapi.apply_mouse_params(*vals)


def _theme_hook():
    winapi.broadcast_setting_change("ImmersiveColorSet")


# ----------------------------------------------------------------------- paths
EXPLORER_ADV = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
CDM = r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"
CLSID = r"Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}"

TWEAKS: List[Tweak] = [
    # ------------------------------------------------------------- FPS & boost
    Tweak(
        "power_plan", "Ultimate Performance power plan",
        "Creates and activates the hidden Ultimate Performance plan (High Performance as "
        "fallback) so the CPU stops down-clocking mid-game. Uses more power on laptops.",
        "boost", [PowerPlan()], admin=True),
    Tweak(
        "game_mode", "Game Mode",
        "Lets Windows prioritise the game you are playing and pause background driver "
        "installs and updates while you play.",
        "boost", [
            RegValue("HKCU", r"Software\Microsoft\GameBar", "AllowAutoGameMode", DWORD, 1, 1),
            RegValue("HKCU", r"Software\Microsoft\GameBar", "AutoGameModeEnabled", DWORD, 1, 1),
        ]),
    Tweak(
        "game_dvr", "Disable Xbox Game DVR capture",
        "Turns off background clip recording, which costs a little CPU/GPU time in games.",
        "boost", [
            RegValue("HKCU", r"System\GameConfigStore", "GameDVR_Enabled", DWORD, 0, 1),
            RegValue("HKCU", r"Software\Microsoft\Windows\CurrentVersion\GameDVR",
                     "AppCaptureEnabled", DWORD, 0, 1),
        ]),
    Tweak(
        "hags", "Hardware-accelerated GPU scheduling",
        "Lets the GPU manage its own memory scheduling. Can reduce latency on supported "
        "GPUs and drivers; results vary by game.",
        "boost", [RegValue("HKLM", r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers",
                           "HwSchMode", DWORD, 2, 1)],
        admin=True, reboot=True),
    Tweak(
        "mouse_accel", "Disable mouse acceleration",
        "Turns off 'Enhance pointer precision' so mouse movement is 1:1, which most "
        "shooters prefer for consistent aim.",
        "boost", [
            RegValue("HKCU", r"Control Panel\Mouse", "MouseSpeed", SZ, "0", "1"),
            RegValue("HKCU", r"Control Panel\Mouse", "MouseThreshold1", SZ, "0", "6"),
            RegValue("HKCU", r"Control Panel\Mouse", "MouseThreshold2", SZ, "0", "10"),
        ], hook=_mouse_hook),
    Tweak(
        "power_throttle", "Disable power throttling",
        "Stops Windows from throttling background apps to save power, which can also "
        "affect launchers and capture tools running next to a game.",
        "boost", [RegValue("HKLM", r"SYSTEM\CurrentControlSet\Control\Power\PowerThrottling",
                           "PowerThrottlingOff", DWORD, 1, None)],
        admin=True),
    Tweak(
        "startup_delay", "Remove startup app delay",
        "Windows waits a few seconds before launching startup apps. This removes the "
        "delay so the desktop is ready sooner.",
        "boost", [RegValue("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize",
                           "StartupDelayInMSec", DWORD, 0, None)]),
    Tweak(
        "sysmain", "Disable SysMain (Superfetch)",
        "Stops the background pre-loader. Fine on SSDs; leave it on if Windows lives on "
        "a hard drive.",
        "boost", [Service("SysMain", default_start=2)], admin=True),

    # ------------------------------------------------------------- debloat & privacy
    Tweak(
        "telemetry", "Disable telemetry",
        "Sets diagnostic data to the minimum and stops the telemetry services. Home "
        "editions can't go below 'Required' data.",
        "debloat", [
            RegValue("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\DataCollection",
                     "AllowTelemetry", DWORD, 0, None),
            Service("DiagTrack", default_start=2),
            Service("dmwappushservice", default_start=3),
        ], admin=True),
    Tweak(
        "ad_id", "Disable advertising ID",
        "Stops apps from using a per-user ID to show targeted ads.",
        "debloat", [RegValue("HKCU", r"Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo",
                             "Enabled", DWORD, 0, 1)]),
    Tweak(
        "suggestions", "Disable tips, suggestions & promoted apps",
        "Removes Start menu suggestions, lock-screen tips and silently installed "
        "'promoted' apps.",
        "debloat", [RegValue("HKCU", CDM, n, DWORD, 0, 1) for n in (
            "SubscribedContent-338388Enabled", "SubscribedContent-338389Enabled",
            "SubscribedContent-353694Enabled", "SubscribedContent-353696Enabled",
            "SubscribedContent-310093Enabled", "SubscribedContent-338393Enabled",
            "SystemPaneSuggestionsEnabled", "SoftLandingEnabled",
            "SilentInstalledAppsEnabled", "OemPreInstalledAppsEnabled",
            "PreInstalledAppsEnabled", "ContentDeliveryAllowed")]),
    Tweak(
        "consumer_features", "Block auto-installed consumer apps",
        "Stops Windows from pulling in sponsored apps (Pro/Enterprise/Education editions "
        "honour this policy).",
        "debloat", [RegValue("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\CloudContent",
                             "DisableWindowsConsumerFeatures", DWORD, 1, None)], admin=True),
    Tweak(
        "web_search", "Disable web results in Start search",
        "Start search only looks at your PC instead of sending queries to Bing.",
        "debloat", [RegValue("HKCU", r"Software\Policies\Microsoft\Windows\Explorer",
                             "DisableSearchBoxSuggestions", DWORD, 1, None)], explorer=True),
    Tweak(
        "activity", "Disable activity history",
        "Stops Windows recording and uploading your activity timeline.",
        "debloat", [RegValue("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\System", n, DWORD, 0, None)
                    for n in ("EnableActivityFeed", "PublishUserActivities", "UploadUserActivities")],
        admin=True),
    Tweak(
        "widgets", "Disable Widgets & News feed",
        "Turns off the Windows 11 Widgets board and the Windows 10 News & Interests feed "
        "(frees a background WebView process).",
        "debloat", [
            RegValue("HKLM", r"SOFTWARE\Policies\Microsoft\Dsh", "AllowNewsAndInterests", DWORD, 0, None),
            RegValue("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\Windows Feeds", "EnableFeeds", DWORD, 0, None),
        ], admin=True, explorer=True),
    Tweak(
        "error_reporting", "Disable Windows Error Reporting",
        "Stops crash reports from being collected and sent to Microsoft.",
        "debloat", [RegValue("HKLM", r"SOFTWARE\Microsoft\Windows\Windows Error Reporting",
                             "Disabled", DWORD, 1, None)], admin=True),
    Tweak(
        "maps_service", "Disable Downloaded Maps Manager",
        "Stops a background service that only matters if you use offline maps.",
        "debloat", [Service("MapsBroker", default_start=2)], admin=True),

    # ------------------------------------------------------------- customise
    Tweak(
        "dark_mode", "Dark mode (apps & Windows)",
        "Switches Windows and apps to the dark theme.",
        "customise", [
            RegValue("HKCU", PERSONALIZE, "AppsUseLightTheme", DWORD, 0, 1),
            RegValue("HKCU", PERSONALIZE, "SystemUsesLightTheme", DWORD, 0, 1),
        ], hook=_theme_hook),
    Tweak(
        "transparency", "Disable transparency effects",
        "Removes the frosted-glass blur from Start, taskbar and windows. Cleaner look and "
        "slightly less GPU work.",
        "customise", [RegValue("HKCU", PERSONALIZE, "EnableTransparency", DWORD, 0, 1)],
        hook=_theme_hook),
    Tweak(
        "file_ext", "Show file extensions",
        "Always show .exe, .txt, .png and friends in File Explorer.",
        "customise", [RegValue("HKCU", EXPLORER_ADV, "HideFileExt", DWORD, 0, 1)], explorer=True),
    Tweak(
        "hidden_files", "Show hidden files",
        "Reveal hidden files and folders in File Explorer.",
        "customise", [RegValue("HKCU", EXPLORER_ADV, "Hidden", DWORD, 1, 2)], explorer=True),
    Tweak(
        "this_pc", "File Explorer opens to 'This PC'",
        "Opens Explorer on your drives instead of Home / Quick access.",
        "customise", [RegValue("HKCU", EXPLORER_ADV, "LaunchTo", DWORD, 1, 2)], explorer=True),
    Tweak(
        "classic_menu", "Classic right-click menu (Windows 11)",
        "Brings back the full context menu without the extra 'Show more options' click.",
        "customise", [RegKey("HKCU", CLSID + r"\InprocServer32", prune=[CLSID])], explorer=True),
    Tweak(
        "taskbar_left", "Left-aligned taskbar (Windows 11)",
        "Moves the Start button and icons to the left like Windows 10.",
        "customise", [RegValue("HKCU", EXPLORER_ADV, "TaskbarAl", DWORD, 0, 1)], explorer=True),
    Tweak(
        "taskbar_search", "Hide taskbar search box",
        "Frees up taskbar space; search is still one key press away.",
        "customise", [RegValue("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Search",
                               "SearchboxTaskbarMode", DWORD, 0, 2)], explorer=True),
    Tweak(
        "task_view", "Hide Task View button",
        "Removes the Task View button (Win+Tab still works).",
        "customise", [RegValue("HKCU", EXPLORER_ADV, "ShowTaskViewButton", DWORD, 0, 1)], explorer=True),
    Tweak(
        "compact_view", "Compact File Explorer spacing (Windows 11)",
        "Tighter rows in File Explorer so more files fit on screen.",
        "customise", [RegValue("HKCU", EXPLORER_ADV, "UseCompactMode", DWORD, 1, 0)], explorer=True),
    Tweak(
        "clock_seconds", "Show seconds in taskbar clock",
        "Adds seconds to the system tray clock.",
        "customise", [RegValue("HKCU", EXPLORER_ADV, "ShowSecondsInSystemClock", DWORD, 1, 0)],
        explorer=True),
]


def by_category(cat: str) -> List[Tweak]:
    return [t for t in TWEAKS if t.category == cat]
