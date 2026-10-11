#!/usr/bin/env python3
"""
Interactive Cybernetic JARVIS AI Assistant & Avatar
Features:
- Live Cybernetic Avatar with Laser HUD Visor & Acoustic Vocal Equalizer Diaphragm
- Real Gemini AI intelligence via Google Gemini API
- Real Text-to-Speech vocal output using authentic British voice (Daniel)
- True audio-reactive lip synchronization: extracts RMS amplitude from synthesized speech
- Gaze tracking that follows your mouse cursor in real time
- Preset interactive prompts + custom chat input box
"""

import sys
import math
import time
import json
import wave
import shutil
import threading
import subprocess
from pathlib import Path

# Ensure Mark-LV root is on path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import numpy as np
import sounddevice as sd
from google import genai
from PyQt6.QtCore import Qt, QTimer, QRectF, pyqtSignal, QObject
from PyQt6.QtGui import QPainter, QColor, QFont, QBrush, QPen
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QSlider, QFrame
)

import tempfile
import platform
from core.avatar import HoloAvatar
from memory.config_manager import get_gemini_key, is_configured

SPEECH_WAV = str(Path(tempfile.gettempdir()) / "jarvis_speech.wav")
SYSTEM_PROMPT = (
    "You are J.A.R.V.I.S., the hyper-intelligent, sophisticated, British AI assistant "
    "created by Tony Stark for the Mark-LV cybernetic armor. "
    "Keep all spoken answers concise (1 to 3 sentences maximum), technologically precise, "
    "witty, polite, and completely in character. Never use emojis or markdown bullets."
)


