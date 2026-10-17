"""Small ctypes wrappers around Win32 calls (lazy-loaded, Windows only)."""
import ctypes
from ctypes import wintypes
from functools import lru_cache

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000


class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * 32),
        ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("dmPositionX", ctypes.c_long),
        ("dmPositionY", ctypes.c_long),
        ("dmDisplayOrientation", wintypes.DWORD),
        ("dmDisplayFixedOutput", wintypes.DWORD),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", ctypes.c_wchar * 32),
        ("dmLogPixels", wintypes.WORD),
        ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD),
        ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD),
        ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD),
        ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD),
        ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD),
        ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD),
        ("dmPanningHeight", wintypes.DWORD),
    ]


@lru_cache(maxsize=None)
def _u32():
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.GetForegroundWindow.restype = wintypes.HWND
    u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    u.GetWindowThreadProcessId.restype = wintypes.DWORD
    u.EnumDisplaySettingsW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(DEVMODEW)]
    u.EnumDisplaySettingsW.restype = wintypes.BOOL
    u.GetParent.argtypes = [wintypes.HWND]
    u.GetParent.restype = wintypes.HWND
    u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    u.GetWindowLongW.restype = ctypes.c_long
    u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    u.SetWindowLongW.restype = ctypes.c_long
    u.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
    u.SystemParametersInfoW.restype = wintypes.BOOL
    u.SendMessageTimeoutW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPCWSTR,
        wintypes.UINT, wintypes.UINT, ctypes.POINTER(wintypes.DWORD),
    ]
    u.SendMessageTimeoutW.restype = ctypes.c_void_p
    return u


def refresh_rate():
    """Current refresh rate (Hz) of the primary display, or None."""
    try:
        dm = DEVMODEW()
        dm.dmSize = ctypes.sizeof(DEVMODEW)
        if _u32().EnumDisplaySettingsW(None, 0xFFFFFFFF, ctypes.byref(dm)):
            hz = int(dm.dmDisplayFrequency)
            return hz if hz > 1 else None
    except Exception:
        pass
    return None


def foreground_pid():
    try:
        u = _u32()
        pid = wintypes.DWORD(0)
        u.GetWindowThreadProcessId(u.GetForegroundWindow(), ctypes.byref(pid))
        return int(pid.value) or None
    except Exception:
        return None


def broadcast_setting_change(area: str = "ImmersiveColorSet"):
    """Tell running apps that a user setting (e.g. the theme) changed."""
    try:
        res = wintypes.DWORD(0)
        _u32().SendMessageTimeoutW(0xFFFF, 0x001A, 0, area, 0x0002, 3000, ctypes.byref(res))
    except Exception:
        pass


def apply_mouse_params(speed: int, threshold1: int, threshold2: int):
    """Apply the mouse acceleration values immediately (SPI_SETMOUSE)."""
    try:
        arr = (ctypes.c_int * 3)(threshold1, threshold2, speed)
        _u32().SystemParametersInfoW(0x0004, 0, ctypes.byref(arr), 0x03)
    except Exception:
        pass


def toplevel_hwnd(widget) -> int:
    u = _u32()
    wid = widget.winfo_id()
    return u.GetParent(wid) or wid


def set_overlay_style(hwnd: int, click_through: bool):
    """Hide from Alt+Tab/taskbar, never take focus, optionally let clicks pass through."""
    u = _u32()
    style = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
    style |= WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_LAYERED
    if click_through:
        style |= WS_EX_TRANSPARENT
    else:
        style &= ~WS_EX_TRANSPARENT
    u.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
