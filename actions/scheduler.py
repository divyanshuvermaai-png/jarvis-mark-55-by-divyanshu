"""
actions/scheduler.py — Autonomous task scheduling and routine planner for JARVIS.
Auto-discovered by core/action_loader.py.
"""
from __future__ import annotations

from typing import Any, Dict

from core.scheduler import (
    add_schedule,
    cancel_schedule,
    list_schedules,
    plan_daily_routine,
    toggle_schedule,
)


def scheduler(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    action = params.get("action", "list").lower().strip()
    title = params.get("title", "").strip()
    time_str = params.get("time", "").strip()
    message = params.get("message", "").strip()
    recurring = params.get("recurring", "daily").lower().strip()
    date_str = params.get("date", "").strip() or None
    identifier = params.get("identifier", "").strip() or title

    if action in ("add", "create", "set"):
        if not time_str:
            return "Please specify a time (e.g. '17:30' or '07:00') for the schedule."
        if not title:
            title = message[:30] if message else "Scheduled Task"

        item = add_schedule(
            title=title,
            time_str=time_str,
            message=message or title,
            recurring=recurring,
            date_str=date_str,
        )
        if player:
            player.write_log(f"[Scheduler] ➕ {item['time']} — {item['title']}")
        return f"Scheduled '{item['title']}' for {item['time']} ({item['recurring']})."

    elif action in ("list", "show", "view", "get"):
        items = list_schedules(active_only=True)
        if not items:
            return "You have no active schedules or routines currently configured."

        lines = ["Active schedules and routines:"]
        for i, item in enumerate(items, 1):
            rec = item.get("recurring", "daily")
            t = item.get("time", "")
            title_text = item.get("title", "")
            msg = item.get("message", "")
            extra = f" — {msg}" if msg and msg != title_text else ""
            lines.append(f"{i}. [{t}] ({rec}) {title_text}{extra}")

        return "\n".join(lines)

    elif action in ("cancel", "remove", "delete"):
        if not identifier:
            return "Please provide the title or identifier of the schedule to cancel."
        ok = cancel_schedule(identifier)
        if ok:
            if player:
                player.write_log(f"[Scheduler] 🗑️ Cancelled: {identifier}")
            return f"Schedule '{identifier}' has been cancelled."
        return f"Could not find any schedule matching '{identifier}'."

    elif action in ("plan_routine", "setup_routine", "create_routine"):
        items = plan_daily_routine()
        if player:
            player.write_log("[Scheduler] 📋 Daily routine initialized")
        lines = [f"Daily routine planned with {len(items)} scheduled milestones:"]
        for it in items:
            lines.append(f"• {it['time']} — {it['title']}")
        return "\n".join(lines)

    elif action in ("toggle", "disable", "enable"):
        if not identifier:
            return "Please specify which schedule to toggle."
        enable_flag = action != "disable"
        ok = toggle_schedule(identifier, enable=enable_flag)
        state_str = "enabled" if enable_flag else "disabled"
        if ok:
            return f"Schedule '{identifier}' is now {state_str}."
        return f"Could not find schedule '{identifier}' to update."

    else:
        return f"Unknown scheduler action: {action}. Available actions: add, list, cancel, plan_routine."


TOOL = {
    "name": "scheduler",
    "description": (
        "Manages scheduled tasks, alarms, and daily routines. Supports adding "
        "one-off and recurring schedules (e.g. workouts, studies, reminders), "
        "listing active schedules, cancelling them, and automatically generating "
        "Boss's tailored daily routine ('plan_routine'). When a schedule triggers, "
        "it notifies Boss on Desktop, Telegram, and via spoken voice alert."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "The action: 'add' | 'list' | 'cancel' | 'plan_routine' | 'toggle'",
            },
            "title": {
                "type": "STRING",
                "description": "Title of the task (e.g. 'Winter Arc Workout', 'Study Block', 'Take Creatine')",
            },
            "time": {
                "type": "STRING",
                "description": "Time in 24h HH:MM format (e.g. '18:00' or '06:30')",
            },
            "message": {
                "type": "STRING",
                "description": "Details or specific message to notify when the schedule triggers",
            },
            "recurring": {
                "type": "STRING",
                "description": "Frequency: 'daily' | 'weekdays' | 'once' | 'custom'",
            },
            "date": {
                "type": "STRING",
                "description": "Date in YYYY-MM-DD format (for one-time tasks)",
            },
            "identifier": {
                "type": "STRING",
                "description": "Title or ID of the schedule to cancel or toggle",
            },
        },
        "required": [
            "action"
        ],
    },
    "handler": scheduler,
}