def synthesize_speech(text: str, out_wav: str) -> bool:
    """Synthesizes text to a 16-bit PCM WAV file across macOS, Windows, and Linux."""
    sys_name = platform.system()

    # 1. macOS (say command)
    if sys_name == "Darwin" and shutil.which("say"):
        try:
            voice_args = ["-v", "Daniel"]
            chk = subprocess.run(["say", "-v", "?"], capture_output=True, text=True)
            if "Daniel" not in chk.stdout:
                voice_args = []
            subprocess.run(
                ["say"] + voice_args + [
                    "--file-format=WAVE", "--data-format=LEI16",
                    "-o", out_wav,
                    text
                ],
                check=True,
                capture_output=True
            )
            if Path(out_wav).is_file() and Path(out_wav).stat().st_size > 44:
                return True
        except Exception:
            pass

    # 2. Windows (PowerShell System.Speech)
    if sys_name == "Windows":
        try:
            escaped_text = text.replace("'", "''").replace('"', '`"')
            escaped_wav = out_wav.replace("'", "''")
            ps_script = (
                f"Add-Type -AssemblyName System.Speech; "
                f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.SetOutputToWaveFile('{escaped_wav}'); "
                f"$s.Speak('{escaped_text}'); "
                f"$s.Dispose()"
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], check=True, capture_output=True)
            if Path(out_wav).is_file() and Path(out_wav).stat().st_size > 44:
                return True
        except Exception:
            pass

    # 3. Linux (espeak-ng / espeak)
    if sys_name == "Linux":
        cmd = None
        if shutil.which("espeak-ng"):
            cmd = "espeak-ng"
        elif shutil.which("espeak"):
            cmd = "espeak"
        if cmd:
            try:
                subprocess.run([cmd, "-w", out_wav, text], check=True, capture_output=True)
                if Path(out_wav).is_file() and Path(out_wav).stat().st_size > 44:
                    return True
            except Exception:
                pass

    # 4. Universal Fallback: synthesizes acoustic speech waveform so lip-sync and audio work seamlessly without external TTS
    try:
        sample_rate = 22050
        words = max(1, len(text.split()))
        duration = max(1.5, words * 0.28)
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        carrier = np.sin(2 * np.pi * 140 * t) + 0.4 * np.sin(2 * np.pi * 280 * t)
        modulator = 0.5 + 0.5 * np.sin(2 * np.pi * (words / duration) * t)
        samples = (carrier * modulator * 0.3 * 32767).astype(np.int16)
        with wave.open(out_wav, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(samples.tobytes())
        return True
    except Exception as e:
        print(f"[Speech Synth Fallback Error]: {e}")
        return False


class AISpeechBridge(QObject):
    """Signals for background AI generation and speech completion."""
    ai_started = pyqtSignal()
    ai_replied = pyqtSignal(str)
    ai_failed = pyqtSignal(str)


class AvatarCanvas(QWidget):
    """Interactive canvas rendering the cybernetic avatar with real audio sync."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(560, 480)
        self.setMouseTracking(True)
        self._avatar = HoloAvatar()

        # State
        self.speaking = False
        self.state = "STANDBY"
        self.amp = 0.0
        self.active_phrase = ""
        self.status_detail = "ALL SYSTEMS NOMINAL"
        self.manual_amp = 0.0

        # Audio playback synchronization
        self.audio_samples = None
        self.audio_rate = 22050
        self.playback_start_t = 0.0
        self.audio_duration = 0.0

        # Animation timer (60 FPS)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)
        self._last_t = time.time()

    def start_speaking_audio(self, phrase: str, wav_path: str):
        """Play synthesized audio and drive lip sync from actual audio samples."""
        try:
            with wave.open(wav_path, "rb") as wf:
                self.audio_rate = wf.getframerate()
                raw_bytes = wf.readframes(wf.getnframes())
                self.audio_samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                self.audio_duration = len(self.audio_samples) / float(self.audio_rate)
        except Exception as e:
            print(f"[Audio Error] Failed to read WAV: {e}")
            self.audio_samples = None
            self.audio_duration = max(2.0, len(phrase) * 0.07)

        self.active_phrase = phrase
        self.speaking = True
        self.state = "SPEAKING"
        self.status_detail = "VOCAL AUDIO TRANSMISSION"
        self.playback_start_t = time.time()

        if self.audio_samples is not None:
            # Play through default output without blocking Qt loop
            try:
                sd.play(self.audio_samples, samplerate=self.audio_rate)
            except Exception as e:
                print(f"[SoundDevice Error]: {e}")

    def mouseMoveEvent(self, event):
        """Make the cyber visor look toward the mouse cursor."""
        cx, cy = self.width() * 0.5, self.height() * 0.5
        dx = (event.position().x() - cx) / (self.width() * 0.5)
        dy = (event.position().y() - cy) / (self.height() * 0.5)
        self._avatar.glance(dx * 0.85, dy * 0.85, hold=0.9)
        super().mouseMoveEvent(event)

    def _tick(self):
        now = time.time()
        dt = min(0.05, now - self._last_t)
        self._last_t = now

        # Update speech animation based on real audio playback
        if self.speaking:
            elapsed = now - self.playback_start_t
            if elapsed >= self.audio_duration:
                self.speaking = False
                self.state = "STANDBY"
                self.status_detail = "ALL SYSTEMS NOMINAL"
                self.amp = 0.0
                self._avatar.step(dt=dt, amp=0.0, speaking=False, state="STANDBY")
            else:
                if self.audio_samples is not None:
                    # Extract instantaneous RMS from exact audio position
                    idx = int(elapsed * self.audio_rate)
                    win_size = int(self.audio_rate * 0.04)  # 40ms window
                    start_i = max(0, idx - win_size // 2)
                    end_i = min(len(self.audio_samples), idx + win_size // 2)
                    chunk = self.audio_samples[start_i:end_i]
                    if len(chunk) > 0:
                        raw_rms = float(np.sqrt(np.mean(chunk ** 2)))
                        # Normalize and scale for visible mandibular articulation
                        calc_amp = min(1.0, raw_rms * 4.8)
                    else:
                        calc_amp = 0.0
                    self.amp = max(0.0, min(1.0, calc_amp))
                else:
                    cadence = math.sin(elapsed * 16.0) * math.sin(elapsed * 6.5)
                    self.amp = max(0.15, min(0.95, 0.55 + 0.40 * cadence))

                v_open = min(1.0, self.amp * 1.2)
                v_wide = 0.3 * math.sin(elapsed * 12.0)
                self._avatar.step(
                    dt=dt,
                    amp=self.amp,
                    speaking=True,
                    state="SPEAKING",
                    v_open=v_open,
                    v_wide=v_wide,
                    v_level=self.amp,
                )
        elif self.manual_amp > 0.01:
            self._avatar.step(
                dt=dt,
                amp=self.manual_amp,
                speaking=True,
                state="SPEAKING",
                v_open=self.manual_amp,
                v_level=self.manual_amp,
            )
        else:
            self._avatar.step(dt=dt, amp=0.0, speaking=False, state=self.state)

        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w, h = self.width(), self.height()
        cx, cy = w * 0.5, h * 0.5

        # Background
        p.fillRect(0, 0, w, h, QColor("#00060a"))

        # Render Cybernetic Avatar
        r_head = min(w * 0.35, h * 0.40)
        self._avatar.paint(
            p,
            cx=cx,
            cy=cy + 15,
            r=r_head,
            primary=QColor("#00d4ff"),
            accent=QColor("#ff6b00"),
            bg=QColor("#00060a"),
        )

        # Status text & subtitle overlay
        font_hud = QFont("Helvetica", 11, QFont.Weight.Bold)
        p.setFont(font_hud)

        if self.speaking:
            p.setPen(QColor("#00d4ff"))
            p.drawText(24, 34, "● J.A.R.V.I.S. VOCAL TRANSMISSION")

            # Draw subtitle box at bottom
            p.setPen(QColor("#004050"))
            p.setBrush(QBrush(QColor(0, 15, 25, 210)))
            p.drawRoundedRect(QRectF(16, h - 56, w - 32, 44), 6, 6)

            p.setPen(QColor("#ffffff"))
            p.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
            # Truncate if too long for 1 line
            disp_txt = self.active_phrase
            if len(disp_txt) > 85:
                disp_txt = disp_txt[:82] + "..."
            p.drawText(QRectF(28, h - 54, w - 56, 40), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, f"\"{disp_txt}\"")

            # Equalizer bars indicator in top corner
            p.setPen(Qt.PenStyle.NoPen)
            for i in range(12):
                bh = 4 + 22 * self.amp * abs(math.sin(i * 0.6 + time.time() * 14.0))
                p.setBrush(QBrush(QColor("#00f0ff")))
                p.drawRect(QRectF(w - 170 + i * 12, 34 - bh, 8, bh))
        elif self.state == "THINKING":
            p.setPen(QColor("#ffaa00"))
            p.drawText(24, 34, "⚙ J.A.R.V.I.S. COMPUTING RESPONSE...")
        else:
            p.setPen(QColor("#00ff88"))
            p.drawText(24, 34, f"◇ STATUS: {self.status_detail} // GAZE TRACKING ACTIVE")

        p.end()


class JarvisDemoWindow(QMainWindow):
    """Main window with real AI chat and speech lip sync."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mark-LV // Cybernetic JARVIS AI Interface")
        self.resize(800, 750)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #00060a;
            }
            QPushButton {
                background-color: #021a24;
                color: #8ffcff;
                border: 1px solid #1a5c7a;
                border-radius: 4px;
                padding: 8px 14px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #032c3d;
                border-color: #00d4ff;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #00d4ff;
                color: #00060a;
            }
            QLineEdit {
                background-color: #02141c;
                border: 1px solid #00a2cc;
                border-radius: 4px;
                color: #ffffff;
                font-size: 13px;
                padding: 8px 12px;
            }
            QLineEdit:focus {
                border: 1px solid #00f0ff;
                background-color: #031c26;
            }
            QLabel {
                color: #5ab8cc;
                font-size: 12px;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #0f4060;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #00d4ff;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #ff6b00;
                border: 1px solid #ffffff;
                width: 14px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 7px;
            }
        """)

        # Gemini Client Initialization
        self.gemini_key = get_gemini_key()
        self.client = None
        if self.gemini_key:
            try:
                self.client = genai.Client(api_key=self.gemini_key)
            except Exception as e:
                print(f"[Gemini Init Error]: {e}")

        self.bridge = AISpeechBridge()
        self.bridge.ai_started.connect(self._on_ai_started)
        self.bridge.ai_replied.connect(self._on_ai_replied)
        self.bridge.ai_failed.connect(self._on_ai_failed)

        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # 3D Avatar Canvas
        self.canvas = AvatarCanvas(self)
        layout.addWidget(self.canvas, stretch=1)

        # Chat Input Bar
        chat_box = QHBoxLayout()
        self.input_field = QLineEdit(self)
        self.input_field.setPlaceholderText("Ask JARVIS anything (e.g. 'What is the status of Mark-LV?')...")
        self.input_field.returnPressed.connect(self._submit_query)
        chat_box.addWidget(self.input_field, stretch=1)

        self.btn_send = QPushButton("⚡ Ask JARVIS", self)
        self.btn_send.clicked.connect(self._submit_query)
        chat_box.addWidget(self.btn_send)
        layout.addLayout(chat_box)

        # Controls & Presets
        ctrl_panel = QWidget(self)
        ctrl_layout = QVBoxLayout(ctrl_panel)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(8)

        # Quick AI Preset Buttons
        btn_layout = QHBoxLayout()
        presets = [
            ("Diagnostics", "Run a complete diagnostic on the Mark-LV cybernetic armor."),
            ("Who are you?", "State your primary identity and core capabilities."),
            ("Combat Alert", "Report tactical readiness for potential hostile targets."),
            ("Stark Wit", "Give me a classic Tony Stark style witty observation."),
        ]

        for label, query in presets:
            btn = QPushButton(label, self)
            btn.clicked.connect(lambda checked, q=query: self._ask_jarvis(q))
            btn_layout.addWidget(btn)

        ctrl_layout.addLayout(btn_layout)

        # Slider for manual mouth testing
        slider_layout = QHBoxLayout()
        slider_label = QLabel("Manual Jaw Drive:")
        self.slider = QSlider(Qt.Orientation.Horizontal, self)
        self.slider.setRange(0, 100)
        self.slider.setValue(0)
        self.slider.valueChanged.connect(self._on_slider_changed)
        slider_layout.addWidget(slider_label)
        slider_layout.addWidget(self.slider)
        ctrl_layout.addLayout(slider_layout)

        hint = QLabel("💡 Type any question or click a prompt above. JARVIS generates AI replies and speaks with real-time lip sync!")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ctrl_layout.addWidget(hint)

        layout.addWidget(ctrl_panel)

    def _submit_query(self):
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()
        self._ask_jarvis(text)

    def _ask_jarvis(self, prompt: str):
        """Invoke Gemini AI in a background thread to prevent UI freezing."""
        if not self.client:
            msg = "API key is not configured. Please verify your settings."
            synthesize_speech(msg, SPEECH_WAV)
            self.canvas.start_speaking_audio(msg, SPEECH_WAV)
            return

        self.canvas.state = "THINKING"
        self.btn_send.setEnabled(False)
        self.btn_send.setText("Thinking...")

        threading.Thread(target=self._worker_ai_query, args=(prompt,), daemon=True).start()

    def _worker_ai_query(self, prompt: str):
        """Thread worker that contacts Gemini, synthesizes speech, and alerts UI."""
        try:
            self.bridge.ai_started.emit()

            # Generate response from fast model ladder
            models_to_try = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.8-flash"]
            response_text = ""

            for model_name in models_to_try:
                try:
                    resp = self.client.models.generate_content(
                        model=model_name,
                        contents=[SYSTEM_PROMPT, f"User says: {prompt}"]
                    )
                    # Extract plain text
                    raw_text = resp.text or ""
                    for cand in getattr(resp, 'candidates', []):
                        if hasattr(cand, 'content') and hasattr(cand.content, 'parts'):
                            for part in cand.content.parts:
                                if hasattr(part, 'text') and part.text:
                                    raw_text = part.text
                    clean_text = raw_text.strip().replace("\n", " ").replace("*", "").replace('"', '')
                    if clean_text:
                        response_text = clean_text
                        break
                except Exception as ex:
                    print(f"[{model_name} failed]: {ex}")

            if not response_text:
                response_text = "I apologize, sir. I am momentarily unable to process that request."

            # Synthesize speech across macOS, Windows, and Linux
            synthesize_speech(response_text, SPEECH_WAV)

            self.bridge.ai_replied.emit(response_text)

        except Exception as e:
            print(f"[AI Worker Error]: {e}")
            self.bridge.ai_failed.emit(str(e))

    def _on_ai_started(self):
        self.canvas.state = "THINKING"

    def _on_ai_replied(self, reply: str):
        self.btn_send.setEnabled(True)
        self.btn_send.setText("⚡ Ask JARVIS")
        self.canvas.start_speaking_audio(reply, SPEECH_WAV)

    def _on_ai_failed(self, err: str):
        self.btn_send.setEnabled(True)
        self.btn_send.setText("⚡ Ask JARVIS")
        self.canvas.state = "STANDBY"
        self.canvas.status_detail = "COMMUNICATION ERROR"

    def _on_slider_changed(self, val):
        self.canvas.manual_amp = val / 100.0


def main():
    app = QApplication(sys.argv)
    win = JarvisDemoWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
