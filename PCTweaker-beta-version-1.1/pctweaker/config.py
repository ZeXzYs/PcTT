"""Paths and persistent settings."""
import copy
import json
import os
import sys
from pathlib import Path

APP_NAME = "PC Tweaker"


def base_dir() -> Path:
    """Folder that holds the .exe (frozen) or the project root (source)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(rel: str) -> Path:
    """Locate a bundled resource (works for source runs and PyInstaller)."""
    root = Path(getattr(sys, "_MEIPASS", base_dir()))
    return root / rel


def data_dir() -> Path:
    d = Path(os.environ.get("APPDATA", str(Path.home()))) / "PCTweaker"
    d.mkdir(parents=True, exist_ok=True)
    return d


TOOLS_DIR = base_dir() / "tools"

DEFAULTS = {
    "overlay": {
        "enabled": False,
        "x": 30,
        "y": 30,
        "opacity": 0.85,
        "click_through": False,
        "interval": 1.0,
        "metrics": {
            "fps": True,
            "cpu_usage": True,
            "cpu_temp": True,
            "gpu_usage": True,
            "gpu_temp": True,
            "vram": False,
            "ram": True,
            "fans": True,
            "refresh": True,
        },
    }
}


def _merge(base: dict, extra: dict) -> dict:
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


class Settings:
    def __init__(self):
        self.path = data_dir() / "settings.json"
        self.data = copy.deepcopy(DEFAULTS)
        try:
            self._load()
        except (OSError, ValueError):
            pass

    def _load(self):
        with open(self.path, "r", encoding="utf-8") as f:
            _merge(self.data, json.load(f))

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except OSError:
            pass

    @property
    def overlay(self) -> dict:
        return self.data["overlay"]
