"""Windows 活动窗口监听模块。

纯 ctypes 实现，无额外依赖。通过 QTimer 轮询前台窗口，
窗口切换时发射 window_changed 信号。
"""

import ctypes
from ctypes import wintypes, Structure, sizeof, byref, POINTER, cast
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

# ═══════════════════════════════════════════════════════════════
#  Win32 API 绑定
# ═══════════════════════════════════════════════════════════════

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# GetForegroundWindow / GetWindowTextW / GetWindowThreadProcessId
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

# CreateToolhelp32Snapshot
TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

# PROCESSENTRY32W
MAX_PATH = 260


class PROCESSENTRY32W(Structure):
    _fields_ = [
        ("dwSize",              wintypes.DWORD),
        ("cntUsage",            wintypes.DWORD),
        ("th32ProcessID",       wintypes.DWORD),
        ("th32DefaultHeapID",   POINTER(wintypes.ULONG)),
        ("th32ModuleID",        wintypes.DWORD),
        ("cntThreads",           wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase",      wintypes.LONG),
        ("dwFlags",             wintypes.DWORD),
        ("szExeFile",           wintypes.WCHAR * MAX_PATH),
    ]


kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, POINTER(PROCESSENTRY32W)]
kernel32.Process32FirstW.restype = wintypes.BOOL
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.restype = wintypes.BOOL


# ═══════════════════════════════════════════════════════════════
#  WindowInfo
# ═══════════════════════════════════════════════════════════════

class WindowInfo:
    """当前活动窗口的快照。"""

    __slots__ = ("hwnd", "title", "process_name")

    def __init__(self, hwnd: int = 0, title: str = "", process_name: str = ""):
        self.hwnd = hwnd
        self.title = title
        self.process_name = process_name

    def __repr__(self) -> str:
        return f"WindowInfo(hwnd={self.hwnd:#x}, process={self.process_name!r}, title={self.title!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, WindowInfo):
            return NotImplemented
        return self.hwnd == other.hwnd


# ═══════════════════════════════════════════════════════════════
#  WindowMonitor
# ═══════════════════════════════════════════════════════════════

class WindowMonitor(QObject):
    """轮询 Windows 前台窗口，切换时发出信号。

    Usage::

        monitor = WindowMonitor(interval_ms=500)
        monitor.window_changed.connect(on_change)
        monitor.start()          # 开始轮询
        info = monitor.current   # 获取当前窗口快照
    """

    window_changed = pyqtSignal(WindowInfo, WindowInfo)

    def __init__(self, interval_ms: int = 500, parent: QObject | None = None):
        super().__init__(parent)
        self._current = WindowInfo()
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._poll)

    @property
    def current(self) -> WindowInfo:
        """返回最近一次捕获的活动窗口信息。"""
        return self._current

    def start(self) -> None:
        """开始轮询。创建后默认自动启动。"""
        self._current = _get_foreground_window()
        self._timer.start()

    def stop(self) -> None:
        """停止轮询。"""
        self._timer.stop()

    def poll_now(self) -> WindowInfo:
        """立即执行一次检测并返回结果（不会触发信号）。"""
        return _get_foreground_window()

    # ── 内部 ──────────────────────────────────────────────────

    def _poll(self) -> None:
        info = _get_foreground_window()
        if info.hwnd != self._current.hwnd:
            old = self._current
            self._current = info
            self.window_changed.emit(old, info)


# ═══════════════════════════════════════════════════════════════
#  底层 Win32 函数
# ═══════════════════════════════════════════════════════════════

def _get_foreground_window() -> WindowInfo:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return WindowInfo()

    title = _get_window_text(hwnd)
    pid = _get_window_pid(hwnd)
    process_name = _get_process_name(pid) if pid else ""
    return WindowInfo(hwnd=int(hwnd), title=title, process_name=process_name)


def _get_window_text(hwnd: wintypes.HWND) -> str:
    buf = (ctypes.c_wchar * 512)()
    length = user32.GetWindowTextW(hwnd, buf, 512)
    return buf[:length] if length > 0 else ""


def _get_window_pid(hwnd: wintypes.HWND) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, byref(pid))
    return pid.value


def _get_process_name(pid: int) -> str:
    """通过 PID 从进程快照中查找 exe 文件名。"""
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        return ""

    entry = PROCESSENTRY32W()
    entry.dwSize = sizeof(PROCESSENTRY32W)

    if not kernel32.Process32FirstW(snapshot, byref(entry)):
        kernel32.CloseHandle(snapshot)
        return ""

    while True:
        if entry.th32ProcessID == pid:
            kernel32.CloseHandle(snapshot)
            return entry.szExeFile
        if not kernel32.Process32NextW(snapshot, byref(entry)):
            break

    kernel32.CloseHandle(snapshot)
    return ""
