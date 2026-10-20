from __future__ import annotations

import json
import math
import os
import platform
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

if platform.system() == "Windows":
    _WIN_HIDE: dict = {"creationflags": subprocess.CREATE_NO_WINDOW}
else:
    _WIN_HIDE: dict = {}

# Qt's video backend prints the ffmpeg stream banner — codec, bitrate, the
# whole signed googlevideo URL — to the console for every stream it opens. That
# is two screenfuls per video, it looks like an error to anyone reading the log,
# and it puts a URL carrying the viewer's IP address into a terminal people
# paste into bug reports. Silenced here, before Qt initialises its logging.
# An explicit setting from the user is left alone.
os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.*=false")

from PyQt6.QtCore import (
    QEasingCurve, QLineF, QMimeData, QObject, QParallelAnimationGroup, QPointF,
    QPoint, QPropertyAnimation, QRect, QRectF, QSize, QSizeF, Qt, QTimer,
    QUrl, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QConicalGradient, QDragEnterEvent, QDropEvent, QFont,
    QFontDatabase, QIcon, QKeySequence, QLinearGradient, QPainter, QPainterPath,
    QPen, QPixmap, QPolygonF, QRadialGradient, QShortcut,
)
# Video playback for the HUD. Part of PyQt6, so it costs no new dependency —
# but the multimedia plugins are a separate piece of the Qt install and can be
# absent on a stripped-down system, so a failure here disables one feature
# rather than stopping JARVIS from starting.
try:
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem
    HAVE_VIDEO = True
except Exception as _e:            # noqa: BLE001 - reported, never fatal
    QAudioOutput = QMediaPlayer = QGraphicsVideoItem = None
    HAVE_VIDEO = False
    print(f"[Video] playback unavailable ({_e}) — the HUD will not show video.")

from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QGraphicsScene, QGraphicsView, QDialog, QRadioButton, QButtonGroup,
    QStackedWidget, QTextEdit, QVBoxLayout, QWidget, QProgressBar,
)

try:
    from core.avatar import HoloAvatar
except Exception:      # pragma: no cover — HUD must never die over cosmetics
    HoloAvatar = None

try:
    from core.gantry_viewer import GantryTurntableWidget
except Exception as _e:
    GantryTurntableWidget = None
    print(f"[GantryViewer] Import warning: {_e}")

import traceback

def _qt_excepthook(exctype, value, tb):
    if issubclass(exctype, (KeyboardInterrupt, SystemExit)):
        sys.__excepthook__(exctype, value, tb)
        return
    print("[UI Exception Caught]", file=sys.stderr)
    traceback.print_exception(exctype, value, tb, file=sys.stderr)

sys.excepthook = _qt_excepthook


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR   = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"


def _read_full_config() -> dict:
    """Read api_keys.json config dict. Returns {} on any error."""
    try:
        return json.loads(API_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


# Single source of truth for the release name — the window title, the header
# badge and the readme must never disagree again.
APP_VERSION  = "MARK LV"
APP_PROTOCOL = APP_VERSION.split()[-1]

_DEFAULT_W, _DEFAULT_H = 1140, 750
_MIN_W,     _MIN_H     = 860, 580
_LEFT_W  = 148
_RIGHT_W = 340

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


class C:
    BG        = "#00060a"
    PANEL     = "#010d14"
    PANEL2    = "#010f18"
    BORDER    = "#0d3347"
    BORDER_B  = "#1a5c7a"
    BORDER_A  = "#0f4060"
    PRI       = "#00d4ff"
    PRI_DIM   = "#007a99"
    PRI_GHO   = "#001f2e"
    ACC       = "#ff6b00"
    ACC2      = "#ffcc00"
    GREEN     = "#00ff88"
    GREEN_D   = "#00aa55"
    RED       = "#ff3355"
    MUTED_C   = "#ff3366"
    TEXT      = "#8ffcff"
    TEXT_DIM  = "#3a8a9a"
    TEXT_MED  = "#5ab8cc"
    WHITE     = "#d8f8ff"
    DARK      = "#000d14"
    BAR_BG    = "#011520"


# Keys tied to the accent colour — status colours (ACC, GREEN, RED…) stay fixed
_HUE_LINKED = (
    "BG", "PANEL", "PANEL2", "BORDER", "BORDER_B", "BORDER_A",
    "PRI", "PRI_DIM", "PRI_GHO", "TEXT", "TEXT_DIM", "TEXT_MED",
    "WHITE", "DARK", "BAR_BG",
)
_PALETTE_DEFAULTS: dict[str, str] = {k: getattr(C, k) for k in _HUE_LINKED}

DEFAULT_UI_COLOR = _PALETTE_DEFAULTS["PRI"]


def apply_ui_accent(accent_hex: str) -> bool:
    """
    Re-derives the whole teal-family palette from the chosen accent colour
    (hue shift — brightness/saturation ratios are preserved, design stays intact).
    Painted elements (HUD, waveform, metrics) pick up the new colour on the next
    frame; stylesheet-based panels pick it up when they are rebuilt.
    """
    import colorsys

    accent_hex = (accent_hex or "").strip().lower()
    if not (accent_hex.startswith("#") and len(accent_hex) == 7):
        return False
    try:
        int(accent_hex[1:], 16)
    except ValueError:
        return False

    def _hsv(h: str) -> tuple[float, float, float]:
        r = int(h[1:3], 16) / 255
        g = int(h[3:5], 16) / 255
        b = int(h[5:7], 16) / 255
        return colorsys.rgb_to_hsv(r, g, b)

    base_h            = _hsv(_PALETTE_DEFAULTS["PRI"])[0]
    acc_h, acc_s, _av = _hsv(accent_hex)
    dh   = acc_h - base_h
    grey = acc_s < 0.08   # near-grey accent → the whole theme is desaturated

    for key, hex0 in _PALETTE_DEFAULTS.items():
        h, s, v = _hsv(hex0)
        if grey:
            s *= 0.15
        r, g, b = colorsys.hsv_to_rgb((h + dh) % 1.0, s, v)
        setattr(C, key, "#{:02x}{:02x}{:02x}".format(
            int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5)))
    return True


def current_palette() -> dict[str, str]:
    """A snapshot of the accent-linked colours currently on class C."""
    return {k: getattr(C, k) for k in _HUE_LINKED}


def retheme_all_widgets(old: dict[str, str], new: dict[str, str]) -> None:
    """
    LIVE full theme change. Replaces the old palette colours with the new ones
    in EVERY widget's stylesheet across the app and repaints them. This way the
    colour change applies INSTANTLY across the whole interface — panels, buttons,
    borders included — not just the painted elements. No restart needed.
    """
    mapping = {old[k].lower(): new[k].lower()
               for k in old if old[k].lower() != new.get(k, old[k]).lower()}
    if not mapping:
        return
    app = QApplication.instance()
    if app is None:
        return
    for w in app.allWidgets():
        try:
            ss = w.styleSheet()
            if ss:
                s2 = ss
                for o, n in mapping.items():
                    if o in s2:
                        s2 = s2.replace(o, n)
                if s2 != ss:
                    w.setStyleSheet(s2)
            w.update()
        except Exception:
            pass


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h); c.setAlpha(a); return c


# ── Windows GPU via NVML DLL (no subprocess, no console window) ──────────────
_nvml_lib: object = None   # cached ctypes DLL
_nvml_ok:  object = None   # None=untested, True=works, False=unavailable


def _nvml_gpu_windows() -> float:
    """Return NVIDIA GPU utilisation % using nvml.dll directly — zero subprocess."""
    global _nvml_lib, _nvml_ok
    if _nvml_ok is False:
        return -1.0
    try:
        import ctypes

        class _Util(ctypes.Structure):
            _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]

        if _nvml_lib is None:
            for dll_name in ("nvml", r"C:\Windows\System32\nvml.dll"):
                try:
                    lib = ctypes.WinDLL(dll_name)
                    lib.nvmlInit_v2()
                    _nvml_lib = lib
                    break
                except Exception:
                    continue

        if _nvml_lib is None:
            import pynvml  # type: ignore
            pynvml.nvmlInit()
            h = pynvml.nvmlDeviceGetHandleByIndex(0)
            _nvml_ok = True
            return float(pynvml.nvmlDeviceGetUtilizationRates(h).gpu)

        dev = ctypes.c_void_p()
        _nvml_lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(dev))
        util = _Util()
        _nvml_lib.nvmlDeviceGetUtilizationRates(dev, ctypes.byref(util))
        _nvml_ok = True
        return float(util.gpu)
    except Exception:
        _nvml_ok = False
        return -1.0


class _SysMetrics:
    def __init__(self):
        self.cpu  = 0.0
        self.mem  = 0.0
        self.net  = 0.0   
        self.gpu  = -1.0  
        self.tmp  = -1.0  
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()
        self._running = True
        # Probe caches — GPU (NVML) and temperature (WMI) are the expensive
        # queries; initialise their handles once and reuse them instead of
        # rebuilding a connection on every poll.
        self._slow_tick = 0            # gpu/temp refreshed every 3rd cycle
        self._pynvml    = None         # cached pynvml module + device handle
        self._pynvml_h  = None
        self._pynvml_ok = None         # None=untested, False=unavailable here
        self._nv_unix   = None         # cached (lib, dev) for Linux/macOS NVML
        self._wmi_conn  = None         # cached WMI connection (creating one is slow)
        self._running = False
        # Background polling thread disabled: sys monitor removed from UI

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(2.0)

    def _update(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent

        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = now - self._last_net_t
        if dt > 0:
            sent = (nc.bytes_sent - self._last_net.bytes_sent) / dt
            recv = (nc.bytes_recv - self._last_net.bytes_recv) / dt
            net  = (sent + recv) / (1024 * 1024)
        else:
            net = 0.0
        self._last_net   = nc
        self._last_net_t = now

        # GPU and temperature change slowly and are the most expensive probes
        # (NVML / WMI) — refresh them every 3rd cycle (~6 s) instead of every
        # cycle, reusing the previous reading in between.
        self._slow_tick = (self._slow_tick + 1) % 3
        if self._slow_tick == 1:
            gpu = self._get_gpu()
            tmp = self._get_temp()
        else:
            gpu = self.gpu
            tmp = self.tmp

        with self._lock:
            self.cpu = cpu
            self.mem = mem
            self.net = net
            self.gpu = gpu
            self.tmp = tmp

    def _get_gpu(self) -> float:
        # pynvml — subprocess-free; initialise once and reuse the handle.
        # Re-initialising NVML on every poll is slow, so cache it and stop
        # retrying pynvml entirely once it proves unavailable here.
        if self._pynvml_ok is not False:
            try:
                if self._pynvml_h is None:
                    import pynvml  # type: ignore
                    pynvml.nvmlInit()
                    self._pynvml    = pynvml
                    self._pynvml_h  = pynvml.nvmlDeviceGetHandleByIndex(0)
                    self._pynvml_ok = True
                return float(self._pynvml.nvmlDeviceGetUtilizationRates(self._pynvml_h).gpu)
            except Exception:
                self._pynvml_ok = False

        # Windows: nvml.dll via ctypes (already cached in _nvml_gpu_windows)
        if _OS == "Windows":
            return _nvml_gpu_windows()

        # Linux / macOS: libnvidia-ml shared lib via ctypes — init once, reuse
        try:
            import ctypes

            class _Util(ctypes.Structure):
                _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]

            if self._nv_unix is None:
                _lib = "libnvidia-ml.so.1" if _OS == "Linux" else "libnvidia-ml.dylib"
                nv = ctypes.CDLL(_lib)
                nv.nvmlInit_v2()
                dev = ctypes.c_void_p()
                nv.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(dev))
                self._nv_unix = (nv, dev)

            nv, dev = self._nv_unix
            u = _Util()
            nv.nvmlDeviceGetUtilizationRates(dev, ctypes.byref(u))
            return float(u.gpu)
        except Exception:
            pass

        return -1.0   # N/A — zero subprocess on all platforms

    def _get_temp(self) -> float:
        # psutil — works on Linux; occasionally Windows with driver support
        try:
            temps = psutil.sensors_temperatures()
            for name in ["coretemp", "k10temp", "cpu_thermal", "acpitz",
                         "cpu-thermal", "zenpower", "it8688"]:
                if name in temps and temps[name]:
                    return temps[name][0].current
            for entries in temps.values():
                if entries:
                    return entries[0].current
        except Exception:
            pass

        # Windows: wmi module (pure Python COM, zero subprocess). Reuse a single
        # connection — building a fresh wmi.WMI() on every poll spins up a COM
        # connection each time and is very slow. Give up after one failure.
        if _OS == "Windows" and self._wmi_ok is not False:
            try:
                if self._wmi_conn is None:
                    import wmi  # type: ignore
                    self._wmi_conn = wmi.WMI(namespace="root/wmi")
                tz = self._wmi_conn.MSAcpi_ThermalZoneTemperature()
                if tz:
                    return (tz[0].CurrentTemperature / 10.0) - 273.15
            except Exception:
                self._wmi_ok   = False
                self._wmi_conn = None

        return -1.0   # N/A — zero subprocess on all platforms

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cpu": self.cpu,
                "mem": self.mem,
                "net": self.net,
                "gpu": self.gpu,
                "tmp": self.tmp,
            }


_metrics = _SysMetrics()

