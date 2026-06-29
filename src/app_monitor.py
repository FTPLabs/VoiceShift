"""
Windows foreground-app monitor.
Polls the active window every 500 ms and returns its process name.
Used to auto-switch presets based on which app is in focus.
"""

import threading
import time
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

try:
    import ctypes
    import ctypes.wintypes
    _WIN32 = True
except ImportError:
    _WIN32 = False


def _get_foreground_process() -> Optional[str]:
    if not _WIN32:
        return None
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = ctypes.wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = ctypes.windll.kernel32.OpenProcess(0x0400, False, pid)
        if not handle:
            return None
        buf = ctypes.create_unicode_buffer(260)
        ctypes.windll.psapi.GetModuleFileNameExW(handle, None, buf, 260)
        ctypes.windll.kernel32.CloseHandle(handle)
        path = buf.value
        return path.split("\\")[-1].lower() if path else None
    except Exception:
        return None


class AppMonitor:
    """
    Fires `on_app_change(process_name)` whenever the foreground app changes.
    Runs in a background daemon thread.
    """

    def __init__(self, on_app_change: Callable[[Optional[str]], None], interval: float = 0.5):
        self._callback = on_app_change
        self._interval = interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last: Optional[str] = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            current = _get_foreground_process()
            if current != self._last:
                self._last = current
                try:
                    self._callback(current)
                except Exception as e:
                    logger.debug("AppMonitor callback error: %s", e)
            time.sleep(self._interval)
