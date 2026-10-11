"""
Direct Google Antigravity MCP Bridge for JARVIS.

Bridges JARVIS with Google Antigravity:
1. Autonomous Project Builder: Builds complete software projects, web apps,
   scripts, games, and tools in `~/Desktop/Antigravity_Projects/`.
2. Antigravity AgentAPI CLI: Spawns and interacts with Antigravity IDE coding
   agents via `agentapi` at `~/.gemini/antigravity-ide/bin/agentapi`.
3. Google Antigravity Python SDK: Direct integration with `google.antigravity`.
4. Workspace IDE Launcher: Seamlessly launches Antigravity IDE (`/Applications/Antigravity IDE.app`).
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Callable, Optional, Dict, Any, List

from core import gemini
from memory.config_manager import get_plugin_setting

DEFAULT_PROJECTS_DIR = Path.home() / "Desktop" / "Antigravity_Projects"
AGENTAPI_BIN = Path.home() / ".gemini" / "antigravity-ide" / "bin" / "agentapi"
ANTIGRAVITY_APP_MACOS = Path("/Applications/Antigravity IDE.app")


def find_agentapi_binary() -> Optional[Path]:
    """Locate the agentapi executable if installed."""
    custom = get_plugin_setting("antigravity_mcp", "agentapi_path")
    if custom:
        p = Path(custom).expanduser()
        if p.exists() and os.access(p, os.X_OK):
            return p

    if AGENTAPI_BIN.exists() and os.access(AGENTAPI_BIN, os.X_OK):
        return AGENTAPI_BIN

    which_agent = shutil.which("agentapi")
    if which_agent:
        return Path(which_agent)

    return None


def is_antigravity_ide_installed() -> bool:
    """Check if Antigravity IDE application is present."""
    if platform.system() == "Darwin":
        if ANTIGRAVITY_APP_MACOS.exists():
            return True
        user_app = Path.home() / "Applications" / "Antigravity IDE.app"
        if user_app.exists():
            return True
    return bool(shutil.which("antigravity") or shutil.which("agy"))


def has_antigravity_sdk() -> bool:
    """Check if the google-antigravity python library is installed."""
    try:
        import google.antigravity  # noqa
        return True
    except ImportError:
        return False


def get_antigravity_status() -> Dict[str, Any]:
    """Collect comprehensive status of Antigravity components on this system."""
    agent_bin = find_agentapi_binary()
    ide_installed = is_antigravity_ide_installed()
    sdk_installed = has_antigravity_sdk()

    projects_dir = Path(get_plugin_setting("antigravity_mcp", "projects_dir") or DEFAULT_PROJECTS_DIR).expanduser()
    existing_projects = []
    if projects_dir.exists():
        for item in projects_dir.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                existing_projects.append(item.name)

    return {
        "ide_installed": ide_installed,
        "agentapi_bin": str(agent_bin) if agent_bin else None,
        "sdk_installed": sdk_installed,
        "projects_dir": str(projects_dir),
        "existing_projects": sorted(existing_projects),
        "ready": ide_installed or bool(agent_bin) or sdk_installed,
    }


def open_in_antigravity_ide(target_path: str | Path) -> bool:
    """Open a project workspace directly inside Antigravity IDE."""
    p = Path(target_path).expanduser().resolve()
    if not p.exists():
        return False

    sys_name = platform.system()
    try:
        if sys_name == "Darwin":
            if ANTIGRAVITY_APP_MACOS.exists():
                subprocess.Popen(["open", "-a", "Antigravity IDE", str(p)])
                return True
            subprocess.Popen(["open", "-b", "com.google.antigravity-ide", str(p)])
            return True
        elif sys_name == "Windows":
            subprocess.Popen(["cmd", "/c", "start", "antigravity", str(p)], shell=True)
            return True
        else:
            subprocess.Popen(["antigravity", str(p)])
            return True
    except Exception as e:
        print(f"[AntigravityBridge] Could not launch IDE: {e}")
        return False


# ── Autonomous Project Builder Engine ─────────────────────────────────────────

def _sanitize_project_name(name: str) -> str:
    cleaned = re.sub(r"[^\w\-_]", "_", name.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "antigravity_app"


def _derive_project_name(prompt: str, project_name: str = "") -> str:
    """Instant local derivation of project name — zero network delay."""
    if project_name:
        return _sanitize_project_name(project_name)
    low = prompt.lower()
    if any(k in low for k in ("portfolio", "personal website", "personal site", "cv", "resume")):
        return "divyanshu_portfolio"
    if any(k in low for k in ("clock", "stopwatch", "timer")):
        return "cyber_clock"
    words = [
        w for w in re.findall(r"[a-z0-9]+", low)
        if w not in ("create", "make", "build", "a", "an", "the", "website", "app",
                     "for", "with", "in", "to", "of", "and", "is", "my", "designed", "highly")
    ]
    slug = "_".join(words[:3]) if words else "antigravity_project"
    return _sanitize_project_name(slug)


def _extract_code_files(raw_text: str) -> List[Dict[str, str]]:
    """
    Extremely resilient multi-file extractor.
    Extracts files from:
    1. Markdown file blocks: `### FILE: filename.ext` or `FILE: filename.ext`
    2. JSON array manifests (if present and valid)
    3. Direct HTML / CSS / JS code blocks
    Never fails on unescaped internal quotes or special characters.
    """
    files: List[Dict[str, str]] = []

    # Strategy 1: Explicit FILE markers (### FILE: filename or FILE: filename)
    file_block_re = re.compile(
        r"(?:###\s*FILE:?|FILE:?)\s*([^\r\n]+)\r?\n+```[a-zA-Z0-9_\-]*\r?\n(.*?)\r?\n```",
        re.DOTALL | re.IGNORECASE,
    )
    matches = file_block_re.findall(raw_text)
    if matches:
        for path_str, content_str in matches:
            clean_path = path_str.strip().strip("`").strip("'").strip('"')
            clean_code = content_str.strip()
            if clean_path and clean_code:
                files.append({"path": clean_path, "content": clean_code})
        if files:
            return files

    # Strategy 2: JSON array manifest fallback
    match_json = re.search(r"```(?:json)?\s*(\[\s*\{.*?\}\s*\])\s*```", raw_text, re.DOTALL)
    json_candidate = match_json.group(1) if match_json else ""
    if not json_candidate:
        start = raw_text.find("[")
        end = raw_text.rfind("]")
        if start != -1 and end != -1 and end > start:
            json_candidate = raw_text[start:end + 1]

    if json_candidate:
        try:
            parsed = json.loads(json_candidate)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        p = item.get("path") or item.get("filename")
                        c = item.get("content", "")
                        if p and c:
                            files.append({"path": p, "content": c})
                if files:
                    return files
        except Exception:
            pass

    # Strategy 3: Standard language code block heuristics
    blocks = re.findall(r"```([a-zA-Z0-9_\-]*)\r?\n(.*?)\r?\n```", raw_text, re.DOTALL)
    found_html, found_css, found_js = None, None, None
    for lang, code in blocks:
        l = lang.lower().strip()
        c = code.strip()
        if "html" in l or "<!doctype html" in c.lower() or "<html" in c.lower():
            if not found_html:
                found_html = c
        elif "css" in l or (("{" in c and "}" in c and ":" in c) and not found_css and "function" not in c):
            if not found_css:
                found_css = c
        elif any(k in l for k in ("js", "javascript", "ts", "typescript")) or "const " in c or "document." in c:
            if not found_js:
                found_js = c

    if found_html:
        files.append({"path": "index.html", "content": found_html})
    if found_css:
        files.append({"path": "style.css", "content": found_css})
    if found_js:
        files.append({"path": "app.js", "content": found_js})

    # Strategy 4: Raw HTML document fallback
    if not files and "<!doctype html" in raw_text.lower():
        start = raw_text.lower().find("<!doctype html")
        end = raw_text.lower().rfind("</html>")
        if start != -1 and end != -1:
            files.append({"path": "index.html", "content": raw_text[start:end + 7]})

    return files


def build_project(
    prompt: str,
    project_name: str = "",
    project_type: str = "auto",
    auto_launch: bool = True,
    logger: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Autonomous software project builder.
    Generates a single, high-quality, production-grade codebase in
    `~/Desktop/Antigravity_Projects/<project_name>`, creates all files,
    and opens it in browser or Antigravity IDE.
    """
    from core.groq_client import call_groq_coder

    def log(msg: str):
        if logger:
            try:
                logger(msg)
            except Exception:
                pass
        print(f"[AntigravityBuilder] {msg}")

    # Instant name resolution
    project_name = _derive_project_name(prompt, project_name)
    projects_dir = Path(get_plugin_setting("antigravity_mcp", "projects_dir") or DEFAULT_PROJECTS_DIR).expanduser()
    out_dir = projects_dir / project_name
    out_dir.mkdir(parents=True, exist_ok=True)

    log(f"🚀 Project destination: {out_dir}")

    # Instructions for the principal software architect
    system_prompt = (
        "You are Google Antigravity, an elite principal software architect and senior web engineer.\n"
        "Your task is to build a single, complete, production-grade, hand-crafted software project.\n"
        "Rules:\n"
        "1. Write complete, high-fidelity, production-ready code with no placeholders or stubs.\n"
        "2. Do NOT use generic or cookie-cutter AI aesthetics. Deliver bespoke, clean typography, "
        "   refined color harmony (e.g. obsidian background, glowing cyan and amber accents), "
        "   subtle glassmorphism, responsive CSS grid/flexbox, and interactive JavaScript.\n"
        "3. Output each file clearly separated using this exact format:\n\n"
        "### FILE: index.html\n"
        "```html\n"
        "<!-- full html code here -->\n"
        "```\n\n"
        "### FILE: style.css\n"
        "```css\n"
        "/* full css code here */\n"
        "```\n\n"
        "### FILE: app.js\n"
        "```javascript\n"
        "// full javascript code here\n"
        "```\n\n"
        "### FILE: README.md\n"
        "```markdown\n"
        "# Project Overview\n"
        "```\n"
    )

    user_req = (
        f"Project Name: {project_name}\n"
        f"User Specification: {prompt}\n"
        f"Preferred Type: {project_type}\n\n"
        "Build the full project now with all source code."
    )

    log("🧠 Generating complete production codebase...")
    t0 = time.time()

    # Try high-speed Groq Qwen first (~450 tokens/sec, completes in 2-4 seconds)
    raw_text = ""
    try:
        groq_resp = call_groq_coder(
            contents=user_req,
            system_prompt=system_prompt,
            max_tokens=8192,
            temperature=0.2,
            timeout=40,
        )
        if groq_resp and groq_resp.text and len(groq_resp.text.strip()) > 100:
            raw_text = groq_resp.text.strip()
            log(f"⚡ Generated via Groq Qwen in {time.time() - t0:.2f}s")
    except Exception as e:
        log(f"Groq coder error: {e}, falling back to Gemini...")

    # Fallback to Gemini if Groq was empty
    if not raw_text:
        log("Querying Gemini engine...")
        raw_text = gemini.text(
            contents=f"{system_prompt}\n\n{user_req}",
            tier=gemini.SMART,
            timeout_ms=60000,
        )

    if not raw_text:
        return {
            "success": False,
            "error": "Antigravity builder did not receive code generation response.",
        }

    # Extract all files using our resilient extractor
    files = _extract_code_files(raw_text)

    if not files:
        return {
            "success": False,
            "error": "Could not extract source files from generator output.",
            "raw_output": raw_text[:300],
        }

    created_files = []
    has_web_index = False
    index_file_path = None

    for item in files:
        rel_path = item.get("path") or ""
        content = item.get("content", "")
        if not rel_path or not content:
            continue

        target_file = out_dir / rel_path
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(content, encoding="utf-8")
        created_files.append(rel_path)

        if rel_path.lower() == "index.html":
            has_web_index = True
            index_file_path = target_file

    log(f"✓ Created {len(created_files)} files in {out_dir}")

    # Launch if requested
    launched_action = None
    if auto_launch:
        if has_web_index and index_file_path:
            try:
                webbrowser.open(f"file://{index_file_path.resolve()}")
                launched_action = "browser"
                log(f"🌐 Opened {index_file_path.name} in default browser.")
            except Exception as e:
                log(f"⚠️ Could not open in browser: {e}")
        else:
            if is_antigravity_ide_installed():
                open_in_antigravity_ide(out_dir)
                launched_action = "ide"
                log("💻 Opened project in Antigravity IDE.")

    return {
        "success": True,
        "project_name": project_name,
        "project_dir": str(out_dir),
        "files": created_files,
        "has_web_index": has_web_index,
        "index_file": str(index_file_path) if index_file_path else None,
        "launched": launched_action,
    }


# ── AgentAPI Subprocess Integration ───────────────────────────────────────────

def run_agentapi_conversation(
    prompt: str,
    title: str = "",
    model: str = "flash",
    logger: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Spawn an interactive Antigravity agent conversation using agentapi."""
    agent_bin = find_agentapi_binary()
    if not agent_bin:
        return {
            "success": False,
            "error": "Antigravity agentapi binary not found at ~/.gemini/antigravity-ide/bin/agentapi",
        }

    cmd = [str(agent_bin), "new-conversation", f"--model={model}"]
    if title:
        cmd.append(f"--title={title}")
    cmd.append(prompt)

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = proc.communicate(timeout=60)
        success = (proc.returncode == 0)
        return {
            "success": success,
            "stdout": stdout.strip(),
            "stderr": stderr.strip(),
            "returncode": proc.returncode,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
