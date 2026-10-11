"""
Direct Blender MCP Bridge for JARVIS.

Connects JARVIS directly to Blender's live MCP socket server (default localhost:9876)
or runs headless Blender scripts as fallback. Enables conversational 3D scene generation,
procedural modeling, shader/lighting setup, automated project (.blend) creation,
viewport captures, rendering, and export to GLB/FBX.
"""
from __future__ import annotations

import json
import math
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional, Tuple, Dict, Any

from core import gemini
from core.groq_client import call_groq_coder
from memory.config_manager import get_plugin_setting

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 9876
SOCKET_TIMEOUT = 45.0
DEFAULT_PROJECTS_DIR = Path.home() / "Desktop" / "Blender_Projects"


# ── Blender Path & Environment Discovery ──────────────────────────────────────

def find_blender_binary() -> Optional[Path]:
    """Finds the installed Blender executable across macOS, Windows, and Linux."""
    # 1. Configured custom path
    custom_path = get_plugin_setting("blender_mcp", "blender_path") or os.environ.get("BLENDER_PATH")
    if custom_path:
        p = Path(custom_path).expanduser()
        if p.exists() and p.is_file():
            return p

    # 2. System PATH
    which_blender = shutil.which("blender")
    if which_blender:
        return Path(which_blender)

    sys_name = platform.system()

    # 3. macOS standard app bundle locations
    if sys_name == "Darwin":
        mac_candidates = [
            Path("/Applications/Blender.app/Contents/MacOS/Blender"),
            Path.home() / "Applications/Blender.app/Contents/MacOS/Blender",
        ]
        # Check versioned names like Blender 4.3.app, Blender 5.2.app
        for app_dir in Path("/Applications").glob("Blender*.app"):
            mac_candidates.append(app_dir / "Contents/MacOS/Blender")
        for app_dir in (Path.home() / "Applications").glob("Blender*.app"):
            mac_candidates.append(app_dir / "Contents/MacOS/Blender")

        for cand in mac_candidates:
            if cand.exists() and cand.is_file():
                return cand

    # 4. Windows standard install locations
    elif sys_name == "Windows":
        prog_files = [
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        ]
        for pf in prog_files:
            base = Path(pf) / "Blender Foundation"
            if base.exists():
                for b_dir in base.glob("Blender*"):
                    b_exe = b_dir / "blender.exe"
                    if b_exe.exists():
                        return b_exe

    # 5. Linux common package locations
    elif sys_name == "Linux":
        linux_candidates = [
            Path("/usr/bin/blender"),
            Path("/usr/local/bin/blender"),
            Path("/snap/bin/blender"),
        ]
        for cand in linux_candidates:
            if cand.exists():
                return cand

    return None


