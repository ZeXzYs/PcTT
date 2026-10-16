# PC Tweaker

A sleek, single-window Windows toolkit for **FPS boosts, debloating, customisation** and a
**live performance overlay** (FPS, CPU/GPU temperature, fan speeds, CPU/GPU/RAM usage, refresh rate).
Windows 10 / 11 (64-bit) only. Source code and a one-click executable build are both included.

---

## 1. Dependencies

| What | Version | Needed for |
|---|---|---|
| **Windows 10 (1809+) or 11, 64-bit** | | everything |
| **Python** (python.org, 64-bit) | 3.10 – 3.13 | running from source / building the exe |
| `customtkinter` | ≥ 5.2.2 | the interface |
| `psutil` | ≥ 5.9.8 | CPU / RAM usage |
| `pywin32` | ≥ 306 | reading hardware sensors through WMI |
| `nvidia-ml-py` | ≥ 12.535.77 | NVIDIA GPU temp / usage / VRAM (uses your NVIDIA driver) |
| `pyinstaller` | ≥ 6.6 | **only** to build the .exe (`requirements-build.txt`) |

Optional helper programs (free, open source, downloaded from their official GitHub releases):

| Helper | Needed for |
|---|---|
| **PresentMon** (Intel) | the FPS counter |
| **LibreHardwareMonitor** | CPU temperature and fan RPM (and GPU data on AMD/Intel) |

You do not install these by hand: open **Overlay → Download helper tools** and they are placed in the `tools` folder.

---

## 2. Set up and run from source

1. Install Python 3.10+ from <https://www.python.org/downloads/> and tick **"Add python.exe to PATH"**.
2. Unzip this folder anywhere.
3. Double-click **`setup.bat`** (creates a `.venv` and installs the packages above — one time).
4. Double-click **`run.bat`** to start, or **`run_as_admin.bat`** to start with full rights
   (needed for most tweaks, the FPS counter and the sensors).

Manual equivalent:

```bat
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## 3. Build the executable

Double-click **`build_exe.bat`**. It installs the build tools and produces **`dist\PCTweaker.exe`**
(single file, no Python needed on the target PC).

* `build_exe.bat` — normal exe. Use the sidebar's **Restart as admin** button when you need elevation.
* `build_exe.bat admin` — exe that always asks for administrator rights at launch.

Keep a `tools` folder next to the exe; the app downloads PresentMon / LibreHardwareMonitor into it.
Windows SmartScreen or antivirus may flag any freshly built, unsigned PyInstaller exe — that is a
false positive; you built it from the source in this folder.

---

## 4. What's inside

**FPS & Boost** — Ultimate Performance power plan, Game Mode, disable Game DVR capture,
hardware-accelerated GPU scheduling, disable mouse acceleration, disable power throttling,
remove startup delay, disable SysMain, clean temp files, flush DNS.

**Debloat & Privacy** — telemetry off, advertising ID off, tips/suggestions/promoted apps off,
block auto-installed consumer apps, no web results in Start search, activity history off,
Widgets/News off, error reporting off, Maps service off, and a tick-box **Remove built-in apps** list
(Clipchamp, News, Solitaire, Teams, Cortana, and more; Xbox / Phone Link etc. are opt-in).

**Customise** — dark mode, no transparency, file extensions, hidden files, Explorer opens to This PC,
classic right-click menu, left taskbar, hide search box / Task View, compact Explorer, clock seconds,
plus a **Restart Explorer** button.

**Admin Tools** — launch Task Manager, Services, Registry Editor, Device Manager, Disk Cleanup,
Optimise Drives, Resource/Performance Monitor, Event Viewer, Task Scheduler, msconfig, Windows Features,
Group Policy, Power Options, System Information, Startup Apps, elevated Command Prompt and PowerShell —
each only when you click it. Maintenance: create a restore point, SFC, DISM.

**Overlay** — one switch to show/hide a draggable always-on-top readout. Choose which metrics appear,
opacity, update rate, click-through mode. Right-click the overlay to close it.

### Everything is reversible
Each switch records your previous value in `%APPDATA%\PCTweaker\backup.json` before changing anything.
Turning the switch off restores exactly what was there before. **Create a restore point** (Debloat page
banner or Admin Tools) before bigger changes. Removed apps can be reinstalled from the Microsoft Store.

---

## 5. Making the overlay show everything

| Reading | Works when |
|---|---|
| CPU / RAM usage, refresh rate | always |
| NVIDIA GPU temp, usage, VRAM, fan % | NVIDIA driver installed |
| GPU usage on AMD / Intel | automatic (Windows GPU counters) |
| CPU temperature, fan RPM | **LibreHardwareMonitor running as administrator** (Overlay → *Start sensor service*, then minimise it) |
| FPS | **PresentMon downloaded** and **PC Tweaker running as administrator** |

The FPS counter shows the foreground game's frame rate (DX9/10/11/12, Vulkan, OpenGL). The overlay is a normal
window — it never injects into games — and shows over windowed and **borderless** games. Exclusive-fullscreen
games hide it; switch them to borderless/windowed-fullscreen.

## 6. Troubleshooting

* **CPU temp / fans show `--`** — start LibreHardwareMonitor as administrator and run PC Tweaker as administrator too.
* **FPS shows `--`** — it needs admin, PresentMon in `tools`, and a game actively presenting frames.
* **A switch bounces back** — the status bar at the bottom shows the reason (usually: needs administrator).
* **Group Policy based tweaks do nothing** — some policies (e.g. consumer features) are honoured on Pro/Enterprise only.
* Logs: `%APPDATA%\PCTweaker\` (`crash.log`, `presentmon.log`, `settings.json`, `backup.json`).

## 7. Project layout

```
main.py                  entry point
pctweaker/app.py         UI (customtkinter)
pctweaker/tweaks.py      the tweak catalogue (add your own here)
pctweaker/registry.py    reversible registry / service / power-plan engine
pctweaker/tools.py       admin launchers + one-shot actions
pctweaker/debloat.py     built-in app list and removal
pctweaker/sensors.py     CPU/GPU/RAM/temps/fans polling
pctweaker/fps.py         PresentMon FPS reader
pctweaker/overlay.py     the floating overlay
pctweaker/helpers.py     downloads PresentMon + LibreHardwareMonitor
setup.bat / run.bat / run_as_admin.bat / build_exe.bat
```

Adding a tweak is one entry in `tweaks.py`, e.g.
`Tweak("my_id", "Name", "What it does", "customise", [RegValue("HKCU", r"Software\...", "Value", DWORD, 1, 0)])`.

Use at your own risk — tweaks change system settings. Gains from "FPS boosts" vary by PC and are usually modest.
