"""Background sensor polling for the dashboard and the overlay.

Sources (all optional, merged in priority order):
  * psutil                  - CPU / RAM usage
  * NVIDIA NVML             - GPU temp / usage / VRAM / fan %   (NVIDIA only, no extra software)
  * LibreHardwareMonitor    - CPU temp, fan RPM, AMD/Intel GPU  (WMI provider while it is running)
  * Windows GPU counters    - GPU usage fallback for any GPU
  * ACPI thermal zone       - last-resort CPU temperature
"""
import re
import threading
import time

import psutil

from . import winapi

CPU_TEMP_PREF = ("package", "tctl", "tdie", "core max", "average")


def parse_lhm(rows) -> dict:
    """rows: iterable of (name, sensor_type, value, identifier) from LibreHardwareMonitor."""
    out = {"fans": []}
    cpu_temps, gpu_temp = [], None
    for name, typ, val, ident in rows:
        if val is None:
            continue
        name, ident, val = name or "", (ident or "").lower(), float(val)
        is_cpu, is_gpu = "cpu/" in ident, "/gpu" in ident
        if typ == "Temperature":
            if is_cpu:
                cpu_temps.append((name.lower(), val))
            elif is_gpu and (name == "GPU Core" or gpu_temp is None):
                gpu_temp = val
        elif typ == "Fan":
            out["fans"].append((name, val, "RPM"))
        elif typ == "Load" and is_gpu and name == "GPU Core":
            out["gpu_usage"] = val
        elif typ == "SmallData" and is_gpu:
            if name == "GPU Memory Used":
                out["vram_used"] = val
            elif name == "GPU Memory Total":
                out["vram_total"] = val
    if cpu_temps:
        pick = None
        for pref in CPU_TEMP_PREF:
            pick = next((v for n, v in cpu_temps if pref in n), None)
            if pick is not None:
                break
        out["cpu_temp"] = pick if pick is not None else max(v for _, v in cpu_temps)
    if gpu_temp is not None:
        out["gpu_temp"] = gpu_temp
    return out


def gpu_usage_from_engines(rows):
    """rows: (instance name, utilisation %) from the 'GPU Engine' perf counter -> busiest 3D engine."""
    per = {}
    for name, util in rows:
        if "engtype_3D" not in (name or ""):
            continue
        m = re.search(r"luid_(0x[0-9a-fA-F]+_0x[0-9a-fA-F]+).*?_eng_(\d+)", name)
        key = m.groups() if m else ("x", "0")
        per[key] = per.get(key, 0.0) + float(util or 0)
    return min(100.0, max(per.values())) if per else None


