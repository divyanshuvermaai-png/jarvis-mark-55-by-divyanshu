"""
core/groq_client.py — High-performance Groq integration for coding tasks.

Uses Groq API with Qwen (default: "qwen/qwen3.8-27b") for coding, refactoring,
debugging, and project building. Runs at ~450 tokens/sec on Groq LPUs.
Transparently falls back to the Gemini ladder if Groq is unavailable or unconfigured.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests
from core import gemini


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _get_base_dir()
CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "qwen/qwen3.8-27b"


def get_groq_api_key() -> str:
    """Retrieve Groq API key from environment or config/api_keys.json."""
    env_key = os.environ.get("GROQ_API_KEY", "").strip()
    if env_key:
        return env_key
    try:
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return data.get("groq_api_key", "").strip()
    except Exception:
        pass
    return ""


def get_groq_model() -> str:
    """Retrieve configured Groq coding model name, defaulting to qwen/qwen3.8-27b."""
    try:
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return data.get("groq_coding_model", "").strip() or DEFAULT_MODEL
    except Exception:
        pass
    return DEFAULT_MODEL


class GroqResponse:
    """Emulates Gemini response structure with .text attribute for seamless compatibility."""
    def __init__(self, text: str):
        self.text = text or ""

    def __str__(self) -> str:
        return self.text


def _extract_prompt(contents: Any) -> str:
    """Flatten string, list, or structured prompt into a plain string prompt."""
    if isinstance(contents, str):
        return contents
    if isinstance(contents, list):
        parts = []
        for item in contents:
            if isinstance(item, str):
                parts.append(item)
            elif hasattr(item, "text"):
                parts.append(getattr(item, "text", ""))
            elif isinstance(item, dict):
                parts.append(item.get("text", str(item)))
            else:
                parts.append(str(item))
        return "\n\n".join(parts)
    if hasattr(contents, "text"):
        return getattr(contents, "text", "")
    return str(contents)


def call_groq_coder(
    contents: Any,
    system_prompt: str = (
        "You are an expert software engineer and programming assistant. "
        "Write clean, idiomatic, efficient, and production-ready code. "
        "Strictly adhere to the user's requirements, preserve formatting, "
        "and provide fully functioning implementations without cutting corners."
    ),
    max_tokens: int = 4096,
    temperature: float = 0.2,
    timeout: int = 45,
) -> GroqResponse | None:
    """Directly invoke Groq API with Qwen for code generation.
    Returns GroqResponse on success or None on failure/quota/missing key.
    """
    key = get_groq_api_key()
    if not key:
        return None

    model = get_groq_model()
    prompt = _extract_prompt(contents)
    if not prompt.strip():
        return GroqResponse("")

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        t0 = time.monotonic()
        resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=timeout)
        elapsed = time.monotonic() - t0

        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"] or ""
            print(f"[GroqCoder] {model} answered {len(content):,} chars in {elapsed:.2f}s")
            return GroqResponse(content)
        else:
            print(f"[GroqCoder] ⚠️ {model} returned HTTP {resp.status_code}: {resp.text[:180]}")
            return None
    except Exception as e:
        print(f"[GroqCoder] ⚠️ Request failed: {e}")
        return None


class GroqCoderModel:
    """Adapter class providing .generate_content(contents) compatible with Gemini callers."""

    def __init__(self, fallback_tier: str = gemini.SMART):
        self._fallback_tier = fallback_tier

    def generate_content(self, contents: Any) -> Any:
        # First attempt: Groq Qwen coding engine
        resp = call_groq_coder(contents)
        if resp is not None:
            return resp

        # Fallback: Gemini model ladder
        print("[GroqCoder] Groq unavailable — falling back to Gemini model ladder...")
        gemini_resp = gemini.call(contents, tier=self._fallback_tier, timeout_ms=60000)
        if gemini_resp is None:
            raise RuntimeError("Both Groq and Gemini models failed to generate response")
        return gemini_resp


def get_coding_model(fallback_tier: str = gemini.SMART) -> GroqCoderModel:
    """Returns a coding model instance (Groq Qwen with Gemini fallback)."""
    return GroqCoderModel(fallback_tier=fallback_tier)