class TacticalHudCanvas(QWidget):
    def __init__(self, face_path: str = "", assistant_name: str = "J.A.R.V.I.S", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(220, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted    = False
        self.speaking = False
        self.state    = "INITIALISING"
        self._assistant_name = assistant_name
        try:
            from memory.config_manager import get_user_name
            self._user_name = get_user_name() or "DIVYANSHU VERMA"
        except Exception:
            self._user_name = "DIVYANSHU VERMA"

        # The holographic head that fills the HUD. If it could not be imported
        # we fall back to the old glowing core so the panel is never empty.
        self._avatar = None
        if HoloAvatar is not None:
            try:
                self._avatar = HoloAvatar()
            except Exception:
                self._avatar = None

        # Which centrepiece to draw. Read once here and changed live by the
        # settings toggle; the avatar object is kept either way so switching
        # back is instant and costs no reload.
        try:
            from memory.config_manager import get_hud_style
            self.hud_style = get_hud_style()
        except Exception:
            self.hud_style = "face"
        self._core_phase = 0.0

        self._tick       = 0
        self._scale      = 1.0
        self._tgt_scale  = 1.0
        self._halo       = 55.0
        self._tgt_halo   = 55.0
        self._last_t     = time.time()
        self._step_t     = time.time()
        self._blink      = True
        self._blink_tick = 0

        # Rescaled-face cache: the smooth rescale is expensive, so we keep the
        # last result and only rebuild it when the (quantised) size changes.

        # Static grid-dot layer, pre-rendered once per size/theme into a pixmap
        # so paintEvent blits it in one call instead of thousands of drawPoint()s.
        self._grid_cache: QPixmap | None = None
        self._grid_key = None
        # Repaint throttle counter (idle frames drop to ~20 Hz — see _step()).
        self._paint_tick = 0

        # Live audio reactivity: _live_amp is written from the audio threads
        # (0.0–1.0), _amp_disp is the smoothed value the paint code reads.
        self._live_amp  = 0.0
        self._amp_disp  = 0.0
        # (frames, start_time, hop) posted by the playback thread — see
        # push_visemes(). None means "no schedule; use the plain level".
        self._visemes = None
        self._vis_i = None        # first schedule frame not yet handed to the mouth
        self._base_scale = 1.0    # slow "breathing" target; amp is added per-frame
        self._base_halo  = 55.0

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(16)

    def glance(self, dx: float, dy: float, hold: float = 1.1) -> None:
        """Ask the avatar to look somewhere for a moment (see HoloAvatar.glance)."""
        try:
            if self._avatar is not None:
                self._avatar.glance(dx, dy, hold)
        except Exception:
            pass

    def push_visemes(self, frames, hop: float, at: float) -> None:
        """Thread-safe: hand over a schedule of (level, openness, width) frames.

        The playback thread writes up to 200 ms of audio in one go, so a single
        averaged level would only move the mouth five times a second — enough to
        flap, nowhere near enough to articulate. It instead posts the whole
        slice's worth of 20 ms frames here and `_step()` plays them out against
        the wall clock, in step with the audio going to the speakers.

        `at` is the wall-clock time this batch will *begin to sound*, which the
        caller tracks as a playback cursor. It is not the time of the call, and
        the difference is the whole point: `stream.write` returns once the buffer
        accepts the samples, so consecutive batches are handed over far faster
        than they play. Anchoring each one to "now" made every batch start while
        its predecessor was still sounding, so each schedule replaced the last
        after a couple of frames and the mouth only ever played the opening
        instant of every 200 ms — the reason it did not match the words.

        Successive batches are therefore *appended* into one continuous
        timeline, not swapped in. A paragraph is one schedule; the mouth stops
        falling into a gap at every chunk boundary and having to climb back out.
        """
        try:
            if not frames:
                return
            hop = max(1e-3, float(hop))
            at = float(at)
            new = list(frames)
            cur = self._visemes
            if cur is not None:
                old, t0, ohop = cur
                if abs(ohop - hop) < 1e-6:
                    # Where in the existing timeline does this batch land?
                    i = int(round((at - t0) / hop))
                    if 0 <= i <= len(old) + 1:
                        # Continues (or slightly overlaps) what is already
                        # queued: extend rather than restart. Drop whatever has
                        # already been played so the list cannot grow without
                        # bound over a long reply.
                        merged = old[:i] + new
                        played = int((time.time() - t0) / hop) - 2
                        if played > 60:
                            merged = merged[played:]
                            t0 += played * hop
                            if self._vis_i is not None:
                                self._vis_i = max(0, self._vis_i - played)
                        self._visemes = (merged, t0, hop)
                        return
            self._visemes = (new, at, hop)
            self._vis_i = None
        except Exception:
            pass

    def set_audio_level(self, level: float) -> None:
        """Thread-safe entry point for the audio threads. Stores the louder of
        the incoming level and the current value so brief gaps between chunks
        don't make the waveform stutter; _step() decays it back down."""
        try:
            lv = float(level)
        except (TypeError, ValueError):
            return
        if lv < 0.0:
            lv = 0.0
        elif lv > 1.0:
            lv = 1.0
        if lv > self._live_amp:
            self._live_amp = lv

    def _make_grid(self, W: int, H: int) -> QPixmap:
        """Pre-render the static grid-dot background into a transparent pixmap so
        paintEvent can blit it once per frame instead of running a nested
        drawPoint() loop across the whole widget every 16 ms."""
        pm = QPixmap(max(1, W), max(1, H))
        pm.fill(Qt.GlobalColor.transparent)
        gp = QPainter(pm)
        gp.setPen(QPen(qcol(C.PRI_GHO), 1))
        for x in range(0, W, 48):
            for y in range(0, H, 48):
                gp.drawPoint(x, y)
        gp.end()
        return pm

    def _step(self):
        try:
            self._tick += 1
            now = time.time()

            # ── Live audio reactivity ────────────────────────────────────────────
            # A viseme schedule, if one is playing, gives both the level and the
            # mouth shape for this exact instant; otherwise fall back to the peak
            # level the audio threads pushed in.
            v_open = v_wide = v_level = None
            v_seq = None
            sched = self._visemes
            if sched is not None:
                frames, t0, hop = sched
                i = int((now - t0) / hop)
                if 0 <= i < len(frames):
                    # Hand over *every* frame since the last tick, not just the one
                    # under the cursor. This timer runs at 60 Hz but the paint is
                    # throttled and the machine may be busy, so a tick can span two
                    # or three 20 ms frames — and a consonant closure is only two
                    # frames long. Sampling one and discarding the rest is how the
                    # closures between words went missing.
                    j = self._vis_i if self._vis_i is not None else i
                    v_seq = frames[max(0, j):i + 1]
                    self._vis_i = max(j, i + 1)
                    v_level, v_open, v_wide = frames[i]
                    if v_seq:
                        peak = max(f[0] for f in v_seq)
                        if peak > self._live_amp:
                            self._live_amp = peak
                elif i >= len(frames):
                    self._visemes = None        # schedule spent
                    self._vis_i = None

            # Audio threads push peaks into _live_amp; decay it toward silence so
            # gaps between chunks fade out instead of freezing, then smooth it.
            self._live_amp *= 0.86
            self._amp_disp += (self._live_amp - self._amp_disp) * 0.45
            amp = self._amp_disp

            # The avatar animates off the very same smoothed level the waveform
            # uses — one audio source, so the mouth can never drift out of sync.
            dt = now - self._step_t
            self._step_t = now
            # Integrated, not derived from absolute time: multiplying wall-clock by
            # a rate that changes with state jumps the rings the instant JARVIS
            # starts talking. Same lesson the head's sway taught.
            self._core_phase += min(0.10, max(0.0, dt))

            if self._avatar is not None and self.hud_style == "face":
                self._avatar.step(dt, amp, speaking=self.speaking,
                                  muted=self.muted, state=self.state,
                                  v_open=v_open, v_wide=v_wide or 0.0,
                                  v_level=v_level, v_seq=v_seq,
                                  v_hop=(sched[2] if sched is not None else 0.02))
            else:
                # Fallback core: slow "breathing" base target, lifted by the level.
                if now - self._last_t > (0.12 if self.speaking else 0.5):
                    if self.speaking:
                        self._base_scale = 1.03
                        self._base_halo  = 122.0
                    elif self.muted:
                        self._base_scale = random.uniform(0.998, 1.002)
                        self._base_halo  = random.uniform(15, 28)
                    else:
                        self._base_scale = random.uniform(1.001, 1.008)
                        self._base_halo  = random.uniform(48, 68)
                    self._last_t = now

                if self.muted:
                    self._tgt_scale, self._tgt_halo = self._base_scale, self._base_halo
                elif self.speaking:
                    self._tgt_scale = self._base_scale + amp * 0.13
                    self._tgt_halo  = self._base_halo  + amp * 95.0
                else:
                    self._tgt_scale = self._base_scale + amp * 0.06
                    self._tgt_halo  = self._base_halo  + amp * 75.0

                sp = 0.38 if self.speaking else (0.30 if amp > 0.02 else 0.15)
                self._scale += (self._tgt_scale - self._scale) * sp
                self._halo  += (self._tgt_halo  - self._halo)  * sp

            self._blink_tick += 1
            if self._blink_tick >= 38:
                self._blink = not self._blink
                self._blink_tick = 0
                _blinked = True
            else:
                _blinked = False

            # Repaint throttling — advancing the animation state above is cheap at
            # 60 Hz, but the paint is heavy. Active (speaking, audio, thinking) runs
            # at ~30 Hz, which is the frame rate animation has used for talking
            # characters forever and is indistinguishable here; idle drops to ~20 Hz
            # so a sleeping HUD stops pinning a CPU core. The visuals stay smooth
            # either way because the animation state keeps stepping at 60 Hz.
            self._paint_tick = (self._paint_tick + 1) % 6
            active = (self.speaking or amp > 0.02
                      or self.state in ("THINKING", "PROCESSING"))
            if _blinked or (self._paint_tick % 2 == 0 if active
                            else self._paint_tick % 3 == 0):
                # Nothing is on screen when the window is hidden or minimised, so
                # rendering the avatar into it is pure waste — and this app is meant
                # to sit running all day. The animation state above keeps stepping,
                # so it picks up mid-motion instead of snapping when you come back.
                if self._on_screen():
                    self.update()
        except Exception:
            pass

    def _on_screen(self) -> bool:
        """True only when this canvas can actually be seen by the user."""
        try:
            if not self.isVisible():
                return False
            win = self.window()
            return not (win.isMinimized() or win.isHidden())
        except Exception:
            return True      # never let a visibility check stop the HUD drawing

    # ── reactor core ─────────────────────────────────────────────────────────
    # The centrepiece for anyone who did not want a face looking back at them.
    # Built from the same budget as the head — software QPainter, no GPU — and
# ── Gold & Cyan Vibranium Arc Reactor Core ───────────────────────────────
    # Ultra-high-fidelity cinematic Arc Reactor core matching the reference design:
    # Outer dark titanium armor chassis with micro-grooves and light-pipes,
    # top arched gold header plate with curved text, corner HUD weather/telemetry,
    # heavy gold/amber annular power ring with radial graduation ticks,
    # 4 cardinal clamps with glowing cyan pins and acoustic piston travel,
    # horizontal anamorphic lens flare with dual diamond glints,
    # 20-block cyan stator turbine ring with outer/inner beveled retaining rims,
    # inner mechanical collar with calibration ticks,
    # inner cyan segmented diffuser ring with counter-rotating aperture wedges,
    # radiant central cyan glow with target crosshairs and rings,
    # 3 mechanical struts anchoring the central inverted vibranium triangle,
    # 3D chrome drop shadow, cyan neon trace, corner vertex rivets,
    # procedural electric lightning discharges, central white-hot singularity,
    # and bottom creator credit with futuristic tech bracket wings.

    def _core_colours(self):
        if self.muted:
            return qcol(C.MUTED_C), QColor("#661122"), qcol(C.WHITE)
        if self.speaking:
            return qcol(C.PRI), QColor("#ffaa00"), qcol(C.WHITE)
        if self.state in ("THINKING", "PROCESSING"):
            return QColor("#ffcc00"), QColor("#ff9900"), qcol(C.WHITE)
        if self.state == "LISTENING":
            return qcol(C.GREEN), QColor("#ffaa00"), qcol(C.WHITE)
        return qcol(C.PRI), QColor("#ffaa00"), qcol(C.WHITE)

    def _paint_core(self, p: QPainter, cx: float, cy: float, r: float,
                    W: float = 0.0, H: float = 0.0):
        """Draw the Gold & Cyan Vibranium Arc Reactor Core at (cx, cy) with radius r across (W x H)."""
        amp = self._amp_disp
        phase = self._core_phase

        # Base space background & metallic tones
        c_space = qcol(C.BG)
        c_metal_deep = QColor("#08101a")
        c_metal_dark = QColor("#0f1b29")
        c_metal_mid  = QColor("#1c2c3e")
        c_metal_light = QColor("#2b425b")
        c_metal_glint = QColor("#54789e")
        c_metal_highlight = QColor("#8ab2d9")

        # Dynamic arc glow palettes
        c_cyan_bloom  = qcol(C.PRI)
        c_cyan_bright = QColor("#3cf2ff")
        c_cyan_mid    = QColor("#00a2e8")
        c_cyan_deep   = QColor("#005b8c")
        c_cyan_dim    = QColor("#002842")

        c_gold_flare  = QColor("#fff0b3")
        c_gold_bright = QColor("#ffd24d")
        c_gold_mid    = QColor("#ffaa00")
        c_gold_deep   = QColor("#b37400")
        c_gold_dim    = QColor("#4d3000")

        c_white = QColor("#ffffff")

        # State overrides
        if self.muted:
            c_cyan_bloom  = qcol(C.MUTED_C)
            c_cyan_bright = QColor("#ff6680")
            c_cyan_mid    = QColor("#a61730")
            c_cyan_deep   = QColor("#660f1f")
            c_gold_mid    = QColor("#661122")
            c_gold_bright = QColor("#992233")
            c_gold_flare  = QColor("#cc3344")
        elif self.state in ("THINKING", "PROCESSING"):
            c_cyan_bloom  = QColor("#ffcc00")
            c_cyan_bright = QColor("#ffe066")
            c_cyan_mid    = QColor("#ff9900")
            c_cyan_deep   = QColor("#995c00")
        elif self.state == "LISTENING":
            c_cyan_bloom  = qcol(C.GREEN)
            c_cyan_bright = QColor("#5cffb8")
            c_cyan_mid    = QColor("#00cc7a")

        def rgba(c: QColor, a: float) -> QColor:
            return QColor(c.red(), c.green(), c.blue(), int(max(0.0, min(1.0, a)) * 255))

        def draw_beveled_ring(r_out: float, r_in: float, col_base: QColor, col_hl: QColor, col_sh: QColor):
            p.setBrush(QBrush(col_base))
            p.setPen(Qt.PenStyle.NoPen)
            path = QPainterPath()
            path.addEllipse(QPointF(cx, cy), r_out, r_out)
            path.addEllipse(QPointF(cx, cy), r_in, r_in)
            p.drawPath(path)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(col_hl, 1.2))
            p.drawArc(QRectF(cx - r_out, cy - r_out, r_out * 2, r_out * 2), 35 * 16, 110 * 16)
            p.setPen(QPen(col_sh, 1.2))
            p.drawArc(QRectF(cx - r_out, cy - r_out, r_out * 2, r_out * 2), 215 * 16, 110 * 16)
            p.setPen(QPen(col_sh, 1.0))
            p.drawArc(QRectF(cx - r_in, cy - r_in, r_in * 2, r_in * 2), 35 * 16, 110 * 16)
            p.setPen(QPen(col_hl, 1.0))
            p.drawArc(QRectF(cx - r_in, cy - r_in, r_in * 2, r_in * 2), 215 * 16, 110 * 16)

        # ── 1. Deep Space Ambient Background & Particles ──────────────────────
        g_ambient = QRadialGradient(cx, cy, r * 1.35)
        g_ambient.setColorAt(0.0, rgba(c_cyan_dim, 0.45 + 0.20 * amp))
        g_ambient.setColorAt(0.4, rgba(QColor("#051220"), 0.35))
        g_ambient.setColorAt(0.8, rgba(c_space, 0.85))
        g_ambient.setColorAt(1.0, rgba(c_space, 1.0))
        p.setBrush(QBrush(g_ambient))
        p.setPen(Qt.PenStyle.NoPen)
        if W > 0 and H > 0:
            p.drawRect(QRectF(0, 0, W, H))
        else:
            p.drawEllipse(QPointF(cx, cy), r * 1.35, r * 1.35)

        # Floating starry embers
        for i in range(48):
            ang = (i * 37.17 + phase * 0.12) % (2 * math.pi)
            dist = r * (0.18 + 0.86 * ((i * 19.33) % 1.0))
            px = cx + dist * math.cos(ang)
            py = cy + dist * math.sin(ang)
            pt_size = 0.8 + 1.8 * ((i * 7.1) % 1.0)
            pt_col = c_cyan_bloom if (i % 3 != 0) else c_gold_bright
            p.setBrush(QBrush(rgba(pt_col, 0.20 + 0.50 * math.sin(phase + i))))
            p.drawEllipse(QPointF(px, py), pt_size, pt_size)

        # ── 2. Corner HUD Elements ────────────────────────────────────────────
        # Top-right weather / telemetry icon
        p.save()
        tr_x, tr_y = cx + r * 0.84, cy - r * 0.89
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(rgba(c_cyan_mid, 0.55), 1.0))
        p.drawPolyline([
            QPointF(tr_x - 18, tr_y - 20),
            QPointF(tr_x + 24, tr_y - 20),
            QPointF(tr_x + 24, tr_y + 14)
        ])
        p.setPen(QPen(rgba(c_cyan_bloom, 0.90), 1.4))
        p.drawEllipse(QPointF(tr_x + 8, tr_y - 10), 3.5, 3.5)
        cloud_path = QPainterPath()
        cloud_path.moveTo(tr_x - 10, tr_y)
        cloud_path.arcTo(QRectF(tr_x - 14, tr_y - 8, 12, 10), 180, 160)
        cloud_path.arcTo(QRectF(tr_x - 6, tr_y - 14, 16, 14), 140, 180)
        cloud_path.arcTo(QRectF(tr_x + 6, tr_y - 8, 10, 10), 270, 180)
        cloud_path.lineTo(tr_x - 10, tr_y + 2)
        p.drawPath(cloud_path)
        p.restore()

        # Top-left circuit trace
        p.save()
        tl_x, tl_y = cx - r * 0.86, cy - r * 0.89
        p.setPen(QPen(rgba(c_cyan_mid, 0.50), 1.0))
        p.drawLine(QLineF(tl_x - 24, tl_y - 15, tl_x + 12, tl_y - 15))
        p.drawLine(QLineF(tl_x + 12, tl_y - 15, tl_x + 24, tl_y - 3))
        p.restore()

        # ── 3. Outer Dark Titanium Armor Chassis (r * 0.86 to r * 1.03) ───────
        draw_beveled_ring(r * 1.03, r * 0.94, c_metal_deep, c_metal_light, c_metal_deep)
        draw_beveled_ring(r * 0.94, r * 0.85, c_metal_dark, c_metal_glint, c_metal_deep)

        # Micro graduation hash marks on the outer rim (120 divisions)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(120):
            deg = i * 3.0
            if 54 <= deg <= 126 or 236 <= deg <= 304:
                continue
            rad = math.radians(deg)
            r1 = r * 0.945
            r2 = r * (0.960 if (i % 5 == 0) else 0.950)
            pen_col = rgba(c_cyan_bright if (i % 10 == 0) else c_metal_glint, 0.65)
            p.setPen(QPen(pen_col, 1.0))
            p.drawLine(QLineF(cx + r1 * math.cos(rad), cy + r1 * math.sin(rad),
                             cx + r2 * math.cos(rad), cy + r2 * math.sin(rad)))

        # Outer curved light-pipe arc slots
        for arc_deg in (30, 150, 210, 330):
            p.setPen(QPen(rgba(c_cyan_bloom, 0.85 + 0.15 * amp), 2.5))
            p.drawArc(QRectF(cx - r * 0.985, cy - r * 0.985, r * 1.97, r * 1.97),
                      int((arc_deg - 18) * 16), int(36 * 16))
            p.setPen(QPen(rgba(c_white, 0.90), 1.2))
            p.drawArc(QRectF(cx - r * 0.985, cy - r * 0.985, r * 1.97, r * 1.97),
                      int((arc_deg - 8) * 16), int(16 * 16))

        # Outer corner diagonal tabs & blue indicator LEDs
        for diag_deg in (45, 135, 225, 315):
            p.save()
            p.translate(cx, cy)
            p.rotate(diag_deg)
            p.setBrush(QBrush(c_gold_mid))
            p.setPen(QPen(c_gold_bright, 1.0))
            p.drawRect(QRectF(r * 0.94, -4, r * 0.045, 8))
            p.setBrush(QBrush(c_cyan_bloom))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(r * 0.995, 0), 1.8, 1.8)
            p.restore()

        # ── 4. Curved Arched Gold Header: J . A . R . V . I . S . ─────────────
        p.save()
        arc_span = 78.0
        arc_start = -90.0 - arc_span / 2.0
        r_text_track = r * 0.925

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(c_gold_bright, 2.0))
        p.drawArc(QRectF(cx - r * 0.98, cy - r * 0.98, r * 1.96, r * 1.96),
                  int((-arc_start - arc_span) * 16), int(arc_span * 16))
        p.drawArc(QRectF(cx - r * 0.87, cy - r * 0.87, r * 1.74, r * 1.74),
                  int((-arc_start - arc_span) * 16), int(arc_span * 16))

        for notch_ang in (arc_start, arc_start + arc_span):
            n_rad = math.radians(notch_ang)
            p.drawLine(QLineF(cx + r * 0.87 * math.cos(n_rad), cy + r * 0.87 * math.sin(n_rad),
                             cx + r * 0.98 * math.cos(n_rad), cy + r * 0.98 * math.sin(n_rad)))

        # Process assistant name characters
        raw_name = (self._assistant_name or "JARVIS").strip()
        if "." in raw_name:
            h_chars = list(raw_name)
        else:
            h_chars = [ch for char in raw_name for ch in (char, ".")]

        num_chars = len(h_chars)
        char_ang_step = (arc_span - 12.0) / max(1, num_chars - 1)

        font_jarvis = QFont("Helvetica Neue", max(9, int(r * 0.043)), QFont.Weight.Bold)
        p.setFont(font_jarvis)

        for c_i, ch in enumerate(h_chars):
            ch_deg = arc_start + 6.0 + c_i * char_ang_step
            ch_rad = math.radians(ch_deg)

            ch_x = cx + r_text_track * math.cos(ch_rad)
            ch_y = cy + r_text_track * math.sin(ch_rad)

            p.save()
            p.translate(ch_x, ch_y)
            p.rotate(ch_deg + 90.0)

            p.setPen(QPen(rgba(c_gold_deep, 0.70), 1.0))
            p.drawText(QRectF(-14, -14, 28, 28), Qt.AlignmentFlag.AlignCenter, ch)
            p.setPen(QPen(c_gold_bright, 1.0))
            p.drawText(QRectF(-14, -14, 28, 28), Qt.AlignmentFlag.AlignCenter, ch)
            p.restore()

        p.restore()

        # ── 5. Heavy Gold / Amber Annular Power Ring (r * 0.69 to r * 0.85) ────
        r_gold_out = r * 0.845
        r_gold_in  = r * 0.695

        draw_beveled_ring(r_gold_out, r_gold_in, c_metal_dark, c_metal_glint, c_metal_deep)

        for s_i, s_start in enumerate((18, 108, 198, 288)):
            s_span = 54
            r_mid_gold = (r_gold_out + r_gold_in) / 2.0

            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(rgba(c_gold_deep, 0.45), 18.0))
            p.drawArc(QRectF(cx - r_mid_gold, cy - r_mid_gold, r_mid_gold * 2, r_mid_gold * 2),
                      int(s_start * 16), int(s_span * 16))

            p.setPen(QPen(rgba(c_gold_mid, 0.92 + 0.08 * math.sin(phase * 2.5 + s_i)), 9.0))
            p.drawArc(QRectF(cx - r_mid_gold, cy - r_mid_gold, r_mid_gold * 2, r_mid_gold * 2),
                      int((s_start + 2) * 16), int((s_span - 4) * 16))

            p.setPen(QPen(rgba(c_gold_flare, 0.95), 2.4))
            p.drawArc(QRectF(cx - r_mid_gold, cy - r_mid_gold, r_mid_gold * 2, r_mid_gold * 2),
                      int((s_start + 6) * 16), int((s_span - 12) * 16))

            for t_step in range(9):
                t_deg = s_start + 4 + t_step * 5.8
                t_rad = math.radians(t_deg)
                p.setPen(QPen(rgba(c_gold_bright, 0.70), 1.0))
                p.drawLine(QLineF(cx + r * 0.830 * math.cos(t_rad), cy + r * 0.830 * math.sin(t_rad),
                                 cx + r * 0.850 * math.cos(t_rad), cy + r * 0.850 * math.sin(t_rad)))

        # ── 6. Cardinal Clamps & Diagonal Sliders ─────────────────────────────
        for c_deg in (0, 90, 180, 270):
            p.save()
            p.translate(cx, cy)
            p.rotate(c_deg)

            piston_travel = (amp * 4.0) if self.speaking else 0.0

            p.setBrush(QBrush(c_metal_light))
            p.setPen(QPen(c_metal_highlight, 1.2))
            p.drawRoundedRect(QRectF(r * 0.65 - piston_travel, -11, r * 0.21, 22), 2.5, 2.5)

            p.setBrush(QBrush(c_metal_deep))
            p.setPen(QPen(c_metal_dark, 1.0))
            p.drawRect(QRectF(r * 0.68 - piston_travel, -6, r * 0.15, 12))

            g_pin = QLinearGradient(r * 0.69 - piston_travel, 0, r * 0.82 - piston_travel, 0)
            g_pin.setColorAt(0.0, rgba(c_cyan_bright, 0.4))
            g_pin.setColorAt(0.5, rgba(c_cyan_bright, 1.0))
            g_pin.setColorAt(1.0, rgba(c_white, 1.0))
            p.setBrush(QBrush(g_pin))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(r * 0.70 - piston_travel, -3.5, r * 0.11, 7), 2, 2)

            p.setBrush(QBrush(c_gold_mid))
            p.setPen(QPen(c_gold_bright, 1.2))
            prong = QPolygonF([
                QPointF(r * 0.65 - piston_travel, -8),
                QPointF(r * 0.62 - piston_travel, -4),
                QPointF(r * 0.62 - piston_travel, 4),
                QPointF(r * 0.65 - piston_travel, 8)
            ])
            p.drawPolygon(prong)

            p.setBrush(QBrush(c_white))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(r * 0.625 - piston_travel, 0), 1.2, 1.2)
            p.restore()

        for d_deg in (45, 135, 225, 315):
            p.save()
            p.translate(cx, cy)
            p.rotate(d_deg)
            p.setBrush(QBrush(c_metal_mid))
            p.setPen(QPen(c_metal_glint, 1.0))
            p.drawRect(QRectF(r * 0.70, -5.5, r * 0.13, 11))
            p.setBrush(QBrush(c_gold_mid))
            p.drawRect(QRectF(r * 0.70, -5.5, 3, 11))
            p.setBrush(QBrush(c_cyan_bloom))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(r * 0.77, 0), 2.2, 2.2)
            p.restore()

        # ── 7. Horizontal Anamorphic Lens Flare & Optical Glints ──────────────
        flare_len = r * 1.35
        flare_h = 10.0 + 10.0 * amp
        g_flare_left = QLinearGradient(cx - flare_len, cy, cx, cy)
        g_flare_left.setColorAt(0.0, rgba(c_gold_mid, 0.0))
        g_flare_left.setColorAt(0.45, rgba(c_gold_bright, 0.40 + 0.30 * amp))
        g_flare_left.setColorAt(0.85, rgba(c_cyan_bloom, 0.75 + 0.25 * amp))
        g_flare_left.setColorAt(1.0, rgba(c_white, 0.95))
        p.setBrush(QBrush(g_flare_left))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRectF(cx - flare_len, cy - flare_h/2, flare_len, flare_h))

        g_flare_right = QLinearGradient(cx, cy, cx + flare_len, cy)
        g_flare_right.setColorAt(0.0, rgba(c_white, 0.95))
        g_flare_right.setColorAt(0.15, rgba(c_cyan_bloom, 0.75 + 0.25 * amp))
        g_flare_right.setColorAt(0.55, rgba(c_gold_bright, 0.40 + 0.30 * amp))
        g_flare_right.setColorAt(1.0, rgba(c_gold_mid, 0.0))
        p.setBrush(QBrush(g_flare_right))
        p.drawRect(QRectF(cx, cy - flare_h/2, flare_len, flare_h))

        p.setPen(QPen(rgba(c_white, 0.95), 1.4))
        p.drawLine(QLineF(cx - flare_len * 0.9, cy, cx + flare_len * 0.9, cy))

        for glint_x in (cx - r * 0.770, cx + r * 0.770):
            g_glint = QRadialGradient(glint_x, cy, 22.0 + 12.0 * amp)
            g_glint.setColorAt(0.0, rgba(c_white, 1.0))
            g_glint.setColorAt(0.25, rgba(c_gold_flare, 0.90))
            g_glint.setColorAt(0.60, rgba(c_gold_mid, 0.45))
            g_glint.setColorAt(1.0, rgba(c_gold_deep, 0.0))
            p.setBrush(QBrush(g_glint))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(glint_x, cy), 22.0 + 12.0 * amp, 22.0 + 12.0 * amp)
            p.setPen(QPen(rgba(c_white, 0.85), 1.2))
            p.drawLine(QLineF(glint_x, cy - 14, glint_x, cy + 14))

        # ── 8. Cyan Segmented Turbine / Stator Ring (r * 0.48 to r * 0.635) ───
        r_turb_out = r * 0.635
        r_turb_in  = r * 0.495

        draw_beveled_ring(r_turb_out + 3, r_turb_out, c_metal_dark, c_metal_glint, c_metal_deep)
        draw_beveled_ring(r_turb_in, r_turb_in - 3, c_metal_dark, c_metal_glint, c_metal_deep)

        g_turb_cushion = QRadialGradient(cx, cy, (r_turb_out + r_turb_in) / 2.0)
        g_turb_cushion.setColorAt(0.0, rgba(c_cyan_dim, 0.2))
        g_turb_cushion.setColorAt(0.6, rgba(c_cyan_mid, 0.65 + 0.35 * amp))
        g_turb_cushion.setColorAt(1.0, rgba(c_cyan_bloom, 0.0))
        p.setBrush(QBrush(g_turb_cushion))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), r_turb_out + 5, r_turb_out + 5)

        num_blocks = 20
        block_step = 360.0 / num_blocks
        rot_offset = (phase * 6.0) if self.state not in ("THINKING", "PROCESSING") else (phase * 40.0)

        for b_i in range(num_blocks):
            b_ang_deg = (b_i * block_step + rot_offset) % 360.0
            b_span = block_step * 0.74

            chase_mult = 1.0
            if self.state in ("THINKING", "PROCESSING"):
                chase_dist = (b_i - (phase * 5.0) % num_blocks) % num_blocks
                chase_mult = 0.35 + 0.65 * math.exp(-chase_dist * 0.4)

            b_glow_a = (0.75 + 0.25 * math.sin(phase * 2.5 + b_i * 0.6)) * chase_mult
            b_glow_a = min(1.0, b_glow_a + amp * 0.3)

            path = QPainterPath()
            ang_rad1 = math.radians(b_ang_deg)
            ang_rad2 = math.radians(b_ang_deg + b_span)

            p1 = QPointF(cx + r_turb_in * math.cos(ang_rad1), cy + r_turb_in * math.sin(ang_rad1))
            p2 = QPointF(cx + r_turb_out * math.cos(ang_rad1), cy + r_turb_out * math.sin(ang_rad1))
            p3 = QPointF(cx + r_turb_out * math.cos(ang_rad2), cy + r_turb_out * math.sin(ang_rad2))
            p4 = QPointF(cx + r_turb_in * math.cos(ang_rad2), cy + r_turb_in * math.sin(ang_rad2))

            path.moveTo(p1)
            path.lineTo(p2)
            path.arcTo(QRectF(cx - r_turb_out, cy - r_turb_out, r_turb_out * 2, r_turb_out * 2),
                       -b_ang_deg, -b_span)
            path.lineTo(p4)
            path.arcTo(QRectF(cx - r_turb_in, cy - r_turb_in, r_turb_in * 2, r_turb_in * 2),
                       -(b_ang_deg + b_span), b_span)
            path.closeSubpath()

            g_block = QLinearGradient(p1, p2)
            g_block.setColorAt(0.0, rgba(c_cyan_bright, b_glow_a * 0.80))
            g_block.setColorAt(0.5, rgba(c_cyan_bloom, b_glow_a * 0.98))
            g_block.setColorAt(1.0, rgba(c_white, b_glow_a * 0.90))

            p.setBrush(QBrush(g_block))
            p.setPen(QPen(rgba(c_cyan_bright, b_glow_a), 1.0))
            p.drawPath(path)

            mid_r = (r_turb_in + r_turb_out) / 2.0
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(rgba(c_white, b_glow_a * 0.95), 1.8))
            p.drawArc(QRectF(cx - mid_r, cy - mid_r, mid_r * 2, mid_r * 2),
                      int(-(b_ang_deg + 2) * 16), int(-(b_span - 4) * 16))

        # ── 9. Inner Mechanical Collar & Calibrations (r * 0.36 to r * 0.48) ──
        draw_beveled_ring(r * 0.48, r * 0.38, c_metal_deep, c_metal_glint, c_metal_deep)

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(rgba(c_cyan_bloom, 0.70), 1.2))
        p.drawEllipse(QPointF(cx, cy), r * 0.44, r * 0.44)

        for t_i in range(36):
            t_rad = math.radians(t_i * 10 + phase * 3.0)
            p.setPen(QPen(rgba(c_cyan_bloom, 0.60), 1.0))
            p.drawLine(QLineF(cx + r * 0.435 * math.cos(t_rad), cy + r * 0.435 * math.sin(t_rad),
                             cx + r * 0.450 * math.cos(t_rad), cy + r * 0.450 * math.sin(t_rad)))

        # ── 10. Inner Cyan Segmented Diffuser Ring (Behind Triangle) ──────────
        r_in_turb_out = r * 0.37
        r_in_turb_in  = r * 0.28

        num_in_blocks = 16
        in_step = 360.0 / num_in_blocks
        for in_i in range(num_in_blocks):
            in_ang = (in_i * in_step - phase * 4.0) % 360.0
            in_span = in_step * 0.70

            path_in = QPainterPath()
            r1, r2 = math.radians(in_ang), math.radians(in_ang + in_span)
            ip1 = QPointF(cx + r_in_turb_in * math.cos(r1), cy + r_in_turb_in * math.sin(r1))
            ip2 = QPointF(cx + r_in_turb_out * math.cos(r1), cy + r_in_turb_out * math.sin(r1))
            ip3 = QPointF(cx + r_in_turb_out * math.cos(r2), cy + r_in_turb_out * math.sin(r2))
            ip4 = QPointF(cx + r_in_turb_in * math.cos(r2), cy + r_in_turb_in * math.sin(r2))

            path_in.moveTo(ip1)
            path_in.lineTo(ip2)
            path_in.arcTo(QRectF(cx - r_in_turb_out, cy - r_in_turb_out, r_in_turb_out * 2, r_in_turb_out * 2),
                          -in_ang, -in_span)
            path_in.lineTo(ip4)
            path_in.arcTo(QRectF(cx - r_in_turb_in, cy - r_in_turb_in, r_in_turb_in * 2, r_in_turb_in * 2),
                          -(in_ang + in_span), in_span)
            path_in.closeSubpath()

            p.setBrush(QBrush(rgba(c_cyan_bright, 0.35 + 0.20 * math.sin(phase * 3.0 + in_i))))
            p.setPen(QPen(rgba(c_cyan_bloom, 0.65), 1.0))
            p.drawPath(path_in)

        # ── 11. Central Radiant Diffuser & Concentric Target Grid Behind Triangle
        r_diff = r * 0.28
        g_diff = QRadialGradient(cx, cy, r_diff)
        g_diff.setColorAt(0.0, rgba(c_white, 1.0))
        g_diff.setColorAt(0.30, rgba(c_cyan_bloom, 0.95))
        g_diff.setColorAt(0.70, rgba(c_cyan_mid, 0.70 + 0.25 * amp))
        g_diff.setColorAt(1.0, rgba(c_cyan_dim, 0.0))
        p.setBrush(QBrush(g_diff))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), r_diff, r_diff)

        # Concentric glowing cyan circular rings
        for trg_r in (r * 0.09, r * 0.16, r * 0.23):
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(rgba(c_cyan_bloom, 0.85 + 0.15 * amp), 1.4))
            p.drawEllipse(QPointF(cx, cy), trg_r, trg_r)

        p.setPen(QPen(rgba(c_cyan_bloom, 0.70), 1.1))
        p.drawLine(QLineF(cx - r * 0.32, cy, cx + r * 0.32, cy))
        p.drawLine(QLineF(cx, cy - r * 0.32, cx, cy + r * 0.32))

        # ── 12. Central Inverted Vibranium Triangle Matrix ────────────────────
        r_tri_outer = r * 0.44
        r_tri_mid   = r * 0.38
        r_tri_inner = r * 0.33

        tri_angles = [math.radians(210), math.radians(330), math.radians(90)]

        def make_tri(radius):
            return QPolygonF([
                QPointF(cx + radius * math.cos(a), cy + radius * math.sin(a))
                for a in tri_angles
            ])

        tri_out = make_tri(r_tri_outer)
        tri_m   = make_tri(r_tri_mid)
        tri_in  = make_tri(r_tri_inner)

        # 3 Mechanical Locking Struts anchoring the triangle vertices to outer collar
        for a in tri_angles:
            vx = cx + r_tri_outer * math.cos(a)
            vy = cy + r_tri_outer * math.sin(a)
            sx = cx + r * 0.52 * math.cos(a)
            sy = cy + r * 0.52 * math.sin(a)
            p.setPen(QPen(c_metal_deep, 7.0))
            p.drawLine(QPointF(vx, vy), QPointF(sx, sy))
            p.setPen(QPen(c_metal_light, 4.0))
            p.drawLine(QPointF(vx, vy), QPointF(sx, sy))
            p.setPen(QPen(rgba(c_cyan_bloom, 0.8), 1.2))
            p.drawLine(QPointF(vx, vy), QPointF(sx, sy))

        # Triangle drop shadow & heavy bevel
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(c_metal_deep, 7.0))
        p.drawPolygon(tri_out)

        p.setPen(QPen(c_metal_light, 4.2))
        p.drawPolygon(tri_out)

        p.setPen(QPen(rgba(c_white, 0.95), 1.8))
        p.drawLine(tri_out[0], tri_out[1])

        p.setPen(QPen(rgba(c_cyan_bloom, 0.98), 2.6))
        p.drawPolygon(tri_m)

        p.setPen(QPen(c_metal_highlight, 1.8))
        p.drawPolygon(tri_in)

        # 3 Corner Vertex Rivets
        for a in tri_angles:
            vx = cx + r_tri_outer * math.cos(a)
            vy = cy + r_tri_outer * math.sin(a)
            p.setBrush(QBrush(c_metal_deep))
            p.setPen(QPen(c_gold_mid, 2.0))
            p.drawEllipse(QPointF(vx, vy), 6.0, 6.0)
            p.setBrush(QBrush(c_cyan_bloom))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(vx, vy), 2.8, 2.8)
            p.setBrush(QBrush(c_white))
            p.drawEllipse(QPointF(vx, vy), 1.2, 1.2)

        # ── 13. Procedural Electrical Discharges (when speaking or high amp) ──
        if self.speaking or amp > 0.15:
            p.setPen(QPen(rgba(c_white, 0.90), 1.5))
            for sp_i in range(3):
                s_ang = tri_angles[sp_i]
                p_s = QPointF(cx + r_tri_outer * 0.85 * math.cos(s_ang),
                              cy + r_tri_outer * 0.85 * math.sin(s_ang))
                p_m = QPointF(cx + r * 0.48 * math.cos(s_ang + 0.12 * math.sin(phase * 40.0 + sp_i)),
                              cy + r * 0.48 * math.sin(s_ang + 0.12 * math.sin(phase * 40.0 + sp_i)))
                p_e = QPointF(cx + r * 0.58 * math.cos(s_ang), cy + r * 0.58 * math.sin(s_ang))
                p.drawLine(QLineF(p_s, p_m))
                p.drawLine(QLineF(p_m, p_e))

        # ── 14. Central Blazing Singularity Nucleus ───────────────────────────
        r_nuc = r * (0.075 + 0.045 * amp)
        g_nuc = QRadialGradient(cx, cy, r_nuc)
        g_nuc.setColorAt(0.00, rgba(c_white, 1.0))
        g_nuc.setColorAt(0.30, rgba(c_white, 0.98))
        g_nuc.setColorAt(0.60, rgba(c_cyan_bloom, 0.90))
        g_nuc.setColorAt(1.00, rgba(c_cyan_bloom, 0.0))
        p.setBrush(QBrush(g_nuc))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(cx - r_nuc, cy - r_nuc, r_nuc * 2, r_nuc * 2))

        # ── 15. Bottom Creator Credit: CREATED BY DIVYANSHU VERMA ─────────────
        p.save()
        credit_y = cy + r * 0.885
        creator_name = (getattr(self, "_user_name", None) or "DIVYANSHU VERMA").strip() or "DIVYANSHU VERMA"

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(rgba(c_gold_mid, 0.85), 1.8))
        p.drawLine(QLineF(cx - 65, credit_y + 6, cx - 110, credit_y + 6))
        p.drawLine(QLineF(cx - 110, credit_y + 6, cx - 122, credit_y + 13))
        p.drawLine(QLineF(cx + 65, credit_y + 6, cx + 110, credit_y + 6))
        p.drawLine(QLineF(cx + 110, credit_y + 6, cx + 122, credit_y + 13))

        f_sub = QFont("Helvetica Neue", max(7, int(r * 0.026)), QFont.Weight.Medium)
        f_sub.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 4.0)
        p.setFont(f_sub)
        p.setPen(QPen(rgba(c_gold_bright, 0.88), 1.0))
        p.drawText(QRectF(cx - 150, credit_y, 300, 16), Qt.AlignmentFlag.AlignCenter, "CREATED BY")

        f_main = QFont("Helvetica Neue", max(9, int(r * 0.038)), QFont.Weight.Bold)
        f_main.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 5.0)
        p.setFont(f_main)
        p.setPen(QPen(rgba(c_gold_deep, 0.60), 1.0))
        p.drawText(QRectF(cx - 200, credit_y + 18, 400, 24), Qt.AlignmentFlag.AlignCenter, creator_name)
        p.setPen(QPen(c_gold_bright, 1.0))
        p.drawText(QRectF(cx - 200, credit_y + 18, 400, 24), Qt.AlignmentFlag.AlignCenter, creator_name)

        p.restore()

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():      # device not ready (e.g. 0-size during layout) — skip cleanly
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), qcol(C.BG))

        W, H = self.width(), self.height()
        cx = W / 2.0

        # Blit cached grid dots
        _gkey = (W, H, C.PRI_GHO)
        if self._grid_cache is None or self._grid_key != _gkey:
            self._grid_cache = self._make_grid(W, H)
            self._grid_key   = _gkey
        p.drawPixmap(0, 0, self._grid_cache)

        # ── Header Bar ────────────────────────────────────────────────────────
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(14, 8, max(40.0, W - 105.0), 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "◈ TACTICAL HUD")

        st_col = qcol(C.PRI)
        st_txt = "SYS: ACTIVE"
        if self.muted:
            st_col = qcol(C.MUTED_C)
            st_txt = "SYS: MUTED"
        elif self.speaking:
            st_col = qcol(C.ACC)
            st_txt = "SYS: VOICE"
        elif self.state in ("THINKING", "PROCESSING"):
            st_col = qcol(C.ACC2)
            st_txt = "SYS: THINKING"
        elif self.state == "LISTENING":
            st_col = qcol(C.GREEN)
            st_txt = "SYS: LISTENING"
        p.setPen(QPen(st_col, 1))
        p.drawText(QRectF(max(14.0, W - 95.0), 8, 80, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, st_txt)

        # ── Arc Reactor Core ──────────────────────────────────────────────────
        core_box_h = max(110.0, min(H * 0.54, W * 0.95))
        core_r = min(W * 0.40, (core_box_h - 22.0) / 2.0)
        core_cy = 28.0 + core_box_h / 2.0
        self._paint_core(p, cx, core_cy, core_r, W, core_box_h)

        # ── Live Waveform Spectrum Bars ───────────────────────────────────────
        amp = self._amp_disp
        wy = core_cy + core_r * 1.05 + 6.0
        N = min(28, max(12, int(W / 14)))
        bw = 6
        wx0 = (W - N * (bw + 2)) / 2.0
        mid = (N - 1) / 2.0
        for i in range(N):
            if self.muted:
                hgt, cl = 2, qcol(C.MUTED_C)
            else:
                env = (1.0 - abs(i - mid) / mid) ** 0.7
                shimmer = 0.55 + 0.45 * math.sin(self._tick * 0.18 + i * 0.7)
                idle = 2.5 + 2.0 * math.sin(self._tick * 0.09 + i * 0.6)
                hgt = int(max(2, min(20, idle + amp * 18.0 * env * shimmer)))
                cl = qcol(C.PRI) if hgt > 10 else qcol(C.PRI_DIM) if amp > 0.05 else qcol(C.BORDER_B)
            p.fillRect(QRectF(wx0 + i * (bw + 2), wy + 20 - hgt, bw, hgt), cl)

        # ── Tactical Telemetry Cards ──────────────────────────────────────────
        card_y = wy + 26.0
        card_h = max(42.0, H - card_y - 10.0)
        p.setBrush(QBrush(QColor(4, 12, 22, 160)))
        p.setPen(QPen(QColor(0, 210, 255, 45), 1.0))
        p.drawRoundedRect(QRectF(12, card_y, W - 24, card_h), 4, 4)

        p.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        line_h = max(13, int(card_h / 5.2))
        flux_val = 3.20 + amp * 0.85

        metrics = [
            ("ARC CORE FLUX", f"{flux_val:.2f} GJ/s", qcol(C.PRI)),
            ("CORE TEMP", "312.4 K [NOMINAL]", qcol(C.TEXT_DIM)),
            ("REPULSOR BUS", "99.8% CHARGED", qcol(C.ACC) if amp > 0.2 else qcol(C.PRI_DIM)),
            ("SERVO MATRIX", "CALIBRATED // ONLINE", qcol(C.GREEN) if not self.muted else qcol(C.MUTED_C)),
            ("AVIONICS LINK", "SYNCHRONIZED", qcol(C.PRI)),
        ]
        curr_y = card_y + 6
        for label, val, val_col in metrics:
            if curr_y + line_h > card_y + card_h - 4:
                break
            p.setPen(QPen(qcol(C.TEXT_DIM), 1))
            p.drawText(QRectF(20, curr_y, W * 0.48, line_h), Qt.AlignmentFlag.AlignLeft, label)
            p.setPen(QPen(val_col, 1))
            p.drawText(QRectF(W * 0.45, curr_y, W * 0.50 - 24, line_h), Qt.AlignmentFlag.AlignRight, val)
            curr_y += line_h

        # Corner Framing Brackets
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(0, 210, 255, 60), 1.0))
        b_len = 10.0
        p.drawLine(QPointF(6, 6), QPointF(6 + b_len, 6))
        p.drawLine(QPointF(6, 6), QPointF(6, 6 + b_len))
        p.drawLine(QPointF(W - 6, 6), QPointF(W - 6 - b_len, 6))
        p.drawLine(QPointF(W - 6, 6), QPointF(W - 6, 6 + b_len))
        p.drawLine(QPointF(6, H - 6), QPointF(6 + b_len, H - 6))
        p.drawLine(QPointF(6, H - 6), QPointF(6, H - 6 - b_len))
        p.drawLine(QPointF(W - 6, H - 6), QPointF(W - 6 - b_len, H - 6))
        p.drawLine(QPointF(W - 6, H - 6), QPointF(W - 6, H - 6 - b_len))

        p.end()


# ─────────────────────────────────────────────────────────────────────────────
# 2. AVATAR FACE CANVAS (Right Panel): JARVIS Hologram, Lip-Sync & Visemes
# ─────────────────────────────────────────────────────────────────────────────
class AvatarFaceCanvas(QWidget):
    """Holographic JARVIS Face Avatar panel (Right Wing).

    Houses the 3D HoloAvatar human anatomy mesh with real-time lip-sync visemes,
    audio-reactive glow, breathing sway, mood lighting, and eye glances.
    """
    def __init__(self, face_path: str = "", assistant_name: str = "J.A.R.V.I.S", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(220, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted    = False
        self.speaking = False
        self.state    = "INITIALISING"
        self._assistant_name = assistant_name
        try:
            from memory.config_manager import get_user_name
            self._user_name = get_user_name() or "DIVYANSHU VERMA"
        except Exception:
            self._user_name = "DIVYANSHU VERMA"

        self._avatar = None
        if HoloAvatar is not None:
            try:
                self._avatar = HoloAvatar()
            except Exception:
                self._avatar = None

        try:
            from memory.config_manager import get_hud_style
            self.hud_style = get_hud_style()
        except Exception:
            self.hud_style = "face"

        self._tick       = 0
        self._last_t     = time.time()
        self._step_t     = time.time()
        self._blink      = True
        self._blink_tick = 0

        self._grid_cache: QPixmap | None = None
        self._grid_key = None
        self._paint_tick = 0

        self._live_amp  = 0.0
        self._amp_disp  = 0.0
        self._visemes   = None
        self._vis_i     = None

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(16)

    def glance(self, dx: float, dy: float, hold: float = 1.1) -> None:
        try:
            if self._avatar is not None:
                self._avatar.glance(dx, dy, hold)
        except Exception:
            pass

    def push_visemes(self, frames, hop: float, at: float) -> None:
        try:
            if not frames:
                return
            hop = max(1e-3, float(hop))
            at = float(at)
            new = list(frames)
            cur = self._visemes
            if cur is not None:
                old, t0, ohop = cur
                if abs(ohop - hop) < 1e-6:
                    i = int(round((at - t0) / hop))
                    if 0 <= i <= len(old) + 1:
                        merged = old[:i] + new
                        played = int((time.time() - t0) / hop) - 2
                        if played > 60:
                            merged = merged[played:]
                            t0 += played * hop
                            if self._vis_i is not None:
                                self._vis_i = max(0, self._vis_i - played)
                        self._visemes = (merged, t0, hop)
                        return
            self._visemes = (new, at, hop)
            self._vis_i = None
        except Exception:
            pass

    def set_audio_level(self, level: float) -> None:
        try:
            lv = float(level)
        except (TypeError, ValueError):
            return
        lv = max(0.0, min(1.0, lv))
        if lv > self._live_amp:
            self._live_amp = lv

    def _make_grid(self, W: int, H: int) -> QPixmap:
        pm = QPixmap(max(1, W), max(1, H))
        pm.fill(Qt.GlobalColor.transparent)
        gp = QPainter(pm)
        gp.setPen(QPen(qcol(C.PRI_GHO), 1))
        for x in range(0, W, 48):
            for y in range(0, H, 48):
                gp.drawPoint(x, y)
        gp.end()
        return pm

    def _step(self):
        try:
            self._tick += 1
            now = time.time()
            v_open = v_wide = v_level = None
            v_seq = None
            sched = self._visemes
            if sched is not None:
                frames, t0, hop = sched
                i = int((now - t0) / hop)
                if 0 <= i < len(frames):
                    j = self._vis_i if self._vis_i is not None else i
                    v_seq = frames[max(0, j):i + 1]
                    self._vis_i = max(j, i + 1)
                    v_level, v_open, v_wide = frames[i]
                    if v_seq:
                        peak = max(f[0] for f in v_seq)
                        if peak > self._live_amp:
                            self._live_amp = peak
                elif i >= len(frames):
                    self._visemes = None
                    self._vis_i = None

            self._live_amp *= 0.86
            self._amp_disp += (self._live_amp - self._amp_disp) * 0.45
            amp = self._amp_disp

            dt = now - self._step_t
            self._step_t = now

            if self._avatar is not None:
                self._avatar.step(dt, amp, speaking=self.speaking,
                                  muted=self.muted, state=self.state,
                                  v_open=v_open, v_wide=v_wide or 0.0,
                                  v_level=v_level, v_seq=v_seq,
                                  v_hop=(sched[2] if sched is not None else 0.02))

            self._blink_tick += 1
            if self._blink_tick >= 38:
                self._blink = not self._blink
                self._blink_tick = 0
                _blinked = True
            else:
                _blinked = False

            self._paint_tick = (self._paint_tick + 1) % 6
            active = (self.speaking or amp > 0.02
                      or self.state in ("THINKING", "PROCESSING"))
            if _blinked or (self._paint_tick % 2 == 0 if active
                            else self._paint_tick % 3 == 0):
                if self._on_screen():
                    self.update()
        except Exception:
            pass

    def _on_screen(self) -> bool:
        try:
            if not self.isVisible():
                return False
            win = self.window()
            return not (win.isMinimized() or win.isHidden())
        except Exception:
            return True

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), qcol(C.BG))

        W, H = self.width(), self.height()
        cx, cy = W / 2.0, H / 2.0

        # Grid dots
        _gkey = (W, H, C.PRI_GHO)
        if self._grid_cache is None or self._grid_key != _gkey:
            self._grid_cache = self._make_grid(W, H)
            self._grid_key   = _gkey
        p.drawPixmap(0, 0, self._grid_cache)

        # ── Header Bar ────────────────────────────────────────────────────────
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(14, 8, max(40.0, W - 105.0), 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"◈ {self._assistant_name} MATRIX")
        p.setPen(QPen(qcol(C.PRI_DIM), 1))
        p.drawText(QRectF(max(14.0, W - 95.0), 8, 80, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "HOLOFACE")

        # ── Holographic Face Avatar ───────────────────────────────────────────
        _sy_status = max(180.0, H - 64.0)
        _band_t = 28.0
        _band_h = max(60.0, _sy_status - 12.0 - _band_t)

        if self._avatar is not None:
            _r_head = min(W * 0.38, _band_h / (self._avatar.SPAN + 0.08))
            _head_cy = _band_t + (_band_h - self._avatar.SPAN * _r_head) / 2.0 + _r_head

            if self.muted:
                _main = _acc = qcol(C.MUTED_C)
            else:
                _main = qcol(C.PRI)
                if self.speaking:
                    _acc = qcol(C.ACC)
                elif self.state in ("THINKING", "PROCESSING"):
                    _acc = qcol(C.ACC2)
                elif self.state == "LISTENING":
                    _acc = qcol(C.GREEN)
                else:
                    _acc = qcol(C.PRI)
            self._avatar.paint(p, cx, _head_cy, _r_head, _main, _acc, qcol(C.BG))
        else:
            p.setPen(QPen(qcol(C.PRI_DIM), 1))
            p.setFont(QFont("Courier New", 9))
            p.drawText(QRectF(0, _band_t, W, _band_h), Qt.AlignmentFlag.AlignCenter, "[AVATAR STANDBY]")

        # ── Status Badge ──────────────────────────────────────────────────────
        sy = _sy_status
        if self.muted:
            txt, col = "⊘  MUTED",     qcol(C.MUTED_C)
        elif self.speaking:
            txt, col = "●  SPEAKING",  qcol(C.ACC)
        elif self.state == "THINKING":
            sym = "◈" if self._blink else "◇"
            txt, col = f"{sym}  THINKING",   qcol(C.ACC2)
        elif self.state == "PROCESSING":
            sym = "▷" if self._blink else "▶"
            txt, col = f"{sym}  PROCESSING", qcol(C.ACC2)
        elif self.state == "LISTENING":
            sym = "●" if self._blink else "○"
            txt, col = f"{sym}  LISTENING",  qcol(C.GREEN)
        else:
            sym = "●" if self._blink else "○"
            txt, col = f"{sym}  {self.state}", qcol(C.PRI)

        p.setPen(QPen(col, 1))
        p.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        p.drawText(QRectF(0, sy, W, 22), Qt.AlignmentFlag.AlignCenter, txt)

        # ── Speech Articulation Waveform Bars ─────────────────────────────────
        wy = sy + 24
        N = min(28, max(12, int(W / 14)))
        bw = 6
        wx0 = (W - N * (bw + 2)) / 2.0
        amp = self._amp_disp
        mid = (N - 1) / 2.0
        for i in range(N):
            if self.muted:
                hgt, cl = 2, qcol(C.MUTED_C)
            else:
                env = (1.0 - abs(i - mid) / mid) ** 0.7
                shimmer = 0.55 + 0.45 * math.sin(self._tick * 0.18 + i * 0.7)
                idle = 2.5 + 2.0 * math.sin(self._tick * 0.09 + i * 0.6)
                hgt = int(max(2, min(18, idle + amp * 18.0 * env * shimmer)))
                cl = qcol(C.ACC) if (self.speaking and hgt > 8) else (qcol(C.PRI) if hgt > 8 else qcol(C.BORDER_B))
            p.fillRect(QRectF(wx0 + i * (bw + 2), wy + 16 - hgt, bw, hgt), cl)

        # Corner Framing Brackets
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(0, 210, 255, 60), 1.0))
        b_len = 10.0
        p.drawLine(QPointF(6, 6), QPointF(6 + b_len, 6))
        p.drawLine(QPointF(6, 6), QPointF(6, 6 + b_len))
        p.drawLine(QPointF(W - 6, 6), QPointF(W - 6 - b_len, 6))
        p.drawLine(QPointF(W - 6, 6), QPointF(W - 6, 6 + b_len))
        p.drawLine(QPointF(6, H - 6), QPointF(6 + b_len, H - 6))
        p.drawLine(QPointF(6, H - 6), QPointF(6, H - 6 - b_len))
        p.drawLine(QPointF(W - 6, H - 6), QPointF(W - 6 - b_len, H - 6))
        p.drawLine(QPointF(W - 6, H - 6), QPointF(W - 6, H - 6 - b_len))

        p.end()


