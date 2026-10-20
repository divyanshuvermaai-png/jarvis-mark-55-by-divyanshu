<div align="center">

# ⚡ J.A.R.V.I.S. MARK 55 (MARK-LV) ⚡
### Autonomous Multimodal Personal AI Operating System
**Conceived, Architected & Engineered by Divyanshu Verma**

[![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux%20%7C%20Windows-00d2ff?style=for-the-badge&logo=apple&logoColor=white)](https://github.com/divyanshuvermaai-png/jarvis-mark-55-by-divyanshu)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![AI Engine](https://img.shields.io/badge/Brain-Gemini%20Live%20%2B%20Groq-ff5500?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)
[![UI Framework](https://img.shields.io/badge/GUI-PyQt6%20Sci--Fi%20HUD-41CD52?style=for-the-badge&logo=qt&logoColor=white)](https://riverbankcomputing.com/software/pyqt/)
[![License](https://img.shields.io/badge/License-Proprietary%20%2F%20All%20Rights%20Reserved-red?style=for-the-badge)](./LICENSE)

---

> *"JARVIS is not merely an assistant — it is an extension of digital sovereignty. Conceived and engineered from pure vision into an autonomous, multimodal personal operating environment that perceives, reasons, speaks, and controls your computer in real-time."*

</div>

---

## 👨‍💻 Creator & Architectural Visionary

<div align="center">

### **Divyanshu Verma**
**Founder, Chief Architect & Lead Engineer — Divyanshu Industries**  
*17-Year-Old Class 11th Commerce Student • Autonomous AI Systems Builder • Hard-Core Vibe Coder*

| Channel | Link |
| :--- | :--- |
| 📧 **Official Email** | [divyanshuverma.ai@gmail.com](mailto:divyanshuverma.ai@gmail.com) |
| 📺 **YouTube** | [@divyanshu_sovereign_agent](https://www.youtube.com/@divyanshu_sovereign_agent) |
| 📸 **Instagram (Official Brand)** | [@the_divyanshu_group](https://www.instagram.com/the_divyanshu_group/) |
| 📸 **Instagram (Sovereign Agent)** | [@divyanshu_sovereign_agent](https://www.instagram.com/divyanshu_sovereign_agent/) |
| 🌐 **Portfolio Website** | [air-m5.lovable.app](https://air-m5.lovable.app) |
| 🐙 **GitHub Organization / Profile** | [@divyanshuvermaai-png](https://github.com/divyanshuvermaai-png) |

</div>

### About the Creator & The Vision
**Divyanshu Verma** (born February 27, 2009 in Bandikui, Dausa; currently based in Jaipur, Rajasthan, India) is a 17-year-old student pursuing Class 11th Commerce with an uncompromising ambition: building sovereign personal artificial intelligence systems that break free from corporate walled gardens, cloud subscriptions, and locked APIs.

Operating across a dedicated multi-device engineering setup — including a primary **MacBook Air M5** (Apple Silicon, macOS), a **Motorola Edge 60 Fusion** (running Termux Linux for mobile terminal builds), and a **Lenovo 81-MT** testbed — Divyanshu spends hundreds of hours designing native C/Python audio-video streaming pipelines, software-rendered 3D vector geometry, and multi-model AI failover architectures.

His overarching objective with **Divyanshu Industries** is to scale an AI-native operational powerhouse, architect transformative personal intelligence software, reach the top 0.0001% net worth bracket, and rival the world's foremost technology titans by age 40.

---

## 🌟 Overview: What is JARVIS Mark 55?

**JARVIS Mark 55 (Mark-LV)** is a cross-platform, autonomous personal AI desktop operating environment. Designed for **macOS (Apple Silicon & Intel)**, **Linux**, and **Windows**, Mark 55 combines real-time conversational intelligence with hands-on computer control.

While Mark LIV introduced an initial facial representation, **Mark 55 introduces full visual consciousness, an embedded video streaming canvas directly inside the holographic HUD, a resilient 9-model API fallback ladder, and comprehensive cross-platform system execution.**

Speak naturally to JARVIS, and it responds with low-latency bidirectional 24 kHz audio via Google Gemini Live, executes complex code tasks via Groq LPU acceleration, browses the web autonomously via Playwright, and renders reactive 3D facial animation in pure software — without requiring a high-end dedicated GPU.

---

## ⚡ Architecture & Verified Capabilities

```
                  ┌──────────────────────────────────────────────┐
                  │          JARVIS MARK 55 ARCHITECTURE         │
                  └──────────────────────┬───────────────────────┘
                                         │
         ┌───────────────────────────────┼───────────────────────────────┐
         ▼                               ▼                               ▼
 ┌───────────────┐               ┌───────────────┐               ┌───────────────┐
 │ MULTIMODAL AI │               │ SCI-FI HUD    │               │ OS CONTROL    │
 ├───────────────┤               ├───────────────┤               ├───────────────┤
 │ • Gemini Live │               │ • PyQt6 Arc   │               │ • App Launch  │
 │ • Groq Qwen   │               │   Reactor HUD │               │ • Screen Vision│
 │ • 9-Model     │               │ • 3D Avatar   │               │ • File Ops    │
 │   Fail-Safe   │               │ • HUD Video   │               │ • Automations │
 │ • Local VAD   │               │ • Reactive FX │               │ • Blender MCP │
 └───────────────┘               └───────────────┘               └───────────────┘
```

### 🧠 1. Dual-Brain Intelligence & 9-Model Resiliency Ladder
- **Gemini Live Bidirectional Streaming:** High-fidelity, natural turn-taking conversation over native 24 kHz WebSocket audio streaming (`google-genai`).
- **Groq LPU Code Acceleration:** Rapid code generation, syntax repair, and file editing powered by high-throughput Groq LPU inference (`qwen/qwen3.8-27b`).
- **Multi-Model Resiliency Ladder:** Requests cascade across an ordered failover ladder in [`core/llm_client.py`](./core/llm_client.py). If primary model quotas or network timeouts occur, JARVIS automatically steps down through secondary models, preventing unhandled session dropouts.
- **Configurable Live Temperature & Turn Tuning:** Grounded, deterministic tool invocation using a calibrated temperature (0.3) and voice activity detection buffers (2000 ms pause tolerance) in [`memory/config_manager.py`](./memory/config_manager.py).

### 🧑‍🎤 2. Holographic 3D Avatar & Facial Mesh
- **Software-Rendered 3D Wireframe Avatar:** Renders 3D facial geometry ([`core/face_model.obj`](./core/face_model.obj)) using mathematical projection via `QPainter` and `numpy`. Operates smoothly on integrated graphics without requiring OpenGL or a discrete GPU.
- **Formant & Viseme Lip Synchronization:** Evaluates audio frequencies to map 50 mouth shapes per second (closures, spreads, rounds) in real time ([`core/viseme.py`](./core/viseme.py)).
- **Expressive Micro-Behaviors:** Natural eye saccades, dynamic blink intervals, cognitive status cues (looks aside during LLM processing, makes eye contact when listening), and volume-reactive soundwave rings.
- **HUD-Integrated Video Player:** Streams YouTube videos and local media directly inside the avatar canvas via `yt-dlp` and `QtMultimedia` ([`actions/video_player.py`](./actions/video_player.py)).
- **Acoustic Self-Echo Shield:** Real-time software acoustic filtering ([`core/echo.py`](./core/echo.py)) prevents the assistant from hearing and looping its own audio output during video playback.

### 🖥️ 3. Autonomous Computer Control & Safeguards
- **Cross-Platform System Management:** Adjusts audio volume, screen brightness, active applications, and window geometry natively across macOS (`osascript`), Linux (`pactl` / `brightnessctl`), and Windows (`pywin32` / `pycaw`).
- **Computer Vision & Desktop Perception:** Captures desktop screenshots and webcam frames to analyze active applications, error dialogs, and documents.
- **File System Operations:** Reads, summarizes, creates, and organizes documents (`.pdf`, `.docx`, `.pptx`, `.xlsx`, `.txt`). File deletions route through `send2trash` for safe recovery.
- **Destructive Action Confirmation Modal:** Potentially dangerous operations (system reboot, shutdown, bulk deletions, process kills) trigger a blocking PyQt6 physical confirmation dialog ([`core/confirm.py`](./core/confirm.py)) before execution.
- **Action Rollback & Undo:** Tracks file and system changes on an undo stack ([`core/undo.py`](./core/undo.py)) to revert unintended operations upon request.

### 🧩 4. Extensibility, MCP & Remote Dashboard
- **Drop-In Plugin Architecture:** Place a self-contained Python module into [`plugins/`](./plugins/) using [`plugins/_template.py`](./plugins/_template.py); the action loader dynamically registers tools on the next launch.
- **Model Context Protocol (MCP) Bridges:** Integrates external systems, including local Blender 3D procedural scene generation ([`plugins/blender_mcp.py`](./plugins/blender_mcp.py)) and Google Antigravity IDE agent coordination ([`plugins/antigravity_mcp.py`](./plugins/antigravity_mcp.py)).
- **Encrypted Remote Web Dashboard:** Run an authenticated local HTTPS / WebSocket dashboard ([`dashboard/server.py`](./dashboard/server.py)) to monitor system telemetry, trigger actions, and speak to JARVIS from a mobile phone using QR-token pairing.
- **Local Wake Word & Push-to-Talk:** Supports offline "Hey Jarvis" activation via optional `openWakeWord` or global keyboard chords (`Ctrl+Space`).

---

## 🛠️ Technology Stack

| Layer | Technologies & Libraries |
| :--- | :--- |
| **Language Runtime** | Python 3.11, 3.12, 3.13 (Hard minimum: Python 3.11) |
| **Desktop GUI & Rendering** | PyQt6, QtMultimedia, NumPy (software 3D projection) |
| **Multimodal Intelligence** | Google Gemini Live SDK (`google-genai`), Groq Python SDK |
| **Audio Processing** | `sounddevice`, `numpy`, formant viseme analysis, `Edge-TTS` fallback |
| **Vision & Screen Perception** | `mss`, `opencv-python`, `pillow` (PIL) |
| **Browser & Input Automation**| Playwright (Chromium/Firefox), PyAutoGUI, pyperclip |
| **System & File Management** | `psutil`, `send2trash`, `python-docx`, `pdfplumber`, `python-pptx`, `openpyxl` |
| **Remote Dashboard** | FastAPI, Uvicorn, Cryptography (TLS), WebSockets, CryptoJS |
| **Media Extraction** | `yt-dlp`, `youtube-transcript-api` |

---

## 📂 Project Structure

```
jarvis-mark-55-by-divyanshu/
├── actions/                  # Autonomous computer control and tools
│   ├── background_monitor.py # Scheduled headline, market, and topic monitoring
│   ├── browser_control.py    # Voice-driven web browser automation via Playwright
│   ├── code_helper.py        # High-speed Groq/Qwen code generation and file writing
│   ├── computer_control.py   # Native OS control (volume, brightness, power)
│   ├── computer_settings.py  # System settings and display management
│   ├── desktop.py            # Window management, taskbar, and application switcher
│   ├── dev_agent.py          # Multi-step autonomous planning and self-correction
│   ├── file_controller.py    # Local filesystem reading, writing, and safe deletion
│   ├── file_processor.py     # Document reading and analysis (PDF, DOCX, PPTX, XLSX)
│   ├── flight_finder.py      # Real-time flight search and itinerary extraction
│   ├── game_updater.py       # Game update tracking and Steam client automation
│   ├── notifier.py           # Native OS desktop banner notifications
│   ├── open_app.py           # Cross-platform application launcher
│   ├── proactive.py          # Proactive routine alerts and context suggestions
│   ├── reminder.py           # Local calendar reminders and scheduled timers
│   ├── scheduler.py          # Persistent cron and interval task manager
│   ├── screen_processor.py   # Screen capture perception and webcam frame analysis
│   ├── send_message.py       # WhatsApp Web and Telegram automation
│   ├── system_monitor.py     # Hardware telemetry (CPU, RAM, GPU, thermal metrics)
│   ├── video_player.py       # HUD-integrated video and media streaming
│   ├── weather_report.py     # Real-time weather data retrieval
│   ├── web_search.py         # Search query synthesis (Google / DuckDuckGo)
│   └── youtube_video.py      # YouTube search, direct stream playback, and transcripts
├── config/                   # Configuration, icons, and credentials template
│   ├── __init__.py           # Cross-platform environment and path resolver
│   ├── api_keys.json.example # Clean template with documented options
│   ├── jarvis.ico            # Windows application icon
│   ├── jarvis.png            # High-resolution HUD logo
│   ├── logo.png              # Sci-Fi arc-reactor brand logo
│   ├── jarvis.icns           # macOS bundle icon
│   └── AppIcon.icns          # macOS application icon
├── core/                     # Core runtime, rendering, and AI orchestration engines
│   ├── __init__.py           # Package initializer
│   ├── action_loader.py      # Dynamic tool discovery and schema binding
│   ├── antigravity_bridge.py # Antigravity agentic workspace bridge
│   ├── audio_devices.py      # Audio input/output device detection and persistence
│   ├── avatar.py             # 3D holographic avatar rendering and facial animator
│   ├── avatar_mesh.py        # 3D facial vertices and wireframe transform calculations
│   ├── blender_bridge.py     # Local Blender headless automation bridge
│   ├── confirm.py            # Safety confirmation modal logic for sensitive actions
│   ├── echo.py               # Self-echo acoustic suppression filter
│   ├── face_model.obj        # 3D facial geometry vertex data
│   ├── face_model.mtl        # Material template definition
│   ├── gantry_viewer.py      # Interactive 3D HUD gantry viewport
│   ├── gemini.py             # Native Gemini Live 24 kHz WebSocket client
│   ├── groq_client.py        # Ultra-fast Groq LPU inference client
│   ├── hotkey.py             # Global keyboard chord hooks (push-to-talk)
│   ├── installer.py          # Runtime dependency dynamic installer
│   ├── llm_client.py         # Multi-model resiliency ladder and failover router
│   ├── notifier.py           # Core notification distribution pipeline
│   ├── plugin_loader.py      # Drop-in plugin manager and sandboxing
│   ├── prompt.txt            # Master personality directives and behavioral rules
│   ├── scheduler.py          # Background routine loop and timer dispatcher
│   ├── screen_share.py       # Live visual context capture and token stream pipeline
│   ├── stt.py                # Local speech-to-text fallback engines
│   ├── telegram_bridge.py    # Remote Telegram command listener and response relay
│   ├── tts.py                # Speech synthesis fallback (Edge-TTS / system speech)
│   ├── undo.py               # Action history stack and rollback controller
│   ├── viseme.py             # Phoneme-to-viseme lip-sync reduction engine
│   └── wake_word.py          # Local wake-word listening loop ("Hey Jarvis")
├── dashboard/                # Remote web control portal
│   ├── __init__.py           # Package initializer
│   ├── server.py             # Local HTTPS FastAPI server with WebSocket relays
│   └── static/               # Web client UI (HTML, CSS, JS, Crypto-JS)
│       ├── app.html          # Remote HUD telemetry and voice interface
│       ├── crypto-js.min.js  # Client-side cryptographic pairing utilities
│       ├── login.html        # QR-authenticated mobile entry portal
│       └── logo.png          # Portal branding asset
├── memory/                   # Context storage and persistence
│   ├── __init__.py           # Package initializer
│   ├── config_manager.py     # Dynamic configuration read/write manager
│   ├── memory_manager.py     # Long-term knowledge base and fact extraction
│   └── schedules.json        # User-defined schedules and routine timers
├── plugins/                  # Extensibility directory for custom actions
│   ├── __init__.py           # Package initializer
│   ├── _template.py          # Starter template for authoring custom plugins
│   ├── antigravity_mcp.py    # Antigravity tool and subagent connector
│   └── blender_mcp.py        # Blender Model Context Protocol tool provider
├── scripts/                  # Development and packaging automation
│   └── build_windows_installer.py # Standalone NSIS Windows binary compiler
├── .gitignore                # Production ignore patterns protecting user secrets
├── CREDITS.md                # Official project credits and creator biography
├── LICENSE                   # Proprietary software license & evaluation terms
├── README.md                 # Main project landing page and documentation
├── SECURITY.md               # Security policy and vulnerability disclosure guide
├── THIRD_PARTY_NOTICES.md    # Verified third-party dependencies and notices
├── demo_avatar.py            # Standalone 3D avatar & lip-sync preview test utility
├── main.py                   # Application entry point and lifecycle bootstrapper
├── requirements.txt          # Python dependency definitions with OS platform markers
├── setup.py                  # One-time automated environment and Playwright installer
└── ui.py                     # Master PyQt6 futuristic HUD desktop interface
```

---

## 💻 System Requirements & Supported Platforms

| Operating System | Supported Architectures | Notes |
| :--- | :--- | :--- |
| **macOS** | Apple Silicon (M1/M2/M3/M4/M5), Intel (x86_64) | macOS 12+ recommended. Built-in `osascript` handles volume, brightness, reminders. |
| **Linux** | Ubuntu / Debian / Fedora / Arch (x86_64) | Requires X11 or Wayland with XWayland. Native tools: `pulseaudio-utils` (`pactl`), `brightnessctl`. |
| **Windows** | Windows 10, Windows 11 (64-bit) | Automatically installs Windows-specific extensions (`pywin32`, `pycaw`, `pywinauto`). |

### Python Requirements
- **Minimum Required Version:** Python **3.11** (syntax requirement for modern typing and asyncio constructs).
- **Verified & Tested Versions:** Python **3.11**, **3.12**, and **3.13**.
- Interpreters below 3.11 will be rejected during setup check.

---

## 🚀 Installation & Setup Guide

### Step 1: Clone the Repository
```bash
git clone https://github.com/divyanshuvermaai-png/jarvis-mark-55-by-divyanshu.git
cd jarvis-mark-55-by-divyanshu
```

### Step 2: Create and Activate a Virtual Environment

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (Command Prompt / PowerShell):**
```cmd
python -m venv .venv
.venv\Scripts\activate
```

### Step 3: Run the Automated Setup Script
Run [`setup.py`](./setup.py). It automatically checks your Python version, installs dependencies tailored to your operating system via platform markers in [`requirements.txt`](./requirements.txt), and downloads the Playwright browser binaries required for browser automation:
```bash
python setup.py
```

*(Manual Alternative):* If you prefer manual installation:
```bash
pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium firefox
```

---

## ⚙️ Configuration & API Credentials

1. Copy the example template [`config/api_keys.json.example`](./config/api_keys.json.example) to create your local config file:
   ```bash
   cp config/api_keys.json.example config/api_keys.json
   ```
2. Open `config/api_keys.json` in your text editor and provide your keys:
   ```json
   {
     "gemini_api_key": "YOUR_GEMINI_API_KEY",
     "groq_api_key": "YOUR_GROQ_API_KEY",
     "groq_coding_model": "qwen/qwen3.8-27b",
     "assistant_name": "JARVIS",
     "user_name": "Boss",
     "os_system": "mac",
     "hud_style": "core",
     "voice_name": "Charon",
     "wake_word_enabled": false,
     "push_to_talk_enabled": false,
     "live_temperature": 0.3,
     "thinking_enabled": false,
     "media_resolution": "medium",
     "camera_index": 0,
     "morning_brief_enabled": true,
     "input_device": "",
     "output_device": "",
     "turn_tuning": {
       "enabled": true,
       "silence_ms": 2000,
       "prefix_ms": 250,
       "end_sensitivity": "low",
       "start_sensitivity": "default"
     },
     "proactive_audio": false,
     "telegram_bot_token": "YOUR_TELEGRAM_BOT_TOKEN_FROM_BOTFATHER",
     "telegram_chat_id": "YOUR_TELEGRAM_CHAT_ID"
   }
   ```
   - **`gemini_api_key` (Required):** Obtainable from [Google AI Studio](https://aistudio.google.com/).
   - **`groq_api_key` (Optional):** Obtainable from [Groq Console](https://console.groq.com/) for fast code reasoning.
   - **`voice_name`:** Supported Gemini Live voices: `Charon`, `Puck`, `Kore`, `Fenrir`, `Aoede`.
   - **`os_system`:** Set to `"mac"`, `"linux"`, or `"windows"`.

---

## 🎬 Launching JARVIS Mark 55

### Main Application
```bash
python main.py
```
On initial boot, JARVIS initializes audio streaming, binds system actions, loads active plugins, and displays the futuristic PyQt6 holographic HUD. If no key was pre-configured, a first-run setup dialog prompts for your Gemini API key.

### Standalone Avatar Demo
To test 3D facial rendering, test viseme mouth shapes, or preview HUD centerpieces without running the full background OS service:
```bash
python demo_avatar.py
```

---

## 🔒 Privacy, Security & Data Boundaries

1. **Local vs. External Transmission:**
   - Your API keys, configuration, custom plugins, and schedule files are stored locally on your device.
   - When conversational voice or vision features are used, audio streams, text prompts, and requested screenshots are transmitted to the configured AI API providers (Google Cloud / Groq) to perform inference.
2. **Secrets Protection:**
   - [`config/api_keys.json`](./config/api_keys.json), TLS certificates (`config/certs/`), session tokens, and long-term memory are excluded by [`.gitignore`](./.gitignore).
   - **Important:** `.gitignore` only prevents newly added files from being staged; it cannot retroactively protect files that are forced into Git. Users must remain vigilant never to commit credentials or sensitive files into public forks.
3. **Execution Safety:**
   - Destructive actions (system power states, mass deletions, process kills) require user confirmation via physical click on the confirmation modal.
   - Refer to [SECURITY.md](./SECURITY.md) for vulnerability disclosure procedures.

---

## ⚠️ Known Limitations & Optional Features

- **Local Wake Word ("Hey Jarvis"):** Local wake-word gating is optional and powered by `openWakeWord`. It can be enabled in settings (`⚙ → WAKE WORD`) and requires installing the optional package (`pip install openwakeword`).
- **Playwright Browser Binaries:** Browser automation features require Chromium/Firefox binaries (`python -m playwright install chromium firefox`). If omitted, other desktop and voice features remain fully functional.
- **Third-Party API Quotas:** Real-time conversational speed and uptime depend on upstream provider availability and your API rate limits.
- **Wayland Compatibility:** On Linux environments running Wayland, some desktop input automation functions may require XWayland or native desktop permissions.

---

## 📜 Intellectual Property & Licensing

JARVIS Mark 55 is proprietary software authored and owned by **Divyanshu Verma**.

```
Copyright © 2026 Divyanshu Verma. All Rights Reserved.
Organization / Brand: Divyanshu Industries
```

- **Personal Evaluation License:** You are granted limited permission to download, view, study, and run an unmodified copy for personal, non-commercial evaluation and learning.
- **Commercial Restrictions:** Redistribution, public re-hosting, commercial exploitation, rebranding, white-labeling, or distributing derivative works without prior written authorization from Divyanshu Verma is strictly prohibited.
- **Third-Party Components:** Third-party libraries, frameworks, and APIs remain governed by their respective upstream open-source licenses.
- Detailed licensing terms are documented in [LICENSE](./LICENSE).
- Upstream open-source notices and compliance information are detailed in [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md).
- Creator attribution guidelines are detailed in [CREDITS.md](./CREDITS.md).

---

## 🤝 Connect with Divyanshu Verma

For commercial licensing, enterprise inquiries, sponsorships, or collaboration proposals:

- 📧 **Direct Email:** [divyanshuverma.ai@gmail.com](mailto:divyanshuverma.ai@gmail.com)
- 📺 **YouTube:** [@divyanshu_sovereign_agent](https://www.youtube.com/@divyanshu_sovereign_agent)
- 📸 **Instagram:** [@the_divyanshu_group](https://www.instagram.com/the_divyanshu_group/) & [@divyanshu_sovereign_agent](https://www.instagram.com/divyanshu_sovereign_agent/)
- 🌐 **Portfolio:** [air-m5.lovable.app](https://air-m5.lovable.app)
- 🐙 **GitHub:** [divyanshuvermaai-png](https://github.com/divyanshuvermaai-png)

---

<div align="center">

**Engineered with pride by Divyanshu Verma • Divyanshu Industries**  
*JARVIS Mark 55 — Intelligent computing, built with a vision.*

</div>
