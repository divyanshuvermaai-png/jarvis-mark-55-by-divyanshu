"""
Blender MCP Plugin for JARVIS.

Directly bridges JARVIS with Blender's live MCP socket server (default localhost:9876).
Enables JARVIS to create complete 3D projects, procedural scenes, custom models,
materials, lighting, and cameras directly from natural language voice or text commands,
inspect live scenes, capture viewport screenshots, and save/export .blend, GLB, and FBX files.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from core import blender_bridge
from memory.config_manager import get_plugin_config, get_plugin_setting

_BUILD_LOCK = threading.Lock()
_LAST_BUILD_TIME = 0.0
_LAST_BUILD_RESULT: Optional[Dict[str, Any]] = None
_LAST_BUILD_PROMPT = ""

PLUGIN = {
    "name": "blender_mcp",
    "description": (
        "Direct Blender MCP integration. Connects to Blender to build complete 3D models, "
        "scenes, assets, and environments directly from natural language in a single command. "
        "Can generate complete 3D scenes, procedural models, materials, lighting, cameras, "
        "run Python bpy scripts in live Blender, inspect scene hierarchy, capture viewport screenshots, "
        "and save/export .blend, GLB, and FBX files. Call this ONCE per user request. "
        "Never call repeatedly in a loop. Once called, report the completed 3D build to the user and stop. "
        "Trigger whenever user asks to: create a 3D model/project/scene in Blender, make something in Blender, "
        "run Blender code, inspect the Blender scene, capture the Blender viewport, or save/render a Blender project."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "Action to perform: 'create_project' (build a complete 3D scene/project from description), "
                    "'execute_code' (run custom Python bpy code in live Blender), "
                    "'get_scene_info' (inspect current scene objects, materials, and count), "
                    "'capture_viewport' (take screenshot of active Blender viewport and show on HUD), "
                    "'save_project' (save active scene to .blend file), "
                    "'open_blender' (launch Blender application with MCP bridge), "
                    "or 'export_scene' (export scene to glb or fbx)."
                ),
            },
            "prompt": {
                "type": "STRING",
                "description": "Natural language description of the 3D scene, object, model, or project to create (used with 'create_project').",
            },
            "code": {
                "type": "STRING",
                "description": "Python code using bpy to execute directly in Blender (used with 'execute_code').",
            },
            "project_name": {
                "type": "STRING",
                "description": "Optional name for the project or file (e.g. 'scifi_drone', 'medieval_castle').",
            },
            "export_format": {
                "type": "STRING",
                "description": "Optional format to export: 'glb' or 'fbx'.",
            },
            "save_path": {
                "type": "STRING",
                "description": "Optional custom filepath to save the .blend file or export. Defaults to Desktop/Blender_Projects.",
            },
        },
        "required": ["action"],
    },
}


def _test_connection_handler(values: dict) -> Tuple[bool, str]:
    """Called by the Settings overlay 'TEST CONNECTION' button."""
    host = values.get("host") or "localhost"
    try:
        port = int(values.get("port") or 9876)
    except ValueError:
        return False, "Invalid port number"

    if not blender_bridge.is_port_listening(host, port):
        b_bin = blender_bridge.find_blender_binary()
        bin_desc = f" (Found at {b_bin.name})" if b_bin else " (Blender not found on PATH)"
        return False, f"Blender MCP socket not listening on {host}:{port}. Start Blender{bin_desc}."

    try:
        info = blender_bridge.get_addon_info(host=host, port=port)
        v = info.get("blender_version", "Unknown")
        addon_v = ".".join(str(x) for x in info.get("addon_version", [1, 0]))
        return True, f"Connected to Blender {v} (Addon v{addon_v}) ✓"
    except Exception as e:
        return False, f"Handshake failed: {e}"


PLUGIN_SETTINGS = {
    "namespace": "blender_mcp",
    "title": "Blender MCP Bridge",
    "fields": [
        {
            "key": "host",
            "label": "Blender Host",
            "type": "text",
            "default": "localhost",
            "placeholder": "localhost",
        },
        {
            "key": "port",
            "label": "Blender MCP Port",
            "type": "text",
            "default": "9876",
            "placeholder": "9876",
        },
        {
            "key": "blender_path",
            "label": "Blender Executable Path",
            "type": "text",
            "default": str(blender_bridge.find_blender_binary() or "/Applications/Blender.app/Contents/MacOS/Blender"),
            "placeholder": "Path to Blender executable",
        },
        {
            "key": "auto_launch",
            "label": "Auto-Launch Blender If Closed",
            "type": "toggle",
            "default": True,
        },
        {
            "key": "projects_dir",
            "label": "Projects Save Directory",
            "type": "text",
            "default": str(blender_bridge.DEFAULT_PROJECTS_DIR),
            "placeholder": "Folder to save .blend files",
        },
    ],
    "action": {
        "label": "TEST CONNECTION",
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
    code = str(parameters.get("code", "")).strip()
    project_name = str(parameters.get("project_name", "")).strip()
    export_format = str(parameters.get("export_format", "")).strip()
    save_path = str(parameters.get("save_path", "")).strip()

    cfg = get_plugin_config("blender_mcp")
    host = cfg.get("host") or "localhost"
    try:
        port = int(cfg.get("port") or 9876)
    except ValueError:
        port = 9876
    auto_launch = bool(cfg.get("auto_launch", True))
    projects_dir = cfg.get("projects_dir") or str(blender_bridge.DEFAULT_PROJECTS_DIR)

    def log(msg: str):
        if player and hasattr(player, "write_log"):
            try:
                player.write_log(f"JARVIS: {msg}")
            except Exception:
                pass
        print(f"[BlenderPlugin] {msg}")

    # ── 1. Create 3D Project ──────────────────────────────────────────────────
    if action in ("create_project", "create", "build", "make"):
        if not prompt and not project_name:
            return "Sir, please provide a description of the 3D project or model you would like me to create in Blender."

        effective_prompt = prompt or f"3D model of {project_name}"

        # Loop-breaker: If an identical or recent build finished in the last 20s, return it immediately
        now = time.time()
        global _LAST_BUILD_TIME, _LAST_BUILD_RESULT, _LAST_BUILD_PROMPT
        with _BUILD_LOCK:
            if (now - _LAST_BUILD_TIME) < 20.0 and _LAST_BUILD_RESULT and _LAST_BUILD_RESULT.get("success"):
                p_name = _LAST_BUILD_RESULT.get("project_name", "project")
                blend_p = _LAST_BUILD_RESULT.get("blend_path", "")
                log(f"⚡ 3D Project '{p_name}' was just created — returning directly to prevent duplicate loop.")
                return (
                    f"Sir, I have already created the {p_name.replace('_', ' ')} project in Blender. "
                    f"It is saved at {blend_p}."
                )

        log(f"🎨 Designing 3D project: '{effective_prompt[:40]}...'")

        if player and hasattr(player, "request_say"):
            try:
                player.request_say("Connecting to Blender and building your 3D project now, sir.")
            except Exception:
                pass

        result = blender_bridge.create_blender_project(
            prompt=effective_prompt,
            project_name=project_name,
            save_dir=save_path or projects_dir,
            export_format=export_format,
            render_preview=True,
            host=host,
            port=port,
            auto_launch=auto_launch,
            logger=log,
        )

        if not result.get("success"):
            err = result.get("error", "Unknown error")
            log(f"⚠️ Blender project creation failed: {err}")
            return f"Sir, I was unable to complete the 3D project in Blender: {err}"

        # Record successful build for loop-prevention
        _LAST_BUILD_TIME = time.time()
        _LAST_BUILD_RESULT = result
        _LAST_BUILD_PROMPT = effective_prompt

        p_name = result.get("project_name", "project")
        blend_path = result.get("blend_path", "")
        preview_path = result.get("preview_path")
        obj_count = result.get("objects_count", 0)

        # Show on HUD content panel if available
        if player and hasattr(player, "show_content"):
            content_text = (
                f"3D PROJECT: {p_name.upper()}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Objects Generated: {obj_count}\n"
                f"Saved File: {blend_path}\n"
            )
            if preview_path:
                content_text += f"Preview Snapshot: {preview_path}\n"
            content_text += f"\nDescription:\n{effective_prompt}"
            try:
                player.show_content(f"BLENDER — {p_name.upper()}", content_text)
            except Exception:
                pass

        log(f"✅ Created '{p_name}' ({obj_count} objects) at {blend_path}")
        return (
            f"Sir, I have created the {p_name.replace('_', ' ')} project in Blender with "
            f"{obj_count} objects, complete materials, and lighting. It is saved to your Desktop."
        )

    # ── 2. Execute Custom bpy Python Code ─────────────────────────────────────
    elif action in ("execute_code", "run_code", "execute"):
        if not code:
            return "Sir, no Blender Python code was provided to execute."

        log("Executing custom script in Blender...")
        try:
            res = blender_bridge.execute_blender_code(code, host=host, port=port)
            output = res.get("result", "")
            log("Script executed in Blender.")
            clean_out = output.strip() if output else "Executed successfully with no stdout."
            return f"Sir, the script ran in Blender: {clean_out[:120]}"
        except Exception as e:
            log(f"⚠️ Code execution error: {e}")
            return f"Sir, the Blender script encountered an error: {e}"

    # ── 3. Inspect Scene Info ─────────────────────────────────────────────────
    elif action in ("get_scene_info", "scene_info", "inspect", "status"):
        log("Inspecting active Blender scene...")
        try:
            info = blender_bridge.get_scene_info(host=host, port=port)
            obj_list = info.get("objects", [])
            mat_count = info.get("materials_count", 0)
            names = [o.get("name") for o in obj_list]
            summary = (
                f"The active Blender scene has {len(names)} objects "
                f"({', '.join(names[:6])}{'...' if len(names) > 6 else ''}) "
                f"and {mat_count} materials."
            )
            log(f"Scene: {summary}")
            if player and hasattr(player, "show_content"):
                try:
                    player.show_content("BLENDER SCENE", summary)
                except Exception:
                    pass
            return f"Sir, {summary}"
        except Exception as e:
            return f"Sir, I could not inspect the Blender scene: {e}"

    # ── 4. Capture Viewport Screenshot ────────────────────────────────────────
    elif action in ("capture_viewport", "screenshot", "render_preview", "look"):
        log("Capturing Blender viewport screenshot...")
        dest = Path(save_path or projects_dir)
        dest.mkdir(parents=True, exist_ok=True)
        shot_path = dest / "viewport_capture.png"

        try:
            res = blender_bridge.capture_viewport_screenshot(str(shot_path), max_size=800, host=host, port=port)
            if res.get("success"):
                log(f"Captured viewport to {shot_path.name}")
                if player and hasattr(player, "show_content"):
                    try:
                        player.show_content("BLENDER VIEWPORT", f"Captured viewport saved to: {shot_path}")
                    except Exception:
                        pass
                return f"Sir, I have captured the Blender viewport and saved it to {shot_path.name}."
            return "Sir, the viewport screenshot could not be captured."
        except Exception as e:
            return f"Sir, failed to capture the Blender viewport: {e}"

    # ── 5. Save Project ───────────────────────────────────────────────────────
    elif action in ("save_project", "save"):
        p_name = project_name or "project"
        dest = Path(save_path or projects_dir)
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / f"{p_name}.blend" if not str(save_path).endswith(".blend") else Path(save_path)

        log(f"Saving Blender project to {target.name}...")
        try:
            blender_bridge.save_project(str(target), host=host, port=port)
            log(f"Project saved to {target}")
            return f"Sir, the project has been saved to {target.name}."
        except Exception as e:
            return f"Sir, failed to save the Blender project: {e}"

    # ── 6. Open / Launch Blender ──────────────────────────────────────────────
    elif action in ("open_blender", "launch_blender", "open", "launch"):
        if blender_bridge.is_port_listening(host, port):
            return "Sir, Blender is already running and connected via MCP."

        log("Launching Blender application...")
        ok = blender_bridge.launch_blender_gui()
        if ok:
            return "Blender has been opened, and the direct MCP bridge is active, sir."
        return "Sir, I tried to launch Blender, but the MCP socket did not start. Please verify Blender is installed."

    # ── 7. Export Scene ───────────────────────────────────────────────────────
    elif action in ("export_scene", "export"):
        fmt = (export_format or "glb").lower()
        p_name = project_name or "export"
        dest = Path(save_path or projects_dir)
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / f"{p_name}.{fmt}"

        log(f"Exporting Blender scene to {fmt.upper()}...")
        try:
            blender_bridge.export_scene(str(target), fmt=fmt, host=host, port=port)
            log(f"Exported to {target}")
            return f"Sir, the scene has been exported to {target.name}."
        except Exception as e:
            return f"Sir, failed to export the scene: {e}"

    else:
        return (
            f"Sir, unknown Blender action '{action}'. "
            f"Available actions are: create_project, execute_code, get_scene_info, "
            f"capture_viewport, save_project, open_blender, and export_scene."
        )