# ─────────────────────────────────────────────────────────────────────────────
# 3. HUD TRIPLE PANEL (Command Deck): Left HUD | Center Gantry 3D | Right Face
# ─────────────────────────────────────────────────────────────────────────────
class HudTriplePanel(QWidget):
    """The master 3-panel JARVIS Holographic Command Deck.

    Arrangement:
    [ Left Wing: Tactical HUD ] | [ Center Stage: 3D Mark VII Gantry / Stack ] | [ Right Wing: Hologram Face ]
    """
    def __init__(self, face_path: str = "", assistant_name: str = "J.A.R.V.I.S", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(480, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._assistant_name = assistant_name

        # Left: Tactical HUD (Rings, Arc Core, Telemetry)
        self.left_hud = TacticalHudCanvas(assistant_name=assistant_name, parent=self)

        # Center: Gantry 3D Turntable / Camera / Video Stack
        self.center_stack = QStackedWidget(self)
        if GantryTurntableWidget is not None:
            self.gantry_viewer = GantryTurntableWidget(self)
        else:
            self.gantry_viewer = QLabel("3D Gantry Turntable Viewer")
            self.gantry_viewer.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.gantry_viewer.setStyleSheet("color: #00d2ff; background: #020710;")

        self.center_stack.addWidget(self.gantry_viewer)  # Index 0 is 3D Gantry!

        # Right: Holographic JARVIS Face Avatar
        self.right_avatar = AvatarFaceCanvas(face_path, assistant_name, self)

        # Horizontal Splitter connecting all three wings
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setStyleSheet("""
            QSplitter::handle:horizontal {
                background: #081522;
                width: 3px;
            }
            QSplitter::handle:horizontal:hover {
                background: #00d2ff;
            }
        """)

        self.splitter.addWidget(self.left_hud)
        self.splitter.addWidget(self.center_stack)
        self.splitter.addWidget(self.right_avatar)

        # Default proportions: Left 28%, Center 44%, Right 28%
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 5)
        self.splitter.setStretchFactor(2, 3)
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setCollapsible(2, False)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.splitter)

    # ── Forwarding APIs ───────────────────────────────────────────────────────

    def glance(self, dx: float, dy: float, hold: float = 1.1) -> None:
        self.right_avatar.glance(dx, dy, hold)

    def push_visemes(self, frames, hop: float, at: float) -> None:
        self.right_avatar.push_visemes(frames, hop, at)

    def set_audio_level(self, level: float) -> None:
        self.left_hud.set_audio_level(level)
        self.right_avatar.set_audio_level(level)

    @property
    def muted(self) -> bool:
        return self.right_avatar.muted

    @muted.setter
    def muted(self, val: bool) -> None:
        self.left_hud.muted = val
        self.right_avatar.muted = val

    @property
    def speaking(self) -> bool:
        return self.right_avatar.speaking

    @speaking.setter
    def speaking(self, val: bool) -> None:
        self.left_hud.speaking = val
        self.right_avatar.speaking = val

    @property
    def state(self) -> str:
        return self.right_avatar.state

    @state.setter
    def state(self, val: str) -> None:
        self.left_hud.state = val
        self.right_avatar.state = val

    @property
    def _user_name(self) -> str:
        return self.right_avatar._user_name

    @_user_name.setter
    def _user_name(self, val: str) -> None:
        self.left_hud._user_name = val
        self.right_avatar._user_name = val

    @property
    def hud_style(self) -> str:
        return getattr(self.right_avatar, "hud_style", "face")

    @hud_style.setter
    def hud_style(self, val: str) -> None:
        self.left_hud.hud_style = val
        self.right_avatar.hud_style = val

    @property
    def _avatar(self):
        return self.right_avatar._avatar

    def update(self) -> None:
        super().update()
        self.left_hud.update()
        self.right_avatar.update()

    def set_side_panels_visible(self, visible: bool) -> None:
        """Toggle side wings (Left HUD and Right Face) e.g. for fullscreen video."""
        self.left_hud.setVisible(visible)
        self.right_avatar.setVisible(visible)

    def toggle_side_panels(self) -> bool:
        new_vis = not self.left_hud.isVisible()
        self.set_side_panels_visible(new_vis)
        return new_vis


# Backward compatibility alias
HudCanvas = HudTriplePanel

class MetricBar(QWidget):

    def __init__(self, label: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._value = 0.0       # 0–100
        self._text  = "--"
        self.setFixedHeight(38)
        self.setMinimumWidth(80)

    def set_value(self, pct: float, text: str):
        v = max(0.0, min(100.0, pct))
        if v == self._value and text == self._text:
            return          # unchanged — skip the repaint
        self._value = v
        self._text  = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        p.setBrush(QBrush(qcol(C.PANEL2)))
        p.setPen(QPen(qcol(C.BORDER_A), 1))
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 4, 4)

        bar_h   = 4
        bar_y   = H - bar_h - 5
        bar_w   = W - 12
        bar_x   = 6
        fill_w  = int(bar_w * self._value / 100)

        p.setBrush(QBrush(qcol(C.BAR_BG)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 2, 2)

        if self._value > 85:
            bar_col = qcol(C.RED)
        elif self._value > 65:
            bar_col = qcol(C.ACC)
        else:
            bar_col = qcol(self._color)

        if fill_w > 0:
            p.setBrush(QBrush(bar_col))
            p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 2, 2)

        p.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(8, 5, 50, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._label)

        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(bar_col if self._text != "--" else qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, 4, W - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._text)

        p.end()

class LogWidget(QWidget):
    """Futuristic system activity stream with structured event cards."""
    _sig = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ai_name_lc = "jarvis"
        self._event_count = 0
        self.setStyleSheet(f"""
            LogWidget {{
                background: {C.PANEL};
                border: 1px solid {C.BORDER};
                border-radius: 4px;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Header bar
        hdr_w = QWidget()
        hdr_w.setFixedHeight(30)
        hdr_w.setStyleSheet(f"background: {C.PANEL2}; border-bottom: 1px solid {C.BORDER};")
        hdr_lay = QHBoxLayout(hdr_w)
        hdr_lay.setContentsMargins(10, 0, 8, 0)
        hdr_lay.setSpacing(6)

        title = QLabel("◈ ACTIVITY STREAM")
        title.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent; letter-spacing: 0.5px;")
        hdr_lay.addWidget(title)

        self._badge = QLabel("0 EVENTS")
        self._badge.setFont(QFont("Courier New", 7))
        self._badge.setStyleSheet(f"""
            color: {C.TEXT_DIM}; background: {C.PRI_GHO};
            border: 1px solid {C.BORDER}; border-radius: 2px; padding: 1px 4px;
        """)
        hdr_lay.addWidget(self._badge)
        hdr_lay.addStretch()

        clear_btn = QPushButton("⊘ CLEAR")
        clear_btn.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_DIM}; border: none; padding: 2px 4px;
            }}
            QPushButton:hover {{ color: {C.PRI}; }}
        """)
        clear_btn.clicked.connect(self.clear_log)
        hdr_lay.addWidget(clear_btn)
        lay.addWidget(hdr_w)

        # High-performance rich text event view
        self._view = QTextEdit()
        self._view.setReadOnly(True)
        self._view.document().setMaximumBlockCount(800)
        self._view.setFont(QFont("Courier New", 9))
        self._view.setStyleSheet(f"""
            QTextEdit {{
                background: {C.PANEL};
                color: {C.TEXT};
                border: none;
                padding: 6px 8px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG};
                width: 6px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {C.PRI_DIM};
            }}
        """)
        lay.addWidget(self._view)

        self._sig.connect(self._add_event)

    def append_log(self, text: str):
        self._sig.emit(str(text))

    def clear_log(self):
        self._view.clear()
        self._event_count = 0
        self._badge.setText("0 EVENTS")

    def textCursor(self):
        return self._view.textCursor()

    def setTextCursor(self, cursor):
        self._view.setTextCursor(cursor)

    def ensureCursorVisible(self):
        self._view.ensureCursorVisible()

    def _add_event(self, raw_text: str):
        raw_text = raw_text.strip()
        if not raw_text:
            return

        ts = time.strftime("%H:%M:%S")
        self._event_count += 1
        self._badge.setText(f"{self._event_count} EVENTS")

        tl = raw_text.lower()
        _ai_pfx = f"{self._ai_name_lc}:"

        if tl.startswith("you:"):
            cat = "COMMAND"
            icon = "▸"
            color = C.PRI
            bg_col = "rgba(0, 212, 255, 0.08)"
            border_col = C.PRI
            content = raw_text[4:].strip()
        elif tl.startswith(_ai_pfx) or tl.startswith("jarvis:"):
            cat = self._ai_name_lc.upper()
            icon = "◈"
            color = C.WHITE
            bg_col = "rgba(216, 248, 255, 0.06)"
            border_col = C.PRI_DIM
            content = raw_text.split(":", 1)[1].strip()
        elif tl.startswith("file:"):
            cat = "FILE"
            icon = "📎"
            color = C.GREEN
            bg_col = "rgba(0, 255, 136, 0.07)"
            border_col = C.GREEN_D
            content = raw_text[5:].strip()
        elif tl.startswith("action:") or "running tool" in tl or "action" in tl:
            cat = "ACTION"
            icon = "⚡"
            color = C.ACC2
            bg_col = "rgba(255, 204, 0, 0.07)"
            border_col = C.ACC
            content = raw_text.split(":", 1)[-1].strip() if ":" in raw_text else raw_text
        elif "err:" in tl or "failed" in tl or "error" in tl:
            cat = "ALERT"
            icon = "✕"
            color = C.RED
            bg_col = "rgba(255, 51, 85, 0.09)"
            border_col = C.RED
            content = raw_text.split(":", 1)[-1].strip() if ":" in raw_text else raw_text
        elif tl.startswith("quiz:"):
            cat = "QUIZ"
            icon = "📝"
            color = C.ACC
            bg_col = "rgba(255, 107, 0, 0.07)"
            border_col = C.ACC
            content = raw_text[5:].strip()
        else:
            cat = "SYS"
            icon = "●"
            color = C.TEXT_MED
            bg_col = "rgba(90, 184, 204, 0.04)"
            border_col = C.BORDER_B
            content = raw_text.split(":", 1)[-1].strip() if raw_text.startswith("SYS:") else raw_text

        content_html = (
            content.replace("&", "&amp;")
                   .replace("<", "&lt;")
                   .replace(">", "&gt;")
                   .replace("\n", "<br>")
        )

        text_color = C.WHITE if cat in ("COMMAND", self._ai_name_lc.upper(), "JARVIS") else C.TEXT
        card_html = (
            f'<table width="100%" cellpadding="3" cellspacing="0" '
            f'style="margin-bottom: 4px; background: {bg_col}; border-left: 2px solid {border_col}; border-radius: 2px;">'
            f'<tr><td style="font-family:\'Courier New\', monospace; font-size:7pt; color:{C.TEXT_DIM};">'
            f'<b style="color:{color};">{icon} {cat}</b> &nbsp; {ts}'
            f'</td></tr>'
            f'<tr><td style="font-family:\'Courier New\', monospace; font-size:8pt; color:{text_color}; padding-left:2px; padding-bottom:2px;">'
            f'{content_html}'
            f'</td></tr></table><br>'
        )

        cur = self._view.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        cur.insertHtml(card_html)
        self._view.setTextCursor(cur)
        self._view.ensureCursorVisible()


class SystemContextPanel(QWidget):
    """Futuristic status and telemetry cockpit pod."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            SystemContextPanel {{
                background: {C.PANEL};
                border: 1px solid {C.BORDER};
                border-radius: 4px;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Header
        hdr_w = QWidget()
        hdr_w.setFixedHeight(30)
        hdr_w.setStyleSheet(f"background: {C.PANEL2}; border-bottom: 1px solid {C.BORDER};")
        hdr_lay = QHBoxLayout(hdr_w)
        hdr_lay.setContentsMargins(10, 0, 10, 0)
        t = QLabel("◈ SYSTEM TELEMETRY")
        t.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        t.setStyleSheet(f"color: {C.PRI}; background: transparent; letter-spacing: 0.5px;")
        hdr_lay.addWidget(t)
        hdr_lay.addStretch()

        self._state_badge = QLabel("● STANDBY")
        self._state_badge.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        self._state_badge.setStyleSheet(f"""
            color: {C.GREEN}; background: {C.PRI_GHO};
            border: 1px solid {C.GREEN_D}; border-radius: 2px; padding: 1px 6px;
        """)
        hdr_lay.addWidget(self._state_badge)
        lay.addWidget(hdr_w)

        # Body items
        body = QWidget()
        b_lay = QVBoxLayout(body)
        b_lay.setContentsMargins(10, 8, 10, 8)
        b_lay.setSpacing(6)

        def _item(lbl_text, val_text, val_color=C.PRI):
            row = QHBoxLayout()
            row.setSpacing(6)
            l = QLabel(lbl_text)
            l.setFont(QFont("Courier New", 8))
            l.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            row.addWidget(l)
            row.addStretch()
            v = QLabel(val_text)
            v.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
            v.setStyleSheet(f"color: {val_color}; background: transparent;")
            row.addWidget(v)
            return row, v

        r1, self._val_core   = _item("CORE ENGINE", "ONLINE", C.GREEN)
        r2, self._val_ai     = _item("AI MODEL", "GEMINI 2.5 LIVE", C.PRI)
        r3, self._val_voice  = _item("AUDIO DUPLEX", "ACTIVE", C.GREEN)
        r4, self._val_memory = _item("PERSISTENT MEM", "ENABLED", C.ACC2)
        r5, self._val_vision = _item("VISION SENSORS", "READY", C.PRI)

        b_lay.addLayout(r1)
        b_lay.addLayout(r2)
        b_lay.addLayout(r3)
        b_lay.addLayout(r4)
        b_lay.addLayout(r5)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        b_lay.addWidget(sep)

        # Capabilities Badges Row
        caps_lay = QHBoxLayout()
        caps_lay.setSpacing(4)
        for cap_txt in ["VOICE", "VISION", "MEMORY", "EXEC"]:
            c_lbl = QLabel(f"✓ {cap_txt}")
            c_lbl.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
            c_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            c_lbl.setStyleSheet(f"""
                background: {C.PANEL2}; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 2px 0;
            """)
            caps_lay.addWidget(c_lbl)
        b_lay.addLayout(caps_lay)
        b_lay.addStretch()

        lay.addWidget(body)

    def set_system_state(self, state: str):
        state = state.upper()
        col = {
            "LISTENING": C.GREEN,
            "SPEAKING": C.PRI,
            "THINKING": C.ACC2,
            "MUTED": C.MUTED_C,
        }.get(state, C.TEXT_MED)
        border_col = {
            "LISTENING": C.GREEN_D,
            "SPEAKING": C.PRI_DIM,
            "THINKING": C.ACC,
            "MUTED": C.RED,
        }.get(state, C.BORDER)
        self._state_badge.setText(f"● {state}")
        self._state_badge.setStyleSheet(f"""
            color: {col}; background: {C.PRI_GHO};
            border: 1px solid {border_col}; border-radius: 2px; padding: 1px 6px;
        """)

_FILE_ICONS = {
    "image":   ("🖼", "#00d4ff"), "video":   ("🎬", "#ff6b00"),
    "audio":   ("🎵", "#cc44ff"), "pdf":     ("📄", "#ff4444"),
    "word":    ("📝", "#4488ff"), "excel":   ("📊", "#44bb44"),
    "code":    ("💻", "#ffcc00"), "archive": ("📦", "#ff8844"),
    "pptx":    ("📊", "#ff6622"), "text":    ("📃", "#aaaaaa"),
    "data":    ("🔧", "#88ddff"), "unknown": ("📎", "#888888"),
}
_EXT_TO_CAT = {
    **dict.fromkeys(["jpg","jpeg","png","gif","webp","bmp","tiff","svg","ico"], "image"),
    **dict.fromkeys(["mp4","avi","mov","mkv","wmv","flv","webm","m4v"],         "video"),
    **dict.fromkeys(["mp3","wav","ogg","m4a","aac","flac","wma","opus"],        "audio"),
    **dict.fromkeys(["pdf"],                                                     "pdf"),
    **dict.fromkeys(["doc","docx"],                                              "word"),
    **dict.fromkeys(["xls","xlsx","ods"],                                        "excel"),
    **dict.fromkeys(["ppt","pptx"],                                              "pptx"),
    **dict.fromkeys(["py","js","ts","jsx","tsx","html","css","java","c","cpp",
                     "cs","go","rs","rb","php","swift","kt","sh","sql","lua"],   "code"),
    **dict.fromkeys(["zip","rar","tar","gz","7z","bz2","xz"],                   "archive"),
    **dict.fromkeys(["txt","md","rst","log"],                                    "text"),
    **dict.fromkeys(["csv","tsv","json","xml"],                                  "data"),
}

def _file_category(path: Path) -> str:
    return _EXT_TO_CAT.get(path.suffix.lower().lstrip("."), "unknown")

def _fmt_size(size: int) -> str:
    if   size < 1024:    return f"{size} B"
    elif size < 1024**2: return f"{size/1024:.1f} KB"
    elif size < 1024**3: return f"{size/1024**2:.1f} MB"
    else:                return f"{size/1024**3:.1f} GB"

class CommandCockpit(QWidget):
    """
    Sleek futuristic command console docked at the bottom.
    Features:
    - Integrated compact File Attachment capsule (when attached: [ 📄 report.pdf · 1.2 MB  ✕ ])
    - Drag-and-drop support directly on the console
    - Large comfortable input with state-aware placeholder & subtle focus glow
    - Micro-action buttons: [ 📎 ATTACH ], [ ✋ STOP ], [ 🎙 MIC ACTIVE ], [ ⮞ SEND ]
    """
    send_requested = pyqtSignal(str)
    file_selected = pyqtSignal(str)
    file_cleared = pyqtSignal()
    interrupt_requested = pyqtSignal()
    mute_toggled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._current_file: str | None = None
        self._drag_over = False

        self.setStyleSheet(f"""
            QWidget#CommandCockpit {{
                background: {C.PANEL2};
                border-top: 1px solid {C.BORDER_B};
            }}
        """)
        self.setObjectName("CommandCockpit")

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(14, 5, 14, 7)
        main_lay.setSpacing(4)

        # ── Top Row: File Attachment Capsule / Status Pill ─────────────────────
        self._top_row = QHBoxLayout()
        self._top_row.setContentsMargins(0, 0, 0, 0)
        self._top_row.setSpacing(8)

        # Attachment capsule (hidden when no file attached)
        self._file_chip = QWidget()
        self._file_chip.setFixedHeight(22)
        self._file_chip.setStyleSheet(f"""
            background: rgba(0, 212, 255, 0.12);
            border: 1px solid {C.PRI};
            border-radius: 4px;
        """)
        chip_lay = QHBoxLayout(self._file_chip)
        chip_lay.setContentsMargins(6, 0, 4, 0)
        chip_lay.setSpacing(6)

        self._chip_lbl = QLabel("")
        self._chip_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._chip_lbl.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        chip_lay.addWidget(self._chip_lbl)

        self._chip_x = QPushButton("✕")
        self._chip_x.setFixedSize(16, 16)
        self._chip_x.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._chip_x.setCursor(Qt.CursorShape.PointingHandCursor)
        self._chip_x.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI}; border: none; padding: 0;
            }}
            QPushButton:hover {{ color: #ff4466; }}
        """)
        self._chip_x.clicked.connect(self.clear_file)
        chip_lay.addWidget(self._chip_x)
        self._file_chip.hide()
        self._top_row.addWidget(self._file_chip)

        self._top_hint = QLabel("💡 Tip: Enter to send  ·  ESC to interrupt  ·  F4 to mute  ·  Drop files anywhere")
        self._top_hint.setFont(QFont("Courier New", 7))
        self._top_hint.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._top_row.addWidget(self._top_hint)
        self._top_row.addStretch()

        self._state_indicator = QLabel("● STANDBY")
        self._state_indicator.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._state_indicator.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
        self._top_row.addWidget(self._state_indicator)

        main_lay.addLayout(self._top_row)

        # ── Bottom Row: Controls & Input ───────────────────────────────────────
        row = QHBoxLayout()
        row.setSpacing(6)

        # Attach button
        self._attach_btn = QPushButton("📎  ATTACH")
        self._attach_btn.setFixedHeight(36)
        self._attach_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._attach_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._attach_btn.setToolTip("Attach a file, image, document or code")
        self._attach_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.DARK}; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 4px; padding: 0 10px;
            }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.PRI_DIM}; background: {C.PRI_GHO}; }}
        """)
        self._attach_btn.clicked.connect(self._browse_file)
        row.addWidget(self._attach_btn)

        # Command input field
        self._input = QLineEdit()
        self._input.setFixedHeight(36)
        self._input.setFont(QFont("Courier New", 9))
        self._input.setPlaceholderText("Ask JARVIS anything, or speak naturally…")
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.DARK}; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 4px; padding: 0 10px;
                selection-background-color: {C.PRI_GHO};
            }}
            QLineEdit:focus {{
                border: 1px solid {C.PRI};
                background: #01111c;
            }}
        """)
        self._input.returnPressed.connect(self._on_send)
        row.addWidget(self._input, stretch=1)

        # Interrupt button
        self._interrupt_btn = QPushButton("✋  STOP [ESC]")
        self._interrupt_btn.setFixedHeight(36)
        self._interrupt_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._interrupt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._interrupt_btn.setToolTip("Interrupt JARVIS speech (Shortcut: ESC)")
        self._interrupt_btn.setStyleSheet(f"""
            QPushButton {{
                background: #140008; color: {C.MUTED_C};
                border: 1px solid {C.BORDER}; border-radius: 4px; padding: 0 10px;
            }}
            QPushButton:hover {{ background: #2b0012; border-color: {C.MUTED_C}; color: #ff6688; }}
        """)
        self._interrupt_btn.clicked.connect(self.interrupt_requested.emit)
        row.addWidget(self._interrupt_btn)

        # Microphone / Mute button
        self._mute_btn = QPushButton("🎙  MIC ACTIVE")
        self._mute_btn.setFixedHeight(36)
        self._mute_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.setToolTip("Toggle microphone mute (Shortcut: F4)")
        self._mute_btn.clicked.connect(self.mute_toggled.emit)
        self._style_mute_btn(False)
        row.addWidget(self._mute_btn)

        # Send button
        self._send_btn = QPushButton("⮞")
        self._send_btn.setFixedSize(36, 36)
        self._send_btn.setFont(QFont("Courier New", 13, QFont.Weight.Bold))
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setToolTip("Send command (Shortcut: Enter)")
        self._send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PRI_GHO}; color: {C.PRI};
                border: 1px solid {C.PRI}; border-radius: 4px;
            }}
            QPushButton:hover {{
                background: {C.PRI}; color: #00060a;
            }}
            QPushButton:pressed {{
                background: #ffffff; color: #000000;
            }}
        """)
        self._send_btn.clicked.connect(self._on_send)
        row.addWidget(self._send_btn)

        main_lay.addLayout(row)

    def _on_send(self):
        txt = self._input.text().strip()
        if txt:
            self.send_requested.emit(txt)

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Attach file for JARVIS", str(Path.home()),
            "All Files (*.*);;Images (*.png *.jpg *.jpeg *.webp);;Docs (*.pdf *.docx *.txt *.md);;Code (*.py *.js *.ts *.html *.css *.json)",
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        p = Path(path)
        cat = _file_category(p)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size = _fmt_size(p.stat().st_size)
        self._chip_lbl.setText(f"{icon}  {p.name}  ·  {size}")
        self._file_chip.show()
        self.file_selected.emit(path)

    def current_file(self) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None
        self._file_chip.hide()
        self.file_cleared.emit()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drag_over = True
            self.setStyleSheet(f"""
                QWidget#CommandCockpit {{
                    background: {C.PANEL2};
                    border-top: 2px dashed {C.PRI};
                }}
            """)

    def dragLeaveEvent(self, e):
        self._drag_over = False
        self.setStyleSheet(f"""
            QWidget#CommandCockpit {{
                background: {C.PANEL2};
                border-top: 1px solid {C.BORDER_B};
            }}
        """)

    def dropEvent(self, e: QDropEvent):
        self.dragLeaveEvent(e)
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_file():
                self._set_file(path)

    def set_system_state(self, state: str):
        state = state.upper()
        col = {
            "LISTENING": C.GREEN,
            "SPEAKING": C.PRI,
            "THINKING": C.ACC2,
            "MUTED": C.MUTED_C,
        }.get(state, C.TEXT_MED)
        self._state_indicator.setText(f"● {state}")
        self._state_indicator.setStyleSheet(f"color: {col}; background: transparent;")

        if state == "SPEAKING":
            self._input.setPlaceholderText("JARVIS is speaking… (Press ESC or click STOP to interrupt)")
            self._interrupt_btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(255, 51, 85, 0.2); color: #ff3355;
                    border: 1px solid #ff3355; border-radius: 4px; padding: 0 10px; font-weight: bold;
                }}
                QPushButton:hover {{ background: #ff3355; color: #ffffff; }}
            """)
        else:
            self._interrupt_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #140008; color: {C.MUTED_C};
                    border: 1px solid {C.BORDER}; border-radius: 4px; padding: 0 10px;
                }}
                QPushButton:hover {{ background: #2b0012; border-color: {C.MUTED_C}; color: #ff6688; }}
            """)
            if state == "THINKING":
                self._input.setPlaceholderText("JARVIS is computing response…")
            elif state == "MUTED":
                self._input.setPlaceholderText("Microphone muted — type a command here…")
            else:
                self._input.setPlaceholderText("Ask JARVIS anything, or speak naturally…")

    def _style_mute_btn(self, muted: bool):
        if muted:
            self._mute_btn.setText("🔇  MIC MUTED")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #140006; color: {C.MUTED_C};
                    border: 1px solid {C.MUTED_C}; border-radius: 4px; padding: 0 10px;
                }}
                QPushButton:hover {{ background: #26000c; color: #ff4466; }}
            """)
        else:
            self._mute_btn.setText("🎙  MIC ACTIVE")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #00140a; color: {C.GREEN};
                    border: 1px solid {C.GREEN}; border-radius: 4px; padding: 0 10px;
                }}
                QPushButton:hover {{ background: #002412; color: #ffffff; }}
            """)


class FileDropZone(QWidget):
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(100)
        self._current_file: str | None = None
        self._hovering  = False
        self._drag_over = False
        self._dash_offset = 0.0
        self._anim_tmr = QTimer(self)
        self._anim_tmr.timeout.connect(self._animate)
        self._anim_tmr.start(40)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._canvas = _DropCanvas(self)
        layout.addWidget(self._canvas)

    def _animate(self):
        # The marching-ants dashed border is only meaningful while the user is
        # hovering or dragging a file over the zone. When idle, skip the repaint
        # entirely instead of redrawing the whole zone 25×/s forever — that idle
        # repaint held the GIL and stole time from the audio/response threads.
        if not (self._hovering or self._drag_over):
            return
        self._dash_offset = (self._dash_offset + 0.8) % 20
        self._canvas.update()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drag_over = True; self._canvas.update()

    def dragLeaveEvent(self, e):
        self._drag_over = False; self._canvas.update()

    def dropEvent(self, e: QDropEvent):
        self._drag_over = False
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_file():
                self._set_file(path)
        self._canvas.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._browse()

    def enterEvent(self, e):
        self._hovering = True; self._canvas.update()

    def leaveEvent(self, e):
        self._hovering = False; self._canvas.update()

    def current_file(self) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None; self._canvas.update()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a file for JARVIS", str(Path.home()),
            "All Files (*.*);;"
            "Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documents (*.pdf *.docx *.txt *.md *.pptx);;"
            "Data (*.csv *.xlsx *.json *.xml);;"
            "Code (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archives (*.zip *.rar *.tar *.gz *.7z)",
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        self._canvas.update()
        self.file_selected.emit(path)


class _DropCanvas(QWidget):
    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z    = self._z
        W, H = self.width(), self.height()
        pad  = 6
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        bg_col = qcol("#001a24" if z._drag_over else ("#001218" if z._hovering else C.PANEL))
        p.setBrush(QBrush(bg_col)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   border_col = qcol(C.GREEN, 200)
        elif z._drag_over:    border_col = qcol(C.PRI, 230)
        elif z._hovering:     border_col = qcol(C.BORDER_B, 200)
        else:                 border_col = qcol(C.BORDER, 160)

        pen = QPen(border_col, 1.5, Qt.PenStyle.DashLine)
        pen.setDashOffset(z._dash_offset)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   self._paint_file(p, W, H)
        elif z._drag_over:    self._paint_drag_over(p, W, H)
        else:                 self._paint_idle(p, W, H, z._hovering)

        p.end()

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2
        col = qcol(C.PRI_DIM if not hover else C.PRI)
        p.setPen(QPen(col, 2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx, cy - 14), QPointF(cx, cy + 4))
        p.drawLine(QPointF(cx - 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx + 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx - 14, cy + 4), QPointF(cx + 14, cy + 4))
        p.setFont(QFont("Courier New", 8))
        p.setPen(QPen(qcol(C.PRI_DIM if not hover else C.TEXT), 1))
        p.drawText(QRectF(0, cy + 8, W, 16), Qt.AlignmentFlag.AlignCenter,
                   "Drop file here  or  Click to Browse")
        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol("#1a4a5a"), 1))
        p.drawText(QRectF(0, cy + 24, W, 14), Qt.AlignmentFlag.AlignCenter,
                   "Images · Video · Audio · PDF · Docs · Code · Data")

    def _paint_drag_over(self, p, W, H):
        cx, cy = W / 2, H / 2
        p.setFont(QFont("Courier New", 20))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy - 24, W, 32), Qt.AlignmentFlag.AlignCenter, "⬇")
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy + 12, W, 16), Qt.AlignmentFlag.AlignCenter, "Release to load")

    def _paint_file(self, p, W, H):
        path = Path(self._z._current_file)
        cat  = _file_category(path)
        icon, icon_col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size_str = _fmt_size(path.stat().st_size)
        ext_str  = path.suffix.upper().lstrip(".") or "FILE"

        block_x, block_w = 10, 60
        p.setFont(QFont("Segoe UI Emoji", 22) if _OS == "Windows" else QFont("Arial", 22))
        p.setPen(QPen(qcol(icon_col), 1))
        p.drawText(QRectF(block_x, 0, block_w, H), Qt.AlignmentFlag.AlignCenter, icon)

        tx = block_x + block_w + 6
        tw = W - tx - 38

        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.WHITE), 1))
        name = path.name if len(path.name) <= 34 else path.name[:31] + "..."
        p.drawText(QRectF(tx, H * 0.18, tw, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(tx, H * 0.18 + 18, tw, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{ext_str}  ·  {size_str}")

        p.setFont(QFont("Courier New", 6))
        p.setPen(QPen(qcol("#1e5c6a"), 1))
        par = str(path.parent)
        if len(par) > 42: par = "…" + par[-41:]
        p.drawText(QRectF(tx, H * 0.18 + 34, tw, 12),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, par)

        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.RED, 180), 1))
        p.drawText(QRectF(W - 34, 0, 28, H), Qt.AlignmentFlag.AlignCenter, "✕")

    def mousePressEvent(self, e):
        z = self._z
        if z._current_file and e.pos().x() > self.width() - 34:
            z.clear_file()
        else:
            z.mousePressEvent(e)


class _CameraPreview(QWidget):
    """Floating overlay that briefly shows what the camera captured."""

    _W, _H = 244, 188

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            _CameraPreview {{
                background: rgba(0, 6, 10, 242);
                border: 1px solid {C.PRI};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._W)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 5, 6, 6)
        lay.setSpacing(4)

        hdr = QHBoxLayout()
        title = QLabel("◈  VISUAL INPUT")
        title.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(title)
        hdr.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(16, 16)
        close_btn.setFont(QFont("Courier New", 8))
        close_btn.setStyleSheet(
            f"color: {C.TEXT_DIM}; background: transparent; border: none;"
        )
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.hide)
        hdr.addWidget(close_btn)
        lay.addLayout(hdr)

        self._img_lbl = QLabel()
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_lbl.setStyleSheet("background: transparent;")
        lay.addWidget(self._img_lbl)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

        self.hide()

    def show_frame(self, img_bytes: bytes) -> None:
        px = QPixmap()
        px.loadFromData(img_bytes)
        if not px.isNull():
            max_w = self._W - 12
            scaled = px.scaled(
                max_w, 160,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._img_lbl.setPixmap(scaled)
            self._img_lbl.setFixedSize(scaled.width(), scaled.height())
            self.adjustSize()
        self.show()
        self.raise_()
        self._timer.start(6_000)   # auto-dismiss after 6 s


class SetupOverlay(QWidget):
    done = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            SetupOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)

        detected = {"darwin": "mac", "windows": "windows"}.get(
            _OS.lower(), "linux"
        )
        self._sel_os = detected

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 22, 30, 22)
        layout.setSpacing(8)

        def _lbl(txt, font_size=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont("Courier New", font_size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        layout.addWidget(_lbl("◈  INITIALISATION REQUIRED", 13, True))
        layout.addWidget(_lbl("Configure J.A.R.V.I.S. before first boot.", 9, color=C.PRI_DIM))
        layout.addSpacing(6)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep)
        layout.addSpacing(4)

        layout.addWidget(_lbl("GEMINI API KEY", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("AIza…")
        self._key_input.setFont(QFont("Courier New", 10))
        self._key_input.setFixedHeight(32)
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d12; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        layout.addWidget(self._key_input)
        layout.addSpacing(12)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep2)
        layout.addSpacing(4)

        layout.addWidget(_lbl("OPERATING SYSTEM", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        det_name = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}[detected]
        layout.addWidget(_lbl(f"Auto-detected: {det_name}", 8, color=C.ACC2,
                               align=Qt.AlignmentFlag.AlignLeft))

        os_row = QHBoxLayout(); os_row.setSpacing(6)
        self._os_btns: dict[str, QPushButton] = {}
        for key, label in [("windows","⊞  Windows"),("mac","  macOS"),("linux","🐧  Linux")]:
            btn = QPushButton(label)
            btn.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            btn.setFixedHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._sel(k))
            os_row.addWidget(btn)
            self._os_btns[key] = btn
        layout.addLayout(os_row)
        self._sel(detected)
        layout.addSpacing(12)

        init_btn = QPushButton("▸  INITIALISE SYSTEMS")
        init_btn.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        init_btn.setFixedHeight(36)
        init_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        init_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
            }}
            QPushButton:hover {{
                background: {C.PRI_GHO}; border: 1px solid {C.PRI};
            }}
        """)
        init_btn.clicked.connect(self._submit)
        layout.addWidget(init_btn)

    def _sel(self, key: str):
        self._sel_os = key
        pal = {"windows":(C.PRI,"#001a22"),"mac":(C.ACC2,"#1a1400"),"linux":(C.GREEN,"#001a0d")}
        for k, btn in self._os_btns.items():
            if k == key:
                fg, bg = pal[k]
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {fg}; color: {bg};
                        border: none; border-radius: 3px; font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #000d12; color: {C.TEXT_DIM};
                        border: 1px solid {C.BORDER}; border-radius: 3px;
                    }}
                    QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
                """)

    def _submit(self):
        key = self._key_input.text().strip()
        if not key:
            self._key_input.setStyleSheet(
                self._key_input.styleSheet() +
                f" QLineEdit {{ border: 1px solid {C.RED}; }}"
            )
            return
        self.done.emit(key, self._sel_os)


class HueWheel(QWidget):
    """
    Circular colour picker. The user drags the handle (small white circle)
    around the wheel to choose from ALL hues. The filled circle in the centre
    is a live preview of the selected colour.
    """

    hue_picked    = pyqtSignal(str)   # while dragging (live)
    hue_committed = pyqtSignal(str)   # when the handle is released

    _RING = 16   # ring thickness (px)

    def __init__(self, initial_hex: str = DEFAULT_UI_COLOR, parent=None):
        super().__init__(parent)
        self.setFixedSize(148, 148)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hue  = 0.53
        self._drag = False
        self.set_color(initial_hex)

    # ── API ──────────────────────────────────────────────────────────────────
    def color(self) -> str:
        return QColor.fromHsvF(self._hue, 1.0, 1.0).name()

    def set_color(self, hex_str: str):
        c = QColor((hex_str or "").strip())
        if c.isValid() and c.hsvHueF() >= 0:
            self._hue = c.hsvHueF()
            self.update()

    # ── geometry helpers ─────────────────────────────────────────────────────
    def _ring_rect(self) -> QRectF:
        m = self._RING / 2 + 3
        return QRectF(self.rect()).adjusted(m, m, -m, -m)

    def _hue_from_pos(self, pos: QPointF) -> float:
        c  = QRectF(self.rect()).center()
        dx = pos.x() - c.x()
        dy = c.y() - pos.y()          # screen y goes down — flip to math axis
        ang = math.atan2(dy, dx)      # [-π, π], counter-clockwise
        return (ang / (2 * math.pi)) % 1.0

    # ── drawing ──────────────────────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect   = self._ring_rect()
        center = rect.center()

        grad = QConicalGradient(center, 0)
        for i in range(0, 361, 20):
            grad.setColorAt(i / 360.0, QColor.fromHsvF((i % 360) / 360.0, 1.0, 1.0))
        p.setPen(QPen(QBrush(grad), self._RING))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect)

        # centre preview circle
        preview = QColor.fromHsvF(self._hue, 1.0, 1.0)
        inner   = rect.adjusted(30, 30, -30, -30)
        p.setPen(QPen(qcol(C.BORDER_B), 1))
        p.setBrush(QBrush(preview))
        p.drawEllipse(inner)

        # draggable handle
        r   = rect.width() / 2
        ang = self._hue * 2 * math.pi
        hx  = center.x() + r * math.cos(ang)
        hy  = center.y() - r * math.sin(ang)
        p.setPen(QPen(QColor("#00060a"), 2))
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawEllipse(QPointF(hx, hy), 7.5, 7.5)
        p.end()

    # ── fare ─────────────────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        self._drag = True
        self._hue  = self._hue_from_pos(e.position())
        self.update()
        self.hue_picked.emit(self.color())

    def mouseMoveEvent(self, e):
        if self._drag:
            self._hue = self._hue_from_pos(e.position())
            self.update()
            self.hue_picked.emit(self.color())

    def mouseReleaseEvent(self, e):
        if self._drag:
            self._drag = False
            self.hue_committed.emit(self.color())


class CustomizeOverlay(QWidget):
    """Floating overlay — change assistant name, user name, UI colour and voice."""

    saved = pyqtSignal(str, str, str, str)   # assistant_name, user_name, ui_color, voice
    _OW, _OH = 400, 588

    def __init__(self, assistant_name="JARVIS", user_name="",
                 ui_color=DEFAULT_UI_COLOR, voice="", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            CustomizeOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(8)

        def _lbl(txt, fs=9, bold=False, color=C.PRI, align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt); w.setAlignment(align)
            w.setFont(QFont("Courier New", fs,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        _fs = (f"QLineEdit {{ background: #000d12; color: {C.TEXT}; "
               f"border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px; }}"
               f"QLineEdit:focus {{ border: 1px solid {C.PRI}; }}")

        lay.addWidget(_lbl("⚙  CUSTOMISE ASSISTANT", 12, True))
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        lay.addWidget(_lbl("ASSISTANT NAME", 8, color=C.TEXT_DIM,
                            align=Qt.AlignmentFlag.AlignLeft))
        self._name_input = QLineEdit(assistant_name)
        self._name_input.setFont(QFont("Courier New", 10))
        self._name_input.setFixedHeight(32)
        self._name_input.setStyleSheet(_fs)
        lay.addWidget(self._name_input)

        lay.addSpacing(4)
        lay.addWidget(_lbl("YOUR NAME  (leave blank for default sir / efendim)", 8,
                            color=C.TEXT_DIM, align=Qt.AlignmentFlag.AlignLeft))
        self._user_input = QLineEdit(user_name)
        self._user_input.setPlaceholderText("e.g.  Tony   (leave blank for auto)")
        self._user_input.setFont(QFont("Courier New", 10))
        self._user_input.setFixedHeight(32)
        self._user_input.setStyleSheet(_fs)
        lay.addWidget(self._user_input)

        # ── Assistant voice — Gemini prebuilt voices ─────────────────────────
        # Names are language-neutral proper nouns, so the row reads the same in
        # every locale. Selecting one and applying rebuilds the Live session.
        from memory.config_manager import AVAILABLE_VOICES, DEFAULT_VOICE
        lay.addSpacing(4)
        lay.addWidget(_lbl("ASSISTANT VOICE", 8, color=C.TEXT_DIM,
                            align=Qt.AlignmentFlag.AlignLeft))
        self._sel_voice   = (voice or DEFAULT_VOICE)
        if self._sel_voice not in AVAILABLE_VOICES:
            self._sel_voice = DEFAULT_VOICE
        self._voice_btns: dict[str, QPushButton] = {}
        voice_row = QHBoxLayout(); voice_row.setSpacing(4)
        for _v in AVAILABLE_VOICES:
            b = QPushButton(_v)
            b.setCheckable(True)
            b.setFixedHeight(28)
            b.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, name=_v: self._on_voice_pick(name))
            self._voice_btns[_v] = b
            voice_row.addWidget(b)
        lay.addLayout(voice_row)
        self._refresh_voice_btns()

        # ── UI colour — colour wheel ─────────────────────────────────────────
        lay.addSpacing(4)
        clr_hdr = QHBoxLayout()
        clr_hdr.addWidget(_lbl("UI COLOUR  —  drag the handle", 8,
                               color=C.TEXT_DIM, align=Qt.AlignmentFlag.AlignLeft))
        clr_hdr.addStretch()
        df_btn = QPushButton("DEFAULT")
        df_btn.setFixedSize(64, 20)
        df_btn.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        df_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        df_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        df_btn.clicked.connect(lambda: self._set_color(DEFAULT_UI_COLOR))
        clr_hdr.addWidget(df_btn)
        lay.addLayout(clr_hdr)

        self._initial_color = (ui_color or DEFAULT_UI_COLOR).strip().lower()
        self._sel_color     = self._initial_color
        self.on_preview     = None   # callable(hex) — live preview; MainWindow wires it

        self._wheel = HueWheel(self._sel_color)
        wheel_row = QHBoxLayout()
        wheel_row.addStretch(); wheel_row.addWidget(self._wheel); wheel_row.addStretch()
        lay.addLayout(wheel_row)
        self._wheel.hue_picked.connect(self._on_wheel_pick)
        self._wheel.hue_committed.connect(self._on_wheel_commit)

        self._hex_input = QLineEdit(self._sel_color)
        self._hex_input.setPlaceholderText("#00d4ff   (custom hex colour)")
        self._hex_input.setFont(QFont("Courier New", 10))
        self._hex_input.setFixedHeight(28)
        self._hex_input.setStyleSheet(_fs)
        self._hex_input.textEdited.connect(self._on_hex_edited)
        lay.addWidget(self._hex_input)

        lay.addSpacing(6)
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)

        save_btn = QPushButton("▸  APPLY CHANGES")
        save_btn.setFixedHeight(34)
        save_btn.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        cancel_btn = QPushButton("CANCEL")
        cancel_btn.setFixedHeight(34)
        cancel_btn.setFont(QFont("Courier New", 9))
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        cancel_btn.clicked.connect(self._cancel)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)

    # ── voice selection ──────────────────────────────────────────────────────
    def _on_voice_pick(self, name: str):
        self._sel_voice = name
        self._refresh_voice_btns()

    def _refresh_voice_btns(self):
        """Highlight the selected voice pill; dim the rest."""
        for name, b in self._voice_btns.items():
            on = (name == self._sel_voice)
            b.setChecked(on)
            if on:
                b.setStyleSheet(f"""
                    QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI};
                        border: 1px solid {C.PRI}; border-radius: 3px; }}
                """)
            else:
                b.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {C.TEXT_MED};
                        border: 1px solid {C.BORDER}; border-radius: 3px; }}
                    QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
                """)

    # ── colour flow ──────────────────────────────────────────────────────────
    def _set_color(self, hx: str, update_wheel: bool = True, preview: bool = True):
        """Updates the selected colour; hex box + wheel stay in sync, theme is live-previewed."""
        self._sel_color = hx.strip().lower()
        self._hex_input.blockSignals(True)
        self._hex_input.setText(self._sel_color)
        self._hex_input.blockSignals(False)
        if update_wheel:
            self._wheel.set_color(self._sel_color)
        if preview and self.on_preview:
            self.on_preview(self._sel_color)

    def _on_wheel_pick(self, hx: str):
        # While dragging: update the hex box, don't apply the theme yet
        self._sel_color = hx
        self._hex_input.blockSignals(True)
        self._hex_input.setText(hx)
        self._hex_input.blockSignals(False)

    def _on_wheel_commit(self, hx: str):
        # Handle released → live-preview the whole interface
        self._set_color(hx, update_wheel=False)

    def _on_hex_edited(self, text: str):
        t = text.strip().lower()
        if t.startswith("#") and len(t) == 7:
            try:
                int(t[1:], 16)
            except ValueError:
                return
            self._set_color(t, update_wheel=True, preview=True)

    def _cancel(self):
        # If a preview was applied, revert to the colour from launch
        if self.on_preview and self._sel_color != self._initial_color:
            self.on_preview(self._initial_color)
        self.hide()

    def _save(self):
        name = self._name_input.text().strip() or "JARVIS"
        user = self._user_input.text().strip()
        self.saved.emit(name, user, self._sel_color or DEFAULT_UI_COLOR, self._sel_voice)
        self.hide()