class Sensors:
    def __init__(self, fps_reader=None):
        self.fps = fps_reader
        self.interval = 1.0
        self.status = {"nvml": False, "lhm": False, "gpu_counters": False}
        self._data = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._nv = None
        self._nv_handle = None
        self._lhm = None
        self._cim = None
        self._wmi_root = None
        self._retry_at = {"lhm": 0.0, "acpi": 0.0}
        self._acpi_ok = True
        self._com = None

    # ---- lifecycle
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._data)

    # ---- setup
    def _init_nvml(self):
        try:
            import pynvml
            pynvml.nvmlInit()
            self._nv = pynvml
            self._nv_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self.status["nvml"] = True
        except Exception:
            self._nv = self._nv_handle = None
            self.status["nvml"] = False

    def _wmi(self, namespace):
        import win32com.client
        return win32com.client.GetObject(rf"winmgmts:\\.\root\{namespace}")

    def _connect_lhm(self):
        for ns in ("LibreHardwareMonitor", "OpenHardwareMonitor"):
            try:
                svc = self._wmi(ns)
                list(svc.ExecQuery("SELECT Name FROM Hardware"))
                self._lhm = svc
                self.status["lhm"] = True
                return
            except Exception:
                continue
        self._lhm = None
        self.status["lhm"] = False

    # ---- readers
    def _read_basic(self, d):
        d["cpu_usage"] = psutil.cpu_percent(interval=None)
        vm = psutil.virtual_memory()
        d["ram_percent"] = vm.percent
        d["ram_used"] = vm.used / 2 ** 30
        d["ram_total"] = vm.total / 2 ** 30

    def _read_nvml(self, d):
        if not self._nv_handle:
            return
        nv, h = self._nv, self._nv_handle
        try:
            d["gpu_temp"] = float(nv.nvmlDeviceGetTemperature(h, nv.NVML_TEMPERATURE_GPU))
            d["gpu_usage"] = float(nv.nvmlDeviceGetUtilizationRates(h).gpu)
            mem = nv.nvmlDeviceGetMemoryInfo(h)
            d["vram_used"], d["vram_total"] = mem.used / 2 ** 20, mem.total / 2 ** 20
        except Exception:
            return
        try:
            d["_nv_fan"] = float(nv.nvmlDeviceGetFanSpeed(h))
        except Exception:
            pass

    def _read_lhm(self, d):
        if not self._lhm:
            if time.time() >= self._retry_at["lhm"]:
                self._retry_at["lhm"] = time.time() + 5
                self._connect_lhm()
            if not self._lhm:
                return
        try:
            rows = [(s.Name, s.SensorType, s.Value, s.Identifier) for s in
                    self._lhm.ExecQuery("SELECT Name, SensorType, Value, Identifier FROM Sensor")]
        except Exception:
            self._lhm, self.status["lhm"] = None, False
            return
        for k, v in parse_lhm(rows).items():
            if k == "fans":
                d["fans"] = v
            else:
                d.setdefault(k, v)

    def _read_gpu_counters(self, d):
        if "gpu_usage" in d:
            self.status["gpu_counters"] = False
            return
        try:
            if self._cim is None:
                self._cim = self._wmi("cimv2")
            rows = [(r.Name, r.UtilizationPercentage) for r in self._cim.ExecQuery(
                "SELECT Name, UtilizationPercentage FROM "
                "Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine")]
            val = gpu_usage_from_engines(rows)
            self.status["gpu_counters"] = val is not None
            if val is not None:
                d["gpu_usage"] = val
        except Exception:
            self.status["gpu_counters"] = False

    def _read_acpi(self, d):
        if "cpu_temp" in d or not self._acpi_ok or time.time() < self._retry_at["acpi"]:
            return
        self._retry_at["acpi"] = time.time() + 10
        try:
            svc = self._wmi("wmi")
            temps = [r.CurrentTemperature / 10.0 - 273.15 for r in svc.ExecQuery(
                "SELECT CurrentTemperature FROM MSAcpi_ThermalZoneTemperature")]
            temps = [t for t in temps if 0 < t < 125]
            if temps:
                d["cpu_temp"] = max(temps)
            else:
                self._acpi_ok = False
        except Exception:
            self._acpi_ok = False

    # ---- loop
    def _run(self):
        try:
            import pythoncom
            pythoncom.CoInitialize()
            self._com = pythoncom
        except Exception:
            self._com = None
        self._init_nvml()
        psutil.cpu_percent(interval=None)
        while not self._stop.is_set():
            t0 = time.time()
            d = {}
            for reader in (self._read_basic, self._read_nvml, self._read_lhm,
                           self._read_gpu_counters, self._read_acpi):
                try:
                    reader(d)
                except Exception:
                    pass
            nv_fan = d.pop("_nv_fan", None)
            fans = d.get("fans", [])
            if nv_fan is not None and not any("gpu" in f[0].lower() for f in fans):
                fans = fans + [("GPU", nv_fan, "%")]
            d["fans"] = fans
            d["refresh"] = winapi.refresh_rate()
            d["fps"] = self.fps.current_fps() if self.fps else None
            d["fps_app"] = getattr(self.fps, "current_app", "") if self.fps else ""
            with self._lock:
                self._data = d
            self._stop.wait(max(0.1, self.interval - (time.time() - t0)))
        if self._com:
            self._com.CoUninitialize()
