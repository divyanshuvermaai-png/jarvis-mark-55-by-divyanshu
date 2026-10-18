"""
actions/notifier.py — Sends multi-channel notifications to Boss.
Auto-discovered by core/action_loader.py.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from core.notifier import send_notification


def notify(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    title = params.get("title", "J.A.R.V.I.S").strip()
    message = params.get("message", "").strip()
    channel = params.get("channel", "all").strip().lower()
    urgency = params.get("urgency", "normal").strip().lower()
    file_path = params.get("file_path", "").strip()

    if not message:
        return "I need a message to send a notification."

    resolved_path = None
    if file_path:
        p = Path(file_path).expanduser()
        if p.exists():
            resolved_path = str(p)

    status = send_notification(
        title=title,
        message=message,
        channel=channel,
        urgency=urgency,
        file_path=resolved_path,
        player=player,
    )

    sent_channels = []
    if status.get("desktop"):
        sent_channels.append("Desktop")
    if status.get("telegram"):
        sent_channels.append("Telegram")
    if status.get("hud"):
        sent_channels.append("HUD")

    if not sent_channels:
        return f"Notification created, but no channels were available (check Telegram Bot token or notification permissions)."

    channels_str = ", ".join(sent_channels)
    return f"Notification delivered to {channels_str}: '{title}'."


TOOL = {
    "name": "notify",
    "description": (
        "Sends a notification to the Boss across Desktop (macOS banner/HUD), "
        "Telegram (direct push to mobile), or both. Use this to notify Boss "
        "about important alerts, reminders, task completions, or updates."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "title": {
                "type": "STRING",
                "description": "Short title or header of the notification (e.g. 'Winter Arc Workout', 'Render Complete', 'Schedule Alert')",
            },
            "message": {
                "type": "STRING",
                "description": "Detailed text content of the notification",
            },
            "channel": {
                "type": "STRING",
                "description": "Target channel: 'all' (Desktop + Telegram), 'desktop', or 'telegram'",
            },
            "urgency": {
                "type": "STRING",
                "description": "Urgency level: 'normal', 'urgent', or 'reminder'",
            },
            "file_path": {
                "type": "STRING",
                "description": "Optional local file path to attach and push to Telegram",
            },
        },
        "required": [
            "message"
        ],
    },
    "handler": notify,
}