class PluginManagerOverlay(QWidget):
    """Floating overlay — lists discovered plugins with per-plugin ON/OFF toggles."""

    _OW = 420

    def __init__(self, plugins: list[dict], parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            PluginManagerOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(6)

        hdr = QLabel("🧩  PLUGIN MANAGER")
        hdr.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        lay.addWidget(hdr)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        if not plugins:
            empty = QLabel("No plugins found in /plugins.")
            empty.setFont(QFont("Courier New", 8))
            empty.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            lay.addWidget(empty)

        for p in plugins:
            lay.addLayout(self._build_row(p))

        lay.addSpacing(4)
        close_btn = QPushButton("CLOSE")
        close_btn.setFixedHeight(30)
        close_btn.setFont(QFont("Courier New", 9))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        close_btn.clicked.connect(self.hide)
        lay.addWidget(close_btn)
        self.adjustSize()

    def _build_row(self, p: dict) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(6)

        label_text = p["name"] if p["valid"] else f"{p['name']}  (⚠ {p['file']})"
        lbl = QLabel(label_text)
        lbl.setFont(QFont("Courier New", 8))
        lbl.setStyleSheet(f"color: {C.TEXT if p['valid'] else C.TEXT_DIM}; background: transparent;")
        lbl.setToolTip(p["description"] if p["valid"] else p["error"])
        lbl.setWordWrap(False)
        row.addWidget(lbl, stretch=1)

        btn = QPushButton()
        btn.setFixedSize(72, 24)
        btn.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        if not p["valid"]:
            btn.setText("BROKEN")
            btn.setEnabled(False)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                }}
            """)
        else:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._style_toggle(btn, p["enabled"])
            btn.clicked.connect(lambda _, name=p["name"], b=btn: self._toggle(name, b))
        row.addWidget(btn)
        return row

    def _style_toggle(self, btn: QPushButton, enabled: bool):
        if enabled:
            btn.setText("ON")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 3px;
                }}
                QPushButton:hover {{ background: #002010; }}
            """)
        else:
            btn.setText("OFF")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
            """)

    def _toggle(self, name: str, btn: QPushButton):
        from memory.config_manager import get_plugin_enabled, save_plugin_enabled
        new_val = not get_plugin_enabled(name)
        save_plugin_enabled(name, new_val)
        self._style_toggle(btn, new_val)


class _HudOverlay(QWidget):
    """Base for the floating panels placed by hand over the HUD.

    They are children of the central widget but sit in no layout, so Qt never
    invalidates the region they occupy when they hide or shrink: the HUD keeps
    painting around them and their last frame stays on screen as a ghost. Any
    overlay positioned with _centre_overlay needs this."""

    def hideEvent(self, e):
        p = self.parentWidget()
        if p is not None:
            # Repaint exactly what we were covering, before we stop covering it.
            p.update(self.geometry())
        super().hideEvent(e)

    def closeEvent(self, e):
        p = self.parentWidget()
        if p is not None:
            p.update(self.geometry())
        super().closeEvent(e)


class ConfirmBanner(_HudOverlay):
    """The gate in front of an action that cannot be taken back.

    The old confirmation was a tool parameter the model filled in itself, which
    means it confirmed its own shutdown requests. This is the interface asking,
    and the answer travels from a human finger to core/confirm.py without the
    model in the loop. Nothing blocks while it is up: the assistant keeps
    talking, so this costs no latency — unlike the old gate, which spent two
    tool round trips on every power command."""

    answered = pyqtSignal(bool)
    _OW = 430

    def __init__(self, title: str, detail: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ConfirmBanner {{
                background: rgba(14, 3, 0, 250);
                border: 1px solid {C.ACC};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)

        hdr = QLabel("⚠  CONFIRM")
        hdr.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.ACC}; background: transparent;")
        lay.addWidget(hdr)

        ttl = QLabel(title)
        ttl.setWordWrap(True)
        ttl.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        ttl.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        lay.addWidget(ttl)

        if detail:
            dtl = QLabel(detail)
            dtl.setWordWrap(True)
            dtl.setFont(QFont("Courier New", 8))
            dtl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            lay.addWidget(dtl)

        row = QHBoxLayout(); row.setSpacing(8)

        yes = QPushButton("▸  CONFIRM")
        yes.setFixedHeight(32)
        yes.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        yes.setCursor(Qt.CursorShape.PointingHandCursor)
        yes.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.ACC};
                border: 1px solid {C.ACC}; border-radius: 3px; }}
            QPushButton:hover {{ background: rgba(255,107,0,40); }}
        """)
        yes.clicked.connect(lambda: self.answered.emit(True))
        row.addWidget(yes)

        no = QPushButton("CANCEL")
        no.setFixedHeight(32)
        no.setFont(QFont("Courier New", 9))
        no.setCursor(Qt.CursorShape.PointingHandCursor)
        no.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        no.clicked.connect(lambda: self.answered.emit(False))
        row.addWidget(no)
        lay.addLayout(row)

        # Default focus on CANCEL: if someone hits Enter without reading, the
        # safe answer wins.
        no.setDefault(True)
        no.setFocus()


class AudioDeviceOverlay(_HudOverlay):
    """Choose which microphone JARVIS listens to and which speakers it uses.

    Both audio streams used to open with no `device=` at all, so they always
    took the OS default — which on Windows moves by itself the moment a headset
    is plugged in. 'JARVIS can't hear me' is usually 'JARVIS is listening to the
    webcam'."""

    picked = pyqtSignal()      # emitted after Apply, when something changed
    _OW = 460

    def __init__(self, parent=None):
        super().__init__(parent)
        from core.audio_devices import list_devices, DEFAULT_LABEL
        from memory.config_manager import get_input_device, get_output_device

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            AudioDeviceOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(6)

        hdr = QLabel("🎧  AUDIO DEVICES")
        hdr.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        lay.addWidget(hdr)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        _combo_css = (
            f"QComboBox {{ background: #000d12; color: {C.TEXT}; "
            f"border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px; }}"
            f"QComboBox:hover {{ border-color: {C.BORDER_B}; }}"
            f"QComboBox QAbstractItemView {{ background: #000d12; color: {C.TEXT}; "
            f"selection-background-color: {C.PRI_GHO}; border: 1px solid {C.BORDER}; }}"
        )

        def _row(label: str, kind: str, current: str) -> QComboBox:
            cap = QLabel(label)
            cap.setFont(QFont("Courier New", 8))
            cap.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            lay.addWidget(cap)

            box = QComboBox()
            box.setFont(QFont("Courier New", 9))
            box.setFixedHeight(30)
            box.setStyleSheet(_combo_css)
            # The list is served from a cache warmed on a background thread at
            # startup, so opening this panel never blocks the Qt thread on the
            # host audio API.
            box.addItem(DEFAULT_LABEL, "")
            for name in list_devices(kind):
                box.addItem(name, name)
            idx = box.findData(current) if current else 0
            box.setCurrentIndex(idx if idx >= 0 else 0)
            if current and idx < 0:
                # Saved device is not plugged in right now. Show it rather than
                # silently resetting the user's choice to default.
                box.addItem(f"{current}  (not connected)", current)
                box.setCurrentIndex(box.count() - 1)
            lay.addWidget(box)
            return box

        self._in_box  = _row("MICROPHONE — what JARVIS hears you with",
                             "input", get_input_device())
        lay.addSpacing(4)
        self._out_box = _row("SPEAKERS — what JARVIS talks through",
                             "output", get_output_device())

        note = QLabel("Applying reconnects the session. Your conversation is kept.")
        note.setWordWrap(True)
        note.setFont(QFont("Courier New", 7))
        note.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addSpacing(6)
        lay.addWidget(note)

        row = QHBoxLayout(); row.setSpacing(8)
        ok = QPushButton("▸  APPLY")
        ok.setFixedHeight(32)
        ok.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px; }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
        """)
        ok.clicked.connect(self._apply)
        row.addWidget(ok)

        cancel = QPushButton("CLOSE")
        cancel.setFixedHeight(32)
        cancel.setFont(QFont("Courier New", 9))
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        cancel.clicked.connect(self.hide)
        row.addWidget(cancel)
        lay.addLayout(row)

    def _apply(self):
        from memory.config_manager import (
            get_input_device, get_output_device,
            save_input_device, save_output_device,
        )
        new_in  = self._in_box.currentData()  or ""
        new_out = self._out_box.currentData() or ""
        changed = (new_in != get_input_device()) or (new_out != get_output_device())
        save_input_device(new_in)
        save_output_device(new_out)
        self.hide()
        # Only rebuild the session if something actually moved — a no-op Apply
        # should not cost a reconnect.
        if changed:
            self.picked.emit()


class MemoryOverlay(_HudOverlay):
    """Everything JARVIS has stored about you, and when it learned it.

    Memory used to be a 2200-character store that deleted its oldest entries
    when full and mentioned it only on stdout. The cap is gone; this panel is
    the other half of that change — a memory you cannot inspect is a memory you
    cannot trust, and 'delete' has to be something the person can do."""

    _OW = 520

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            MemoryOverlay {{
                background: rgba(0, 6, 10, 246);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(20, 16, 20, 16)
        self._lay.setSpacing(5)
        self._rebuild()

    def _clear_layout(self):
        """Take every item out of the layout and detach it from the widget tree
        in this call.

        deleteLater() on its own is not enough: it queues destruction for the
        next event-loop pass, and until then the old rows are still children of
        this widget and still paint — which is what drew half of the previous
        panel over the new one. setParent(None) removes them from the tree now;
        deleteLater() then frees them safely."""
        while self._lay.count():
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None:
                # hide() stops it painting in this frame; deleteLater() frees it
                # safely afterwards. setParent(None) would also stop the paint,
                # but it turns the widget into a top-level window for the moment
                # between the two calls, which is not something to leave lying
                # around inside a click handler.
                w.hide()
                w.deleteLater()
                continue
            sub = item.layout()
            if sub is not None:
                while sub.count():
                    si = sub.takeAt(0)
                    sw = si.widget()
                    if sw is not None:
                        sw.hide()
                        sw.deleteLater()
                sub.deleteLater()

    def _settle(self, before):
        """Size the panel to its content, re-centre it, and repaint what the old
        size covered.

        The re-size has to happen here rather than at the end of _rebuild
        because Qt has not polished the freshly-created children at that point,
        so the size hint it would read is the empty-layout one. Measured: a
        first adjustSize() returned 32 px for a panel whose content needed 155,
        and a second call — after the same widgets had been through the event
        loop — returned 155. So this runs twice: once now, once on the next
        turn, from _rebuild.

        The re-centre and the repaint are needed because the overlay is placed
        by hand and is in no layout: shrinking it leaves it off-centre and
        leaves its former pixels on screen, since nothing tells the parent that
        region changed. The repaint has to cover the union of the old and new
        rectangles."""
        self._lay.invalidate()
        self._lay.activate()
        self.updateGeometry()
        self.adjustSize()

        p = self.parentWidget()
        if p is None:
            self.update()
            return
        self.move(max(0, (p.width()  - self.width())  // 2),
                  max(0, (p.height() - self.height()) // 2))
        p.update(before.united(self.geometry()))
        self.update()

    def _rebuild(self):
        before = self.geometry()
        self._clear_layout()

        from memory.memory_manager import all_entries_for_ui

        hdr = QLabel("🧠  WHAT JARVIS REMEMBERS")
        hdr.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._lay.addWidget(hdr)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        self._lay.addWidget(sep)

        rows = all_entries_for_ui()

        cap = QLabel(f"{len(rows)} stored facts — newest first. "
                     f"Nothing here is sent anywhere; it lives in "
                     f"memory/long_term.json on this machine.")
        cap.setWordWrap(True)
        cap.setFont(QFont("Courier New", 7))
        cap.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._lay.addWidget(cap)

        if not rows:
            empty = QLabel("Nothing stored yet.")
            empty.setFont(QFont("Courier New", 9))
            empty.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            self._lay.addWidget(empty)
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFixedHeight(min(420, 34 * len(rows) + 10))
            scroll.setStyleSheet(
                f"QScrollArea {{ border: 1px solid {C.BORDER}; border-radius: 3px; "
                f"background: transparent; }}"
            )
            inner = QWidget()
            ilay  = QVBoxLayout(inner)
            ilay.setContentsMargins(6, 6, 6, 6)
            ilay.setSpacing(3)

            for r in rows:
                line = QHBoxLayout(); line.setSpacing(6)
                txt = QLabel(f"<b>{r['key'].replace('_', ' ')}</b> "
                             f"<span style='color:{C.TEXT_MED}'>— {r['value']}</span>")
                txt.setWordWrap(True)
                txt.setFont(QFont("Courier New", 8))
                txt.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
                line.addWidget(txt, 1)

                meta = QLabel(f"{r['category'][:4]} · {r['updated'] or '—'}")
                meta.setFont(QFont("Courier New", 7))
                meta.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
                line.addWidget(meta)

                rm = QPushButton("✕")
                rm.setFixedSize(20, 20)
                rm.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
                rm.setCursor(Qt.CursorShape.PointingHandCursor)
                rm.setToolTip("Forget this")
                rm.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                        border: 1px solid {C.BORDER}; border-radius: 3px; }}
                    QPushButton:hover {{ color: {C.RED}; border-color: {C.RED}; }}
                """)
                rm.clicked.connect(
                    lambda _=False, c=r["category"], k=r["key"]: self._forget(c, k))
                line.addWidget(rm)

                holder = QWidget()
                holder.setLayout(line)
                ilay.addWidget(holder)

            ilay.addStretch()
            scroll.setWidget(inner)
            self._lay.addWidget(scroll)

        close = QPushButton("CLOSE")
        close.setFixedHeight(30)
        close.setFont(QFont("Courier New", 9))
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        close.clicked.connect(self.hide)
        self._lay.addWidget(close)

        self._settle(before)
        # …and again once Qt has polished the new children, because the size
        # hint is not final until then. Harmless when the first pass already
        # got it right: _settle is idempotent.
        QTimer.singleShot(0, lambda g=before: self._settle(g))

    def _forget(self, category: str, key: str):
        from memory.memory_manager import forget
        forget(key, category)
        # Rebuild on the NEXT event-loop turn, not inside this click handler.
        # The rebuild destroys the very ✕ button that emitted this signal, and
        # Qt is entitled to touch the sender after a slot returns; tearing it
        # down mid-emission is how a widget ends up half-alive on screen.
        QTimer.singleShot(0, self._rebuild)


class ClipboardPanel(QWidget):
    """Floating panel shown when text is copied — offers quick Jarvis actions."""

    action_requested = pyqtSignal(str)
    _W, _H = 326, 112

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ClipboardPanel {{
                background: rgba(0, 8, 14, 248);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._W)
        self._clip_text = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 7)
        lay.setSpacing(4)

        hdr = QHBoxLayout(); hdr.setSpacing(4)
        icon_lbl = QLabel("◈  CLIPBOARD DETECTED")
        icon_lbl.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        icon_lbl.setStyleSheet(f"color: {C.ACC2}; background: transparent;")
        hdr.addWidget(icon_lbl); hdr.addStretch()
        x_btn = QPushButton("✕")
        x_btn.setFixedSize(16, 16)
        x_btn.setFont(QFont("Courier New", 8))
        x_btn.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        x_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        x_btn.clicked.connect(self.hide)
        hdr.addWidget(x_btn)
        lay.addLayout(hdr)

        self._preview = QLabel()
        self._preview.setFont(QFont("Courier New", 8))
        self._preview.setStyleSheet(f"""
            color: {C.TEXT}; background: {C.PANEL2};
            border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 6px;
        """)
        self._preview.setWordWrap(False)
        self._preview.setFixedHeight(28)
        lay.addWidget(self._preview)

        btn_row = QHBoxLayout(); btn_row.setSpacing(4)
        _bs = (f"QPushButton {{ background: {C.PANEL2}; color: {C.TEXT_MED}; "
               f"border: 1px solid {C.BORDER}; border-radius: 2px; }}"
               f"QPushButton:hover {{ color: {C.PRI}; border-color: {C.BORDER_B}; }}")
        for label, cmd_fmt in [
            ("TRANSLATE", "Translate this text to English: {text}"),
            ("SUMMARISE", "Summarise this: {text}"),
            ("EXPLAIN",   "Explain this: {text}"),
            ("FIX",       "Fix grammar and spelling: {text}"),
        ]:
            b = QPushButton(label)
            b.setFixedHeight(22)
            b.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(_bs)
            b.clicked.connect(lambda _, c=cmd_fmt: self._trigger(c))
            btn_row.addWidget(b)
        lay.addLayout(btn_row)

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self.hide)
        self.hide()

    def _trigger(self, cmd_fmt: str):
        if self._clip_text:
            self.action_requested.emit(cmd_fmt.format(text=self._clip_text[:800]))
        self.hide()

    def show_clipboard(self, text: str):
        self._clip_text = text
        preview = text[:58].replace('\n', ' ')
        if len(text) > 58:
            preview += "…"
        self._preview.setText(f'"{preview}"')
        self.show(); self.raise_()
        self._dismiss_timer.start(8000)


