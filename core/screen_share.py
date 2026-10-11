"""
Screen & Window Share Engine for Mark-LV.

Supports:
- Sharing the Entire Screen (all displays / selected monitor)
- Sharing a Specific Application Window (dynamic bounds tracking on macOS, Windows, Linux)
- High-performance capture using mss and OS window managers
- Real-time frame streaming for HUD display & Gemini AI Live Vision integration
"""
from __future__ import annotations

import io
import sys
import time
import platform
import threading
import subprocess
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any

import numpy as np

try:
    import mss
    import mss.tools
    _MSS = True
except ImportError:
    _MSS = False

try:
    import cv2
    _CV2 = True
except ImportError:
    _CV2 = False

try:
    import PIL.Image
    _PIL = True
except ImportError:
    _PIL = False

_IS_MAC = platform.system() == "Darwin"
_IS_WIN = platform.system() == "Windows"
_IS_LINUX = platform.system() == "Linux"

_IMG_MAX_W = 1280
_IMG_MAX_H = 720
_JPEG_Q = 80


class ScreenShareManager:
    """Singleton manager controlling active screen/window sharing."""

    def __init__(self):
        self._lock = threading.Lock()
        self._active_target: Optional[Dict[str, Any]] = None
        self._is_active = False
        self._last_frame_bytes: Optional[bytes] = None
        self._last_frame_time = 0.0

    def is_sharing(self) -> bool:
        with self._lock:
            return self._is_active and self._active_target is not None

    def get_active_target(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return dict(self._active_target) if self._active_target else None

    def get_share_targets(self) -> List[Dict[str, Any]]:
        """Discover available entire screens and individual application windows."""
        targets: List[Dict[str, Any]] = []

        # 1. Full Monitors
        if _MSS:
            try:
                with mss.mss() as sct:
                    # sct.monitors[0] is virtual combined, [1..n] are individual screens
                    screens = sct.monitors[1:] if len(sct.monitors) > 1 else sct.monitors[:1]
                    for idx, mon in enumerate(screens, 1):
                        targets.append({
                            "id": f"screen:{idx}",
                            "type": "screen",
                            "name": f"Entire Screen (Display {idx})",
                            "detail": f"{mon['width']}x{mon['height']} @ ({mon['left']}, {mon['top']})",
                            "monitor_idx": idx,
                            "bounds": (mon["left"], mon["top"], mon["width"], mon["height"]),
                        })
            except Exception as e:
                print(f"[ScreenShare] ⚠️ Error enumerating monitors: {e}")

        # 2. Open Application Windows
        if _IS_MAC:
            targets.extend(self._get_mac_windows())
        elif _IS_WIN:
            targets.extend(self._get_win_windows())
        elif _IS_LINUX:
            targets.extend(self._get_linux_windows())

        return targets

    def get_screens(self) -> List[Dict[str, Any]]:
        """Return list of available display screens."""
        return [t for t in self.get_share_targets() if t["type"] == "screen"]

    def get_windows(self) -> List[Dict[str, Any]]:
        """Return list of active application windows."""
        return [t for t in self.get_share_targets() if t["type"] == "window"]

    def _get_mac_windows(self) -> List[Dict[str, Any]]:
        """Enumerate active on-screen application windows on macOS using Quartz."""
        windows: List[Dict[str, Any]] = []
        try:
            import Quartz
            options = (
                Quartz.kCGWindowListOptionOnScreenOnly
                | Quartz.kCGWindowListExcludeDesktopElements
            )
            raw_list = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)
            ignored_owners = {
                "Window Server", "Dock", "SystemUIServer", "Control Center",
                "Notification Center", "Spotlight", "MenuBarAgent", "loginwindow",
                "CoreServicesUIAgent", "Talagent", "WindowManager", "UniversalAccessControl"
            }

            for win in raw_list:
                owner = str(win.get("kCGWindowOwnerName", "")).strip()
                title = str(win.get("kCGWindowName", "")).strip()
                wid = win.get("kCGWindowNumber", 0)
                bounds = win.get("kCGWindowBounds", {})
                w = int(bounds.get("Width", 0))
                h = int(bounds.get("Height", 0))
                x = int(bounds.get("X", 0))
                y = int(bounds.get("Y", 0))

                # Filter out background daemons, tiny status items, empty off-screen rects
                if (
                    w >= 200 and h >= 140
                    and owner
                    and owner not in ignored_owners
                    and not owner.endswith("Agent")
                    and not owner.endswith("Service")
                    and not owner.endswith("Helper")
                ):
                    label = f"{owner} — {title}" if title else owner
                    windows.append({
                        "id": f"win:{wid}",
                        "type": "window",
                        "name": label,
                        "detail": f"{w}x{h} ({owner})",
                        "app": owner,
                        "title": title,
                        "window_id": wid,
                        "bounds": (x, y, w, h),
                    })
        except Exception as e:
            print(f"[ScreenShare] ⚠️ Quartz window enumeration failed: {e}")
        return windows

    def _get_win_windows(self) -> List[Dict[str, Any]]:
        """Enumerate active windows on Windows."""
        windows: List[Dict[str, Any]] = []
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32

            def enum_proc(hwnd, _):
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buff, length + 1)
                        title = buff.value
                        rect = wintypes.RECT()
                        user32.GetWindowRect(hwnd, ctypes.byref(rect))
                        w = rect.right - rect.left
                        h = rect.bottom - rect.top
                        if w >= 200 and h >= 140 and title not in ("Program Manager", "Settings"):
                            windows.append({
                                "id": f"win:{hwnd}",
                                "type": "window",
                                "name": title,
                                "detail": f"{w}x{h}",
                                "window_id": hwnd,
                                "bounds": (rect.left, rect.top, w, h),
                            })
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(WNDENUMPROC(enum_proc), 0)
        except Exception as e:
            print(f"[ScreenShare] ⚠️ Windows enum error: {e}")
    def _get_linux_windows(self) -> List[Dict[str, Any]]:
        """Enumerate active windows on Linux (X11 via wmctrl or pygetwindow)."""
        windows: List[Dict[str, Any]] = []
        # Attempt 1: wmctrl
        if shutil.which("wmctrl"):
            try:
                res = subprocess.run(["wmctrl", "-l", "-G"], capture_output=True, text=True, timeout=2)
                for line in res.stdout.strip().splitlines():
                    parts = line.split(None, 7)
                    if len(parts) >= 8:
                        wid_hex, desktop, x, y, w, h, host, title = parts
                        try:
                            x_val, y_val, w_val, h_val = int(x), int(y), int(w), int(h)
                        except ValueError:
                            continue
                        if w_val >= 200 and h_val >= 140 and title.strip():
                            clean_title = title.strip()
                            windows.append({
                                "id": f"win:{wid_hex}",
                                "type": "window",
                                "name": clean_title,
                                "detail": f"{w_val}x{h_val}",
                                "window_id": wid_hex,
                                "bounds": (x_val, y_val, w_val, h_val),
                            })
                if windows:
                    return windows
            except Exception:
                pass

        # Attempt 2: pygetwindow if installed
        try:
            import pygetwindow as gw
            for win in gw.getAllWindows():
                if win.title and win.width >= 200 and win.height >= 140:
                    windows.append({
                        "id": f"win:{id(win)}",
                        "type": "window",
                        "name": win.title,
                        "detail": f"{win.width}x{win.height}",
                        "window_id": getattr(win, "_hWnd", id(win)),
                        "bounds": (win.left, win.top, win.width, win.height),
                    })
        except Exception:
            pass

        return windows

    def start_sharing(self, target: Dict[str, Any]) -> bool:
        """Activate sharing for the chosen target."""
        with self._lock:
            self._active_target = dict(target)
            self._is_active = True
            print(f"[ScreenShare] 📺 Started sharing: {target.get('name')}")
            return True

    def stop_sharing(self) -> None:
        """Stop active screen sharing."""
        with self._lock:
            if self._is_active:
                name = self._active_target.get("name") if self._active_target else "Screen"
                print(f"[ScreenShare] 🛑 Stopped sharing: {name}")
            self._is_active = False
            self._active_target = None

    def capture_frame(self) -> Optional[np.ndarray]:
        """Capture the current frame of the active target as an RGB numpy array."""
        target = self.get_active_target()
        if not target or not _MSS:
            return None

        try:
            with mss.mss() as sct:
                if target["type"] == "screen":
                    idx = target.get("monitor_idx", 1)
                    monitors = sct.monitors
                    mon = monitors[idx] if idx < len(monitors) else monitors[0]
                    shot = sct.grab(mon)
                    return np.array(shot, dtype=np.uint8)[:, :, :3]  # BGR

                elif target["type"] == "window":
                    x, y, w, h = target["bounds"]

                    # Query fresh coordinates in case window was moved
                    wid = target.get("window_id")
                    if _IS_MAC and wid:
                        try:
                            import Quartz
                            wl = Quartz.CGWindowListCopyWindowInfo(
                                Quartz.kCGWindowListOptionIncludingWindow, wid
                            )
                            if wl:
                                b = wl[0].get("kCGWindowBounds", {})
                                x = int(b.get("X", x))
                                y = int(b.get("Y", y))
                                w = int(b.get("Width", w))
                                h = int(b.get("Height", h))
                        except Exception:
                            pass
                    elif _IS_WIN and wid:
                        try:
                            import ctypes
                            from ctypes import wintypes
                            rect = wintypes.RECT()
                            if ctypes.windll.user32.GetWindowRect(int(wid), ctypes.byref(rect)):
                                x = int(rect.left)
                                y = int(rect.top)
                                w = int(rect.right - rect.left)
                                h = int(rect.bottom - rect.top)
                        except Exception:
                            pass
                    elif _IS_LINUX and wid and shutil.which("xwininfo"):
                        try:
                            res = subprocess.run(
                                ["xwininfo", "-id", str(wid)],
                                capture_output=True, text=True, timeout=1
                            )
                            rx, ry, rw, rh = None, None, None, None
                            for l in res.stdout.splitlines():
                                l_str = l.strip()
                                if l_str.startswith("Absolute upper-left X:"):
                                    rx = int(l_str.split(":")[-1].strip())
                                elif l_str.startswith("Absolute upper-left Y:"):
                                    ry = int(l_str.split(":")[-1].strip())
                                elif l_str.startswith("Width:"):
                                    rw = int(l_str.split(":")[-1].strip())
                                elif l_str.startswith("Height:"):
                                    rh = int(l_str.split(":")[-1].strip())
                            if rx is not None and ry is not None and rw and rh:
                                x, y, w, h = rx, ry, rw, rh
                        except Exception:
                            pass

                    # Ensure coordinates are within display
                    if w <= 0 or h <= 0:
                        return None

                    shot = sct.grab({"left": x, "top": y, "width": w, "height": h})
                    return np.array(shot, dtype=np.uint8)[:, :, :3]  # BGR
        except Exception:
            return None

    def capture_for_vision(self) -> Tuple[bytes, str]:
        """Produce compressed JPEG bytes for Gemini Live vision injection."""
        frame = self.capture_frame()
        if frame is None:
            # Fallback to entire screen grab
            with mss.mss() as sct:
                target_mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                shot = sct.grab(target_mon)
                frame = np.array(shot, dtype=np.uint8)[:, :, :3]

        # Convert BGR -> RGB and compress
        if _PIL:
            rgb = frame[:, :, ::-1] if _CV2 else frame
            img = PIL.Image.fromarray(rgb)
            img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), PIL.Image.BILINEAR)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=_JPEG_Q, optimize=False)
            return buf.getvalue(), "image/jpeg"

        if _CV2:
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_Q])
            return buf.tobytes(), "image/jpeg"

        return b"", "image/jpeg"


# Global shared instance
screen_share_engine = ScreenShareManager()