def is_port_listening(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = 0.3) -> bool:
    """Returns True if the Blender MCP TCP socket is active and accepting connections."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(timeout)
    try:
        return probe.connect_ex((host, port)) == 0
    except Exception:
        return False
    finally:
        probe.close()


def launch_blender_gui(blender_path: Optional[Path] = None, wait_seconds: float = 8.0) -> bool:
    """Launches Blender GUI with the MCP addon enabled and waits for port 9876 to open."""
    b_bin = blender_path or find_blender_binary()
    sys_name = platform.system()

    try:
        if sys_name == "Darwin":
            app_path = None
            if b_bin and "Contents/MacOS" in str(b_bin):
                app_path = str(b_bin).split("/Contents/MacOS")[0]
            if app_path and Path(app_path).exists():
                subprocess.Popen(["open", "-a", app_path])
            else:
                subprocess.Popen(["open", "-a", "Blender"])
        elif b_bin and b_bin.exists():
            subprocess.Popen([str(b_bin)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["blender"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"[BlenderBridge] Failed to launch Blender GUI: {e}")
        return False

    # Poll until port is open
    start = time.time()
    while time.time() - start < wait_seconds:
        if is_port_listening():
            return True
        time.sleep(0.4)

    return is_port_listening()


# ── Socket Client for Blender MCP ─────────────────────────────────────────────

class BlenderMCPClient:
    """Manages raw socket protocol communication with Blender's MCP addon."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = SOCKET_TIMEOUT):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None

    def connect(self) -> bool:
        self.close()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(self.timeout)
            s.connect((self.host, self.port))
            self.sock = s
            return True
        except Exception as e:
            self.sock = None
            return False

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def send_command(self, cmd_type: str, params: Optional[dict] = None) -> dict:
        """Sends a JSON command to Blender and waits for the full JSON response."""
        if not self.sock and not self.connect():
            raise ConnectionError(f"Cannot connect to Blender MCP at {self.host}:{self.port}")

        payload = {"type": cmd_type, "params": params or {}}
        cmd_bytes = json.dumps(payload).encode("utf-8")

        try:
            self.sock.sendall(cmd_bytes)

            # Receive chunked response until complete valid JSON is decoded
            chunks = []
            while True:
                data = self.sock.recv(16384)
                if not data:
                    break
                chunks.append(data)
                raw = b"".join(chunks)
                try:
                    resp = json.loads(raw.decode("utf-8"))
                    if resp.get("status") == "error":
                        raise RuntimeError(resp.get("message", "Unknown error from Blender"))
                    return resp.get("result", {})
                except json.JSONDecodeError:
                    continue

            # Incomplete read
            if chunks:
                raw_text = b"".join(chunks).decode("utf-8", errors="replace")
                raise RuntimeError(f"Incomplete JSON response from Blender: {raw_text[:200]}")
            raise RuntimeError("No response data received from Blender")

        except (ConnectionError, BrokenPipeError, ConnectionResetError, socket.timeout) as e:
            self.close()
            raise ConnectionError(f"Blender connection error: {e}") from e