class PluginSettingsOverlay(QWidget):
    """Floating overlay — renders per-plugin settings forms.

    Fully generic: it iterates the settings schemas a plugin declared via its
    PLUGIN_SETTINGS constant (delivered by PluginRegistry.settings_schemas) and
    builds a form for each. It knows NOTHING about any specific plugin, so the
    core stays clean and plugins remain pure drop-in — install a plugin that
    declares fields (e.g. the 3D-printer suite) and its section appears here;
    install none and this panel simply says there's nothing to configure.
    """

    _test_done = pyqtSignal(str, bool, str)   # namespace, ok, message
    _OW = 460

    def __init__(self, sections: list[dict], parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            PluginSettingsOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self._sections = sections or []
        self._widgets: dict[tuple, object] = {}    # (namespace, key) -> input widget
        self._types:   dict[tuple, str]    = {}     # (namespace, key) -> field type
        self._status_labels: dict[str, QLabel] = {} # namespace -> status QLabel
        self._test_done.connect(self._on_test_done)

        self._fs = (f"QLineEdit {{ background: #000d12; color: {C.TEXT}; "
                    f"border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px; }}"
                    f"QLineEdit:focus {{ border: 1px solid {C.PRI}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 16, 22, 16)
        root.setSpacing(8)

        root.addWidget(self._lbl("⚙  PLUGIN SETTINGS", 12, True))
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        root.addWidget(sep)

        if not self._sections:
            root.addWidget(self._lbl(
                "No configurable plugins are installed.\nDrop a plugin that needs "
                "settings (like the 3D-printer suite) into the plugins folder and "
                "it will show up here.", 9, color=C.TEXT_DIM))
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setStyleSheet("QScrollArea { background: transparent; }")
            inner = QWidget()
            inner.setStyleSheet("background: transparent;")
            form = QVBoxLayout(inner)
            form.setContentsMargins(0, 0, 6, 0)
            form.setSpacing(6)
            for sec in self._sections:
                self._build_section(form, sec)
            form.addStretch(1)
            scroll.setWidget(inner)
            root.addWidget(scroll, 1)

        # ── bottom buttons ───────────────────────────────────────────────────
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        if self._sections:
            save_btn = QPushButton("▸  SAVE")
            save_btn.setFixedHeight(34)
            save_btn.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            save_btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {C.PRI};
                    border: 1px solid {C.PRI_DIM}; border-radius: 3px; }}
                QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
            """)
            save_btn.clicked.connect(self._save_all)
            btn_row.addWidget(save_btn)

        close_btn = QPushButton("CLOSE")
        close_btn.setFixedHeight(34)
        close_btn.setFont(QFont("Courier New", 9))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        close_btn.clicked.connect(self.hide)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

    # ── helpers ───────────────────────────────────────────────────────────────
    def _lbl(self, txt, fs=9, bold=False, color=C.PRI,
             align=Qt.AlignmentFlag.AlignLeft):
        w = QLabel(txt); w.setAlignment(align); w.setWordWrap(True)
        w.setFont(QFont("Courier New", fs,
                        QFont.Weight.Bold if bold else QFont.Weight.Normal))
        w.setStyleSheet(f"color: {color}; background: transparent;")
        return w

    def _build_section(self, form: QVBoxLayout, sec: dict):
        ns     = sec.get("namespace") or sec.get("plugin") or "plugin"
        title  = sec.get("title") or ns
        fields = sec.get("fields") or []
        values = sec.get("values") or {}

        form.addSpacing(4)
        form.addWidget(self._lbl(title, 10, True, C.PRI))

        for field in fields:
            if not isinstance(field, dict) or not field.get("key"):
                continue
            key   = field["key"]
            ftype = (field.get("type") or "text").lower()
            label = field.get("label") or key
            default = field.get("default")
            stored  = values.get(key, default)

            form.addWidget(self._lbl(label.upper(), 8, color=C.TEXT_DIM))

            if ftype == "choice":
                w = QComboBox()
                w.addItems([str(o) for o in field.get("options", [])])
                w.setFont(QFont("Courier New", 9))
                w.setFixedHeight(30)
                w.setStyleSheet(
                    f"QComboBox {{ background: #000d12; color: {C.TEXT}; "
                    f"border: 1px solid {C.BORDER}; border-radius: 3px; padding: 2px 8px; }}"
                    f"QComboBox QAbstractItemView {{ background: #000d12; color: {C.TEXT}; "
                    f"selection-background-color: {C.PRI_GHO}; }}")
                if stored is not None:
                    w.setCurrentText(str(stored))
            elif ftype == "toggle":
                w = QPushButton()
                w.setCheckable(True)
                w.setChecked(bool(stored))
                w.setFixedHeight(28)
                w.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
                w.setCursor(Qt.CursorShape.PointingHandCursor)
                self._style_toggle(w)
                w.toggled.connect(lambda _=False, b=w: self._style_toggle(b))
            else:  # text / password
                w = QLineEdit("" if stored is None else str(stored))
                w.setFont(QFont("Courier New", 10))
                w.setFixedHeight(30)
                w.setStyleSheet(self._fs)
                if field.get("placeholder"):
                    w.setPlaceholderText(str(field["placeholder"]))
                if ftype == "password":
                    w.setEchoMode(QLineEdit.EchoMode.Password)

            self._widgets[(ns, key)] = w
            self._types[(ns, key)]   = ftype
            form.addWidget(w)

        # optional test/connect action button + status line
        action = sec.get("action")
        if isinstance(action, dict) and callable(action.get("run")):
            form.addSpacing(2)
            ab = QPushButton(str(action.get("label") or "TEST"))
            ab.setFixedHeight(30)
            ab.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
            ab.setCursor(Qt.CursorShape.PointingHandCursor)
            ab.setStyleSheet(f"""
                QPushButton {{ background: #00091a; color: {C.PRI};
                    border: 1px solid {C.PRI_DIM}; border-radius: 3px; }}
                QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
            """)
            ab.clicked.connect(lambda _=False, n=ns: self._run_action(n))
            form.addWidget(ab)

        status = self._lbl("", 8, color=C.TEXT_DIM)
        self._status_labels[ns] = status
        form.addWidget(status)

        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {C.BORDER}; margin: 4px 0;")
        form.addWidget(line)

    def _style_toggle(self, btn: QPushButton):
        on = btn.isChecked()
        btn.setText("ON" if on else "OFF")
        if on:
            btn.setStyleSheet(f"QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI}; "
                              f"border: 1px solid {C.PRI}; border-radius: 3px; }}")
        else:
            btn.setStyleSheet(f"QPushButton {{ background: transparent; color: {C.TEXT_MED}; "
                              f"border: 1px solid {C.BORDER}; border-radius: 3px; }}")

    # ── data ──────────────────────────────────────────────────────────────────
    def _gather(self, ns: str) -> dict:
        out = {}
        for (n, key), w in self._widgets.items():
            if n != ns:
                continue
            t = self._types.get((n, key), "text")
            if t == "choice":
                out[key] = w.currentText()
            elif t == "toggle":
                out[key] = w.isChecked()
            else:
                out[key] = w.text().strip()
        return out

    def _save_ns(self, ns: str):
        from memory.config_manager import save_plugin_config
        save_plugin_config(ns, self._gather(ns))

    def _save_all(self):
        for sec in self._sections:
            ns = sec.get("namespace") or sec.get("plugin")
            if ns:
                self._save_ns(ns)
                lbl = self._status_labels.get(ns)
                if lbl:
                    lbl.setText("Saved ✓")
                    lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")

    def _run_action(self, ns: str):
        sec = next((s for s in self._sections
                    if (s.get("namespace") or s.get("plugin")) == ns), None)
        if not sec:
            return
        run_fn = (sec.get("action") or {}).get("run")
        if not callable(run_fn):
            return
        self._save_ns(ns)                 # persist what the user typed before testing
        values = self._gather(ns)
        lbl = self._status_labels.get(ns)
        if lbl:
            lbl.setText("Testing…")
            lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")

        def worker():
            try:
                res = run_fn(values)
                if isinstance(res, tuple) and len(res) == 2:
                    ok, msg = bool(res[0]), str(res[1])
                else:
                    ok, msg = bool(res), str(res)
            except Exception as e:
                ok, msg = False, str(e)
            self._test_done.emit(ns, ok, msg)

        threading.Thread(target=worker, daemon=True).start()

    def _on_test_done(self, ns: str, ok: bool, msg: str):
        lbl = self._status_labels.get(ns)
        if not lbl:
            return
        lbl.setText(msg)
        color = C.PRI if ok else "#ff6b6b"
        lbl.setStyleSheet(f"color: {color}; background: transparent;")


class RemoteKeyOverlay(QWidget):
    """Floating overlay — QR code for instant phone pairing + manual key fallback."""

    closed = pyqtSignal()

    _OW, _OH = 400, 465

    def __init__(self, url: str, key: str, auto_login_url: str = "",
                 manual_url: str = "", expiry_secs: int = 600, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            RemoteKeyOverlay {{
                background: rgba(0, 4, 12, 0.95);
                border: 1px solid {C.BORDER_B};
                border-radius: 14px;
            }}
        """)
        self._expiry          = time.time() + expiry_secs
        self._on_new_key      = None
        self._auto_login_url  = auto_login_url
        self._manual_url      = manual_url or url

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 16, 24, 16)
        lay.setSpacing(5)

        def _lbl(txt, fs=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont("Courier New", fs,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            w.setWordWrap(True)
            return w

        lay.addWidget(_lbl("◈  REMOTE ACCESS", 12, True))
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 1px 0;")
        lay.addWidget(sep)

        # ── QR code ───────────────────────────────────────────────────────────
        self._qr_label = QLabel()
        self._qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr_label.setFixedSize(176, 176)
        self._qr_label.setStyleSheet(
            "background: white; border-radius: 10px; padding: 4px;"
        )
        qr_row = QHBoxLayout()
        qr_row.addStretch()
        qr_row.addWidget(self._qr_label)
        qr_row.addStretch()
        lay.addLayout(qr_row)

        self._update_qr(auto_login_url)

        lay.addWidget(_lbl("Scan with phone camera to connect instantly", 8, color=C.TEXT_DIM))

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER}; margin: 1px 0;")
        lay.addWidget(sep2)

        lay.addWidget(_lbl("Or enter manually:", 7, color=C.TEXT_DIM,
                           align=Qt.AlignmentFlag.AlignLeft))

        self._url_lbl = QLabel(self._manual_url)
        self._url_lbl.setFont(QFont("Courier New", 8))
        self._url_lbl.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        self._url_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._url_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._url_lbl)

        self._key_lbl = QLabel(key)
        self._key_lbl.setFont(QFont("Courier New", 28, QFont.Weight.Bold))
        self._key_lbl.setStyleSheet(f"""
            color: {C.ACC};
            background: {C.PANEL2};
            border: 1px solid {C.BORDER_B};
            border-radius: 8px;
            padding: 6px 4px;
            letter-spacing: 10px;
        """)
        self._key_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._key_lbl)

        self._timer_lbl = QLabel()
        self._timer_lbl.setFont(QFont("Courier New", 8))
        self._timer_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._timer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._timer_lbl)

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        new_btn = QPushButton("NEW KEY")
        new_btn.setFixedHeight(32)
        new_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 5px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """)
        new_btn.clicked.connect(self._refresh_key)
        btn_row.addWidget(new_btn)

        close_btn = QPushButton("DISMISS")
        close_btn.setFixedHeight(32)
        close_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 5px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
        """)
        close_btn.clicked.connect(self._do_close)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)

        self._ctimer = QTimer(self)
        self._ctimer.timeout.connect(self._tick)
        self._ctimer.start(1000)
        self._tick()

    def set_new_key_callback(self, fn) -> None:
        self._on_new_key = fn

    def _update_qr(self, url: str) -> None:
        if not url:
            self._qr_label.setText("—")
            return
        try:
            import qrcode as _qrmod
            from io import BytesIO
            qr = _qrmod.QRCode(
                box_size=5, border=2,
                error_correction=_qrmod.constants.ERROR_CORRECT_M,
            )
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = BytesIO()
            img.save(buf, format="PNG")
            px = QPixmap()
            px.loadFromData(buf.getvalue())
            self._qr_label.setPixmap(
                px.scaled(170, 170,
                          Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            )
        except ImportError:
            self._qr_label.setText("pip install\nqrcode[pil]")
            self._qr_label.setFont(QFont("Courier New", 8))
            self._qr_label.setStyleSheet(
                "color: #888; background: white; border-radius: 10px; padding: 4px;"
            )
        except Exception:
            self._qr_label.setText(url[:28])
            self._qr_label.setFont(QFont("Courier New", 7))
            self._qr_label.setStyleSheet(
                f"color: {C.PRI}; background: white; border-radius: 10px; padding: 4px;"
            )

    def _tick(self):
        remaining = max(0, int(self._expiry - time.time()))
        m, s = divmod(remaining, 60)
        self._timer_lbl.setText(f"Key expires in  {m:02d}:{s:02d}")
        if remaining == 0:
            self._do_close()

    def mark_connected(self) -> None:
        """Call from any thread when a phone successfully connects."""
        self._ctimer.stop()
        self._key_lbl.setText("CONNECTED")
        self._key_lbl.setStyleSheet(f"""
            color: {C.GREEN};
            background: rgba(34,197,94,0.08);
            border: 2px solid rgba(34,197,94,0.4);
            border-radius: 8px;
            padding: 6px 4px;
            letter-spacing: 4px;
        """)
        self._qr_label.setText("✓")
        self._qr_label.setFont(QFont("Courier New", 54, QFont.Weight.Bold))
        self._qr_label.setStyleSheet(
            "color: #00ff88; background: #001a0d; border-radius: 10px;"
        )
        self._timer_lbl.setText("Phone connected — JARVIS ready")
        self._timer_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent;")

    def _refresh_key(self):
        if self._on_new_key:
            result = self._on_new_key()
            if result:
                url    = result[0]
                key    = result[1]
                auto   = result[2] if len(result) >= 3 else ""
                manual = result[3] if len(result) >= 4 else url
                self._manual_url     = manual or url
                self._url_lbl.setText(self._manual_url)
                self._key_lbl.setText(key)
                self._auto_login_url = auto
                self._update_qr(auto or url)
                self._expiry = time.time() + 600
                self._key_lbl.setStyleSheet(f"""
                    color: {C.ACC};
                    background: {C.PANEL2};
                    border: 1px solid {C.BORDER_B};
                    border-radius: 8px;
                    padding: 6px 4px;
                    letter-spacing: 10px;
                """)
                self._timer_lbl.setStyleSheet(
                    f"color: {C.TEXT_MED}; background: transparent;"
                )
                self._ctimer.start(1000)
                self._tick()

    def _do_close(self):
        self._ctimer.stop()
        self.hide()
        self.closed.emit()


class ScreenShareDialog(QDialog):
    """Futuristic modal dialog allowing selection of Entire Screen or Specific Window."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mark-LV // Screen Share Setup")
        self.setFixedSize(540, 440)
        self.setModal(True)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {C.DARK};
                border: 1px solid {C.BORDER};
                border-radius: 6px;
            }}
            QLabel {{
                color: {C.TEXT};
                font-family: 'Courier New', monospace;
            }}
            QRadioButton {{
                color: {C.TEXT};
                font-family: 'Courier New', monospace;
                font-size: 13px;
                font-weight: bold;
                spacing: 8px;
            }}
            QRadioButton::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid {C.PRI_DIM};
                border-radius: 8px;
                background: {C.PANEL2};
            }}
            QRadioButton::indicator:checked {{
                background-color: {C.PRI};
                border: 2px solid #ffffff;
            }}
            QComboBox {{
                background-color: {C.PANEL2};
                color: {C.PRI};
                border: 1px solid {C.BORDER};
                border-radius: 4px;
                padding: 6px 10px;
                font-family: 'Courier New', monospace;
                font-size: 12px;
            }}
            QComboBox:hover {{
                border-color: {C.PRI};
            }}
            QComboBox QAbstractItemView {{
                background-color: {C.DARK};
                color: {C.TEXT};
                selection-background-color: {C.PRI_GHO};
                selection-color: {C.PRI};
                border: 1px solid {C.BORDER};
            }}
            QPushButton {{
                background-color: {C.PANEL2};
                color: {C.PRI};
                border: 1px solid {C.BORDER};
                border-radius: 4px;
                padding: 7px 14px;
                font-family: 'Courier New', monospace;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {C.PRI_GHO};
                border-color: {C.PRI};
                color: #ffffff;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        # Header
        hdr = QLabel("◈ SELECT SCREEN SHARE SOURCE")
        hdr.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; border-bottom: 1px solid {C.BORDER}; padding-bottom: 6px;")
        layout.addWidget(hdr)

        # Option 1: Entire Screen
        self._rb_screen = QRadioButton("🖥  Entire Screen (Display)")
        self._rb_screen.setChecked(True)
        layout.addWidget(self._rb_screen)

        self._screen_combo = QComboBox()
        layout.addWidget(self._screen_combo)

        layout.addSpacing(6)

        # Option 2: Selected Window
        win_row = QHBoxLayout()
        self._rb_window = QRadioButton("🪟  Selected Application Window")
        win_row.addWidget(self._rb_window)
        win_row.addStretch()

        self._btn_refresh = QPushButton("↻ REFRESH")
        self._btn_refresh.setFixedWidth(100)
        self._btn_refresh.clicked.connect(self._refresh_targets)
        win_row.addWidget(self._btn_refresh)
        layout.addLayout(win_row)

        self._window_combo = QComboBox()
        layout.addWidget(self._window_combo)

        # Toggle combo enabled states based on radio selection
        self._rb_screen.toggled.connect(self._on_mode_toggled)
        self._rb_window.toggled.connect(self._on_mode_toggled)

        layout.addStretch()

        hint = QLabel("💡 When sharing, JARVIS AI vision actively sees this stream.\nYou can minimize to avatar at any time.")
        hint.setFont(QFont("Courier New", 8))
        hint.setStyleSheet(f"color: {C.TEXT_DIM};")
        layout.addWidget(hint)

        # Bottom action buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)
        btn_box.addStretch()

        self._btn_cancel = QPushButton("✕ Cancel")
        self._btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self._btn_cancel)

        self._btn_start = QPushButton("▶ START SHARING")
        self._btn_start.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(0, 212, 255, 0.15);
                color: {C.PRI};
                border: 1px solid {C.PRI};
                border-radius: 4px;
                padding: 7px 18px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {C.PRI};
                color: #00060a;
            }}
        """)
        self._btn_start.clicked.connect(self._on_start_clicked)
        btn_box.addWidget(self._btn_start)

        layout.addLayout(btn_box)

        self._screen_targets = []
        self._window_targets = []
        self.selected_target = None

        self._refresh_targets()
        self._on_mode_toggled()

    def _refresh_targets(self):
        try:
            from core.screen_share import screen_share_engine
            targets = screen_share_engine.get_share_targets()
        except Exception as e:
            print(f"[ScreenShareDialog] Error fetching targets: {e}")
            targets = []

        self._screen_targets = [t for t in targets if t["type"] == "screen"]
        self._window_targets = [t for t in targets if t["type"] == "window"]

        self._screen_combo.clear()
        for t in self._screen_targets:
            self._screen_combo.addItem(f"{t['name']} ({t.get('detail', '')})", t)

        self._window_combo.clear()
        for t in self._window_targets:
            self._window_combo.addItem(f"{t['name']}", t)

        if not self._window_targets:
            self._window_combo.addItem("No open application windows detected", None)
            self._window_combo.setEnabled(False)
        else:
            self._window_combo.setEnabled(self._rb_window.isChecked())

    def _on_mode_toggled(self):
        is_screen = self._rb_screen.isChecked()
        self._screen_combo.setEnabled(is_screen)
        self._window_combo.setEnabled(not is_screen and len(self._window_targets) > 0)

    def _on_start_clicked(self):
        if self._rb_screen.isChecked():
            self.selected_target = self._screen_combo.currentData()
        else:
            self.selected_target = self._window_combo.currentData()

        if self.selected_target:
            self.accept()
        else:
            self.reject()


