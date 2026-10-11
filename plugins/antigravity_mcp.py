"""
Google Antigravity MCP Plugin for JARVIS.

Directly bridges JARVIS with the Google Antigravity autonomous development engine:
1. Builds complete software projects, web apps, tools, scripts, and games directly
   from natural language voice or text commands into ~/Desktop/Antigravity_Projects/.
2. Launches and interacts with Antigravity IDE (/Applications/Antigravity IDE.app).
3. Spawns interactive Antigravity coding agents via agentapi.
4. Inspects status and manages existing Antigravity projects.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

from core import antigravity_bridge
from memory.config_manager import get_plugin_config, get_plugin_setting

_BUILD_LOCK = threading.Lock()
_LAST_BUILD_TIME = 0.0
_LAST_BUILD_RESULT: Optional[Dict[str, Any]] = None
_LAST_BUILD_PROMPT = ""

PLUGIN = {
    "name": "antigravity_mcp",
    "description": (
        "Direct Google Antigravity MCP integration. Connects to the Antigravity autonomous "
        "software development engine to build complete software projects, web applications, "
        "Python scripts, CLI tools, and games directly from natural language voice or text commands. "
        "Call this ONCE per user request. Never call repeatedly in a loop. Once called, report "
        "the completed build to the user and stop. "
        "Can generate complete multi-file codebases in ~/Desktop/Antigravity_Projects/, auto-open "
        "web apps in the browser, launch projects inside Antigravity IDE, spawn Antigravity coding "
        "agents via agentapi, inspect system engine status, and list previously built projects. "
        "Trigger whenever the user asks to: build an app, code a project, create a website or tool, "
        "make something with Antigravity, open Antigravity IDE, or run an Antigravity agent."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "Action to perform: "
                    "'build_project' (build a complete software project/web app/tool from description), "
                    "'open_ide' (launch Antigravity IDE targeting a project or workspace), "
                    "'run_agent' (spawn an Antigravity agentic task/conversation via agentapi), "
                    "'get_status' (check Antigravity IDE, SDK, agentapi binary, and project status), "
                    "or 'list_projects' (list all projects created by Antigravity)."
                ),
            },
            "prompt": {
                "type": "STRING",
                "description": (
                    "Natural language description of the project, app, game, or tool to build "
                    "(e.g., 'A futuristic cyber dashboard with live charts', 'A classic retro arcade game', 'A currency converter CLI')."
                ),
            },
            "project_name": {
                "type": "STRING",
                "description": (
                    "Optional snake_case or clean name for the project folder (e.g. 'cyber_dashboard', 'space_invaders'). "
                    "If omitted, Antigravity will automatically determine a fitting name."
                ),
            },
            "project_type": {
                "type": "STRING",
                "description": "Optional type preference: 'web' (HTML/CSS/JS), 'python', 'cli', 'game', or 'auto'. Defaults to 'auto'.",
            },
            "auto_launch": {
                "type": "BOOLEAN",
                "description": "Whether to automatically open the completed project in browser or Antigravity IDE. Defaults to True.",
            },
            "target_path": {
                "type": "STRING",
                "description": "Optional specific path or project name to open when action is 'open_ide'.",
            },
        },
        "required": ["action"],
    },
}


def _test_connection_handler(values: dict) -> Tuple[bool, str]:
    """Called by the Settings overlay 'TEST ANTIGRAVITY ENGINE' button."""
    status = antigravity_bridge.get_antigravity_status()
    components = []
    if status.get("ide_installed"):
        components.append("IDE")
    if status.get("agentapi_bin"):
        components.append("AgentAPI")
    if status.get("sdk_installed"):
        components.append("SDK")

    comp_desc = ", ".join(components) if components else "Autonomous Engine"
    p_count = len(status.get("existing_projects", []))
    return True, f"Google Antigravity Online ({comp_desc}) • {p_count} Projects Found ✓"


PLUGIN_SETTINGS = {
    "namespace": "antigravity_mcp",
    "title": "Google Antigravity MCP Bridge",
    "fields": [
        {
            "key": "projects_dir",
            "label": "Projects Directory",
            "type": "text",
            "default": str(antigravity_bridge.DEFAULT_PROJECTS_DIR),
            "placeholder": "~/Desktop/Antigravity_Projects",
        },
        {
            "key": "agentapi_path",
            "label": "Antigravity agentapi CLI Path",
            "type": "text",
            "default": str(antigravity_bridge.AGENTAPI_BIN),
            "placeholder": "Path to agentapi executable",
        },
        {
            "key": "auto_launch",
            "label": "Auto-Launch Created Projects",
            "type": "toggle",
            "default": True,
        },
    ],
    "action": {
        "label": "TEST ANTIGRAVITY ENGINE",
        "run": _test_connection_handler,
    },
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    """
    Main plugin execution handler invoked by JARVIS.
    parameters: dict of arguments extracted by Gemini.
    player: the JarvisUI instance for write_log, show_content, request_say.
    """
    action = str(parameters.get("action", "")).strip().lower()
    prompt = str(parameters.get("prompt", "")).strip()
    project_name = str(parameters.get("project_name", "")).strip()
    project_type = str(parameters.get("project_type", "auto")).strip().lower()
    auto_launch = parameters.get("auto_launch", True)
    if isinstance(auto_launch, str):
        auto_launch = auto_launch.lower() in ("true", "1", "yes")
    target_path = str(parameters.get("target_path", "")).strip()

    cfg = get_plugin_config("antigravity_mcp")
    projects_dir = cfg.get("projects_dir") or str(antigravity_bridge.DEFAULT_PROJECTS_DIR)

    def log(msg: str):
        if player and hasattr(player, "write_log"):
            try:
                player.write_log(f"JARVIS: {msg}")
            except Exception:
                pass
        print(f"[AntigravityPlugin] {msg}")

    # ── 1. Build Autonomous Software Project ──────────────────────────────────
    if action in ("build_project", "build", "create", "create_project", "make", "code"):
        if not prompt and not project_name:
            return "Sir, please describe what project, application, or tool you would like me to build with Antigravity."

        effective_prompt = prompt or f"A software project for {project_name}"

        # Loop-breaker: If an identical or recent build finished in the last 20s, return it immediately
        now = time.time()
        global _LAST_BUILD_TIME, _LAST_BUILD_RESULT, _LAST_BUILD_PROMPT
        with _BUILD_LOCK:
            if (now - _LAST_BUILD_TIME) < 20.0 and _LAST_BUILD_RESULT and _LAST_BUILD_RESULT.get("success"):
                p_name = _LAST_BUILD_RESULT.get("project_name", "project")
                files = _LAST_BUILD_RESULT.get("files", [])
                log(f"⚡ Project '{p_name}' was just generated — returning it directly to prevent duplicate loop.")
                return (
                    f"Sir, I have already built the {p_name.replace('_', ' ')} project with {len(files)} files. "
                    f"It is ready and open on your system."
                )

        log(f"⚡ Antigravity Engine: Initiating build for '{effective_prompt[:40]}...'")

        # Provide immediate spoken feedback so user knows JARVIS is working
        if player and hasattr(player, "request_say"):
            try:
                player.request_say("Initiating Google Antigravity engine. Designing your project now, sir.")
            except Exception:
                pass

        result = antigravity_bridge.build_project(
            prompt=effective_prompt,
            project_name=project_name,
            project_type=project_type,
            auto_launch=auto_launch,
            logger=log,
        )

        if not result.get("success"):
            err = result.get("error", "Unknown build error")
            log(f"⚠️ Antigravity build error: {err}")
            return f"Sir, I encountered an issue building the project with Antigravity: {err}"

        # Record successful build for loop-prevention
        _LAST_BUILD_TIME = time.time()
        _LAST_BUILD_RESULT = result
        _LAST_BUILD_PROMPT = effective_prompt

        p_name = result.get("project_name", "project")
        p_dir = result.get("project_dir", "")
        files = result.get("files", [])
        launched = result.get("launched")

        # Display on HUD content panel
        if player and hasattr(player, "show_content"):
            content_text = (
                f"GOOGLE ANTIGRAVITY — PROJECT READY\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Project Name:  {p_name}\n"
                f"Directory:     {p_dir}\n"
                f"Files Created: {len(files)} file(s)\n"
            )
            for f in files[:8]:
                content_text += f"  • {f}\n"
            if len(files) > 8:
                content_text += f"  ... and {len(files) - 8} more files\n"

            if launched == "browser":
                content_text += f"\nStatus: Launched in Browser\n"
            elif launched == "ide":
                content_text += f"\nStatus: Opened in Antigravity IDE\n"
            content_text += f"\nPrompt:\n{effective_prompt}"

            try:
                player.show_content(f"ANTIGRAVITY — {p_name.upper()}", content_text)
            except Exception:
                pass

        log(f"✅ Antigravity Project '{p_name}' complete with {len(files)} files.")

        launch_phrase = ""
        if launched == "browser":
            launch_phrase = " It has been launched directly in your browser."
        elif launched == "ide":
            launch_phrase = " I have opened the workspace in Antigravity IDE."

        return (
            f"Sir, I have completed building the {p_name.replace('_', ' ')} project with {len(files)} files "
            f"and saved it to your Antigravity Projects folder.{launch_phrase}"
        )

    # ── 2. Open Antigravity IDE ───────────────────────────────────────────────
    elif action in ("open_ide", "launch_ide", "open", "launch"):
        target = target_path
        if not target and project_name:
            target = Path(projects_dir).expanduser() / project_name
        elif not target:
            # Default to the Antigravity projects folder or current workspace
            target = Path(projects_dir).expanduser()

        log(f"Opening Antigravity IDE at {target}...")
        ok = antigravity_bridge.open_in_antigravity_ide(target)
        if ok:
            log("Antigravity IDE workspace launched.")
            return "Sir, I have opened the workspace in Antigravity IDE."
        return "Sir, I was unable to launch Antigravity IDE. Please ensure it is installed in Applications."

    # ── 3. Run AgentAPI Task ──────────────────────────────────────────────────
    elif action in ("run_agent", "agent", "task", "agentapi"):
        if not prompt:
            return "Sir, please provide the prompt or task you would like the Antigravity agent to work on."

        log(f"Spawning Antigravity agent for: '{prompt[:40]}...'")
        res = antigravity_bridge.run_agentapi_conversation(
            prompt=prompt,
            title=project_name or "JARVIS Autonomous Task",
            logger=log,
        )

        if not res.get("success"):
            err = res.get("error", res.get("stderr", "Unknown error"))
            log(f"⚠️ Antigravity agent error: {err}")
            return f"Sir, the Antigravity agent reported an issue: {err[:120]}"

        output = res.get("stdout", "Task complete.")
        log("Antigravity agent completed task.")
        if player and hasattr(player, "show_content"):
            try:
                player.show_content("ANTIGRAVITY AGENT", output[:1000])
            except Exception:
                pass
        return f"Sir, the Antigravity agent has executed your task: {output[:150]}"

    # ── 4. System Status ──────────────────────────────────────────────────────
    elif action in ("get_status", "status", "info"):
        log("Checking Antigravity engine status...")
        status = antigravity_bridge.get_antigravity_status()
        ide_str = "Installed" if status["ide_installed"] else "Not detected"
        agent_str = "Available" if status["agentapi_bin"] else "Not found"
        sdk_str = "Installed" if status["sdk_installed"] else "Not installed"
        projects = status["existing_projects"]

        summary = (
            f"Google Antigravity Status:\n"
            f"• IDE Application: {ide_str}\n"
            f"• AgentAPI CLI: {agent_str}\n"
            f"• Python SDK: {sdk_str}\n"
            f"• Projects Folder: {status['projects_dir']}\n"
            f"• Existing Projects ({len(projects)}): {', '.join(projects[:5]) if projects else 'None'}"
        )
        log(summary)
        if player and hasattr(player, "show_content"):
            try:
                player.show_content("ANTIGRAVITY STATUS", summary)
            except Exception:
                pass

        return (
            f"Sir, Google Antigravity is online. IDE is {ide_str}, AgentAPI is {agent_str}, "
            f"and there are {len(projects)} projects currently stored."
        )

    # ── 5. List Projects ──────────────────────────────────────────────────────
    elif action in ("list_projects", "projects", "list"):
        status = antigravity_bridge.get_antigravity_status()
        projects = status["existing_projects"]
        if not projects:
            return "Sir, there are currently no projects in your Antigravity Projects directory."

        proj_list_str = "\n".join(f"• {p}" for p in projects)
        if player and hasattr(player, "show_content"):
            try:
                player.show_content("ANTIGRAVITY PROJECTS", f"Projects in {status['projects_dir']}:\n\n{proj_list_str}")
            except Exception:
                pass

        log(f"Found {len(projects)} Antigravity projects.")
        return f"Sir, you have {len(projects)} projects built by Antigravity: {', '.join(projects[:6])}."

    else:
        return (
            f"Sir, unknown Antigravity action '{action}'. "
            f"Available actions are: build_project, open_ide, run_agent, get_status, and list_projects."
        )
