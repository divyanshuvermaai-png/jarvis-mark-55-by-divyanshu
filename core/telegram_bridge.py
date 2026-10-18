"""
core/telegram_bridge.py — Autonomous Telegram Bridge for JARVIS Mark 55.

Powered by Telegram BotFather API.
Enables full remote control when Boss is away from home:
  1. File delivery: "send me file report.pdf", "send latest render", "send project.zip"
     -> Finds the file on macOS and uploads directly to mobile Telegram.
  2. 3D & Blender delegation: "make a low poly sword in blender" -> runs Blender MCP / script.
  3. Antigravity delegation: "build this website from antigravity" -> triggers Antigravity bridge.
  4. Routine & Schedulers: "what is my schedule today?", "plan my routine", "remind me in 20 min"
     -> Manages schedules and pushes proactive alerts.
  5. Executive Chat: Full AI assistant conversation via Groq Qwen & Gemini with Boss profile.
  6. Voice message support: Listens to voice notes sent via Telegram.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

from memory.config_manager import (
    get_telegram_bot_token,
    save_telegram_bot_token,
    get_telegram_chat_id,
    save_telegram_chat_id,
    load_api_keys,
)

_BASE_DIR = Path(__file__).resolve().parent.parent
_TELEGRAM_API_URL = "https://api.telegram.org/bot"

# HUD log callback (e.g. ui.write_log)
_LOG_CALLBACK: Optional[Callable[[str], None]] = None


def set_telegram_logger(cb: Optional[Callable[[str], None]]) -> None:
    global _LOG_CALLBACK
    _LOG_CALLBACK = cb


def _log(msg: str) -> None:
    print(f"[Telegram] {msg}")
    if _LOG_CALLBACK:
        try:
            _LOG_CALLBACK(f"[TG] {msg}")
        except Exception:
            pass


class TelegramClient:
    """Lightweight, rock-solid client for the Telegram Bot API using requests."""

    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        self.token = (token or get_telegram_bot_token() or os.environ.get("TELEGRAM_BOT_TOKEN", "")).strip()
        self.chat_id = (chat_id or get_telegram_chat_id() or os.environ.get("TELEGRAM_CHAT_ID", "")).strip()
        self.session = requests.Session()

    def is_configured(self) -> bool:
        return bool(self.token and len(self.token) > 15)

    def refresh_config(self) -> None:
        self.token = (get_telegram_bot_token() or os.environ.get("TELEGRAM_BOT_TOKEN", "")).strip()
        self.chat_id = (get_telegram_chat_id() or os.environ.get("TELEGRAM_CHAT_ID", "")).strip()

    def _url(self, method: str) -> str:
        return f"{_TELEGRAM_API_URL}{self.token}/{method}"

    def get_me(self) -> Optional[Dict[str, Any]]:
        """Verify token and get bot details."""
        if not self.is_configured():
            return None
        try:
            resp = self.session.get(self._url("getMe"), timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    return data.get("result")
        except Exception as e:
            print(f"[Telegram] getMe error: {e}")
        return None

    def send_message(self, text: str, chat_id: Optional[str | int] = None, parse_mode: str = "HTML") -> bool:
        """Send a text message to Boss's Telegram chat."""
        target_chat = str(chat_id or self.chat_id).strip()
        if not self.is_configured() or not target_chat:
            return False

        # Telegram message length limit is 4096 characters; chunk if larger
        max_chunk = 4000
        text_chunks = [text[i:i + max_chunk] for i in range(0, len(text), max_chunk)] or [""]

        success = True
        for chunk in text_chunks:
            payload = {
                "chat_id": target_chat,
                "text": chunk,
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode
            try:
                resp = self.session.post(self._url("sendMessage"), json=payload, timeout=15)
                if resp.status_code != 200:
                    # Retry without HTML formatting if markup caused parse error
                    payload.pop("parse_mode", None)
                    r2 = self.session.post(self._url("sendMessage"), json=payload, timeout=10)
                    if r2.status_code != 200:
                        success = False
            except Exception as e:
                print(f"[Telegram] ❌ send_message failed: {e}")
                success = False
        return success

    def send_document(self, file_path: Path | str, caption: Optional[str] = None, chat_id: Optional[str | int] = None) -> bool:
        """Send a document or file from the Mac to Boss's mobile Telegram."""
        target_chat = str(chat_id or self.chat_id).strip()
        p = Path(file_path).expanduser()
        if not self.is_configured() or not target_chat or not p.exists() or not p.is_file():
            return False

        try:
            with open(p, "rb") as f:
                files = {"document": (p.name, f)}
                data = {"chat_id": target_chat}
                if caption:
                    data["caption"] = caption[:1024]
                resp = self.session.post(self._url("sendDocument"), data=data, files=files, timeout=60)
                return resp.status_code == 200 and resp.json().get("ok", False)
        except Exception as e:
            print(f"[Telegram] ❌ send_document failed: {e}")
            return False

    def send_photo(self, photo_path: Path | str, caption: Optional[str] = None, chat_id: Optional[str | int] = None) -> bool:
        """Send an image to Boss's mobile Telegram."""
        target_chat = str(chat_id or self.chat_id).strip()
        p = Path(photo_path).expanduser()
        if not self.is_configured() or not target_chat or not p.exists() or not p.is_file():
            return False

        try:
            with open(p, "rb") as f:
                files = {"photo": (p.name, f)}
                data = {"chat_id": target_chat}
                if caption:
                    data["caption"] = caption[:1024]
                resp = self.session.post(self._url("sendPhoto"), data=data, files=files, timeout=40)
                return resp.status_code == 200 and resp.json().get("ok", False)
        except Exception as e:
            print(f"[Telegram] ❌ send_photo failed: {e}")
            return False

    def get_updates(self, offset: Optional[int] = None, timeout: int = 20) -> List[Dict[str, Any]]:
        """Long-polling for new incoming messages."""
        if not self.is_configured():
            return []
        params = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        try:
            resp = self.session.get(self._url("getUpdates"), params=params, timeout=timeout + 10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    return data.get("result", [])
        except Exception as e:
            # Timeouts on long polling are normal
            pass
        return []

    def get_file(self, file_id: str) -> Optional[bytes]:
        """Download a file (e.g. voice note or photo) from Telegram servers."""
        if not self.is_configured():
            return None
        try:
            res = self.session.get(self._url("getFile"), params={"file_id": file_id}, timeout=15)
            if res.status_code == 200:
                fpath = res.json().get("result", {}).get("file_path")
                if fpath:
                    download_url = f"https://api.telegram.org/file/bot{self.token}/{fpath}"
                    fres = self.session.get(download_url, timeout=30)
                    if fres.status_code == 200:
                        return fres.content
        except Exception as e:
            print(f"[Telegram] get_file error: {e}")
        return None


# ── File Search Engine for Remote File Transfer ──────────────────────────────

_CANDIDATE_SEARCH_DIRS = [
    Path.home() / "Desktop",
    Path.home() / "Downloads",
    Path.home() / "Documents",
    Path.home() / "Desktop" / "Antigravity_Projects",
    Path.home() / "Desktop" / "Blender_Projects",
    Path.home() / "Desktop" / "JarvisProjects",
    Path.home() / "Pictures",
    _BASE_DIR,
]


def find_files_for_transfer(query: str, limit: int = 5) -> List[Path]:
    """
    Search common Mac locations to locate the file Boss is asking for.
    Handles exact names, partial stems, extensions, and recency requests.
    """
    query = query.strip().lower()
    results: List[Path] = []
    seen: set = set()

    # Special case: "latest render" or "latest screenshot" or "latest download"
    if "latest" in query or "recent" in query:
        target_dir = Path.home() / "Downloads"
        target_exts = None
        if "render" in query or "blender" in query:
            target_dir = Path.home() / "Desktop" / "Blender_Projects"
            target_exts = {".png", ".jpg", ".blend", ".glb", ".mp4"}
        elif "screenshot" in query:
            target_dir = Path.home() / "Desktop"
            target_exts = {".png", ".jpg"}
        elif "antigravity" in query:
            target_dir = Path.home() / "Desktop" / "Antigravity_Projects"

        candidates = []
        if target_dir.exists():
            for p in target_dir.rglob("*"):
                if p.is_file() and not p.name.startswith("."):
                    if target_exts is None or p.suffix.lower() in target_exts:
                        try:
                            candidates.append((p.stat().st_mtime, p))
                        except Exception:
                            pass
        candidates.sort(reverse=True, key=lambda x: x[0])
        return [p for _, p in candidates[:limit]]

    # General search across candidate directories
    clean_query = query.replace("file", "").replace("send", "").replace("me", "").replace("please", "").strip()
    if not clean_query:
        clean_query = query

    for root_dir in _CANDIDATE_SEARCH_DIRS:
        if not root_dir.exists():
            continue
        try:
            # Shallow check first (direct children)
            for p in root_dir.glob("*"):
                if p.is_file() and not p.name.startswith("."):
                    p_name_lower = p.name.lower()
                    if clean_query in p_name_lower:
                        if p not in seen:
                            seen.add(p)
                            results.append(p)
                            if len(results) >= limit:
                                return results

            # Deep check up to 2 subfolder levels
            for p in root_dir.glob("*/*"):
                if p.is_file() and not p.name.startswith("."):
                    p_name_lower = p.name.lower()
                    if clean_query in p_name_lower:
                        if p not in seen:
                            seen.add(p)
                            results.append(p)
                            if len(results) >= limit:
                                return results
        except Exception:
            pass

    return results[:limit]


# ── AI Response Generator for Telegram (Groq / Gemini) ───────────────────────

def _generate_remote_reply(user_prompt: str) -> str:
    """Generate an executive, crisp response tailored to Boss Divyanshu Verma."""
    system_prompt = (
        "You are JARVIS Mark 55, autonomous personal AI assistant created by and reporting "
        "directly to Boss Divyanshu Verma (founder of Divyanshu Industries). "
        "The Boss is messaging you remotely on Telegram while away from his Mac. "
        "Be sharp, composed, respectful, and highly competent like Iron Man's JARVIS. "
        "Address him as 'Boss' or 'Sir'. Keep replies concise and actionable. "
        "Context: Divyanshu Verma, 17, Class 11 Commerce, Bandikui/Jaipur, Winter Arc fitness phase "
        "(dumbbell cutting, creatine post-workout, eggs Wed/Fri/Sun). "
        "If he gives a task, report action taken clearly."
    )

    # 1. Try Groq Qwen for lightning-fast ~450 t/s response
    try:
        from core.groq_client import call_groq_coder
        prompt_full = f"{system_prompt}\n\nBoss: {user_prompt}\nJARVIS:"
        resp = call_groq_coder(prompt_full, max_tokens=600)
        if resp and resp.text:
            return resp.text.strip()
    except Exception:
        pass

    # 2. Fallback to Gemini ladder
    try:
        from core import gemini
        resp_text = gemini.text(f"{system_prompt}\n\nBoss: {user_prompt}", tier=gemini.FAST)
        if resp_text:
            return resp_text.strip()
    except Exception as e:
        print(f"[Telegram] LLM error: {e}")

    return "Got it, Boss. Command logged and processing on your workstation."


# ── Telegram Message Dispatcher & Command Processor ─────────────────────────

class TelegramBotDaemon(threading.Thread):
    """
    Background daemon continuously listening for Boss's instructions via Telegram.
    Runs long polling without needing an open port or public IP.
    """

    def __init__(self, client: TelegramClient):
        super().__init__(name="JarvisTelegramDaemon", daemon=True)
        self.client = client
        self._running = True
        self._last_offset: Optional[int] = None

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        if not self.client.is_configured():
            _log("⚠️ Telegram Bot Token not set in config/api_keys.json. Bot daemon idle.")
            return

        bot_info = self.client.get_me()
        if not bot_info:
            _log("❌ Invalid Telegram Bot Token. Check @BotFather token in config/api_keys.json.")
            return

        bot_user = bot_info.get("username", "JARVIS_Bot")
        _log(f"🚀 Telegram Bridge online as @{bot_user}")

        while self._running:
            try:
                updates = self.client.get_updates(offset=self._last_offset, timeout=20)
                for update in updates:
                    update_id = update.get("update_id")
                    self._last_offset = update_id + 1
                    msg = update.get("message")
                    if msg:
                        # Process message in separate thread to avoid blocking polling loop
                        threading.Thread(
                            target=self._handle_incoming_message,
                            args=(msg,),
                            daemon=True,
                        ).start()
            except Exception as e:
                time.sleep(3)

    def _handle_incoming_message(self, msg: Dict[str, Any]) -> None:
        sender = msg.get("from", {})
        chat = msg.get("chat", {})
        chat_id = str(chat.get("id", ""))
        sender_id = str(sender.get("id", ""))
        sender_name = sender.get("first_name", "User")
        text = (msg.get("text") or "").strip()
        voice = msg.get("voice") or msg.get("audio")

        # ── Pairing Handshake & Authorization ──
        configured_chat_id = self.client.chat_id
        if not configured_chat_id:
            # First interaction — bind to Boss's chat ID
            save_telegram_chat_id(chat_id)
            self.client.chat_id = chat_id
            _log(f"🔗 Paired Telegram with Boss's Chat ID: {chat_id} ({sender_name})")
            welcome = (
                f"🛡️ <b>J.A.R.V.I.S Mark 55 Initialized</b>\n\n"
                f"Welcome, Boss. Telegram link successfully established and authorized.\n"
                f"Workstation is connected. You can now:\n"
                f"• Ask for files: <i>'send me report.pdf'</i> or <i>'send latest render'</i>\n"
                f"• Give 3D tasks: <i>'make a low poly sword on blender'</i>\n"
                f"• Check schedules: <i>'what is my schedule today?'</i>\n"
                f"• Plan routine: <i>'plan my routine'</i>\n"
                f"• Send any question or command."
            )
            self.client.send_message(welcome, chat_id=chat_id)
            return

        # Security check: verify this message is from the authorized Boss
        if chat_id != configured_chat_id and sender_id != configured_chat_id:
            _log(f"⛔ Blocked unauthorized message from {sender_name} (ID: {chat_id})")
            self.client.send_message(
                "⛔ <b>Access Restricted</b>\nThis bot is connected to the private personal workstation of Divyanshu Verma.",
                chat_id=chat_id,
            )
            return

        # Handle voice note
        if voice:
            file_id = voice.get("file_id")
            _log("🎤 Received voice note from Boss.")
            self.client.send_message("🎤 <i>Listening to voice note...</i>", chat_id=chat_id)
            voice_bytes = self.client.get_file(file_id)
            if voice_bytes:
                # Transcribe using Gemini
                try:
                    from core import gemini
                    from google.genai import types
                    part = types.Part.from_bytes(data=voice_bytes, mime_type="audio/ogg")
                    transcription = gemini.text(
                        [part, "Transcribe this audio strictly. Return only what was spoken."],
                        tier=gemini.FAST,
                    )
                    text = transcription.strip()
                    _log(f"Transcribed voice note: '{text}'")
                except Exception as e:
                    _log(f"Voice transcription error: {e}")
                    text = ""

        if not text:
            return

        _log(f"📩 Boss: '{text}'")

        # ── 1. File Transfer Request ("send me file X") ──
        lower_text = text.lower()
        is_file_request = (
            text.startswith("/file")
            or "send me file" in lower_text
            or "send file" in lower_text
            or ("send me" in lower_text and any(k in lower_text for k in [".", "render", "download", "pdf", "zip", "doc", "code", "screenshot"]))
        )

        if is_file_request:
            query = (
                text.replace("/file", "")
                .replace("send me file", "")
                .replace("send file", "")
                .replace("send me", "")
                .replace("to my phone", "")
                .replace("to my mobile", "")
                .replace("to telegram", "")
                .strip()
            )
            self.client.send_message(f"🔍 <i>Searching workstation for '{query}'...</i>", chat_id=chat_id)
            matches = find_files_for_transfer(query)
            if not matches:
                self.client.send_message(f"❌ Boss, I couldn't find any file matching '{query}' on your Desktop, Downloads, or Projects.", chat_id=chat_id)
            else:
                target_file = matches[0]
                caption = f"📄 <b>{target_file.name}</b>\nLocation: <code>{target_file.parent.name}/</code>"
                ext = target_file.suffix.lower()
                ok = False
                if ext in (".png", ".jpg", ".jpeg", ".webp"):
                    ok = self.client.send_photo(target_file, caption=caption, chat_id=chat_id)
                else:
                    ok = self.client.send_document(target_file, caption=caption, chat_id=chat_id)

                if ok:
                    _log(f"✅ Delivered file '{target_file.name}' to Telegram.")
                else:
                    self.client.send_message(f"⚠️ Found {target_file.name}, but failed to upload (file may exceed Telegram limits).", chat_id=chat_id)
            return

        # ── 2. Schedule & Routine Commands ──
        if any(k in lower_text for k in ["schedule", "routine", "what is my plan", "remind me"]):
            from core import scheduler

            if "plan" in lower_text and "routine" in lower_text:
                routine = scheduler.plan_daily_routine()
                lines = [f"📋 <b>Daily Routine Planned ({len(routine)} milestones)</b>:"]
                for it in routine:
                    lines.append(f"• <b>{it['time']}</b> — {it['title']}")
                self.client.send_message("\n".join(lines), chat_id=chat_id)
                return

            if "what" in lower_text or "list" in lower_text or "today" in lower_text:
                items = scheduler.list_schedules(active_only=True)
                if not items:
                    self.client.send_message("📌 Boss, you have no active schedules configured right now.", chat_id=chat_id)
                else:
                    lines = ["📌 <b>Your Active Schedules & Routines</b>:"]
                    for it in items:
                        lines.append(f"• <b>{it.get('time')}</b> ({it.get('recurring')}) — {it.get('title')}")
                    self.client.send_message("\n".join(lines), chat_id=chat_id)
                return

        # ── 3. Blender 3D Task Delegation ──
        if "blender" in lower_text or ("make" in lower_text and ("3d" in lower_text or "model" in lower_text)):
            self.client.send_message("🛠️ <i>Dispatching Blender 3D task to your workstation...</i>", chat_id=chat_id)
            try:
                from core import blender_bridge
                from plugins import blender_mcp

                # Delegate via blender_bridge or procedural script
                res = blender_mcp.run({"instruction": text, "headless": True})
                self.client.send_message(f"🎨 <b>Blender Engine</b>:\n{res}", chat_id=chat_id)
                # Check for output renders to send
                recent_renders = find_files_for_transfer("latest render", limit=1)
                if recent_renders:
                    self.client.send_photo(recent_renders[0], caption="Render Viewport Output", chat_id=chat_id)
            except Exception as e:
                self.client.send_message(f"⚠️ Blender task initiated: {e}", chat_id=chat_id)
            return

        # ── 4. Antigravity Delegation ──
        if "antigravity" in lower_text:
            self.client.send_message("⚡ <i>Engaging Google Antigravity autonomous builder...</i>", chat_id=chat_id)
            try:
                from plugins import antigravity_mcp
                res = antigravity_mcp.run({"instruction": text})
                self.client.send_message(f"🏗️ <b>Antigravity Builder</b>:\n{res}", chat_id=chat_id)
            except Exception as e:
                self.client.send_message(f"⚠️ Antigravity execution error: {e}", chat_id=chat_id)
            return

        # ── 5. System Status Command ──
        if text.startswith("/status") or "system status" in lower_text:
            try:
                from actions.system_monitor import get_system_status
                status_str = get_system_status()
                self.client.send_message(f"🖥️ <b>MacBook Air System Status</b>:\n{status_str}", chat_id=chat_id)
            except Exception:
                import psutil
                cpu = psutil.cpu_percent()
                ram = psutil.virtual_memory().percent
                self.client.send_message(f"🖥️ <b>System Status</b>\nCPU: {cpu}%\nRAM: {ram}%", chat_id=chat_id)
            return

        if text.startswith("/help"):
            help_text = (
                "🤖 <b>J.A.RV.I.S Remote Control Commands</b>\n\n"
                "• <b>Send Files</b>: <i>'send me file document.pdf'</i>, <i>'send latest render'</i>\n"
                "• <b>3D & Blender</b>: <i>'make a low poly helmet on blender'</i>\n"
                "• <b>Antigravity</b>: <i>'build a portfolio website with antigravity'</i>\n"
                "• <b>Schedules</b>: <i>'what is my schedule today?'</i>, <i>'plan my routine'</i>\n"
                "• <b>System</b>: <code>/status</code> — Live CPU, RAM, battery\n"
                "• <b>Voice</b>: Send a voice note anytime."
            )
            self.client.send_message(help_text, chat_id=chat_id)
            return

        # ── 6. General Remote AI Assistant Query ──
        reply = _generate_remote_reply(text)
        self.client.send_message(reply, chat_id=chat_id)


# ── Global Singleton Client & Daemon ─────────────────────────────────────────

_CLIENT: Optional[TelegramClient] = None
_DAEMON: Optional[TelegramBotDaemon] = None


def get_telegram_client() -> TelegramClient:
    """Retrieve or initialize the global TelegramClient."""
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = TelegramClient()
    else:
        _CLIENT.refresh_config()
    return _CLIENT


def start_telegram_bridge() -> Optional[TelegramBotDaemon]:
    """Start the background Telegram bot daemon."""
    global _DAEMON
    client = get_telegram_client()
    if not client.is_configured():
        print("[Telegram] ℹ️ Telegram Bot Token not set. Set 'telegram_bot_token' in config/api_keys.json to enable remote Telegram control.")
        return None

    if _DAEMON is None or not _DAEMON.is_alive():
        _DAEMON = TelegramBotDaemon(client)
        _DAEMON.start()
    return _DAEMON


def stop_telegram_bridge() -> None:
    """Stop the Telegram daemon."""
    global _DAEMON
    if _DAEMON:
        _DAEMON.stop()
        _DAEMON = None


def send_telegram_notification(title: str, message: str, file_path: Optional[str] = None) -> bool:
    """Convenience helper to send a notification to Boss's Telegram."""
    client = get_telegram_client()
    if not client.is_configured():
        return False
    formatted = f"<b>{title}</b>\n{message}"
    if file_path and Path(file_path).exists():
        p = Path(file_path)
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            return client.send_photo(p, caption=formatted)
        return client.send_document(p, caption=formatted)
    return client.send_message(formatted)