class MainWindow(QMainWindow):
    _log_sig        = pyqtSignal(str)
    _state_sig      = pyqtSignal(str)
    _content_sig    = pyqtSignal(str, str)   # (title, text) — thread-safe content display
    _reconfig_sig   = pyqtSignal()           # trigger setup overlay from any thread
    _camera_sig     = pyqtSignal(bytes)      # show camera frame preview (small overlay)
    _cam_stream_sig = pyqtSignal(bool)       # True=start live stream, False=stop
    _cam_frame_sig  = pyqtSignal(bytes)      # live camera frame → HUD area
    _video_open_sig  = pyqtSignal(str, str, bool, str)  # video, title, muted, audio
    _wake_btns_sig   = pyqtSignal()          # wake state resolved off-thread
    _video_close_sig = pyqtSignal()
    _video_mute_sig  = pyqtSignal(bool)
    _clipboard_sig  = pyqtSignal(str)        # clipboard text changed (thread-safe)
    _confirm_sig    = pyqtSignal(str, str)   # (title, detail) — irreversible-action gate
    _confirm_hide_sig = pyqtSignal()
    _wake_dl_sig    = pyqtSignal(bool, str)  # wake-word install finished (ok, message)
    _quiz_sig       = pyqtSignal(str, object, object)  # (topic, questions, grader)
    _quiz_hide_sig  = pyqtSignal()
    _review_sig     = pyqtSignal(str, str, object, object)  # document review payload
    _screenshare_frame_sig = pyqtSignal(bytes)  # live screen share frame → HUD area
    _screenshare_open_dlg_sig = pyqtSignal()
    _screenshare_start_sig = pyqtSignal(dict)
    _screenshare_stop_sig = pyqtSignal()

    def write_log(self, text: str) -> None:
        self._log_sig.emit(str(text))

    def __init__(self, face_path: str):
        super().__init__()
        self._face_path = face_path

        # Load customization from config
        _cfg = _read_full_config()
        self._assistant_name: str = (_cfg.get("assistant_name") or "JARVIS").strip()
        _display = self._assistant_name.upper()

        # Apply the saved UI colour BEFORE panels/stylesheets are built
        _ui_color = (_cfg.get("ui_color") or "").strip()
        if _ui_color and _ui_color.lower() != DEFAULT_UI_COLOR:
            apply_ui_accent(_ui_color)

        self.setWindowTitle(f"{_display} — {APP_VERSION}")
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        _ico_path = CONFIG_DIR / "jarvis.png"
        if not _ico_path.exists():
            _ico_path = CONFIG_DIR / "jarvis.ico"
        if _ico_path.exists():
            try:
                _app_icon = QIcon(str(_ico_path))
                self.setWindowIcon(_app_icon)
                _q_app = QApplication.instance()
                if _q_app:
                    _q_app.setWindowIcon(_app_icon)
            except Exception:
                pass

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width()  - _DEFAULT_W) // 2,
            (screen.height() - _DEFAULT_H) // 2,
        )

        self.on_text_command   = None
        self.on_remote_clicked = None   # callable: () -> (url, key) | None
        self.on_interrupt      = None   # callable: () -> None — stop JARVIS mid-speech
        self.on_voice_change   = None   # callable: () -> None — rebuild session with new voice
        self.on_audio_device_change = None  # callable: () -> None — reopen audio streams
        self._confirm_overlay  = None   # live ConfirmBanner, if one is on screen
        self.get_plugins       = None   # callable: () -> list[dict], set by JarvisLive
        self.get_plugin_settings = None # callable: () -> list[dict] settings schemas, set by JarvisLive
        self.on_wake_toggle    = None   # callable: (enable: bool) -> str, set by JarvisLive
        self.on_wake_manual    = None   # callable: () -> None — manual sleep/wake
        self.on_push_to_talk   = None   # callable: (enable: bool) -> str scope
        self.ptt_hold          = None   # callable: (held: bool) -> None — windowed chord
        self.wake_get_state    = None   # callable: () -> dict {enabled, awake, ready}
        self._muted            = False
        self._current_file: str | None = None
        self._remote_overlay: RemoteKeyOverlay | None = None
        self._customize_overlay: CustomizeOverlay | None = None

        central = QWidget()
        central.setStyleSheet(f"background: {C.BG};")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        # Left panel (SYS MONITOR) removed from UI per user request
        self._left_panel = None

        # Center column: HUD + resizable content panel via QSplitter
        self.hud = HudCanvas(face_path, _display)
        self.hud.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._content_panel = self._build_content_panel()
        self._quiz_panel = self._build_quiz_panel()

        # Live camera container — replaces HUD when camera stream is active
        _cam_cont = QWidget()
        _cam_cont.setStyleSheet("background: #000308;")
        _cam_v = QVBoxLayout(_cam_cont)
        _cam_v.setContentsMargins(0, 0, 0, 0)
        _cam_v.setSpacing(0)
        _cam_hdr = QHBoxLayout()
        _cam_hdr.setContentsMargins(8, 5, 8, 5)
        _cam_title = QLabel("◈  CAMERA FEED")
        _cam_title.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        _cam_title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        _cam_hdr.addWidget(_cam_title)
        _cam_hdr.addStretch()
        _cam_x = QPushButton("✕  CLOSE")
        _cam_x.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        _cam_x.setCursor(Qt.CursorShape.PointingHandCursor)
        _cam_x.setStyleSheet(f"""
            QPushButton {{
                color: {C.TEXT_DIM}; background: transparent;
                border: none; padding: 2px 6px;
            }}
            QPushButton:hover {{ color: {C.PRI}; }}
        """)
        _cam_x.clicked.connect(self.stop_camera_stream)
        _cam_hdr.addWidget(_cam_x)
        _cam_v.addLayout(_cam_hdr)
        self._cam_live_lbl = QLabel()
        self._cam_live_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cam_live_lbl.setStyleSheet("background: transparent;")
        self._cam_live_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        _cam_v.addWidget(self._cam_live_lbl, stretch=1)

        # ── Video surface ────────────────────────────────────────────────
        # Built exactly like the camera page above and stacked beside it,
        # because it is the same idea: something takes the centre of the HUD
        # for a while and then gives it back. Sharing the stack rather than
        # inventing a second mechanism means the avatar, the camera and a video
        # can never be on screen at once.
        self._video_split = False        # is the sound a separate stream?
        self._video_auto_muted = False   # did JARVIS close the mic, or the user?
        # A plain flag rather than reading the widget. video_is_playing() is
        # called from plugin threads, and reading a widget's state from one is
        # not something to rely on; an attribute is.
        self._video_on = False
        self._video_cont = QWidget()
        self._video_cont.setStyleSheet(f"background: {C.BG};")
        _vid_v = QVBoxLayout(self._video_cont)
        _vid_v.setContentsMargins(8, 6, 8, 8)
        _vid_v.setSpacing(4)

        _vid_hdr = QHBoxLayout()
        self._video_title = QLabel("▶  VIDEO")
        self._video_title.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        self._video_title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        _vid_hdr.addWidget(self._video_title)
        _vid_hdr.addStretch()

        def _vid_btn(text: str) -> QPushButton:
            b = QPushButton(text)
            b.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{
                    color: {C.TEXT_DIM}; background: transparent;
                    border: none; padding: 2px 6px;
                }}
                QPushButton:hover {{ color: {C.PRI}; }}
            """)
            return b

        # Muted is the default and the button says so, because a soundtrack
        # talking over JARVIS is the one way this feature could make the
        # assistant worse rather than better.
        self._video_mute_btn = _vid_btn("🔇  SOUND OFF")
        self._video_mute_btn.clicked.connect(self._toggle_video_mute)
        _vid_hdr.addWidget(self._video_mute_btn)

        self._vid_expand_btn = _vid_btn("⛶  EXPAND")
        self._vid_expand_btn.clicked.connect(self._toggle_expand_center)
        _vid_hdr.addWidget(self._vid_expand_btn)

        _vid_x = _vid_btn("✕  CLOSE")
        _vid_x.clicked.connect(self.stop_video)
        _vid_hdr.addWidget(_vid_x)
        _vid_v.addLayout(_vid_hdr)

        if HAVE_VIDEO:
            # A GRAPHICS ITEM, NOT A QVideoWidget.
            #
            # QVideoWidget gets a native window of its own, and a native window
            # is painted by the compositor above every ordinary widget that
            # shares the screen with it — so the settings drawer opened
            # *underneath* the video and raise_() could not help, because the
            # two are not in the same painting order at all. A video item drawn
            # into a QGraphicsView goes through Qt's own painter like any other
            # widget, and anything laid over it stays over it.
            self._video_scene = QGraphicsScene(self)
            self._video_item = QGraphicsVideoItem()
            self._video_scene.addItem(self._video_item)
            self._video_widget = QGraphicsView(self._video_scene)
            self._video_widget.setStyleSheet("background: #000; border: none;")
            self._video_widget.setFrameShape(QGraphicsView.Shape.NoFrame)
            self._video_widget.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._video_widget.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._video_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            _vid_v.addWidget(self._video_widget, stretch=1)

            self._video_audio = QAudioOutput()
            self._video_audio.setMuted(True)
            self._video_player = QMediaPlayer()
            self._video_player.setVideoOutput(self._video_item)
            # Keep the picture filling the view as the window is resized.
            self._video_item.nativeSizeChanged.connect(self._fit_video)
            self._video_player.setAudioOutput(self._video_audio)
            self._video_player.errorOccurred.connect(self._on_video_error)

            # A SECOND player, for sound that arrives separately.
            #
            # YouTube no longer serves a single stream carrying both picture and
            # sound — not for new uploads and not for old ones; checked against
            # three videos including the oldest on the site, and every one of
            # them offered zero combined formats. Picture and sound are two
            # URLs, so they are two players, started together and nudged back
            # into line by the timer below.
            #
            # A local file or a direct video URL still uses the first player
            # alone: one stream, one player, nothing to synchronise.
            self._video_sound = QMediaPlayer()
            self._video_sound_out = QAudioOutput()
            self._video_sound_out.setMuted(True)
            self._video_sound.setAudioOutput(self._video_sound_out)

            self._video_sync = QTimer(self)
            self._video_sync.setInterval(1000)
            self._video_sync.timeout.connect(self._sync_video_sound)
        else:
            self._video_scene = None
            self._video_item = None
            self._video_widget = None
            self._video_player = None
            self._video_audio = None
            self._video_sound = None
            self._video_sound_out = None
            self._video_sync = None
            _miss = QLabel("Video playback is not available in this Qt install.")
            _miss.setAlignment(Qt.AlignmentFlag.AlignCenter)
            _miss.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            _vid_v.addWidget(_miss, stretch=1)

        # ── Screen Share surface ──────────────────────────────────────────
        self._screenshare_cont = QWidget()
        self._screenshare_cont.setStyleSheet("background: #000308;")
        _ss_v = QVBoxLayout(self._screenshare_cont)
        _ss_v.setContentsMargins(0, 0, 0, 0)
        _ss_v.setSpacing(0)
        _ss_hdr_w = QWidget()
        _ss_hdr_w.setStyleSheet(f"background: {C.PANEL2}; border-bottom: 1px solid {C.BORDER};")
        _ss_hdr = QHBoxLayout(_ss_hdr_w)
        _ss_hdr.setContentsMargins(10, 6, 10, 6)
        self._ss_title = QLabel("◈  SCREEN SHARING: ENTIRE SCREEN")
        self._ss_title.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        self._ss_title.setStyleSheet(f"color: {C.ACC}; background: transparent;")
        _ss_hdr.addWidget(self._ss_title)
        _ss_hdr.addStretch()

        _ss_min = QPushButton("👁  MINIMIZE TO AVATAR")
        _ss_min.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        _ss_min.setCursor(Qt.CursorShape.PointingHandCursor)
        _ss_min.setStyleSheet(f"""
            QPushButton {{
                color: {C.PRI}; background: transparent;
                border: 1px solid {C.PRI_DIM}; border-radius: 3px; padding: 3px 8px; margin-right: 6px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; color: #ffffff; }}
        """)
        _ss_min.clicked.connect(self._minimize_screen_share)
        _ss_hdr.addWidget(_ss_min)

        self._ss_expand_btn = QPushButton("⛶  EXPAND")
        self._ss_expand_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._ss_expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ss_expand_btn.setStyleSheet(f"""
            QPushButton {{
                color: {C.PRI}; background: {C.PRI_GHO};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 3px 10px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {C.PRI_DIM}; color: #ffffff; }}
        """)
        self._ss_expand_btn.clicked.connect(self._toggle_expand_center)
        _ss_hdr.addWidget(self._ss_expand_btn)

        _ss_stop = QPushButton("■  STOP SHARING")
        _ss_stop.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        _ss_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        _ss_stop.setStyleSheet(f"""
            QPushButton {{
                color: #ff4466; background: rgba(255, 68, 102, 0.12);
                border: 1px solid #ff4466; border-radius: 3px; padding: 3px 10px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #ff4466; color: #ffffff; }}
        """)
        _ss_stop.clicked.connect(self.stop_screen_share)
        _ss_hdr.addWidget(_ss_stop)
        _ss_v.addWidget(_ss_hdr_w)

        self._ss_live_lbl = QLabel()
        self._ss_live_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ss_live_lbl.setStyleSheet("background: #000407;")
        self._ss_live_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        _ss_v.addWidget(self._ss_live_lbl, stretch=1)

        # Center Stack: 0 = 3D Gantry turntable, 1 = live camera, 2 = video, 3 = screen share
        self.gantry_viewer = self.hud.gantry_viewer
        self._hud_cam_stack = self.hud.center_stack
        self._hud_cam_stack.addWidget(_cam_cont)
        self._hud_cam_stack.addWidget(self._video_cont)
        self._hud_cam_stack.addWidget(self._screenshare_cont)

        # Lower monitoring pods (Activity stream on left, System telemetry on right)
        self._pods_container = QWidget()
        self._pods_container.setStyleSheet(f"background: {C.BG};")
        _pods_lay = QHBoxLayout(self._pods_container)
        _pods_lay.setContentsMargins(12, 4, 12, 6)
        _pods_lay.setSpacing(10)

        self._log = LogWidget()
        self._system_telemetry = SystemContextPanel()
        _pods_lay.addWidget(self._log, stretch=3)
        _pods_lay.addWidget(self._system_telemetry, stretch=2)

        self._main_splitter = QSplitter(Qt.Orientation.Vertical)
        self._main_splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background: {C.BORDER};
                height: 3px;
            }}
            QSplitter::handle:hover {{
                background: {C.PRI_DIM};
            }}
        """)
        self._main_splitter.addWidget(self.hud)
        self._main_splitter.addWidget(self._content_panel)
        self._main_splitter.addWidget(self._quiz_panel)
        self._main_splitter.addWidget(self._pods_container)
        self._main_splitter.setStretchFactor(0, 5)  # Dominant 3D Avatar space
        self._main_splitter.setStretchFactor(1, 0)
        self._main_splitter.setStretchFactor(2, 0)
        self._main_splitter.setStretchFactor(3, 3)  # Lower monitoring pods
        self._main_splitter.setCollapsible(0, False)
        self._main_splitter.setCollapsible(3, False)
        self._main_splitter.setSizes([450, 0, 0, 220])
        self._center_split = self._main_splitter  # For backward-compatibility

        root.addWidget(self._main_splitter, stretch=1)

        # Command Cockpit console docked at bottom
        self._command_cockpit = CommandCockpit()
        self._command_cockpit.send_requested.connect(lambda _: self._send())
        self._command_cockpit.interrupt_requested.connect(self._do_interrupt)
        self._command_cockpit.mute_toggled.connect(self._toggle_mute)
        self._command_cockpit.file_selected.connect(self._on_file_selected)
        self._command_cockpit.file_cleared.connect(self._on_file_cleared)
        root.addWidget(self._command_cockpit)

        # Retain backward-compatible references
        self._drop_zone     = self._command_cockpit
        self._input         = self._command_cockpit._input
        self._interrupt_btn = self._command_cockpit._interrupt_btn
        self._mute_btn      = self._command_cockpit._mute_btn
        self._file_hint     = self._command_cockpit._top_hint
        self._right_panel   = None

        root.addWidget(self._build_footer())

        # Quick-access drawer (floating overlay, built after central widget layout is done)
        self._quick_drawer = self._build_quick_drawer()
        self._ctrl_drawer = self._build_controls_drawer()
        self._warm_wake_state()
        self._update_autostart_btn(self._check_autostart())
        from memory.config_manager import get_brief_enabled as _gbe
        self._update_brief_btn(_gbe())

        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        # Metric update timer (disabled: sys monitor removed from UI)
        self._metric_tmr = QTimer(self)

        self._log_sig.connect(self._log.append_log)
        self._state_sig.connect(self._apply_state)
        self._content_sig.connect(self._show_content)
        self._reconfig_sig.connect(self._show_setup)
        self._camera_sig.connect(self._show_camera_frame)
        self._confirm_sig.connect(self._show_confirm_banner)
        self._confirm_hide_sig.connect(self._hide_confirm_banner)
        self._cam_stream_sig.connect(self._on_cam_stream)
        self._cam_frame_sig.connect(self._on_cam_frame)
        self._wake_btns_sig.connect(self._refresh_wake_btns)
        self._video_open_sig.connect(self._on_video_open)
        self._video_close_sig.connect(self._on_video_close)
        self._video_mute_sig.connect(self._on_video_mute)
        self._clipboard_sig.connect(self._show_clipboard_panel)
        self._wake_dl_sig.connect(self._on_wake_install_done)
        self._quiz_sig.connect(self._show_quiz)
        self._quiz_hide_sig.connect(self._hide_quiz)
        self._review_sig.connect(self._show_review)
        self._screenshare_frame_sig.connect(self._on_screenshare_frame)
        self._screenshare_open_dlg_sig.connect(self._open_screen_share_dialog)
        self._screenshare_start_sig.connect(self.start_screen_share)
        self._screenshare_stop_sig.connect(self.stop_screen_share)
        self._cam_stop = threading.Event()
        self._ss_stop = threading.Event()

        # Camera preview overlay (child of central widget, positioned in resizeEvent)
        self._cam_preview = _CameraPreview(self.centralWidget())

        # Clipboard panel (child of central widget, bottom-center)
        self._clipboard_panel = ClipboardPanel(self.centralWidget())
        self._clipboard_panel.action_requested.connect(self._on_clipboard_action)
        QApplication.clipboard().dataChanged.connect(self._on_clipboard_changed)

        self._overlay: SetupOverlay | None = None
        self._ready = self._check_config()
        if not self._ready:
            self._show_setup()

        sc_mute = QShortcut(QKeySequence("F4"), self)
        sc_mute.activated.connect(self._toggle_mute)
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)
        sc_intr = QShortcut(QKeySequence("Escape"), self)
        sc_intr.activated.connect(self._do_interrupt)

    def _show_camera_frame(self, img_bytes: bytes):
        """Slot — display camera preview overlay (main thread)."""
        self._cam_preview.show_frame(img_bytes)
        cw = self.centralWidget()
        pw = _CameraPreview._W
        ph = self._cam_preview.height()
        self._cam_preview.setGeometry(
            cw.width() - _RIGHT_W - pw - 12,
            cw.height() - ph - 28,
            pw, ph,
        )

    # --- Live camera stream in HUD area ------------------------------------
    def _on_cam_stream(self, start: bool) -> None:
        if start:
            self._hud_cam_stack.setCurrentIndex(1)
        else:
            self._hud_cam_stack.setCurrentIndex(0)
            self._cam_live_lbl.clear()

    def _on_cam_frame(self, data: bytes) -> None:
        px = QPixmap()
        px.loadFromData(data)
        if not px.isNull():
            w, h = self._cam_live_lbl.width(), self._cam_live_lbl.height()
            if w > 1 and h > 1:
                self._cam_live_lbl.setPixmap(
                    px.scaled(w, h,
                              Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
                )

    def start_camera_stream(self) -> None:
        self._cam_stop.clear()
        self._cam_stream_sig.emit(True)
        t = threading.Thread(target=self._cam_loop, daemon=True, name="cam-stream")
        t.start()

    def _cam_loop(self) -> None:
        try:
            import cv2
            # Reuse camera index detected by screen_processor (cached in api_keys.json)
            cam_idx = 0
            try:
                import json as _j
                cfg = _j.loads((CONFIG_DIR / "api_keys.json").read_text())
                cam_idx = int(cfg.get("camera_index", 0))
            except Exception:
                pass
            try:
                backend = cv2.CAP_DSHOW if _OS == "Windows" else cv2.CAP_ANY
            except AttributeError:
                backend = 0
            cap = cv2.VideoCapture(cam_idx, backend)
            if not cap.isOpened():
                cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return
            # warm-up frames
            for _ in range(5):
                cap.read()
            while not self._cam_stop.wait(0.033) and cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
                    self._cam_frame_sig.emit(buf.tobytes())
            cap.release()
        except Exception as e:
            print(f"[Camera] Stream error: {e}")
        finally:
            self._cam_stream_sig.emit(False)

    def stop_camera_stream(self) -> None:
        self._cam_stop.set()

    # --- Screen & Window Share in the HUD area -----------------------------
    def _open_screen_share_dialog(self) -> None:
        from core.screen_share import screen_share_engine
        if screen_share_engine.is_sharing():
            if self._hud_cam_stack.currentIndex() != 3:
                # If currently minimized, clicking the button restores view to the screen share stream
                self._hud_cam_stack.setCurrentIndex(3)
                self._screenshare_btn.setText("● STOP SHARE")
                return
            self.stop_screen_share()
            return

        dlg = ScreenShareDialog(self)
        if dlg.exec() and hasattr(dlg, "selected_target") and dlg.selected_target:
            self.start_screen_share(dlg.selected_target)

    def start_screen_share(self, target: dict = None) -> None:
        from core.screen_share import screen_share_engine
        if target is None:
            screens = screen_share_engine.get_screens()
            target = screens[0] if screens else {"type": "screen", "index": 0, "name": "Primary Display"}
        # Stop camera if active
        self._cam_stop.set()
        screen_share_engine.start_sharing(target)
        self._ss_stop.clear()
        target_name = target.get("name", "Screen")
        self._ss_title.setText(f"◈  SCREEN SHARING: {target_name.upper()}")
        self._hud_cam_stack.setCurrentIndex(3)
        self._screenshare_btn.setText("● STOP SHARE")
        self._screenshare_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255, 68, 102, 0.18); color: #ff4466;
                border: 1px solid #ff4466; border-radius: 4px; padding: 2px 10px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #ff4466; color: #ffffff; }}
        """)
        self.write_log(f"SYS: Started screen share: {target_name}")

        t = threading.Thread(target=self._screenshare_loop, daemon=True, name="ss-stream")
        t.start()

    def _screenshare_loop(self) -> None:
        from core.screen_share import screen_share_engine
        try:
            import cv2
            while not self._ss_stop.wait(0.04):  # ~25 FPS
                frame = screen_share_engine.capture_frame()
                if frame is not None and frame.size > 0:
                    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                    self._screenshare_frame_sig.emit(buf.tobytes())
        except Exception as e:
            print(f"[ScreenShare] Loop error: {e}")

    def _on_screenshare_frame(self, frame_bytes: bytes) -> None:
        pix = QPixmap()
        if pix.loadFromData(frame_bytes):
            lbl_sz = self._ss_live_lbl.size()
            if lbl_sz.width() > 10 and lbl_sz.height() > 10:
                self._ss_live_lbl.setPixmap(
                    pix.scaled(
                        lbl_sz,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )

    def _minimize_screen_share(self) -> None:
        self._hud_cam_stack.setCurrentIndex(0)
        self._screenshare_btn.setText("● SHARING (VIEW)")
        self.write_log("SYS: Screen share minimized to HUD avatar.")

    def stop_screen_share(self) -> None:
        from core.screen_share import screen_share_engine
        self._ss_stop.set()
        screen_share_engine.stop_sharing()
        if self._hud_cam_stack.currentIndex() == 3:
            self._hud_cam_stack.setCurrentIndex(0)
        if hasattr(self, "hud") and hasattr(self.hud, "set_side_panels_visible"):
            self.hud.set_side_panels_visible(True)
        if hasattr(self, "_ss_expand_btn"):
            self._ss_expand_btn.setText("⛶  EXPAND")
        self._screenshare_btn.setText("📺  SHARE SCREEN")
        self._screenshare_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.BORDER}; border-radius: 4px; padding: 2px 10px;
            }}
            QPushButton:hover {{ color: #ffffff; border-color: {C.PRI}; background: {C.PRI_GHO}; }}
        """)
        self._ss_live_lbl.clear()
        self.write_log("SYS: Screen sharing stopped.")

    def _toggle_expand_center(self) -> None:
        """Toggle side HUD and Avatar wings on/off to give full width to center stage."""
        if hasattr(self, "hud") and hasattr(self.hud, "toggle_side_panels"):
            side_vis = self.hud.toggle_side_panels()
            txt = "⛶  EXPAND" if side_vis else "❐  RESTORE"
            if hasattr(self, "_vid_expand_btn"):
                self._vid_expand_btn.setText(txt)
            if hasattr(self, "_ss_expand_btn"):
                self._ss_expand_btn.setText(txt)

    # --- Video in the HUD area ---------------------------------------------
    #
    # Everything below runs on the Qt thread. Plugins and the assistant reach it
    # through the signals above, the same way every other panel is driven, so a
    # background thread never touches a widget.
    def _on_video_open(self, source: str, title: str, muted: bool,
                       audio_source: str = "") -> None:
        if not HAVE_VIDEO or not self._video_player:
            self.write_log("SYS: Video playback is not available in this Qt "
                           "install.")
            return
        # A video and the live camera cannot share the centre of the HUD.
        self._cam_stop.set()

        self._video_title.setText(f"▶  {(title or 'VIDEO')[:44].upper()}")
        self._video_split = bool(audio_source)
        self._set_video_muted(bool(muted))

        url = (QUrl.fromLocalFile(source) if Path(source).exists()
               else QUrl(source))
        self._video_player.setSource(url)
        if self._video_split:
            self._video_sound.setSource(QUrl(audio_source))
        self._hud_cam_stack.setCurrentIndex(2)
        self._video_on = True
        # Re-run now that the video counts as playing: _set_video_muted ran
        # before this line and saw no video, so its mic check was a no-op.
        self._sync_mic_for_video()
        self._video_player.play()
        if self._video_split:
            self._video_sound.play()
            self._video_sync.start()

    def _fit_video(self, *_a) -> None:
        """Size the picture to the panel, keeping its shape."""
        if not (self._video_item and self._video_widget):
            return
        try:
            native = self._video_item.nativeSize()
            if native.isEmpty():
                return
            view = self._video_widget.viewport().size()
            scale = min(view.width() / native.width(),
                        view.height() / native.height())
            w, h = native.width() * scale, native.height() * scale
            self._video_item.setSize(QSizeF(w, h))
            self._video_scene.setSceneRect(0, 0, w, h)
            self._video_widget.centerOn(self._video_item)
        except Exception:
            pass

    def _on_video_close(self) -> None:
        if self._video_sync:
            self._video_sync.stop()
        self._last_sound_seek = 0
        for p in (self._video_player, self._video_sound):
            if p:
                p.stop()
                p.setSource(QUrl())
        self._video_split = False
        self._video_on = False
        self._hud_cam_stack.setCurrentIndex(0)
        if hasattr(self, "hud") and hasattr(self.hud, "set_side_panels_visible"):
            self.hud.set_side_panels_visible(True)
        if hasattr(self, "_vid_expand_btn"):
            self._vid_expand_btn.setText("⛶  EXPAND")
        self._sync_mic_for_video()      # gives the microphone back

    def _set_video_muted(self, muted: bool) -> None:
        """Silence whichever output is carrying the sound for this video."""
        muted = bool(muted)
        if self._video_audio:
            # When the sound is a separate stream this player has none, but
            # muting it too costs nothing and keeps the two paths identical.
            self._video_audio.setMuted(muted)
        if self._video_sound_out:
            self._video_sound_out.setMuted(muted)
        self._sync_video_mute_btn()
        self._sync_mic_for_video()

    def _on_video_mute(self, muted: bool) -> None:
        self._set_video_muted(muted)

    def _sync_mic_for_video(self) -> None:
        """Close the microphone while the video is making sound.

        JARVIS subtracts its OWN output from the microphone — that is what
        core/echo.py does — but a video plays through a different output
        entirely, so the guard has never heard of it and the assistant answers
        the film. There is no arrangement in which an open microphone and a
        loudspeaker in the same room do not do that.

        So the microphone closes for exactly as long as the sound is on, and
        opens again by itself the moment it goes off or the video is closed.
        Only if JARVIS closed it: a microphone the user muted themselves stays
        muted, and pressing the mute key during a video hands the decision back
        to them for good.
        """
        sound_on = bool(self._video_on and self._video_sound_out
                        and not self._video_sound_out.isMuted())
        if sound_on and not self._muted:
            self._video_auto_muted = True
            self._set_muted(True, "The video's sound is on — silence it, close "
                                  "it, or press F4 to talk. Typing still works.")
        elif not sound_on and self._video_auto_muted:
            self._video_auto_muted = False
            self._set_muted(False, "The video is quiet again.")

    def _sync_video_sound(self) -> None:
        """Keep the separate soundtrack in step with the picture.

        Two players started at the same moment do not stay together: they buffer
        independently. We pause the soundtrack while the picture is buffering
        so it never runs ahead, and gently nudge it if a noticeable drift
        (> 1200ms) accumulates, with a cooldown so network seeks never cascade
        into repeated buffering and stutter.
        """
        if not (self._video_split and self._video_sound and self._video_player):
            return
        try:
            if self._video_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                return

            v_status = self._video_player.mediaStatus()
            a_status = self._video_sound.mediaStatus()

            # If the picture is buffering or stalled, pause audio so it doesn't run ahead
            if v_status in (QMediaPlayer.MediaStatus.BufferingMedia, QMediaPlayer.MediaStatus.StalledMedia):
                if self._video_sound.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                    self._video_sound.pause()
                return

            # If picture resumed playing, ensure audio is playing too
            if self._video_sound.playbackState() == QMediaPlayer.PlaybackState.PausedState:
                self._video_sound.play()

            # If audio itself is buffering, don't calculate drift or seek
            if a_status in (QMediaPlayer.MediaStatus.BufferingMedia, QMediaPlayer.MediaStatus.StalledMedia):
                return

            # Rate limit seeks: maximum once every 3 seconds to prevent seek storms
            now = time.time()
            if hasattr(self, "_last_sound_seek") and (now - self._last_sound_seek) < 3.0:
                return

            drift = self._video_sound.position() - self._video_player.position()
            if abs(drift) > 1200:
                self._last_sound_seek = now
                self._video_sound.setPosition(self._video_player.position())
        except Exception:
            pass

    def _sync_video_mute_btn(self) -> None:
        out = self._video_sound_out if self._video_split else self._video_audio
        muted = bool(out and out.isMuted())
        self._video_mute_btn.setText("🔇  SOUND OFF" if muted else "🔊  SOUND ON")

    def _toggle_video_mute(self) -> None:
        out = self._video_sound_out if self._video_split else self._video_audio
        if out:
            self._set_video_muted(not out.isMuted())

    def _on_video_error(self, *_a) -> None:
        err = ""
        try:
            err = self._video_player.errorString()
        except Exception:
            pass
        self.write_log(f"SYS: The video could not be played{(' — ' + err) if err else ''}.")
        self._on_video_close()

    def stop_video(self) -> None:
        self._video_close_sig.emit()

    def video_is_playing(self) -> bool:
        return bool(self._video_on)

    # ------------------------------------------------------------------
    # Icon generation — arc-reactor style, rendered with Pillow
    # ------------------------------------------------------------------
    @staticmethod
    def _build_jarvis_icon(out_path: Path) -> bool:
        """
        Render a JARVIS arc-reactor icon at 4× resolution and downsample
        for crisp results at all sizes. Saves a multi-res .ico to out_path.
        Returns True on success.
        """
        try:
            import math
            import PIL.Image
            import PIL.ImageDraw
            import PIL.ImageFilter
        except ImportError:
            return False

        CYAN   = (0, 212, 255)
        DIM    = (0, 100, 140)
        DARK   = (0, 6, 10)
        GLOW   = (0, 160, 200)
        WHITE  = (220, 240, 255)

        def _render(sz: int) -> PIL.Image.Image:
            S  = sz * 4                     # draw at 4× then downscale
            img = PIL.Image.new("RGBA", (S, S), (0, 0, 0, 0))
            d   = PIL.ImageDraw.Draw(img)
            cx = cy = S // 2

            # ── filled background circle ──────────────────────────────────
            R = S // 2 - 2
            d.ellipse([cx-R, cy-R, cx+R, cy+R], fill=(*DARK, 255))

            # ── outer border ring ─────────────────────────────────────────
            lw = max(2, S // 40)
            d.ellipse([cx-R, cy-R, cx+R, cy+R],
                      outline=(*CYAN, 220), width=lw)

            # ── mid decorative ring ───────────────────────────────────────
            R2 = int(R * 0.72)
            d.ellipse([cx-R2, cy-R2, cx+R2, cy+R2],
                      outline=(*DIM, 180), width=max(1, lw // 2))

            # ── 6 radial spokes (hex bolt) ────────────────────────────────
            R_inner = int(R * 0.30)
            R_outer = int(R * 0.62)
            spoke_w = max(1, S // 80)
            for i in range(6):
                angle = math.radians(i * 60 - 30)
                x1 = cx + int(R_inner * math.cos(angle))
                y1 = cy + int(R_inner * math.sin(angle))
                x2 = cx + int(R_outer * math.cos(angle))
                y2 = cy + int(R_outer * math.sin(angle))
                d.line([x1, y1, x2, y2], fill=(*GLOW, 200), width=spoke_w)

            # ── 6 tick marks on outer ring ────────────────────────────────
            for i in range(6):
                angle = math.radians(i * 60)
                for dr in range(lw * 2):
                    rx = (R - lw - dr)
                    d.point(
                        [cx + int(rx * math.cos(angle)),
                         cy + int(rx * math.sin(angle))],
                        fill=(*WHITE, 220),
                    )

            # ── inner glowing ring ────────────────────────────────────────
            Ri = int(R * 0.26)
            d.ellipse([cx-Ri, cy-Ri, cx+Ri, cy+Ri],
                      outline=(*CYAN, 255), width=max(2, lw))

            # ── bright glow soft blur applied before core ─────────────────
            # (draw a slightly larger cyan circle on a separate layer)
            glow_layer = PIL.Image.new("RGBA", (S, S), (0, 0, 0, 0))
            gd = PIL.ImageDraw.Draw(glow_layer)
            Rc = int(R * 0.13)
            gd.ellipse([cx-Rc*2, cy-Rc*2, cx+Rc*2, cy+Rc*2],
                       fill=(*CYAN, 110))
            glow_layer = glow_layer.filter(PIL.ImageFilter.GaussianBlur(S // 14))
            img = PIL.Image.alpha_composite(img, glow_layer)
            d   = PIL.ImageDraw.Draw(img)

            # ── core dot ──────────────────────────────────────────────────
            d.ellipse([cx-Rc, cy-Rc, cx+Rc, cy+Rc], fill=(*WHITE, 255))

            # ── downscale to target size ──────────────────────────────────
            return img.resize((sz, sz), PIL.Image.LANCZOS)

        try:
            sizes  = [256, 128, 64, 48, 32, 16]
            frames = [_render(s) for s in sizes]
            frames[0].save(
                out_path,
                format="ICO",
                append_images=frames[1:],
                sizes=[(s, s) for s in sizes],
            )
            return True
        except Exception as e:
            print(f"[Shortcut] ⚠️  Icon generation failed: {e}")
            return False

    @staticmethod
    def _create_lnk_windows(lnk: str, target: str, args: str,
                             work_dir: str, icon_loc: str) -> None:
        """
        Create a Windows .lnk shortcut WITHOUT launching PowerShell or cmd.
        Tries win32com (pywin32) first; falls back to wscript.exe + VBScript.
        wscript.exe is a GUI-mode host — it never opens a console window.
        """
        # ── Option 1: pywin32 (pure Python COM, zero subprocess) ──────────
        try:
            from win32com.client import Dispatch   # type: ignore
            sh = Dispatch("WScript.Shell")
            sc = sh.CreateShortCut(lnk)
            sc.TargetPath       = target
            sc.Arguments        = f'"{args}"'
            sc.WorkingDirectory = work_dir
            sc.Description      = "J.A.R.V.I.S AI Assistant"
            sc.IconLocation     = icon_loc
            sc.save()
            return
        except ImportError:
            pass

        # ── Option 2: wscript.exe + VBScript (always available on Windows,
        #    GUI-mode executable — never opens a console window) ────────────
        vbs = "\n".join([
            'Set ws = CreateObject("WScript.Shell")',
            f'Set sc = ws.CreateShortcut("{lnk}")',
            f'sc.TargetPath = "{target}"',
            f'sc.Arguments = Chr(34) & "{args}" & Chr(34)',
            f'sc.WorkingDirectory = "{work_dir}"',
            'sc.Description = "J.A.R.V.I.S AI Assistant"',
            f'sc.IconLocation = "{icon_loc}"',
            'sc.Save',
        ])
        import tempfile
        fd, tmp = tempfile.mkstemp(suffix=".vbs")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(vbs)
            proc = subprocess.Popen(
                ["wscript.exe", "/nologo", tmp],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
            )
            proc.wait(timeout=10)
        finally:
            try:
                os.unlink(tmp)
            except Exception:
                pass

    @staticmethod
    def _get_desktop_dir() -> Path:
        """
        Resolve the user's REAL desktop directory instead of assuming
        ~/Desktop, which breaks when:
          • OneDrive "Known Folder Move" relocates the desktop
            (C:/Users/x/OneDrive/Desktop) — very common on Win 10/11;
          • the XDG desktop is localized on Linux (~/Masaüstü,
            ~/Schreibtisch, ~/Bureau, …).
        Falls back to ~/Desktop only as a last resort.
        """
        home = Path.home()
        _os = platform.system()

        if _os == "Windows":
            # ── 1) SHGetKnownFolderPath(FOLDERID_Desktop) — the canonical
            #       answer; follows OneDrive redirection. No dependencies. ──
            try:
                import ctypes
                from ctypes import wintypes

                class _GUID(ctypes.Structure):
                    _fields_ = [("Data1", wintypes.DWORD),
                                ("Data2", wintypes.WORD),
                                ("Data3", wintypes.WORD),
                                ("Data4", ctypes.c_ubyte * 8)]

                # FOLDERID_Desktop {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
                fid = _GUID(0xB4BFCC3A, 0xDB2C, 0x424C,
                            (ctypes.c_ubyte * 8)(0xB0, 0x29, 0x7F, 0xE9,
                                                 0x9A, 0x87, 0xC6, 0x41))
                buf = ctypes.c_wchar_p()
                if ctypes.windll.shell32.SHGetKnownFolderPath(
                        ctypes.byref(fid), 0, None, ctypes.byref(buf)) == 0:
                    p = Path(buf.value)
                    ctypes.windll.ole32.CoTaskMemFree(buf)
                    if p.is_dir():
                        return p
            except Exception:
                pass

            # ── 2) Registry: User Shell Folders (may contain %VARS%) ──────
            try:
                import winreg
                with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion"
                        r"\Explorer\User Shell Folders") as key:
                    val, _t = winreg.QueryValueEx(key, "Desktop")
                p = Path(os.path.expandvars(val))
                if p.is_dir():
                    return p
            except Exception:
                pass

        elif _os == "Linux":
            # ── xdg-user-dir honours localized names (~/Masaüstü, …) ──────
            try:
                out = subprocess.run(["xdg-user-dir", "DESKTOP"],
                                     capture_output=True, text=True, timeout=5)
                p = Path(out.stdout.strip())
                if out.stdout.strip() and p != home and p.is_dir():
                    return p
            except Exception:
                pass
            try:
                cfg = home / ".config" / "user-dirs.dirs"
                for line in cfg.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("XDG_DESKTOP_DIR"):
                        val = line.split("=", 1)[1].strip().strip('"')
                        p = Path(val.replace("$HOME", str(home)))
                        if p != home and p.is_dir():
                            return p
            except Exception:
                pass

        # macOS: ~/Desktop is always the real path (localization is
        # display-only). Everything else lands here as a last resort.
        return home / "Desktop"

    def _create_desktop_shortcut(self):
        """
        Create a desktop shortcut on Windows / macOS / Linux.
        Never opens a terminal, console, or PowerShell window on any platform.
        """
        import stat as _stat
        script  = Path(__file__).resolve().parent / "main.py"
        python  = Path(sys.executable)
        desktop = self._get_desktop_dir()

        # Arc-reactor icon (.ico — also exported as .png for Linux/macOS)
        ico_path = Path(__file__).resolve().parent / "config" / "jarvis.ico"
        if not ico_path.exists():
            self._build_jarvis_icon(ico_path)

        try:
            _os = platform.system()

            # ── Windows ───────────────────────────────────────────────────────
            if _os == "Windows":
                pythonw  = python.parent / "pythonw.exe"
                target   = str(pythonw if pythonw.exists() else python)
                lnk      = str(desktop / "J.A.R.V.I.S.lnk")
                icon_loc = str(ico_path) if ico_path.exists() else f"{target},0"
                self._create_lnk_windows(lnk, target, str(script),
                                         str(script.parent), icon_loc)

            # ── macOS — proper .app bundle (no Terminal window) ───────────────
            elif _os == "Darwin":
                app     = desktop / "J.A.R.V.I.S.app"
                mac_dir = app / "Contents" / "MacOS"
                res_dir = app / "Contents" / "Resources"
                mac_dir.mkdir(parents=True, exist_ok=True)
                res_dir.mkdir(exist_ok=True)

                # Launcher executable (bash — runs as background process,
                # macOS does NOT open Terminal for executables inside .app bundles)
                launcher = mac_dir / "JARVIS"
                launcher.write_text(
                    "#!/usr/bin/env bash\n"
                    f'cd "{script.parent}"\n'
                    f'exec "{python}" "{script}"\n'
                )
                launcher.chmod(launcher.stat().st_mode
                               | _stat.S_IEXEC | _stat.S_IXGRP | _stat.S_IXOTH)

                # Minimal Info.plist (required for .app recognition)
                (app / "Contents" / "Info.plist").write_text(
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                    '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                    '<plist version="1.0"><dict>\n'
                    '  <key>CFBundleExecutable</key><string>JARVIS</string>\n'
                    '  <key>CFBundleIdentifier</key>'
                    '<string>com.jarvis.assistant</string>\n'
                    '  <key>CFBundleName</key><string>J.A.R.V.I.S</string>\n'
                    '  <key>CFBundlePackageType</key><string>APPL</string>\n'
                    '  <key>CFBundleVersion</key><string>1.0</string>\n'
                    '</dict></plist>\n'
                )

                # Optional: copy icon as .icns (skip silently if Pillow is missing)
                try:
                    import PIL.Image
                    icns = res_dir / "AppIcon.icns"
                    PIL.Image.open(ico_path).save(icns, format="ICNS")
                    # Inject icon reference into plist
                    plist = app / "Contents" / "Info.plist"
                    txt = plist.read_text()
                    plist.write_text(
                        txt.replace(
                            '</dict></plist>',
                            '  <key>CFBundleIconFile</key>'
                            '<string>AppIcon</string>\n</dict></plist>\n',
                        )
                    )
                except Exception:
                    pass  # icon is optional

            # ── Linux — .desktop file (Terminal=false, no console) ────────────
            else:
                # Export .ico → .png for better desktop integration
                png_path = ico_path.with_suffix(".png")
                if not png_path.exists() and ico_path.exists():
                    try:
                        import PIL.Image
                        PIL.Image.open(ico_path).resize(
                            (256, 256), PIL.Image.LANCZOS
                        ).save(png_path, format="PNG")
                    except Exception:
                        png_path = ico_path  # fallback to .ico

                icon_line = f"Icon={png_path}\n" if png_path.exists() else ""
                desk = desktop / "J.A.R.V.I.S.desktop"
                desk.write_text(
                    "[Desktop Entry]\n"
                    "Name=J.A.R.V.I.S\n"
                    f"Exec={python} {script}\n"
                    f"Path={script.parent}\n"
                    "Type=Application\n"
                    "Terminal=false\n"
                    "Categories=Utility;\n"
                    + icon_line
                )
                desk.chmod(desk.stat().st_mode | 0o755)

            self._log.append_log("SYS: Desktop shortcut created.")
        except Exception as e:
            self._log.append_log(f"ERR: Shortcut failed — {e}")

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cw = self.centralWidget()
        if self._overlay and self._overlay.isVisible():
            ow, oh = 460, 390
            self._overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._remote_overlay and self._remote_overlay.isVisible():
            ow, oh = RemoteKeyOverlay._OW, RemoteKeyOverlay._OH
            self._remote_overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._customize_overlay and self._customize_overlay.isVisible():
            ow, oh = CustomizeOverlay._OW, CustomizeOverlay._OH
            self._customize_overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        # Camera preview — bottom-right corner of the center/HUD area
        pw = _CameraPreview._W
        ph = self._cam_preview.height() or _CameraPreview._H
        cam_y = max(60, (self._hud_cam_stack.height() - ph - 16) if hasattr(self, '_hud_cam_stack') else (cw.height() - ph - 28))
        self._cam_preview.setGeometry(
            cw.width() - pw - 18,
            cam_y,
            pw, ph,
        )
        # Clipboard panel — bottom-center
        if hasattr(self, '_clipboard_panel') and self._clipboard_panel.isVisible():
            self._position_clipboard_panel()
        # Quick drawer — reposition if open
        if hasattr(self, '_quick_drawer') and self._quick_drawer.isVisible():
            self._position_quick_drawer()
        if hasattr(self, '_ctrl_drawer') and self._ctrl_drawer.isVisible():
            self._position_ctrl_drawer()
        self._fit_video()

    def _update_metrics(self):
        if not hasattr(self, "_bar_cpu") or self._bar_cpu is None:
            return
        snap = _metrics.snapshot()

        # CPU
        cpu = snap["cpu"]
        self._bar_cpu.set_value(cpu, f"{cpu:.0f}%")

        # MEM
        mem = snap["mem"]
        self._bar_mem.set_value(mem, f"{mem:.0f}%")

        # NET
        net = snap["net"]
        if net < 1.0:
            net_str = f"{net*1024:.0f}KB/s"
        else:
            net_str = f"{net:.1f}MB/s"
        net_pct = min(100, net * 10)  # 10 MB/s = %100
        self._bar_net.set_value(net_pct, net_str)

        # GPU
        gpu = snap["gpu"]
        if gpu >= 0:
            self._bar_gpu.set_value(gpu, f"{gpu:.0f}%")
        else:
            self._bar_gpu.set_value(0, "N/A")

        # TMP
        tmp = snap["tmp"]
        if tmp >= 0:
            tmp_pct = min(100, (tmp / 100) * 100)
            self._bar_tmp.set_value(tmp_pct, f"{tmp:.0f}°C")
        else:
            self._bar_tmp.set_value(0, "N/A")

        try:
            boot_t  = psutil.boot_time()
            elapsed = time.time() - boot_t
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            self._uptime_lbl.setText(f"UP  {h:02d}:{m:02d}")
        except Exception:
            self._uptime_lbl.setText("UP  --:--")

        try:
            proc_count = len(psutil.pids())
            self._proc_lbl.setText(f"PROC  {proc_count}")
        except Exception:
            self._proc_lbl.setText("PROC  --")


    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(54)
        w.setStyleSheet(f"background: {C.DARK}; border-bottom: 1px solid {C.BORDER_B};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(10)

        # ── Left: System branding & drawers ──────────────────────────────────
        left_box = QHBoxLayout()
        left_box.setSpacing(8)

        _logo_path = CONFIG_DIR / "jarvis.png"
        if _logo_path.exists():
            try:
                logo_lbl = QLabel()
                logo_lbl.setFixedSize(26, 26)
                pix = QPixmap(str(_logo_path)).scaled(
                    26, 26,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                logo_lbl.setPixmap(pix)
                logo_lbl.setStyleSheet("background: transparent; border-radius: 4px;")
                left_box.addWidget(logo_lbl)
            except Exception:
                pass

        sys_emblem = QLabel("◈ JARVIS OS")
        sys_emblem.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        sys_emblem.setStyleSheet(f"color: {C.PRI}; background: transparent; letter-spacing: 0.5px;")
        left_box.addWidget(sys_emblem)

        ver_badge = QLabel("MARK LV")
        ver_badge.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        ver_badge.setStyleSheet(f"""
            color: {C.PRI_DIM}; background: {C.PRI_GHO};
            border: 1px solid {C.BORDER_B}; border-radius: 2px;
            padding: 1px 5px;
        """)
        left_box.addWidget(ver_badge)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet(f"color: {C.BORDER}; margin: 14px 2px;")
        left_box.addWidget(sep1)

        self._drawer_btn = QPushButton("⚙")
        self._drawer_btn.setFixedSize(26, 26)
        self._drawer_btn.setFont(QFont("Courier New", 11))
        self._drawer_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._drawer_btn.setToolTip("System Setup & Configuration")
        self._drawer_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 4px;
            }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.PRI_DIM}; background: {C.PRI_GHO}; }}
            QPushButton:checked {{ color: {C.PRI}; border-color: {C.PRI}; background: {C.PRI_GHO}; }}
        """)
        self._drawer_btn.setCheckable(True)
        self._drawer_btn.clicked.connect(self._toggle_drawer)
        left_box.addWidget(self._drawer_btn)

        self._ctrl_btn = QPushButton("🎛")
        self._ctrl_btn.setFixedSize(26, 26)
        self._ctrl_btn.setFont(QFont("Courier New", 11))
        self._ctrl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ctrl_btn.setToolTip("Hardware & Assistant Controls")
        self._ctrl_btn.setStyleSheet(self._drawer_btn.styleSheet())
        self._ctrl_btn.setCheckable(True)
        self._ctrl_btn.clicked.connect(self._toggle_controls)
        left_box.addWidget(self._ctrl_btn)

        # Screen share button
        self._screenshare_btn = QPushButton("📺  SHARE SCREEN")
        self._screenshare_btn.setFixedHeight(26)
        self._screenshare_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._screenshare_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._screenshare_btn.setToolTip("Share Entire Screen or an Application Window with JARVIS")
        self._screenshare_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.BORDER_B}; border-radius: 4px; padding: 2px 10px;
            }}
            QPushButton:hover {{ color: #ffffff; border-color: {C.PRI}; background: {C.PRI_GHO}; }}
        """)
        self._screenshare_btn.clicked.connect(self._open_screen_share_dialog)
        left_box.addWidget(self._screenshare_btn)

        lay.addLayout(left_box)
        lay.addStretch()

        # ── Center: Holographic Assistant Title & State Pill ─────────────────
        mid = QVBoxLayout()
        mid.setSpacing(1)
        _disp = self._assistant_name.upper()
        self._title_lbl = QLabel(_disp)
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_lbl.setFont(QFont("Courier New", 15, QFont.Weight.Bold))
        self._title_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent; letter-spacing: 2px;")
        mid.addWidget(self._title_lbl)

        # Dynamic state pill
        self._header_state_lbl = QLabel("● STANDBY")
        self._header_state_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._header_state_lbl.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        self._header_state_lbl.setStyleSheet(f"""
            color: {C.GREEN}; background: rgba(0, 255, 136, 0.08);
            border: 1px solid {C.GREEN_D}; border-radius: 9px;
            padding: 1px 8px;
        """)
        mid.addWidget(self._header_state_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        lay.addLayout(mid)
        lay.addStretch()

        # ── Right: Precision Clock & Telemetry Link ──────────────────────────
        right_col = QVBoxLayout()
        right_col.setSpacing(1)
        self._clock_lbl = QLabel("00:00:00")
        self._clock_lbl.setFont(QFont("Courier New", 13, QFont.Weight.Bold))
        self._clock_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._clock_lbl)

        bottom_r = QHBoxLayout()
        bottom_r.setSpacing(6)
        self._date_lbl = QLabel("")
        self._date_lbl.setFont(QFont("Courier New", 7))
        self._date_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        bottom_r.addWidget(self._date_lbl)

        link_tag = QLabel("◈ SYNC")
        link_tag.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        link_tag.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
        bottom_r.addWidget(link_tag)
        right_col.addLayout(bottom_r)

        lay.addLayout(right_col)
        return w

    def _tick_clock(self):
        self._clock_lbl.setText(time.strftime("%H:%M:%S"))
        self._date_lbl.setText(time.strftime("%a %d %b %Y"))

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_LEFT_W)
        w.setStyleSheet(f"background: {C.DARK}; border-right: 1px solid {C.BORDER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 10, 8, 10)
        lay.setSpacing(6)

        hdr = QLabel("◈ SYS MONITOR")
        hdr.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent; "
                          f"border-bottom: 1px solid {C.BORDER}; padding-bottom: 4px;")
        lay.addWidget(hdr)
        lay.addSpacing(2)

        self._bar_cpu = MetricBar("CPU", C.PRI)
        self._bar_mem = MetricBar("MEM", C.ACC2)
        self._bar_net = MetricBar("NET", C.GREEN)
        self._bar_gpu = MetricBar("GPU", C.ACC)
        self._bar_tmp = MetricBar("TMP", "#ff6688")

        for bar in [self._bar_cpu, self._bar_mem, self._bar_net,
                    self._bar_gpu, self._bar_tmp]:
            lay.addWidget(bar)

        lay.addSpacing(4)

        info_panel = QWidget()
        info_panel.setStyleSheet(
            f"background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 4px;"
        )
        ip_lay = QVBoxLayout(info_panel)
        ip_lay.setContentsMargins(6, 5, 6, 5)
        ip_lay.setSpacing(3)

        self._uptime_lbl = QLabel("UP  --:--")
        self._uptime_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._uptime_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent; border: none;")
        ip_lay.addWidget(self._uptime_lbl)

        self._proc_lbl = QLabel("PROC  --")
        self._proc_lbl.setFont(QFont("Courier New", 8))
        self._proc_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        ip_lay.addWidget(self._proc_lbl)

        os_name = {"Windows": "WIN", "Darwin": "macOS", "Linux": "LINUX"}.get(_OS, _OS.upper())
        os_lbl = QLabel(f"OS  {os_name}")
        os_lbl.setFont(QFont("Courier New", 8))
        os_lbl.setStyleSheet(f"color: {C.ACC2}; background: transparent; border: none;")
        ip_lay.addWidget(os_lbl)

        lay.addWidget(info_panel)
        lay.addSpacing(4)

        lay.addStretch()

        for txt, col in [
            ("AI CORE\nACTIVE",  C.GREEN),
            ("SEC\nCLEARED",     C.PRI),
            ("PROTOCOL\n" + APP_PROTOCOL,   C.TEXT_DIM),
        ]:
            lbl = QLabel(txt)
            lbl.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color: {col}; background: {C.PANEL2};"
                f"border: 1px solid {C.BORDER_A}; border-radius: 3px; padding: 4px;"
            )
            lay.addWidget(lbl)

        return w
    def _build_right_panel(self) -> QWidget:
        # Legacy stub preserved for compatibility
        return QWidget()

    def _build_quick_drawer(self) -> QWidget:
        """Floating overlay panel shown when the ⚙ header button is toggled."""
        _BTN_STYLE_PRI = f"""
            QPushButton {{
                background: #00091a; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
                text-align: left; padding: 0 8px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
        """
        _BTN_STYLE_DIM = f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
                text-align: left; padding: 0 8px;
            }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.BORDER_B}; }}
        """

        self._BTN_PRI, self._BTN_DIM = _BTN_STYLE_PRI, _BTN_STYLE_DIM
        w = QWidget(self.centralWidget())
        w.setObjectName("QuickDrawer")
        w.setStyleSheet(f"""
            QWidget#QuickDrawer {{
                background: {C.DARK};
                border: 1px solid {C.BORDER_B};
                border-top: none;
                border-radius: 0 0 6px 6px;
            }}
        """)
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(5)

        hdr = QLabel("◈ SETUP")
        hdr.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent; "
                          f"border-bottom: 1px solid {C.BORDER}; padding-bottom: 4px;")
        lay.addWidget(hdr)

        remote_btn = QPushButton("◉  REMOTE CONTROL")
        remote_btn.setFixedHeight(30)
        remote_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        remote_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remote_btn.setStyleSheet(_BTN_STYLE_PRI)
        remote_btn.clicked.connect(self._open_remote)
        lay.addWidget(remote_btn)

        sc_btn = QPushButton("⊞  CREATE DESKTOP SHORTCUT")
        sc_btn.setFixedHeight(26)
        sc_btn.setFont(QFont("Courier New", 7))
        sc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sc_btn.setStyleSheet(_BTN_STYLE_DIM)
        sc_btn.clicked.connect(self._create_desktop_shortcut)
        lay.addWidget(sc_btn)

        self._autostart_btn = QPushButton("◉  AUTO-START: OFF")
        self._autostart_btn.setFixedHeight(26)
        self._autostart_btn.setFont(QFont("Courier New", 7))
        self._autostart_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._autostart_btn.clicked.connect(self._toggle_autostart)
        lay.addWidget(self._autostart_btn)

        cust_btn = QPushButton("⚙  CUSTOMISE ASSISTANT")
        cust_btn.setFixedHeight(26)
        cust_btn.setFont(QFont("Courier New", 7))
        cust_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cust_btn.setStyleSheet(_BTN_STYLE_DIM)
        cust_btn.clicked.connect(self._open_customize)
        lay.addWidget(cust_btn)

        audio_btn = QPushButton("🎧  AUDIO DEVICES")
        audio_btn.setFixedHeight(26)
        audio_btn.setFont(QFont("Courier New", 7))
        audio_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        audio_btn.setStyleSheet(_BTN_STYLE_DIM)
        audio_btn.clicked.connect(self._open_audio_devices)
        lay.addWidget(audio_btn)

        mem_btn = QPushButton("🧠  MEMORY")
        mem_btn.setFixedHeight(26)
        mem_btn.setFont(QFont("Courier New", 7))
        mem_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        mem_btn.setStyleSheet(_BTN_STYLE_DIM)
        mem_btn.clicked.connect(self._open_memory_panel)
        lay.addWidget(mem_btn)

        plugin_btn = QPushButton("🧩  PLUGINS")
        plugin_btn.setFixedHeight(26)
        plugin_btn.setFont(QFont("Courier New", 7))
        plugin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        plugin_btn.setStyleSheet(_BTN_STYLE_DIM)
        plugin_btn.clicked.connect(self._open_plugin_manager)
        lay.addWidget(plugin_btn)

        settings_btn = QPushButton("⚙  PLUGIN SETTINGS")
        settings_btn.setFixedHeight(26)
        settings_btn.setFont(QFont("Courier New", 7))
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.setStyleSheet(_BTN_STYLE_DIM)
        settings_btn.clicked.connect(self._open_plugin_settings)
        lay.addWidget(settings_btn)

        w.adjustSize()
        return w

    def _build_controls_drawer(self) -> QWidget:
        """The switches that get flicked every day, in their own panel."""
        w = QWidget(self.centralWidget())
        w.setObjectName("QuickDrawer")
        w.setStyleSheet(self._quick_drawer.styleSheet())
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(5)

        hdr = QLabel("◈ CONTROLS")
        hdr.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent; "
                          f"border-bottom: 1px solid {C.BORDER}; padding-bottom: 4px;")
        lay.addWidget(hdr)

        def _row(button, style=None, height=26):
            button.setFixedHeight(height)
            button.setFont(QFont("Courier New", 7))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if style:
                button.setStyleSheet(style)
            lay.addWidget(button)
            return button

        fs_btn = _row(QPushButton("⛶  FULLSCREEN  [F11]"), self._BTN_DIM)
        fs_btn.clicked.connect(self._toggle_fullscreen)

        self._brief_btn = _row(QPushButton())
        self._brief_btn.clicked.connect(self._toggle_brief)

        self._wake_btn = _row(QPushButton())
        self._wake_btn.clicked.connect(self._toggle_wake_word)
        self._wake_sleep_btn = _row(QPushButton())
        self._wake_sleep_btn.clicked.connect(self._tap_wake_manual)
        # Neutral until the real state lands from the background warm-up.
        self._wake_btn.setText("🎙  WAKE WORD")
        self._wake_btn.setStyleSheet(self._BTN_DIM)
        self._wake_sleep_btn.hide()

        self._ptt_btn = _row(QPushButton())
        self._ptt_btn.clicked.connect(self._toggle_ptt)
        self._refresh_talk_btns()

        self._hud_btn = _row(QPushButton())
        self._hud_btn.clicked.connect(self._toggle_hud_style)
        self._refresh_hud_btn()

        w.adjustSize()
        return w

    def _warm_wake_state(self) -> None:
        """Work out the wake-word state off the UI thread, once.

        It used to be resolved when the drawer opened, and that made opening the
        drawer take two seconds the first time — measured at 2.10s, all of it
        `import openwakeword` dragging in onnxruntime behind it. The button
        count had nothing to do with it; the Qt thread was simply waiting on an
        import. Afterwards the same check costs about a millisecond, so it only
        ever needed to happen somewhere other than in front of the user.
        """
        def work():
            try:
                self._wake_state()
            except Exception:
                pass
            self._wake_btns_sig.emit()
        threading.Thread(target=work, daemon=True, name="wake-state-warm").start()

    def _toggle_drawer(self, checked: bool):
        if checked:
            self._close_controls()
            self._position_quick_drawer()
            self._quick_drawer.show()
            self._quick_drawer.raise_()
        else:
            self._quick_drawer.hide()

    def _toggle_controls(self, checked: bool):
        if checked:
            self._close_setup()
            self._refresh_wake_btns()   # cheap now: the state was warmed at boot
            self._position_ctrl_drawer()
            self._ctrl_drawer.show()
            self._ctrl_drawer.raise_()
        else:
            self._ctrl_drawer.hide()

    def _close_setup(self):
        if hasattr(self, "_quick_drawer"):
            self._quick_drawer.hide()
        if hasattr(self, "_drawer_btn"):
            self._drawer_btn.setChecked(False)

    def _close_controls(self):
        if hasattr(self, "_ctrl_drawer"):
            self._ctrl_drawer.hide()
        if hasattr(self, "_ctrl_btn"):
            self._ctrl_btn.setChecked(False)

    def _place_drawer(self, drawer, left: int):
        _W = 220
        drawer.setFixedWidth(_W)
        drawer.adjustSize()
        drawer.setGeometry(left, 54, _W, drawer.sizeHint().height())

    def _position_quick_drawer(self):
        if hasattr(self, "_quick_drawer"):
            self._place_drawer(self._quick_drawer, 12)

    def _position_ctrl_drawer(self):
        # Under its own header button rather than under the other one's.
        if hasattr(self, "_ctrl_drawer"):
            left = 12
            try:
                left = max(12, self._ctrl_btn.mapTo(self.centralWidget(),
                                                    QPoint(0, 0)).x() - 8)
            except Exception:
                pass
            self._place_drawer(self._ctrl_drawer, left)

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(5)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a command or question…")
        self._input.setFont(QFont("Courier New", 9))
        self._input.setFixedHeight(30)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d14; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 3px 7px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input)

        send = QPushButton("▸")
        send.setFixedSize(30, 30)
        send.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """)
        send.clicked.connect(self._send)
        row.addWidget(send)
        return row

    def _build_content_panel(self) -> QWidget:
        """
        Collapsible panel below the HUD — shows search results, news, briefings.
        Hidden by default; appears when show_content() is called.
        """
        w = QWidget()
        w.setObjectName("ContentPanel")
        w.setStyleSheet(f"""
            QWidget#ContentPanel {{
                background: {C.PANEL};
                border-top: 1px solid {C.BORDER_B};
            }}
        """)
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 7, 12, 8)
        lay.setSpacing(5)

        # ── header row ───────────────────────────────────────────────────────
        hdr = QHBoxLayout(); hdr.setSpacing(6)

        dot = QLabel("◈")
        dot.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        dot.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(dot)

        self._content_title_lbl = QLabel("BRIEFING")
        self._content_title_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._content_title_lbl.setStyleSheet(
            f"color: {C.PRI}; background: transparent; letter-spacing: 1px;"
        )
        hdr.addWidget(self._content_title_lbl)
        hdr.addStretch()

        self._content_ts_lbl = QLabel("")
        self._content_ts_lbl.setFont(QFont("Courier New", 7))
        self._content_ts_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        hdr.addWidget(self._content_ts_lbl)

        dismiss = QPushButton("DISMISS  ✕")
        dismiss.setFont(QFont("Courier New", 7))
        dismiss.setFixedHeight(18)
        dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 2px; padding: 0 5px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        dismiss.clicked.connect(w.hide)
        hdr.addWidget(dismiss)
        lay.addLayout(hdr)

        # ── separator ─────────────────────────────────────────────────────────
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); lay.addWidget(sep)

        # ── text display ──────────────────────────────────────────────────────
        self._content_display = QTextEdit()
        self._content_display.setReadOnly(True)
        self._content_display.setFont(QFont("Courier New", 8))
        self._content_display.setMinimumHeight(60)
        self._content_display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._content_display.setStyleSheet(f"""
            QTextEdit {{
                background: {C.DARK};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 3px;
                padding: 6px 8px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG}; width: 6px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B}; border-radius: 3px; min-height: 16px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0; border: none;
            }}
        """)
        lay.addWidget(self._content_display)

        return w

    def _show_content(self, title: str, text: str):
        """Slot — runs on Qt main thread. Updates and shows the content panel."""
        import time as _time
        # The panel opens below the head, so the head looks down at it. It is a
        # tiny thing that answers "did that land?" before you read a word.
        self.hud.glance(0.0, -0.85, hold=1.3)
        self._content_title_lbl.setText(title.upper()[:48])
        self._content_ts_lbl.setText(_time.strftime("%H:%M:%S"))
        self._content_display.setPlainText(text)
        self._content_display.moveCursor(
            self._content_display.textCursor().MoveOperation.Start
        )
        first_show = not self._content_panel.isVisible()
        self._content_panel.show()
        if first_show:
            total = self._center_split.height()
            pods_h = self._pods_container.height() if hasattr(self, "_pods_container") else 200
            self._center_split.setSizes([max(total - pods_h - 220, 120), 220, 0, pods_h])

    # ── document review ──────────────────────────────────────────────────────
    # Rendered as rich text into the content panel that already exists, rather
    # than into a panel of its own. A review is read, not clicked, so QTextEdit
    # gives scrolling, selection and copy for nothing, and the HUD gains no
    # widget it has to lay out. Severity decides colour and order here because
    # that is presentation; the plugin supplies no styling and knows no palette,
    # which is also what lets a re-theme repaint a review correctly.

    # Severity is marked by a symbol and a colour, not by a word. The findings
    # themselves are in the user's language, and "[SERIOUS]" sitting inside a
    # Turkish sentence is the kind of seam this project tries not to have —
    # while translating the tag would mean a table per language, which is worse.
    # A shape carries it in every language, and shape plus colour still reads
    # for someone who cannot separate red from amber. What the marks mean
    # arrives the way everything else does: JARVIS says it out loud.
    _REVIEW_MARKS = {"serious": ("RED", "▲"), "caution": ("ACC2", "●"), "note": ("PRI_DIM", "·")}

    @staticmethod
    def _esc(s) -> str:
        return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace("\n", "<br>"))

    def _show_review(self, title: str, summary: str, findings, unclear):
        """Slot — Qt main thread. Lays a document review into the content panel."""
        e = self._esc
        parts = [f'<div style="color:{C.TEXT}; font-family:Courier New;">']

        if summary:
            parts.append(
                f'<div style="color:{C.WHITE}; border-left:2px solid {C.PRI};'
                f' padding-left:8px; margin-bottom:10px;">{e(summary)}</div>')

        for f in (findings or []):
            key, mark = self._REVIEW_MARKS.get(f.get("severity"), ("PRI_DIM", "·"))
            colour = getattr(C, key)
            parts.append(f'<div style="margin-bottom:11px;">')
            parts.append(
                f'<span style="color:{colour}; font-weight:bold;">{mark}</span> '
                f'<span style="color:{C.WHITE}; font-weight:bold;">'
                f'{e(f.get("heading"))}</span>')
            if f.get("detail"):
                parts.append(f'<div style="margin-left:12px;">{e(f["detail"])}</div>')
            if f.get("quote"):
                # The document's own wording, visually separated from the
                # explanation so the two are never mistaken for each other.
                parts.append(
                    f'<div style="margin-left:12px; color:{C.TEXT_DIM};'
                    f' border-left:1px solid {C.BORDER}; padding-left:7px;">'
                    f'&ldquo;{e(f["quote"])}&rdquo;</div>')
            if f.get("suggestion"):
                parts.append(
                    f'<div style="margin-left:12px; color:{C.PRI};">'
                    f'&rarr; {e(f["suggestion"])}</div>')
            parts.append('</div>')

        if unclear:
            parts.append(
                f'<div style="margin-top:6px; border-top:1px solid {C.BORDER};'
                f' padding-top:7px; color:{C.TEXT_MED};">'
                'The document does not settle:</div>')
            for u in unclear:
                parts.append(
                    f'<div style="margin-left:12px; color:{C.TEXT_MED};">'
                    f'&middot; {e(u)}</div>')
        parts.append('</div>')

        import time as _time
        self.hud.glance(0.0, -0.85, hold=1.3)
        # Left as written, not upper-cased. The other content-panel titles are
        # the app's own English labels, but this one is the document's name in
        # the user's language, and str.upper() applies English casing rules to
        # it: Turkish "Sözleşmesi" comes back "SÖZLEŞMESI", having lost the
        # dotted capital İ. Python has no locale-aware upper to reach for, and
        # imposing one language's rules on all of them is the bug, not the fix.
        self._content_title_lbl.setText((title or "Document")[:48])
        self._content_ts_lbl.setText(_time.strftime("%H:%M:%S"))
        self._content_display.setHtml("".join(parts))
        self._content_display.moveCursor(
            self._content_display.textCursor().MoveOperation.Start)
        first_show = not self._content_panel.isVisible()
        self._content_panel.show()
        if first_show:
            total = self._center_split.height()
            pods_h = self._pods_container.height() if hasattr(self, "_pods_container") else 200
            self._center_split.setSizes([max(total - pods_h - 260, 120), 260, 0, pods_h])

    # ── quiz panel ───────────────────────────────────────────────────────────
    # An interactive twin of the content panel. The plugin only ever hands over
    # questions; everything about asking, marking and reporting happens here,
    # and the finished result is pushed back into the conversation the same way
    # a dropped file is — as a message JARVIS reads and responds to. That keeps
    # the tool call short (it returns the moment the board is up) and leaves the
    # talking to the assistant, in the user's own language.

    def _quiz_btn(self, text: str, primary: bool = False) -> QPushButton:
        b = QPushButton(text)
        b.setFont(QFont("Courier New", 8))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setMinimumHeight(24)
        edge = C.BORDER_B if primary else C.BORDER
        col = C.PRI if primary else C.TEXT_MED
        b.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL2}; color: {col};
                border: 1px solid {edge}; border-radius: 2px;
                padding: 3px 9px; text-align: left;
            }}
            QPushButton:hover {{ color: {C.WHITE}; border-color: {C.PRI_DIM}; }}
            QPushButton:disabled {{ color: {C.TEXT_DIM}; border-color: {C.BORDER}; }}
        """)
        return b

    def _build_quiz_panel(self) -> QWidget:
        w = QWidget()
        w.setObjectName("QuizPanel")
        w.setStyleSheet(f"""
            QWidget#QuizPanel {{
                background: {C.PANEL};
                border-top: 1px solid {C.BORDER_B};
            }}
        """)
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 7, 12, 8)
        lay.setSpacing(6)

        hdr = QHBoxLayout(); hdr.setSpacing(6)
        dot = QLabel("◈")
        dot.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        dot.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(dot)

        self._quiz_title_lbl = QLabel("QUIZ")
        self._quiz_title_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._quiz_title_lbl.setStyleSheet(
            f"color: {C.PRI}; background: transparent; letter-spacing: 1px;")
        hdr.addWidget(self._quiz_title_lbl)
        hdr.addStretch()

        self._quiz_count_lbl = QLabel("")
        self._quiz_count_lbl.setFont(QFont("Courier New", 7))
        self._quiz_count_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        hdr.addWidget(self._quiz_count_lbl)

        quit_btn = QPushButton("DISMISS  ✕")
        quit_btn.setFont(QFont("Courier New", 7))
        quit_btn.setFixedHeight(18)
        quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        quit_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 2px; padding: 0 5px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        quit_btn.clicked.connect(self._hide_quiz)
        hdr.addWidget(quit_btn)
        lay.addLayout(hdr)

        rule = QFrame(); rule.setFixedHeight(1)
        rule.setStyleSheet(f"background: {C.BORDER};")
        lay.addWidget(rule)

        self._quiz_q_lbl = QLabel("")
        self._quiz_q_lbl.setWordWrap(True)
        self._quiz_q_lbl.setFont(QFont("Courier New", 9))
        self._quiz_q_lbl.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        lay.addWidget(self._quiz_q_lbl)

        self._quiz_answers = QWidget()
        self._quiz_answers.setStyleSheet("background: transparent;")
        self._quiz_answers_lay = QVBoxLayout(self._quiz_answers)
        self._quiz_answers_lay.setContentsMargins(0, 2, 0, 0)
        self._quiz_answers_lay.setSpacing(4)
        lay.addWidget(self._quiz_answers)

        self._quiz_note_lbl = QLabel("")
        self._quiz_note_lbl.setWordWrap(True)
        self._quiz_note_lbl.setFont(QFont("Courier New", 8))
        self._quiz_note_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._quiz_note_lbl.hide()
        lay.addWidget(self._quiz_note_lbl)

        foot = QHBoxLayout()
        foot.addStretch()
        self._quiz_next_btn = self._quiz_btn("NEXT  →", primary=True)
        self._quiz_next_btn.setFixedWidth(110)
        self._quiz_next_btn.clicked.connect(self._quiz_next)
        self._quiz_next_btn.hide()
        foot.addWidget(self._quiz_next_btn)
        lay.addLayout(foot)

        self._quiz = None
        return w

    def _show_quiz(self, topic: str, questions, grader=None):
        """Slot — Qt main thread. Puts a fresh quiz on the board."""
        if not questions:
            return
        self._quiz = {
            "topic": topic or "",
            "questions": list(questions),
            "grader": grader,
            "i": 0,
            "results": [],
            "answered": False,
        }
        self._quiz_title_lbl.setText((topic or "quiz").upper()[:48])
        self.hud.glance(0.0, -0.85, hold=1.3)
        first_show = not self._quiz_panel.isVisible()
        self._quiz_panel.show()
        if first_show:
            total = self._center_split.height()
            pods_h = self._pods_container.height() if hasattr(self, "_pods_container") else 200
            self._center_split.setSizes([max(total - pods_h - 250, 120), 0, 250, pods_h])
        self._quiz_render()

    def _hide_quiz(self):
        self._quiz = None
        self._quiz_panel.hide()

    def _quiz_clear_answers(self):
        while self._quiz_answers_lay.count():
            item = self._quiz_answers_lay.takeAt(0)
            child = item.widget()
            if child is not None:
                child.setParent(None)
                child.deleteLater()

    def _quiz_render(self):
        q = self._quiz["questions"][self._quiz["i"]]
        n, total = self._quiz["i"] + 1, len(self._quiz["questions"])
        self._quiz_count_lbl.setText(f"{n} / {total}")
        self._quiz_q_lbl.setText(q.get("question", ""))
        self._quiz_note_lbl.hide()
        self._quiz_next_btn.hide()
        self._quiz["answered"] = False
        self._quiz_clear_answers()

        opts = q.get("options") or []
        if opts:
            for text in opts:
                b = self._quiz_btn("   " + text)
                b.clicked.connect(lambda _=False, t=text: self._quiz_submit(t))
                self._quiz_answers_lay.addWidget(b)
        else:
            row = QWidget(); row.setStyleSheet("background: transparent;")
            h = QHBoxLayout(row); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(6)
            field = QLineEdit()
            field.setFont(QFont("Courier New", 9))
            field.setPlaceholderText("your answer")
            field.setStyleSheet(f"""
                QLineEdit {{
                    background: {C.PANEL2}; color: {C.WHITE};
                    border: 1px solid {C.BORDER}; border-radius: 2px; padding: 4px 7px;
                }}
                QLineEdit:focus {{ border-color: {C.PRI_DIM}; }}
            """)
            send = self._quiz_btn("ANSWER", primary=True)
            send.setFixedWidth(90)
            field.returnPressed.connect(lambda: self._quiz_submit(field.text()))
            send.clicked.connect(lambda: self._quiz_submit(field.text()))
            h.addWidget(field, stretch=1)
            h.addWidget(send)
            self._quiz_answers_lay.addWidget(row)
            field.setFocus()

    def _quiz_submit(self, given: str):
        if self._quiz is None or self._quiz["answered"]:
            return
        self._quiz["answered"] = True
        q = self._quiz["questions"][self._quiz["i"]]
        grader = self._quiz.get("grader")
        verdict = None
        if callable(grader):
            try:
                verdict = grader(q, given)
            except Exception:
                verdict = None
        self._quiz["results"].append({
            "question": q.get("question", ""),
            "type": q.get("type", ""),
            "given": str(given or "").strip(),
            "answer": q.get("answer", ""),
            "correct": verdict,
        })

        for i in range(self._quiz_answers_lay.count()):
            wdg = self._quiz_answers_lay.itemAt(i).widget()
            if wdg is not None:
                wdg.setEnabled(False)

        if verdict is True:
            mark, colour = "✓  correct", C.GREEN
        elif verdict is False:
            mark, colour = "✕  " + str(q.get("answer", "")), C.RED
        else:
            # Open answers and near-miss gap-fills are JARVIS's to judge. Saying
            # so is honest; marking it wrong here would be a guess.
            mark, colour = "…  noted — I'll go over this one with you", C.ACC2
        note = q.get("note") or ""
        self._quiz_note_lbl.setText(mark + (("\n" + note) if note else ""))
        self._quiz_note_lbl.setStyleSheet(f"color: {colour}; background: transparent;")
        self._quiz_note_lbl.show()

        last = self._quiz["i"] >= len(self._quiz["questions"]) - 1
        self._quiz_next_btn.setText("FINISH  →" if last else "NEXT  →")
        self._quiz_next_btn.show()
        self._quiz_next_btn.setFocus()

    def _quiz_next(self):
        if self._quiz is None:
            return
        if self._quiz["i"] >= len(self._quiz["questions"]) - 1:
            self._quiz_finish()
        else:
            self._quiz["i"] += 1
            self._quiz_render()

    def _quiz_finish(self):
        if self._quiz is None:
            return
        topic = self._quiz["topic"]
        results = self._quiz["results"]
        right = sum(1 for r in results if r["correct"] is True)
        unsure = sum(1 for r in results if r["correct"] is None)
        total = len(results)
        self._quiz_panel.hide()
        self._quiz = None

        self._log.append_log(f"QUIZ: {topic or 'quiz'} — {right}/{total} correct")

        # Hand it back to JARVIS as a message, not as a tool return: the tool
        # call ended minutes ago. This is the same channel a dropped file uses.
        lines = [f"[QUIZ_DONE] topic={topic or 'general'} | "
                 f"auto-marked {right}/{total} correct"
                 + (f", {unsure} still need your marking" if unsure else "")]
        for i, r in enumerate(results, 1):
            state = ("correct" if r["correct"] is True
                     else "wrong" if r["correct"] is False else "NEEDS MARKING")
            lines.append(
                f"{i}. [{r['type']}] {r['question']} | they answered: "
                f"{r['given'] or '(blank)'} | expected: {r['answer']} | {state}")
        lines.append(
            "Mark every question flagged NEEDS MARKING yourself — accept an answer "
            "that means the same thing. Then tell them how they did in their own "
            "language: the score, what they got wrong and why, in a couple of "
            "sentences. Offer another round only if it fits. "
            "Remember something only if it would still matter next week — that they "
            "are working through a subject, or keep missing the same thing. A score "
            "from one session is not worth a memory, and a memory per quiz would "
            "bury the things that are.")
        msg = "\n".join(lines)
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(22)
        w.setStyleSheet(f"background: {C.DARK}; border-top: 1px solid {C.BORDER};")
        lay = QHBoxLayout(w); lay.setContentsMargins(14, 0, 14, 0)

        def _fl(txt, color=C.TEXT_MED):
            l = QLabel(txt); l.setFont(QFont("Courier New", 7))
            l.setStyleSheet(f"color: {color}; background: transparent;")
            return l

        lay.addWidget(_fl("[F4] Mute  ·  [F11] Fullscreen"))
        lay.addStretch()
        lay.addWidget(_fl("By Divyanshu verma", C.PRI_DIM))
        return w

    def _on_file_selected(self, path: str):
        self._current_file = path
        p    = Path(path)
        cat  = _file_category(p)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size = _fmt_size(p.stat().st_size)
        if hasattr(self, "_command_cockpit") and self._command_cockpit:
            self._command_cockpit._current_file = path
            self._command_cockpit._chip_lbl.setText(f"{icon}  {p.name}  ·  {size}")
            self._command_cockpit._file_chip.show()
        if hasattr(self, "_file_hint") and self._file_hint:
            self._file_hint.setText(f"{icon}  {p.name}  ·  {size}  ·  Tell {self._assistant_name} what to do with it")
        self._log.append_log(f"FILE: {p.name} ({size}) loaded")
        if self.on_text_command:
            msg = (
                f"[FILE_UPLOADED] path={path} | name={p.name} | "
                f"type={p.suffix.lstrip('.')} | size={size} | "
                f"Briefly tell the user you can see the file '{p.name}' "
                f"({size}) has been uploaded and ask what they'd like to do with it."
            )
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def _on_file_cleared(self):
        self._current_file = None
        if hasattr(self, "_command_cockpit") and self._command_cockpit:
            self._command_cockpit._current_file = None
            self._command_cockpit._file_chip.hide()
        if hasattr(self, "_file_hint") and self._file_hint:
            self._file_hint.setText("💡 Tip: Enter to send  ·  ESC to interrupt  ·  F4 to mute  ·  Drop files anywhere")
        self._log.append_log("SYS: Attachment cleared.")

    def notify_phone_connected(self) -> None:
        if self._remote_overlay and self._remote_overlay.isVisible():
            self._remote_overlay.mark_connected()

    def _open_remote(self):
        if not self.on_remote_clicked:
            self._log.append_log("SYS: Dashboard not running — remote unavailable.")
            return
        result = self.on_remote_clicked()
        if not result:
            self._log.append_log("SYS: Could not generate remote key.")
            return
        url    = result[0]
        key    = result[1]
        auto   = result[2] if len(result) >= 3 else ""
        manual = result[3] if len(result) >= 4 else url
        if self._remote_overlay:
            self._remote_overlay._do_close()
        cw  = self.centralWidget()
        ow, oh = RemoteKeyOverlay._OW, RemoteKeyOverlay._OH
        ov  = RemoteKeyOverlay(url, key, auto_login_url=auto, manual_url=manual,
                               expiry_secs=600, parent=cw)
        ov.set_new_key_callback(self.on_remote_clicked)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.closed.connect(lambda: setattr(self, '_remote_overlay', None))
        ov.show()
        self._remote_overlay = ov
        self._log.append_log(f"SYS: Remote key generated — manual: {manual or url}")

    # ── Auto-start ──────────────────────────────────────────────────────────────

    def _check_autostart(self) -> bool:
        """Returns True if auto-start is currently registered on this OS."""
        try:
            if _OS == "Windows":
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
                try:
                    winreg.QueryValueEx(key, "JARVIS_AI")
                    return True
                except FileNotFoundError:
                    return False
                finally:
                    winreg.CloseKey(key)
            elif _OS == "Darwin":
                return (Path.home() / "Library" / "LaunchAgents"
                        / "com.jarvis.assistant.plist").exists()
            else:
                return (Path.home() / ".config" / "autostart" / "jarvis.desktop").exists()
        except Exception:
            return False

    def _toggle_autostart(self):
        currently_on = self._check_autostart()
        try:
            script = str(Path(__file__).resolve().parent / "main.py")
            if _OS == "Windows":
                import winreg
                reg = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
                if currently_on:
                    winreg.DeleteValue(reg, "JARVIS_AI")
                else:
                    pythonw = Path(sys.executable).parent / "pythonw.exe"
                    exe = str(pythonw if pythonw.exists() else sys.executable)
                    winreg.SetValueEx(reg, "JARVIS_AI", 0, winreg.REG_SZ,
                                      f'"{exe}" "{script}"')
                winreg.CloseKey(reg)
            elif _OS == "Darwin":
                plist_dir = Path.home() / "Library" / "LaunchAgents"
                plist_dir.mkdir(parents=True, exist_ok=True)
                plist = plist_dir / "com.jarvis.assistant.plist"
                if currently_on:
                    plist.unlink(missing_ok=True)
                else:
                    plist.write_text(
                        '<?xml version="1.0" encoding="UTF-8"?>\n'
                        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                        '<plist version="1.0"><dict>\n'
                        '  <key>Label</key><string>com.jarvis.assistant</string>\n'
                        '  <key>ProgramArguments</key><array>\n'
                        f'    <string>{sys.executable}</string>\n'
                        f'    <string>{script}</string>\n'
                        '  </array>\n'
                        '  <key>RunAtLoad</key><true/>\n'
                        '</dict></plist>\n'
                    )
            else:
                desk_dir = Path.home() / ".config" / "autostart"
                desk_dir.mkdir(parents=True, exist_ok=True)
                desk = desk_dir / "jarvis.desktop"
                if currently_on:
                    desk.unlink(missing_ok=True)
                else:
                    desk.write_text(
                        "[Desktop Entry]\n"
                        f"Name={self._assistant_name}\n"
                        f"Exec={sys.executable} {script}\n"
                        "Type=Application\nTerminal=false\n"
                        "X-GNOME-Autostart-enabled=true\n"
                    )
            enabled = not currently_on
            self._update_autostart_btn(enabled)
            self._log.append_log(
                f"SYS: Auto-start {'enabled' if enabled else 'disabled'}.")
        except Exception as e:
            self._log.append_log(f"ERR: Auto-start failed — {e}")

    def _update_autostart_btn(self, enabled: bool):
        if not hasattr(self, '_autostart_btn'):
            return
        if enabled:
            self._autostart_btn.setText("◉  AUTO-START: ON")
            self._autostart_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 3px;
                }}
                QPushButton:hover {{ background: #002010; }}
            """)
        else:
            self._autostart_btn.setText("◉  AUTO-START: OFF")
            self._autostart_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
            """)

    def _toggle_brief(self):
        from memory.config_manager import get_brief_enabled, save_brief_enabled
        new_val = not get_brief_enabled()
        save_brief_enabled(new_val)
        self._update_brief_btn(new_val)

    # ── Wake word settings ───────────────────────────────────────────────────

    def _wake_state(self) -> dict:
        """Combined state for the two wake-word buttons. Readiness is a cheap,
        deterministic on-disk check now (see core.wake_word.is_ready), so there
        is nothing to cache — the button never flickers to a stale value."""
        if self.wake_get_state:
            try:
                s = self.wake_get_state()
                return {"ready": bool(s.get("ready")),
                        "enabled": bool(s.get("enabled")),
                        "awake": bool(s.get("awake"))}
            except Exception:
                pass
        # Before JarvisLive has wired its callback (drawer built at startup).
        ready, enabled = False, False
        try:
            from core.wake_word import is_ready
            from memory.config_manager import get_wake_word_enabled
            ready, enabled = is_ready(), get_wake_word_enabled()
        except Exception:
            pass
        return {"ready": ready, "enabled": enabled, "awake": True}

    def _refresh_wake_btns(self):
        if not hasattr(self, '_wake_btn'):
            return
        st = self._wake_state()
        _on = f"""
            QPushButton {{ background: #001a08; color: {C.GREEN};
                border: 1px solid {C.GREEN_D}; border-radius: 3px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ background: #002010; }}"""
        _off = f"""
            QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 3px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}"""
        self._wake_btn.setEnabled(True)
        if not st["ready"]:
            self._wake_btn.setText("⬇  WAKE WORD: DOWNLOAD")
            self._wake_btn.setStyleSheet(_off)
            self._wake_sleep_btn.hide()
        elif st["enabled"]:
            self._wake_btn.setText("🎙  WAKE WORD: ON")
            self._wake_btn.setStyleSheet(_on)
            self._wake_sleep_btn.show()
            self._wake_sleep_btn.setText("😴  SLEEP NOW" if st["awake"] else "👂  WAKE NOW")
            self._wake_sleep_btn.setStyleSheet(_off)
        else:
            self._wake_btn.setText("🎙  WAKE WORD: OFF")
            self._wake_btn.setStyleSheet(_off)
            self._wake_sleep_btn.hide()

    def _refresh_talk_btns(self):
        """Repaint the push-to-talk row from the saved setting."""
        if not hasattr(self, "_ptt_btn"):
            return
        from core.hotkey import chord_label
        from memory.config_manager import get_push_to_talk_enabled
        _on = f"""
            QPushButton {{ background: #001a08; color: {C.GREEN};
                border: 1px solid {C.GREEN_D}; border-radius: 3px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ background: #002010; }}"""
        _off = f"""
            QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 3px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}"""

        ptt = get_push_to_talk_enabled()
        self._ptt_btn.setText(f"🎚  PUSH-TO-TALK: {chord_label()}" if ptt
                              else "🎚  PUSH-TO-TALK: OFF")
        self._ptt_btn.setStyleSheet(_on if ptt else _off)
        self._ptt_btn.setToolTip(
            "Microphone stays closed until you hold the key — nothing is sent "
            "while you are not holding it." if ptt
            else "Hold a key to talk instead of streaming the mic continuously.")


    def _refresh_hud_btn(self):
        from memory.config_manager import get_hud_style
        face = get_hud_style() == "face"
        # Neither state is "off", so both read as active — this is a choice
        # between two things, not a switch with a disabled side.
        style = f"""
            QPushButton {{ background: {C.PANEL2}; color: {C.PRI};
                border: 1px solid {C.BORDER_A}; border-radius: 3px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ color: {C.WHITE}; border: 1px solid {C.BORDER_B}; }}"""
        self._hud_btn.setText("🧑  HUD: ANIMATED FACE" if face
                              else "◉  HUD: REACTOR CORE")
        self._hud_btn.setStyleSheet(style)
        self._hud_btn.setToolTip(
            "An animated head that speaks your words and shows what JARVIS is "
            "doing. Tap to switch to the Mark 85 Arc Reactor core."
            if face else
            "The Mark 85 Arc Reactor core that turns with the state and moves with your voice. "
            "Tap to switch to the animated head.")

    def _toggle_hud_style(self):
        """Swap the centrepiece. Both objects stay in memory, so the change is
        instant and switching back costs nothing."""
        from memory.config_manager import get_hud_style, save_hud_style
        want = "core" if get_hud_style() == "face" else "face"
        save_hud_style(want)
        try:
            self.hud.hud_style = want
            self.hud.update()
        except Exception:
            pass
        self._refresh_hud_btn()
        self._log.append_log(
            "SYS: HUD switched to the animated face." if want == "face"
            else "SYS: HUD switched to the reactor core.")

    def _toggle_ptt(self):
        from memory.config_manager import (get_push_to_talk_enabled,
                                           save_push_to_talk_enabled)
        want = not get_push_to_talk_enabled()
        save_push_to_talk_enabled(want)
        scope = None
        if self.on_push_to_talk:
            try:
                scope = self.on_push_to_talk(want)
            except Exception as e:
                self._log.append_log(f"ERR: Push-to-talk failed — {e}")
                save_push_to_talk_enabled(False)
                want = False
        self._apply_ptt_shortcut(want and scope != "global")
        self._refresh_talk_btns()

    def _apply_ptt_shortcut(self, needed: bool):
        """Bind the chord inside the window when no global hook is available.

        On macOS and Linux there is no dependency-free way to read global key
        state, so the chord is at least live whenever this window has focus.
        Qt gives no key-release for a QShortcut, so a press latches the mic open
        and a short timer closes it; held down, auto-repeat keeps pushing that
        timer out, which behaves like holding a key.
        """
        from PyQt6.QtGui import QKeySequence, QShortcut
        from core.hotkey import qt_sequence

        if not needed:
            sc = getattr(self, "_ptt_sc", None)
            if sc is not None:
                sc.setEnabled(False)
                self._ptt_sc = None
            self._ptt_hold(False)
            return
        if getattr(self, "_ptt_sc", None) is not None:
            return

        self._ptt_release = QTimer(self)
        self._ptt_release.setSingleShot(True)
        self._ptt_release.setInterval(420)
        self._ptt_release.timeout.connect(lambda: self._ptt_hold(False))

        def _press():
            self._ptt_hold(True)
            self._ptt_release.start()

        self._ptt_sc = QShortcut(QKeySequence(qt_sequence()), self)
        self._ptt_sc.setAutoRepeat(True)
        self._ptt_sc.activated.connect(_press)

    def _ptt_hold(self, held: bool):
        """Report a windowed press/release to whoever owns the microphone."""
        cb = getattr(self, "ptt_hold", None)
        if cb:
            try:
                cb(bool(held))
            except Exception:
                pass

    def _toggle_wake_word(self):
        st = self._wake_state()
        if not st["ready"]:
            # First time: download openwakeword + model in a worker thread.
            self._wake_btn.setText("⬇  DOWNLOADING… (one-time)")
            self._wake_btn.setEnabled(False)
            def _work():
                try:
                    from core.wake_word import install_and_download
                    ok, msg = install_and_download(
                        logger=lambda m: self._log_sig.emit(f"SYS: {m}"))
                except Exception as e:
                    ok, msg = False, str(e)
                if ok and self.on_wake_toggle:
                    try:
                        self.on_wake_toggle(True)   # auto-enable after a successful download
                    except Exception:
                        pass
                self._wake_dl_sig.emit(ok, msg)
            threading.Thread(target=_work, daemon=True).start()
            return
        # Already downloaded → just flip enabled/disabled through JarvisLive.
        if self.on_wake_toggle:
            try:
                self.on_wake_toggle(not st["enabled"])
            except Exception:
                pass
        self._refresh_wake_btns()

    def _on_wake_install_done(self, ok: bool, msg: str):
        self._log_sig.emit(f"SYS: {'Wake word ready.' if ok else 'Wake word setup failed: ' + msg}")
        self._refresh_wake_btns()

    def _tap_wake_manual(self):
        if self.on_wake_manual:
            try:
                self.on_wake_manual()
            except Exception:
                pass
        self._refresh_wake_btns()

    def _update_brief_btn(self, enabled: bool):
        if not hasattr(self, '_brief_btn'):
            return
        if enabled:
            self._brief_btn.setText("☀  MORNING BRIEF: ON")
            self._brief_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 3px;
                    text-align: left; padding: 0 8px;
                }}
                QPushButton:hover {{ background: #002010; }}
            """)
        else:
            self._brief_btn.setText("☀  MORNING BRIEF: OFF")
            self._brief_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                    text-align: left; padding: 0 8px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
            """)

    # ── Customization ────────────────────────────────────────────────────────────

    def _open_customize(self):
        cfg = _read_full_config()
        if self._customize_overlay:
            self._customize_overlay.hide()
        cw = self.centralWidget()
        ov = CustomizeOverlay(
            cfg.get("assistant_name", "JARVIS") or "JARVIS",
            cfg.get("user_name", ""),
            cfg.get("ui_color", "") or DEFAULT_UI_COLOR,
            cfg.get("voice_name", ""),
            parent=cw,
        )
        ow, oh = CustomizeOverlay._OW, CustomizeOverlay._OH
        oh = min(oh, cw.height() - 16)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.on_preview = self._preview_ui_color
        ov.saved.connect(self._apply_name_update)
        ov.show()
        self._customize_overlay = ov

    def _preview_ui_color(self, hex_color: str):
        """Live preview — paints the whole interface the new colour (does NOT write to config)."""
        old = current_palette()
        if apply_ui_accent(hex_color):
            retheme_all_widgets(old, current_palette())

    def _apply_name_update(self, name: str, user_name: str, ui_color: str = "",
                           voice: str = ""):
        """Update all name/theme-dependent UI elements and persist to config."""
        self._assistant_name = name.strip() or "JARVIS"
        display = self._assistant_name.upper()
        self.setWindowTitle(f"{display} — {APP_VERSION}")
        self._title_lbl.setText(display)
        if display in ("JARVIS", "J.A.R.V.I.S"):
            self._sub_lbl.setText("Just A Rather Very Intelligent System")
        else:
            self._sub_lbl.setText("Personal AI Assistant")
        self._log._ai_name_lc = self._assistant_name.lower()
        self.hud._assistant_name = display
        self.hud._user_name = user_name.strip() or "DIVYANSHU VERMA"

        color_changed = False
        if ui_color:
            old = current_palette()
            if apply_ui_accent(ui_color):
                # Live-paint the whole interface (panels, buttons, borders, HUD)
                retheme_all_widgets(old, current_palette())
                color_changed = old["PRI"] != C.PRI

        # Voice change → persist and, if it actually changed, rebuild the Live
        # session so the new voice takes effect (it's fixed at connect time).
        voice_changed = False
        if voice:
            from memory.config_manager import get_voice, save_voice
            if voice != get_voice():
                save_voice(voice)
                voice_changed = True

        try:
            data = _read_full_config()
            data["assistant_name"] = self._assistant_name
            data["user_name"] = user_name.strip()
            if ui_color:
                data["ui_color"] = ui_color.strip().lower()
            API_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
            self._log.append_log(f"SYS: Identity updated — {display}")
            if color_changed:
                self._log.append_log(f"SYS: UI colour applied — {ui_color}")
            if voice_changed:
                self._log.append_log(f"SYS: Voice set — {voice}")
        except Exception as e:
            self._log.append_log(f"ERR: Config save failed — {e}")

        if voice_changed and self.on_voice_change:
            self.on_voice_change()

    def _centre_overlay(self, ov) -> None:
        """Place a floating overlay in the middle of the HUD and show it."""
        cw = self.centralWidget()
        ov.adjustSize()
        ov.setGeometry(
            max(0, (cw.width()  - ov.width())  // 2),
            max(0, (cw.height() - ov.height()) // 2),
            ov.width(), ov.height(),
        )
        ov.show()
        ov.raise_()

    # ── Audio devices ────────────────────────────────────────────────────────

    def _open_audio_devices(self):
        ov = AudioDeviceOverlay(parent=self.centralWidget())
        ov.picked.connect(self._on_audio_devices_applied)
        self._centre_overlay(ov)
        self._audio_overlay = ov            # keep a reference so it isn't GC'd

    def _on_audio_devices_applied(self):
        self._log.append_log("SYS: Audio devices updated.")
        if self.on_audio_device_change:
            self.on_audio_device_change()

    # ── Memory panel ─────────────────────────────────────────────────────────

    def _open_memory_panel(self):
        ov = MemoryOverlay(parent=self.centralWidget())
        self._centre_overlay(ov)
        self._memory_overlay = ov

    # ── Irreversible-action confirmation ─────────────────────────────────────

    def _show_confirm_banner(self, title: str, detail: str):
        self._hide_confirm_banner()
        ov = ConfirmBanner(title, detail, parent=self.centralWidget())
        ov.answered.connect(self._on_confirm_answered)
        self._centre_overlay(ov)
        self._confirm_overlay = ov

    def _hide_confirm_banner(self):
        ov = getattr(self, "_confirm_overlay", None)
        if ov is not None:
            ov.hide()
            ov.deleteLater()
            self._confirm_overlay = None

    def _on_confirm_answered(self, accepted: bool):
        # Tear the banner down first: core.confirm.resolve() may be about to
        # shut the machine down, and a live widget mid-callback is not where you
        # want to be when that happens.
        self._hide_confirm_banner()
        try:
            from core.confirm import resolve
            resolve(bool(accepted))
        except Exception as e:
            self._log.append_log(f"ERR: Confirmation failed — {e}")

    def _open_plugin_manager(self):
        plugins = self.get_plugins() if self.get_plugins else []
        cw = self.centralWidget()
        ov = PluginManagerOverlay(plugins, parent=cw)
        ov.adjustSize()
        ov.setGeometry(
            (cw.width()  - ov.width())  // 2,
            (cw.height() - ov.height()) // 2,
            ov.width(), ov.height(),
        )
        ov.show()
        ov.raise_()
        self._plugin_manager_overlay = ov   # keep a reference so it isn't GC'd

    def _open_plugin_settings(self):
        sections = self.get_plugin_settings() if self.get_plugin_settings else []
        cw = self.centralWidget()
        ov = PluginSettingsOverlay(sections, parent=cw)
        ow = PluginSettingsOverlay._OW
        oh = min(560, cw.height() - 16)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.show()
        ov.raise_()
        self._plugin_settings_overlay = ov   # keep a reference so it isn't GC'd

    # ── Clipboard intelligence ───────────────────────────────────────────────────

    def _on_clipboard_changed(self):
        try:
            text = QApplication.clipboard().text()
            if not text:
                return
            text = text.strip()
            # Ignore short strings, repetitive triggers, or massive dumps
            if 10 <= len(text) <= 5000:
                if getattr(self, "_last_clipboard_text", None) == text:
                    return
                self._last_clipboard_text = text
                self._clipboard_sig.emit(text)
        except Exception:
            pass

    def _show_clipboard_panel(self, text: str):
        try:
            self._clipboard_panel.show_clipboard(text)
            self._position_clipboard_panel()
        except Exception as e:
            print(f"[UI] Show clipboard panel error: {e}")

    def _position_clipboard_panel(self):
        try:
            cw = self.centralWidget()
            pw = ClipboardPanel._W
            ph = self._clipboard_panel.sizeHint().height() or ClipboardPanel._H
            x = (cw.width() - pw) // 2
            cockpit_h = self._command_cockpit.height() if hasattr(self, '_command_cockpit') and self._command_cockpit else 80
            y = max(60, cw.height() - cockpit_h - ph - 24)
            self._clipboard_panel.setGeometry(x, y, pw, ph)
            self._clipboard_panel.raise_()
        except Exception as e:
            print(f"[UI] Position clipboard panel error: {e}")

    def _on_clipboard_action(self, cmd: str):
        try:
            if self.on_text_command:
                threading.Thread(target=self.on_text_command, args=(cmd,), daemon=True).start()
        except Exception as e:
            print(f"[UI] Clipboard action error: {e}")

    # ────────────────────────────────────────────────────────────────────────────

    def _do_interrupt(self):
        if self.on_interrupt:
            self.on_interrupt()

    def _toggle_mute(self):
        # A deliberate press settles the question: whatever the video did, or is
        # about to do, the user has now said what they want.
        self._video_auto_muted = False
        self._set_muted(not self._muted)

    def _set_muted(self, muted: bool, note: str = ""):
        muted = bool(muted)
        if muted == self._muted:
            return
        self._muted = muted
        self.hud.muted = muted
        self._style_mute_btn()
        if muted:
            self._apply_state("MUTED")
            self._log.append_log("SYS: Microphone muted." + (f" {note}" if note else ""))
        else:
            self._apply_state("LISTENING")
            self._log.append_log("SYS: Microphone active." + (f" {note}" if note else ""))

    def _style_mute_btn(self):
        if hasattr(self, "_command_cockpit") and self._command_cockpit:
            self._command_cockpit._style_mute_btn(self._muted)
        elif hasattr(self, "_mute_btn") and self._mute_btn:
            if self._muted:
                self._mute_btn.setText("🔇  MICROPHONE MUTED")
                self._mute_btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #140006; color: {C.MUTED_C};
                        border: 1px solid {C.MUTED_C}; border-radius: 4px; padding: 0 10px;
                    }}
                """)
            else:
                self._mute_btn.setText("🎙  MICROPHONE ACTIVE")
                self._mute_btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #00140a; color: {C.GREEN};
                        border: 1px solid {C.GREEN}; border-radius: 4px; padding: 0 10px;
                    }}
                    QPushButton:hover {{ background: #002412; color: #ffffff; }}
                """)

    def _send(self):
        txt = self._input.text().strip()
        if not txt: return
        self._input.clear()
        self._log.append_log(f"You: {txt}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(txt,), daemon=True).start()

    def _apply_state(self, state: str):
        self.hud.state    = state
        self.hud.speaking = (state == "SPEAKING")
        if hasattr(self, "_system_telemetry") and self._system_telemetry:
            self._system_telemetry.set_system_state(state)
        if hasattr(self, "_command_cockpit") and self._command_cockpit:
            self._command_cockpit.set_system_state(state)
        if hasattr(self, "_header_state_lbl") and self._header_state_lbl:
            _col = {
                "LISTENING": C.GREEN,
                "SPEAKING": C.PRI,
                "THINKING": C.ACC2,
                "MUTED": C.MUTED_C,
            }.get(state.upper(), C.TEXT_MED)
            _bg = {
                "LISTENING": "rgba(0, 255, 136, 0.08)",
                "SPEAKING": "rgba(0, 212, 255, 0.08)",
                "THINKING": "rgba(255, 204, 0, 0.08)",
                "MUTED": "rgba(255, 68, 102, 0.08)",
            }.get(state.upper(), "rgba(90, 184, 204, 0.08)")
            _border = {
                "LISTENING": C.GREEN_D,
                "SPEAKING": C.PRI_DIM,
                "THINKING": C.ACC,
                "MUTED": C.RED,
            }.get(state.upper(), C.BORDER)
            self._header_state_lbl.setText(f"● {state.upper()}")
            self._header_state_lbl.setStyleSheet(f"""
                color: {_col}; background: {_bg};
                border: 1px solid {_border}; border-radius: 9px;
                padding: 1px 8px; font-weight: bold;
            """)

    def _check_config(self) -> bool:
        if not API_FILE.exists(): return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            if not d.get("gemini_api_key"):
                return False
            detected = {"darwin": "mac", "windows": "windows"}.get(_OS.lower(), "linux")
            if d.get("os_system") != detected:
                d["os_system"] = detected
                API_FILE.write_text(json.dumps(d, indent=4), encoding="utf-8")
            return True
        except Exception:
            return False

    def _show_setup(self):
        ov = SetupOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow, oh = 460, 390
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.done.connect(self._on_setup_done)
        ov.show()
        self._overlay = ov

    def _on_setup_done(self, key: str, os_name: str):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        cfg = _read_full_config()
        cfg["gemini_api_key"] = key
        cfg["os_system"] = os_name
        API_FILE.write_text(
            json.dumps(cfg, indent=4),
            encoding="utf-8",
        )
        self._ready = True
        if self._overlay:
            self._overlay.hide()
            self._overlay = None
        self._apply_state("LISTENING")
        self._assistant_name = _read_full_config().get("assistant_name", "JARVIS") or "JARVIS"
        self._log.append_log(f"SYS: Initialised. OS={os_name.upper()}. {self._assistant_name} online.")


class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app
    def mainloop(self):
        self._app.exec()
    def protocol(self, *_):
        pass


class JarvisUI:
    def __init__(self, face_path: str, size=None):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self._win = MainWindow(face_path)
        self.root = _RootShim(self._app)
        self._win.show()

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if v != self._win._muted:
            self._win._toggle_mute()

    @property
    def current_file(self) -> str | None:
        if hasattr(self._win, "_current_file") and self._win._current_file:
            return self._win._current_file
        if hasattr(self._win, "_drop_zone") and self._win._drop_zone:
            return self._win._drop_zone.current_file()
        return None

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    @property
    def on_remote_clicked(self):
        return self._win.on_remote_clicked

    @on_remote_clicked.setter
    def on_remote_clicked(self, cb):
        self._win.on_remote_clicked = cb

    @property
    def on_interrupt(self):
        return self._win.on_interrupt

    @on_interrupt.setter
    def on_interrupt(self, cb):
        self._win.on_interrupt = cb

    @property
    def on_voice_change(self):
        return self._win.on_voice_change

    @on_voice_change.setter
    def on_voice_change(self, cb):
        self._win.on_voice_change = cb

    @property
    def on_audio_device_change(self):
        return self._win.on_audio_device_change

    @on_audio_device_change.setter
    def on_audio_device_change(self, cb):
        self._win.on_audio_device_change = cb

    def show_confirm(self, title: str, detail: str) -> None:
        """Thread-safe: raise the irreversible-action gate. Called from action
        handlers running in executor threads, so it goes through a signal."""
        self._win._confirm_sig.emit(str(title)[:120], str(detail)[:300])

    def hide_confirm(self) -> None:
        """Thread-safe: take the gate down."""
        self._win._confirm_hide_sig.emit()

    @property
    def get_plugins(self):
        return self._win.get_plugins

    @get_plugins.setter
    def get_plugins(self, cb):
        self._win.get_plugins = cb

    @property
    def get_plugin_settings(self):
        return self._win.get_plugin_settings

    @get_plugin_settings.setter
    def get_plugin_settings(self, cb):
        self._win.get_plugin_settings = cb

    @property
    def on_wake_toggle(self):
        return self._win.on_wake_toggle

    @on_wake_toggle.setter
    def on_wake_toggle(self, cb):
        self._win.on_wake_toggle = cb

    @property
    def on_wake_manual(self):
        return self._win.on_wake_manual

    @on_wake_manual.setter
    def on_wake_manual(self, cb):
        self._win.on_wake_manual = cb

    @property
    def wake_get_state(self):
        return self._win.wake_get_state

    @wake_get_state.setter
    def wake_get_state(self, cb):
        self._win.wake_get_state = cb

    def set_audio_level(self, level: float) -> None:
        """Thread-safe: feed a 0.0–1.0 live audio level to the HUD waveform.
        Called from the audio threads; a plain float store is atomic under the
        GIL, so no signal/lock is needed for this cosmetic value."""
        try:
            self._win.hud.set_audio_level(level)
        except Exception:
            pass

    def glance(self, dx: float, dy: float, hold: float = 1.1) -> None:
        """Ask the avatar to look somewhere for a moment (see HoloAvatar.glance)."""
        try:
            if self._avatar is not None:
                self._avatar.glance(dx, dy, hold)
        except Exception:
            pass

    @property
    def ptt_hold(self):
        return self._win.ptt_hold

    @ptt_hold.setter
    def ptt_hold(self, cb):
        self._win.ptt_hold = cb

    @property
    def on_push_to_talk(self):
        return self._win.on_push_to_talk

    @on_push_to_talk.setter
    def on_push_to_talk(self, cb):
        self._win.on_push_to_talk = cb

    def push_visemes(self, frames, hop: float, at: float) -> None:
        """Thread-safe: post a schedule of (level, openness, width) mouth frames
        for JARVIS's own speech. `at` is the wall-clock time the batch begins to
        sound, not the time of the call. See HudCanvas.push_visemes()."""
        try:
            self._win.hud.push_visemes(frames, hop, at)
        except Exception:
            pass

    def notify_phone_connected(self) -> None:
        self._win.notify_phone_connected()

    def set_state(self, state: str):
        self._win._state_sig.emit(state)

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)

    def show_content(self, title: str, text: str):
        """Thread-safe: display content in the panel below the HUD."""
        self._win._content_sig.emit(title[:48], text[:4000])

    def show_quiz(self, topic: str, questions, grade=None) -> None:
        """Thread-safe: put an interactive quiz on the board.

        `grade(question, given)` decides each answer — the plugin supplies it so
        the marking rules live with the questions rather than being duplicated
        here. Returning None from it means "JARVIS should judge this one", which
        is how open answers and near-miss gap-fills are handled.

        Returns immediately: the user answers at their own pace and the finished
        result is delivered back through on_text_command.
        """
        self._win._quiz_sig.emit(str(topic or ""), list(questions or []), grade)

    def hide_quiz(self) -> None:
        """Thread-safe: clear any quiz currently on the board."""
        self._win._quiz_hide_sig.emit()

    def show_review(self, title: str, summary: str, findings, unclear=None) -> None:
        """Thread-safe: lay a document review into the panel below the HUD.

        `findings` is a list of {heading, detail, severity, quote, suggestion};
        severity is one of 'serious' / 'caution' / 'note' and decides colour and
        order here, so the caller supplies no styling of its own.
        """
        self._win._review_sig.emit(str(title or ""), str(summary or ""),
                                   list(findings or []), list(unclear or []))

    def prompt_reconfig(self):
        """Thread-safe: show the API key setup overlay (e.g. after an auth error)."""
        self._win._ready = False
        self._win._reconfig_sig.emit()

    def show_camera_frame(self, img_bytes: bytes):
        """Thread-safe: show a webcam frame in the small overlay (screen captures)."""
        self._win._camera_sig.emit(img_bytes)

    def show_video(self, source: str, title: str = "", muted: bool = True,
                   audio_source: str = "") -> None:
        """Thread-safe: play a video where the avatar normally is.

        `source` is a local path or a direct media URL. `audio_source` is for
        the case where the sound arrives as its own stream — YouTube serves no
        combined format any more — and when it is given the two are played
        together and kept in step.

        Muted by default, and that is a decision rather than a default: a
        soundtrack talking over JARVIS is the one way this could make the
        assistant worse. The user turns sound on from the header button or by
        asking, and closes it the same two ways.
        """
        self._win._video_open_sig.emit(str(source or ""), str(title or ""),
                                       bool(muted), str(audio_source or ""))

    def stop_video(self) -> None:
        """Thread-safe: close the video and give the HUD back to the avatar."""
        self._win._video_close_sig.emit()

    def set_video_muted(self, muted: bool) -> None:
        """Thread-safe: silence or unsilence whatever is playing."""
        self._win._video_mute_sig.emit(bool(muted))

    def video_is_playing(self) -> bool:
        return bool(self._win.video_is_playing())

    def start_camera_stream(self) -> None:
        """Thread-safe: start live camera feed in the full HUD area."""
        self._win.start_camera_stream()

    def stop_camera_stream(self) -> None:
        """Thread-safe: stop the live camera feed."""
        self._win.stop_camera_stream()

    def open_screen_share_dialog(self) -> None:
        """Thread-safe: open screen share selection dialog."""
        self._win._screenshare_open_dlg_sig.emit()

    def start_screen_share(self, target: dict = None) -> None:
        """Thread-safe: start screen or window sharing in the HUD area."""
        self._win._screenshare_start_sig.emit(target or {})

    def stop_screen_share(self) -> None:
        """Thread-safe: stop screen sharing and restore avatar."""
        self._win._screenshare_stop_sig.emit()

    @property
    def assistant_name(self) -> str:
        return self._win._assistant_name

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")