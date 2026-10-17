"""Downloads the optional helper tools (PresentMon for FPS, LibreHardwareMonitor for sensors)."""
import io
import re
import urllib.request
import zipfile

from .config import TOOLS_DIR

UA = {"User-Agent": "PCTweaker/1.0"}
PRESENTMON_REPO = "GameTechDev/PresentMon"
LHM_REPO = "LibreHardwareMonitor/LibreHardwareMonitor"


def _open(url, timeout=60):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout)


def _latest_asset_urls(repo):
    """Resolve the newest release and list its download URLs (no API rate limit)."""
    with _open(f"https://github.com/{repo}/releases/latest") as r:
        tag = r.geturl().rstrip("/").split("/")[-1]
    with _open(f"https://github.com/{repo}/releases/expanded_assets/{tag}") as r:
        html = r.read().decode("utf-8", "replace")
    hrefs = re.findall(r'href="([^"]+/releases/download/[^"]+)"', html)
    return ["https://github.com" + h if h.startswith("/") else h for h in hrefs]


def presentmon_path():
    """Newest PresentMon console exe inside tools/, or None."""
    if not TOOLS_DIR.exists():
        return None
    found = sorted(TOOLS_DIR.rglob("PresentMon*.exe"))
    return found[-1] if found else None


def lhm_path():
    folder = TOOLS_DIR / "LibreHardwareMonitor"
    if not folder.exists():
        return None
    return next(folder.rglob("LibreHardwareMonitor.exe"), None)


def download_presentmon(log=print):
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    urls = _latest_asset_urls(PRESENTMON_REPO)
    exe = next((u for u in urls if re.search(r"PresentMon-[\d.]+-x64\.exe$", u)), None)
    if not exe:
        raise RuntimeError("Could not find the PresentMon x64 download on GitHub.")
    log("Downloading PresentMon...")
    with _open(exe, timeout=180) as r:
        data = r.read()
    (TOOLS_DIR / "PresentMon.exe").write_bytes(data)


def download_lhm(log=print):
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    urls = _latest_asset_urls(LHM_REPO)
    # The classic .NET Framework build runs on every Windows 10/11 without extra installs.
    zp = next((u for u in urls if u.endswith("/LibreHardwareMonitor.zip")), None)
    if not zp:
        raise RuntimeError("Could not find the LibreHardwareMonitor download on GitHub.")
    log("Downloading LibreHardwareMonitor...")
    with _open(zp, timeout=180) as r:
        data = r.read()
    dest = TOOLS_DIR / "LibreHardwareMonitor"
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        z.extractall(dest)
    if not (dest / "LibreHardwareMonitor.exe").exists():
        # some releases wrap everything in a sub-folder
        inner = next(dest.rglob("LibreHardwareMonitor.exe"), None)
        if not inner:
            raise RuntimeError("The LibreHardwareMonitor archive had an unexpected layout.")


def download_all(log=print):
    download_presentmon(log)
    download_lhm(log)
    return "Helper tools downloaded to the 'tools' folder."


if __name__ == "__main__":
    print(download_all())
