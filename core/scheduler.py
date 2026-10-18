"""
core/scheduler.py — Autonomous Schedule & Routine Engine for JARVIS Mark 55.

Persists schedules to memory/schedules.json.
Runs a background worker to evaluate due tasks and trigger:
  1. Multi-channel notifications (Desktop + Telegram) via core.notifier
  2. Spoken proactive announcements when JARVIS is live
  3. Tailored routine management (Winter Arc, Class 11 studies, project sprints)
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.notifier import send_notification

_BASE_DIR = Path(__file__).resolve().parent.parent
_SCHEDULES_FILE = _BASE_DIR / "memory" / "schedules.json"
_LOCK = threading.Lock()

# Global proactive speech callback: callback(prompt: str)
_PROACTIVE_CALLBACK: Optional[Callable[[str], None]] = None


def set_proactive_callback(cb: Optional[Callable[[str], None]]) -> None:
    """Set the callback used to speak a reminder or schedule alert through JARVIS."""
    global _PROACTIVE_CALLBACK
    _PROACTIVE_CALLBACK = cb


def _load_schedules() -> List[Dict[str, Any]]:
    if not _SCHEDULES_FILE.exists():
        return []
    try:
        with _LOCK:
            content = _SCHEDULES_FILE.read_text(encoding="utf-8")
            data = json.loads(content)
            return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[Scheduler] ⚠️ Error loading schedules: {e}")
        return []


def _save_schedules(schedules: List[Dict[str, Any]]) -> None:
    try:
        with _LOCK:
            _SCHEDULES_FILE.parent.mkdir(parents=True, exist_ok=True)
            _SCHEDULES_FILE.write_text(
                json.dumps(schedules, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
    except Exception as e:
        print(f"[Scheduler] ❌ Error saving schedules: {e}")


def add_schedule(
    title: str,
    time_str: str,
    message: str = "",
    recurring: str = "daily",
    date_str: Optional[str] = None,
    days: Optional[List[str]] = None,
    action_type: str = "notification",
    action_payload: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Register a new schedule or routine task.

    Args:
        title: Short title (e.g. 'Winter Arc Workout', 'Study Block')
        time_str: HH:MM in 24-hour format (e.g. '17:30' or '07:00')
        message: Description or detail for the reminder
        recurring: 'daily' | 'weekdays' | 'once' | 'custom'
        date_str: YYYY-MM-DD for one-off tasks (defaults to today/tomorrow if omitted and 'once')
        days: List of weekday names if recurring='custom' (e.g. ['wednesday', 'friday', 'sunday'])
        action_type: 'notification' | 'proactive_prompt' | 'task'
        action_payload: Additional payload or command text
    """
    time_str = time_str.strip()
    # Normalize time e.g. "7:00" -> "07:00"
    if ":" in time_str:
        parts = time_str.split(":")
        time_str = f"{int(parts[0]):02d}:{int(parts[1]):02d}"

    recurring = recurring.lower().strip()
    if recurring not in ("daily", "weekdays", "once", "custom"):
        recurring = "daily"

    now = datetime.now()
    if recurring == "once" and not date_str:
        # Check if the time has already passed today
        sched_time = datetime.strptime(time_str, "%H:%M").time()
        if sched_time <= now.time():
            date_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            date_str = now.strftime("%Y-%m-%d")

    sched_id = f"sched_{now.strftime('%Y%m%d%H%M%S')}_{len(_load_schedules()) + 1}"

    item = {
        "id": sched_id,
        "title": title.strip() or "Scheduled Task",
        "time": time_str,
        "message": (message or title).strip(),
        "recurring": recurring,
        "date": date_str,
        "days": [d.lower() for d in days] if days else [],
        "action_type": action_type,
        "action_payload": action_payload or "",
        "enabled": True,
        "last_run": "",
        "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
    }

    schedules = _load_schedules()
    schedules.append(item)
    _save_schedules(schedules)
    print(f"[Scheduler] ➕ Scheduled: '{item['title']}' at {time_str} ({recurring})")
    return item


def list_schedules(active_only: bool = True) -> List[Dict[str, Any]]:
    """Return all stored schedules."""
    items = _load_schedules()
    if active_only:
        return [i for i in items if i.get("enabled", True)]
    return items


def cancel_schedule(identifier: str) -> bool:
    """Cancel / delete a schedule by ID or matching title."""
    ident = identifier.strip().lower()
    schedules = _load_schedules()
    new_schedules = []
    removed = False

    for item in schedules:
        item_id = item.get("id", "").lower()
        item_title = item.get("title", "").lower()
        if not removed and (item_id == ident or ident in item_title or item_title in ident):
            removed = True
            print(f"[Scheduler] 🗑️ Removed schedule: {item['title']} ({item['id']})")
            continue
        new_schedules.append(item)

    if removed:
        _save_schedules(new_schedules)
    return removed


def toggle_schedule(identifier: str, enable: bool) -> bool:
    """Enable or disable a schedule."""
    ident = identifier.strip().lower()
    schedules = _load_schedules()
    found = False

    for item in schedules:
        if item.get("id", "").lower() == ident or ident in item.get("title", "").lower():
            item["enabled"] = bool(enable)
            found = True
            break

    if found:
        _save_schedules(schedules)
    return found


