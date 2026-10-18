"""
core/notifier.py — Unified Multi-Channel Notifier for JARVIS Mark 55.

Dispatches notifications across:
  1. Desktop: Native macOS banner (osascript) / Windows toast / Linux notify-send
  2. HUD: Real-time system log on the JARVIS holographic display
  3. Telegram: Instant push notifications & file attachments directly to Boss's phone
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

_OS = platform.system()  # "Darwin" (macOS), "Windows", "Linux"

# Registered HUD logger callback (e.g. ui.write_log)
_HUD_LOGGER: Optional[Callable[[str], None]] = None


def set_hud_logger(logger: Callable[[str], None]) -> None:
    """Register a UI/HUD logger callback so notifications appear on screen."""
    global _HUD_LOGGER
    _HUD_LOGGER = logger


def _send_desktop_notification(title: str, message: str, urgency: str = "normal") -> bool:
    """Show a native desktop notification without blocking."""
    clean_title = title.replace('"', '\\"').replace("'", "")
    clean_msg = message.replace('"', '\\"').replace("'", "")

    try:
        if _OS == "Darwin":  # macOS
            sound_clause = ' sound name "Hero"' if urgency == "urgent" else ' sound name "Subtle"'
            script = f'display notification "{clean_msg}" with title "{clean_title}"{sound_clause}'
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
            return res.returncode == 0

        elif _OS == "Windows":
            notified = False
            try:
                from plyer import notification
                notification.notify(title=title, message=message, timeout=10)
                notified = True
            except Exception:
                pass

            if not notified:
                try:
                    from win10toast import ToastNotifier
                    ToastNotifier().show_toast(title, message, duration=10, threaded=True)
                    notified = True
                except Exception:
                    pass

            if not notified:
                subprocess.Popen(
                    ["msg", "*", f"{title}: {message}"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            return True

        else:  # Linux
            urg = "critical" if urgency == "urgent" else "normal"
            res = subprocess.run(
                ["notify-send", f"--urgency={urg}", clean_title, clean_msg],
                capture_output=True,
                timeout=5,
            )
            return res.returncode == 0

    except Exception as e:
        print(f"[Notifier] ❌ Desktop notification failed: {e}")
        return False


def send_notification(
    title: str,
    message: str,
    channel: str = "all",
    urgency: str = "normal",
    file_path: Optional[str] = None,
    player: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Dispatch a multi-channel notification.

    Args:
        title: Notification header/title
        message: Notification body text
        channel: 'all' | 'desktop' | 'telegram'
        urgency: 'normal' | 'urgent' | 'reminder'
        file_path: Optional path to a file or image to send to Telegram
        player: Optional JarvisUI instance for HUD logging

    Returns:
        Dict showing delivery status across channels: {'desktop': bool, 'telegram': bool, 'hud': bool}
    """
    title = (title or "J.A.R.V.I.S").strip()
    message = (message or "").strip()
    channel = (channel or "all").lower().strip()
    status = {"desktop": False, "telegram": False, "hud": False}

    # 1. Write to HUD
    hud_fn = getattr(player, "write_log", None) or _HUD_LOGGER
    if hud_fn:
        try:
            prefix = "🔔" if urgency == "urgent" else "📌"
            hud_fn(f"{prefix} [{title}] {message[:120]}")
            status["hud"] = True
        except Exception:
            pass

    # 2. Desktop notification
    if channel in ("all", "desktop"):
        status["desktop"] = _send_desktop_notification(title, message, urgency)

    # 3. Telegram push notification
    if channel in ("all", "telegram"):
        try:
            from core.telegram_bridge import get_telegram_client
            tg = get_telegram_client()
            if tg and tg.is_configured():
                formatted_text = f"<b>{title}</b>\n{message}"
                if file_path and Path(file_path).exists():
                    p = Path(file_path)
                    ext = p.suffix.lower()
                    if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
                        status["telegram"] = tg.send_photo(photo_path=p, caption=formatted_text)
                    else:
                        status["telegram"] = tg.send_document(file_path=p, caption=formatted_text)
                else:
                    status["telegram"] = tg.send_message(formatted_text)
            else:
                status["telegram"] = False
        except Exception as e:
            print(f"[Notifier] ⚠️ Telegram dispatch error: {e}")
            status["telegram"] = False

    print(f"[Notifier] Dispatched '{title}': desktop={status['desktop']}, telegram={status['telegram']}, hud={status['hud']}")
    return status