def send_mcp_command(cmd_type: str, params: Optional[dict] = None,
                     host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> dict:
    """Convenience helper to send a single command to Blender MCP."""
    client = BlenderMCPClient(host=host, port=port)
    try:
        return client.send_command(cmd_type, params)
    finally:
        client.close()


# ── Blender Operations ────────────────────────────────────────────────────────

def get_addon_info(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> dict:
    """Returns version, capabilities, and status of the Blender MCP addon."""
    return send_mcp_command("get_addon_info", {}, host=host, port=port)


def get_scene_info(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> dict:
    """Returns information on the active Blender scene (objects, counts, materials)."""
    return send_mcp_command("get_scene_info", {}, host=host, port=port)


def execute_blender_code(code: str, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> dict:
    """Runs Python code inside Blender via the live MCP socket."""
    return send_mcp_command("execute_code", {"code": code}, host=host, port=port)


def capture_viewport_screenshot(filepath: str, max_size: int = 800,
                                host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> dict:
    """Captures offscreen GPU viewport screenshot and writes it to filepath."""
    return send_mcp_command("get_viewport_screenshot", {"filepath": str(filepath), "max_size": max_size},
                            host=host, port=port)


def export_scene(filepath: str, fmt: str = "glb",
                 host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> dict:
    """Exports the active scene to GLB or FBX."""
    return send_mcp_command("export_scene", {"filepath": str(filepath), "format": fmt.lower()},
                            host=host, port=port)


def save_project(filepath: str, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> dict:
    """Saves the current Blender scene to a .blend file."""
    p = Path(filepath).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    code = f"import bpy\nbpy.ops.wm.save_as_mainfile(filepath=r'{str(p)}')\nprint('Saved project to {p.name}')"
    return execute_blender_code(code, host=host, port=port)


def render_beauty_shot(filepath: str, width: int = 1280, height: int = 720,
                       host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> dict:
    """Renders the current scene from the active camera with lighting and materials."""
    p = Path(filepath).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    code = f"""
import bpy
scene = bpy.context.scene
scene.render.image_settings.file_format = 'PNG'
scene.render.resolution_x = {width}
scene.render.resolution_y = {height}
scene.render.filepath = r'{str(p)}'
bpy.ops.render.render(write_still=True)
print('Rendered beauty shot to {p.name}')
"""
    return execute_blender_code(code, host=host, port=port)


# ── Clean Code Helper ─────────────────────────────────────────────────────────

def clean_python_code(text: str) -> str:
    """Extracts Python code from Markdown fences or raw text."""
    text = text.strip()
    match = re.search(r"```(?:python)?\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


# ── AI 3D Project Generator Engine ────────────────────────────────────────────

_SYSTEM_3D_DESIGNER = """You are an expert 3D Technical Artist and Python developer for Blender (compatible with Blender 4.x and 5.x).
Your task is to write complete, clean, self-contained Blender Python (bpy) scripts that build stunning, well-proportioned 3D models and complete scenes from natural language prompts.

CRITICAL DESIGN & TECHNICAL RULES:
1. Always start by clearing existing mesh objects, lights, and cameras so the scene is clean:
   import bpy
   import math
   import mathutils
   
   # Reset scene
   bpy.ops.object.select_all(action='SELECT')
   bpy.ops.object.delete(use_global=False)

2. Geometric Craft & Proportion:
   - Construct multi-part detailed models using primitives (cubes, cylinders, spheres, cones, curves, toruses).
   - Position, scale, and rotate components accurately with sensible real-world or stylized proportions.
   - Use modifiers where helpful (e.g. Bevel modifier for soft bevel edges, Subdivision Surface for organic smoothness).
   - Apply smooth shading: bpy.ops.object.shade_smooth() on rounded parts.

3. Materials & Shaders (Crucial for Blender 4.x/5.x):
   - Create distinct materials with rich color palettes.
   - Always find the Principled BSDF node safely:
     bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
   - Set parameters using standard modern names:
     * 'Base Color' -> (r, g, b, 1.0)
     * 'Roughness' -> float (0.1 to 0.9)
     * 'Metallic' -> float (0.0 to 1.0)
     * For glowing lights/neon: check if 'Emission Color' in bsdf.inputs, set color and 'Emission Strength' to 3.0-10.0.
     * For glass/water: set 'Transmission Weight' (or 'Transmission') and roughness to 0.05.

4. Cinematic Lighting Setup:
   - Add a 3-point lighting setup:
     * Key Light (Sun or Area light, bright, angled from front-quarter)
     * Fill Light (Soft cool light from opposite side)
     * Rim / Accent Light (Behind the subject for silhouette highlights)

5. Camera Positioning:
   - Create a camera positioned to give an appealing 3/4 isometric or perspective hero shot of the model.
   - Set bpy.context.scene.camera = camera_obj.

6. Project Saving:
   - Save the blend file at the target path specified in TARGET_FILEPATH variable:
     if 'TARGET_FILEPATH' in locals() and TARGET_FILEPATH:
         bpy.ops.wm.save_as_mainfile(filepath=TARGET_FILEPATH)

7. Output Format:
   - Return ONLY the executable Python code inside a ```python ``` block.
   - No explanations, no introductory text, no comments outside the code.
   - End the script with a print statement summarizing what was built.
"""

def generate_blender_script(prompt: str, project_name: str, target_blend_path: str, logger: Optional[Callable[[str], None]] = None) -> str:
    """Generates the complete Blender Python script for the project using high-speed Groq Qwen (with Gemini fallback)."""
    log = logger or (lambda msg: None)
    user_msg = (
        f"Create a complete 3D project in Blender based on this request:\n\n"
        f"Prompt: {prompt}\n"
        f"Project Name: {project_name}\n"
        f"Target Save Filepath: {target_blend_path}\n\n"
        f"Ensure the script sets TARGET_FILEPATH = r'{target_blend_path}' and saves the project at the end."
    )
    raw_code = ""

    # Try high-speed Groq Qwen coder first (completes in ~1-2s)
    try:
        groq_resp = call_groq_coder(
            contents=user_msg,
            system_prompt=_SYSTEM_3D_DESIGNER,
            max_tokens=4096,
            temperature=0.2,
            timeout=30,
        )
        if groq_resp and groq_resp.text and len(groq_resp.text.strip()) > 80:
            raw_code = groq_resp.text.strip()
            log("⚡ Generated 3D Blender script via Groq Qwen in ~1.5s")
    except Exception as e:
        log(f"Groq coder error: {e}, falling back to Gemini...")

    if not raw_code:
        log("Generating 3D script via Gemini...")
        full_prompt = f"{_SYSTEM_3D_DESIGNER}\n\n[USER REQUEST]\n{user_msg}"
        raw_code = gemini.text(full_prompt, tier=gemini.FAST, timeout_ms=30000)
        if not raw_code:
            raw_code = gemini.text(full_prompt, tier=gemini.SMART, timeout_ms=45000)

    return clean_python_code(raw_code)


def repair_blender_script(code: str, error_msg: str, target_blend_path: str, logger: Optional[Callable[[str], None]] = None) -> str:
    """Repairs a failed Blender script using Groq Qwen / Gemini with the error traceback."""
    log = logger or (lambda msg: None)
    repair_req = (
        f"The following script failed when executed in Blender:\n\n"
        f"ERROR:\n{error_msg}\n\n"
        f"PREVIOUS CODE:\n```python\n{code}\n```\n\n"
        f"Fix the error, ensure Blender 4.x/5.x compatibility, keep TARGET_FILEPATH = r'{target_blend_path}', "
        f"and return the complete corrected Python script inside ```python ```."
    )
    repaired_code = ""
    try:
        groq_resp = call_groq_coder(
            contents=repair_req,
            system_prompt=_SYSTEM_3D_DESIGNER,
            max_tokens=4096,
            temperature=0.1,
            timeout=30,
        )
        if groq_resp and groq_resp.text and len(groq_resp.text.strip()) > 80:
            repaired_code = groq_resp.text.strip()
            log("⚡ Repaired 3D Blender script via Groq Qwen")
    except Exception as e:
        log(f"Groq repair error: {e}, falling back to Gemini...")

    if not repaired_code:
        repair_prompt = f"{_SYSTEM_3D_DESIGNER}\n\n[ERROR IN PREVIOUS EXECUTION]\n{repair_req}"
        repaired_code = gemini.text(repair_prompt, tier=gemini.FAST, timeout_ms=30000)
        if not repaired_code:
            repaired_code = gemini.text(repair_prompt, tier=gemini.SMART, timeout_ms=45000)

    return clean_python_code(repaired_code)


# ── Master Project Creation Pipeline ──────────────────────────────────────────

def create_blender_project(
    prompt: str,
    project_name: str = "",
    save_dir: Optional[str] = None,
    export_format: Optional[str] = None,
    render_preview: bool = True,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    auto_launch: bool = True,
    logger: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Directly creates a complete 3D project in Blender from a natural language prompt.
    1. Ensures Blender is connected (or launches it).
    2. Generates complete bpy code with Gemini.
    3. Executes code in Blender via MCP socket.
    4. Auto-heals code if any error occurs.
    5. Saves project (.blend) and captures viewport screenshot/render.
    6. Returns structured status dictionary.
    """
    log = logger or (lambda msg: print(f"[BlenderBridge] {msg}"))

    # Sanitize project name
    if not project_name:
        words = re.findall(r"[a-zA-Z0-9]+", prompt)
        project_name = "_".join(words[:4]).lower() if words else "blender_project"
    project_name = re.sub(r"[^a-zA-Z0-9_]", "_", project_name).strip("_") or "blender_project"

    dest_dir = Path(save_dir).expanduser() if save_dir else DEFAULT_PROJECTS_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    target_blend_path = str(dest_dir / f"{project_name}.blend")
    preview_img_path = str(dest_dir / f"{project_name}_preview.png")

    # Step 1: Ensure Blender connection
    log(f"Checking Blender connection at {host}:{port}...")
    if not is_port_listening(host, port):
        if auto_launch:
            log("Blender MCP socket not detected — launching Blender...")
            launched = launch_blender_gui(wait_seconds=9.0)
            if not launched or not is_port_listening(host, port):
                log("Could not establish socket connection to Blender GUI. Checking CLI fallback...")
        else:
            return {
                "success": False,
                "error": f"Blender MCP is not listening on {host}:{port}, and auto-launch is disabled."
            }

    # Step 2: Generate bpy script
    log(f"Generating 3D model script for '{project_name}'...")
    code = generate_blender_script(prompt, project_name, target_blend_path, logger=log)
    if not code:
        return {"success": False, "error": "Gemini/Groq could not generate a Blender script."}

    # Inject TARGET_FILEPATH header if not present
    header = f"TARGET_FILEPATH = r'{target_blend_path}'\n"
    if "TARGET_FILEPATH =" not in code:
        code = header + code

    # Step 3: Execute in Blender with self-healing retry loop
    max_attempts = 3
    executed = False
    last_error = ""

    for attempt in range(1, max_attempts + 1):
        log(f"Executing 3D script in Blender (attempt {attempt}/{max_attempts})...")

        if is_port_listening(host, port):
            try:
                res = execute_blender_code(code, host=host, port=port)
                executed = True
                log("Script executed successfully in live Blender!")
                break
            except Exception as e:
                last_error = str(e)
                log(f"Execution attempt {attempt} failed: {last_error[:120]}")
                if attempt < max_attempts:
                    log("Repairing script with AI...")
                    code = repair_blender_script(code, last_error, target_blend_path, logger=log)
        else:
            # Headless CLI fallback if GUI socket is unavailable
            b_bin = find_blender_binary()
            if b_bin and b_bin.exists():
                log("Running via Blender CLI headless execution...")
                tmp_py = dest_dir / f"_tmp_{project_name}.py"
                try:
                    tmp_py.write_text(code, encoding="utf-8")
                    proc = subprocess.run(
                        [str(b_bin), "-b", "--python", str(tmp_py)],
                        capture_output=True, text=True, timeout=90
                    )
                    if proc.returncode == 0:
                        executed = True
                        log("Headless Blender execution succeeded!")
                        break
                    else:
                        last_error = proc.stderr or proc.stdout
                        log(f"Headless attempt {attempt} failed: {last_error[:120]}")
                        if attempt < max_attempts:
                            code = repair_blender_script(code, last_error, target_blend_path)
                finally:
                    if tmp_py.exists():
                        try:
                            tmp_py.unlink()
                        except Exception:
                            pass
            else:
                return {
                    "success": False,
                    "error": f"Blender MCP socket not listening and no Blender CLI binary found: {last_error}"
                }

    if not executed:
        return {
            "success": False,
            "error": f"Failed to execute 3D project in Blender after {max_attempts} attempts: {last_error}"
        }

    # Step 4: Verify scene & capture preview
    scene_data = {}
    objects_list = []
    if is_port_listening(host, port):
        try:
            scene_data = get_scene_info(host=host, port=port)
            objects_list = [obj.get("name") for obj in scene_data.get("objects", [])]
        except Exception:
            pass

        # Capture viewport preview image
        if render_preview:
            try:
                log(f"Capturing preview screenshot to {Path(preview_img_path).name}...")
                capture_viewport_screenshot(preview_img_path, max_size=800, host=host, port=port)
            except Exception as e:
                log(f"Viewport capture failed: {e}")

        # Optional export
        if export_format and export_format.lower() in ("glb", "fbx"):
            exp_path = str(dest_dir / f"{project_name}.{export_format.lower()}")
            try:
                log(f"Exporting scene to {Path(exp_path).name}...")
                export_scene(exp_path, fmt=export_format.lower(), host=host, port=port)
            except Exception as e:
                log(f"Export failed: {e}")

    summary = (
        f"Created 3D project '{project_name}' in Blender with {len(objects_list)} objects. "
        f"Project file saved to: {target_blend_path}"
    )

    return {
        "success": True,
        "project_name": project_name,
        "blend_path": target_blend_path,
        "preview_path": preview_img_path if Path(preview_img_path).exists() else None,
        "objects_count": len(objects_list),
        "objects": objects_list,
        "summary": summary,
    }