def plan_daily_routine() -> List[Dict[str, Any]]:
    """
    Set up Boss Divyanshu Verma's high-performance daily routine.
    Tailored to: Class 11 commerce studies, Winter Arc workouts (eggs Wed/Fri/Sun, creatine post-workout),
    vibe coding & autonomous systems building, and evening review.
    """
    routine = [
        {
            "title": "Morning Focus & System Initialization",
            "time": "06:30",
            "recurring": "daily",
            "message": "Good morning Boss! Time to begin the day with high energy and review daily priorities.",
        },
        {
            "title": "Class 11 Commerce Deep Study Block",
            "time": "07:15",
            "recurring": "daily",
            "message": "Focus sprint: Class 11 Commerce syllabus, accounts, and business concepts.",
        },
        {
            "title": "Nutritious Lunch & Recharge Break",
            "time": "13:00",
            "recurring": "daily",
            "message": "High-protein meal time. Take a proper break to keep mental bandwidth sharp.",
        },
        {
            "title": "Autonomous AI & Vibe Coding Block",
            "time": "16:00",
            "recurring": "daily",
            "message": "Engineering sprint: Antigravity IDE, JARVIS enhancements, or Divyanshu Industries projects.",
        },
        {
            "title": "Winter Arc Dumbbell Workout",
            "time": "18:00",
            "recurring": "daily",
            "message": "Winter Arc workout session! Hit the dumbbells. (Reminder: Eggs on Wed/Fri/Sun).",
        },
        {
            "title": "Post-Workout Creatine & Nutrition Check",
            "time": "19:15",
            "recurring": "daily",
            "message": "Post-workout nutrition: Wellcore creatine with bread and high-protein vegetarian meal.",
        },
        {
            "title": "Evening Review & Next Day Architecture",
            "time": "21:30",
            "recurring": "daily",
            "message": "Day retrospective: Review today's code and study milestones. Plan tomorrow's top 3 objectives.",
        },
    ]

    # Clean existing routine items with matching titles to avoid duplicates
    existing = _load_schedules()
    routine_titles = {r["title"] for r in routine}
    filtered = [item for item in existing if item.get("title") not in routine_titles]
    _save_schedules(filtered)

    created = []
    for r in routine:
        item = add_schedule(
            title=r["title"],
            time_str=r["time"],
            message=r["message"],
            recurring=r["recurring"],
        )
        created.append(item)

    return created


class SchedulerRunner(threading.Thread):
    """Background daemon thread checking for due schedules every 15 seconds."""

    def __init__(self, check_interval: int = 15):
        super().__init__(name="JarvisSchedulerRunner", daemon=True)
        self.check_interval = check_interval
        self._running = True

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        print("[Scheduler] 🚀 Autonomous scheduler service started.")
        while self._running:
            try:
                self._check_and_execute()
            except Exception as e:
                print(f"[Scheduler] ⚠️ Runner check error: {e}")
            time.sleep(self.check_interval)

    def _check_and_execute(self) -> None:
        now = datetime.now()
        current_time_str = now.strftime("%H:%M")
        current_date_str = now.strftime("%Y-%m-%d")
        current_weekday = now.strftime("%A").lower()
        minute_key = now.strftime("%Y-%m-%d %H:%M")

        schedules = _load_schedules()
        modified = False

        for item in list(schedules):
            if not item.get("enabled", True):
                continue

            item_time = item.get("time", "")
            if item_time != current_time_str:
                continue

            # Prevent double-execution within the same minute
            if item.get("last_run") == minute_key:
                continue

            recurring = item.get("recurring", "daily")
            days = item.get("days", [])
            date_req = item.get("date")

            # Check recurrence conditions
            due = False
            if recurring == "daily":
                due = True
            elif recurring == "weekdays":
                due = current_weekday in ("monday", "tuesday", "wednesday", "thursday", "friday")
            elif recurring == "custom":
                due = current_weekday in days
            elif recurring == "once":
                due = (not date_req) or (date_req == current_date_str)

            if not due:
                continue

            # Execute the scheduled task
            self._trigger_task(item)
            item["last_run"] = minute_key
            modified = True

            # If it's a one-time event, disable or delete
            if recurring == "once":
                item["enabled"] = False
                print(f"[Scheduler] ✅ Completed one-time task: {item['title']}")

        if modified:
            _save_schedules(schedules)

    def _trigger_task(self, item: Dict[str, Any]) -> None:
        title = item.get("title", "Scheduled Alert")
        message = item.get("message", "Time for your scheduled task.")
        action_type = item.get("action_type", "notification")
        print(f"[Scheduler] ⏰ TRIGGERING: {title} ({item.get('time')})")

        # 1. Multi-channel notification: Desktop banner + Telegram push to mobile
        send_notification(
            title=f"Schedule: {title}",
            message=message,
            channel="all",
            urgency="reminder",
        )

        # 2. Voice announcement via JARVIS if connected
        if _PROACTIVE_CALLBACK:
            try:
                spoken_text = (
                    f"Sir, according to your schedule, it is now time for {title}. {message} "
                    "Inform the Boss politely in one or two sentences."
                )
                _PROACTIVE_CALLBACK(spoken_text)
            except Exception as e:
                print(f"[Scheduler] ⚠️ Proactive callback error: {e}")


# Singleton runner instance
_RUNNER: Optional[SchedulerRunner] = None


def start_scheduler_runner() -> SchedulerRunner:
    """Initialize and start the global scheduler runner daemon."""
    global _RUNNER
    if _RUNNER is None or not _RUNNER.is_alive():
        _RUNNER = SchedulerRunner()
        _RUNNER.start()
    return _RUNNER


def stop_scheduler_runner() -> None:
    """Stop the scheduler runner daemon."""
    global _RUNNER
    if _RUNNER:
        _RUNNER.stop()
        _RUNNER = None
