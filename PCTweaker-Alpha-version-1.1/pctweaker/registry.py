"""Reversible tweak engine: registry values, registry keys, services, power plans.

Every change first records the previous state in %APPDATA%\\PCTweaker\\backup.json,
so toggling a tweak off restores exactly what was there before.
"""
import json
import re
import winreg

from .admin import run_hidden
from .config import data_dir

HIVES = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}
VIEW = winreg.KEY_WOW64_64KEY
DWORD = winreg.REG_DWORD
SZ = winreg.REG_SZ


# --------------------------------------------------------------------------- backup
class Backup:
    def __init__(self):
        self.path = data_dir() / "backup.json"
        self.data = {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        except (OSError, ValueError):
            self.data = {}

    def get(self, key: str) -> dict:
        return self.data.setdefault(key, {})

    def peek(self, key: str) -> dict:
        """Read-only view that never creates an entry."""
        return self.data.get(key, {})

    def drop(self, key: str):
        self.data.pop(key, None)
        self.save()

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({k: v for k, v in self.data.items() if v}, f, indent=2)
        except OSError:
            pass


BACKUP = Backup()


# --------------------------------------------------------------------------- low level
def _enc(data):
    return {"hex": data.hex()} if isinstance(data, (bytes, bytearray)) else data


def _dec(data):
    return bytes.fromhex(data["hex"]) if isinstance(data, dict) and "hex" in data else data


def read_value(hive, path, name):
    try:
        with winreg.OpenKey(HIVES[hive], path, 0, winreg.KEY_READ | VIEW) as k:
            data, typ = winreg.QueryValueEx(k, name)
        return {"exists": True, "type": typ, "data": _enc(data)}
    except OSError:
        return {"exists": False}


def write_value(hive, path, name, typ, data):
    with winreg.CreateKeyEx(HIVES[hive], path, 0, winreg.KEY_SET_VALUE | VIEW) as k:
        winreg.SetValueEx(k, name, 0, typ, _dec(data))


def delete_value(hive, path, name):
    try:
        with winreg.OpenKey(HIVES[hive], path, 0, winreg.KEY_SET_VALUE | VIEW) as k:
            winreg.DeleteValue(k, name)
    except OSError:
        pass


def delete_key(hive, path):
    """Deletes a key only if it has no sub-keys (safe by design)."""
    try:
        winreg.DeleteKeyEx(HIVES[hive], path, VIEW, 0)
    except OSError:
        pass


def key_exists(hive, path) -> bool:
    try:
        with winreg.OpenKey(HIVES[hive], path, 0, winreg.KEY_READ | VIEW):
            return True
    except OSError:
        return False


# --------------------------------------------------------------------------- parts
class RegValue:
    """One registry value. `default` is what Windows ships with (None = value absent)."""

    def __init__(self, hive, path, name, typ, data, default=None):
        self.hive, self.path, self.name, self.typ, self.data, self.default = (
            hive, path, name, typ, data, default)
        self.key = f"{hive}\\{path}\\{name}"

    def is_applied(self, store) -> bool:
        cur = read_value(self.hive, self.path, self.name)
        return bool(cur["exists"]) and cur["data"] == self.data

    def apply(self, store):
        if self.key not in store:
            store[self.key] = read_value(self.hive, self.path, self.name)
        write_value(self.hive, self.path, self.name, self.typ, self.data)

    def revert(self, store):
        prev = store.get(self.key)
        if prev is None:  # nothing recorded: fall back to the Windows default
            if self.default is None:
                delete_value(self.hive, self.path, self.name)
            else:
                write_value(self.hive, self.path, self.name, self.typ, self.default)
        elif prev.get("exists"):
            write_value(self.hive, self.path, self.name, prev["type"], prev["data"])
        else:
            delete_value(self.hive, self.path, self.name)


class RegKey:
    """A key that only needs to exist with an empty default value (classic context menu)."""

    def __init__(self, hive, path, prune=()):
        self.hive, self.path, self.prune = hive, path, list(prune)

    def is_applied(self, store) -> bool:
        return key_exists(self.hive, self.path)

    def apply(self, store):
        write_value(self.hive, self.path, "", SZ, "")

    def revert(self, store):
        delete_key(self.hive, self.path)
        for p in self.prune:
            delete_key(self.hive, p)


def service_start_type(name):
    rc, out = run_hidden(["sc.exe", "qc", name])
    if rc != 0:
        return None
    m = re.search(r"START_TYPE\s*:\s*(\d+)", out)
    return int(m.group(1)) if m else None


class Service:
    """Disable a Windows service (and stop it). Restores the old start type on revert."""

    def __init__(self, name, default_start=3):
        self.name, self.default_start = name, default_start
        self.key = f"svc:{name}"

    def is_applied(self, store) -> bool:
        st = service_start_type(self.name)
        return st is None or st == 4  # a missing service counts as "already off"

    def apply(self, store):
        st = service_start_type(self.name)
        if st is None:
            return
        if self.key not in store and st != 4:
            store[self.key] = st
        rc, out = run_hidden(["sc.exe", "config", self.name, "start=", "disabled"])
        if rc != 0:
            raise RuntimeError(f"Could not disable service {self.name}: {out.strip()}")
        run_hidden(["sc.exe", "stop", self.name])

    def revert(self, store):
        if service_start_type(self.name) is None:
            return
        prev = store.get(self.key, self.default_start)
        mode = {2: "auto", 3: "demand"}.get(prev, "demand")
        rc, out = run_hidden(["sc.exe", "config", self.name, "start=", mode])
        if rc != 0:
            raise RuntimeError(f"Could not restore service {self.name}: {out.strip()}")
        if mode == "auto":
            run_hidden(["sc.exe", "start", self.name])


ULTIMATE = "e9a42b02-d5df-448d-aa00-03f14749eb61"
HIGH = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
BALANCED = "381b4222-f694-41f0-9685-ff5bb260df2e"
GUID_RE = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")


def active_scheme():
    rc, out = run_hidden(["powercfg.exe", "/getactivescheme"])
    m = GUID_RE.search(out) if rc == 0 else None
    return m.group(0).lower() if m else None


class PowerPlan:
    """Creates + activates an Ultimate Performance plan (High Performance as fallback)."""

    def is_applied(self, store) -> bool:
        new = store.get("power_new")
        return bool(new) and active_scheme() == new

    def apply(self, store):
        if "power_prev" not in store:
            store["power_prev"] = active_scheme()
        new = None
        for template in (ULTIMATE, HIGH):
            rc, out = run_hidden(["powercfg.exe", "/duplicatescheme", template])
            m = GUID_RE.search(out) if rc == 0 else None
            if m:
                new = m.group(0).lower()
                break
        if not new:
            raise RuntimeError("Windows would not create a performance power plan on this PC.")
        store["power_new"] = new
        run_hidden(["powercfg.exe", "/changename", new, "PC Tweaker Performance"])
        rc, out = run_hidden(["powercfg.exe", "/setactive", new])
        if rc != 0:
            raise RuntimeError(f"Could not activate the power plan: {out.strip()}")

    def revert(self, store):
        prev = store.get("power_prev") or BALANCED
        rc, _ = run_hidden(["powercfg.exe", "/setactive", prev])
        if rc != 0:
            run_hidden(["powercfg.exe", "/setactive", BALANCED])
        new = store.get("power_new")
        if new:
            run_hidden(["powercfg.exe", "/delete", new])
