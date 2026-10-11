"""
3D Interactive Mark VII Gantry Turntable Viewer for JARVIS.

Renders high-fidelity 360-degree turntable frames generated from
`IronMan_Mark7_Gantry_Production.blend` with real-time mouse-drag rotation,
mouse-wheel zoom, idle auto-spin, and sci-fi Iron Man HUD telemetry overlays.
"""
from __future__ import annotations

import math
import os
import subprocess
import time
from pathlib import Path
from typing import Optional, List

from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QPixmap, QImage, QColor, QPen, QBrush, QFont,
    QRadialGradient, QLinearGradient, QPainterPath
)
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QSizePolicy, QToolTip
)


GANTRY_DIR = Path(__file__).resolve().parent.parent / "assets" / "gantry_turntable"
GANTRY_BLEND = Path(__file__).resolve().parent.parent / "IronMan_Mark7_Gantry_Production.blend"


class GantryTurntableWidget(QWidget):
    """Interactive 3D Turntable viewer for the Mark VII Gantry."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(280, 280)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        self._frames: List[QPixmap] = []
        self._frame_idx: int = 0
        self._total_frames: int = 36
        self._angle_deg: float = 0.0

        # Interaction state
        self._dragging: bool = False
        self._drag_start_x: float = 0.0
        self._drag_start_frame: int = 0
        self._last_mouse_pos: QPointF = QPointF(0, 0)
        self._zoom: float = 1.0       # 0.65 to 2.4
        self._tgt_zoom: float = 1.0

        # Auto-rotation state
        self._auto_rotate: bool = True
        self._last_interaction_time: float = 0.0
        self._pause_auto_duration: float = 3.0  # seconds pause after manual touch
        self._rotate_speed_divisor: int = 18    # 18 ticks * 33ms = ~594ms per frame (~21s per 360° turn)

        # Animation & telemetry tick
        self._tick: int = 0
        self._glow_pulse: float = 0.0

        # Load frames
        self._load_turntable_frames()

        # Step timer (60 Hz for smooth auto-rotation and HUD overlay animation)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(33)  # ~30 FPS timer for buttery smoothness and low CPU

        # Overlay control buttons
        self._init_controls()

    def _load_turntable_frames(self) -> None:
        """Pre-load all 36 transparent PNG turntable frames into memory."""
        self._frames.clear()
        if GANTRY_DIR.exists():
            for i in range(self._total_frames):
                p = GANTRY_DIR / f"frame_{i:03d}.png"
                if p.exists():
                    pm = QPixmap(str(p))
                    if not pm.isNull():
                        self._frames.append(pm)
        if self._frames:
            self._total_frames = len(self._frames)
            self._frame_idx = 0
            self._angle_deg = 0.0

    def _init_controls(self) -> None:
        """Create sleek translucent HUD control buttons in top/bottom corners."""
        self._root_lay = QVBoxLayout(self)
        self._root_lay.setContentsMargins(12, 10, 12, 10)

        # Top Bar: Bay Header + Status + Auto Toggle
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self._lbl_header = QLabel("◈ MARK VII // GANTRY BAY 07")
        self._lbl_header.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        self._lbl_header.setStyleSheet("color: #00d2ff; background: transparent;")
        top_bar.addWidget(self._lbl_header)

        top_bar.addStretch()

        # Auto-rotate toggle pill
        self._btn_auto = QPushButton("⟳ AUTO")
        self._btn_auto.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._btn_auto.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_auto.setToolTip("Toggle automatic 360° turntable rotation")
        self._btn_auto.setStyleSheet("""
            QPushButton {
                background: rgba(0, 210, 255, 0.12);
                color: #00d2ff;
                border: 1px solid rgba(0, 210, 255, 0.45);
                border-radius: 4px;
                padding: 3px 8px;
            }
            QPushButton:hover {
                background: rgba(0, 210, 255, 0.28);
                color: #ffffff;
                border-color: #00d2ff;
            }
        """)
        self._btn_auto.clicked.connect(self._toggle_auto_rotate)
        top_bar.addWidget(self._btn_auto)

        # Reset button
        self._btn_reset = QPushButton("↺ RESET")
        self._btn_reset.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_reset.setToolTip("Reset rotation angle to 0° and zoom to 100%")
        self._btn_reset.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #8da4be;
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 4px;
                padding: 3px 7px;
            }
            QPushButton:hover {
                background: rgba(0, 210, 255, 0.15);
                color: #00d2ff;
                border-color: rgba(0, 210, 255, 0.5);
            }
        """)
        self._btn_reset.clicked.connect(self.reset_view)
        top_bar.addWidget(self._btn_reset)

        self._root_lay.addLayout(top_bar)
        self._root_lay.addStretch(1)

        # Bottom Bar: Azimuth readout
        bot_bar = QHBoxLayout()
        bot_bar.setSpacing(8)

        self._lbl_azimuth = QLabel("AZIMUTH: 000° [BEARING: N]")
        self._lbl_azimuth.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._lbl_azimuth.setStyleSheet("color: rgba(0, 210, 255, 0.75); background: transparent;")
        bot_bar.addWidget(self._lbl_azimuth)

        bot_bar.addStretch()

        self._root_lay.addLayout(bot_bar)

    def _toggle_auto_rotate(self) -> None:
        self._auto_rotate = not self._auto_rotate
        if self._auto_rotate:
            self._btn_auto.setText("⟳ AUTO")
            self._btn_auto.setStyleSheet("""
                QPushButton {
                    background: rgba(0, 210, 255, 0.18);
                    color: #00d2ff;
                    border: 1px solid rgba(0, 210, 255, 0.5);
                    border-radius: 4px;
                    padding: 3px 8px;
                }
                QPushButton:hover {
                    background: rgba(0, 210, 255, 0.3);
                    color: #ffffff;
                }
            """)
        else:
            self._btn_auto.setText("⏸ PAUSED")
            self._btn_auto.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.05);
                    color: #6a829a;
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 4px;
                    padding: 3px 8px;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 0.1);
                    color: #ffffff;
                }
            """)

    def reset_view(self) -> None:
        """Reset rotation to frame 0 (front view) and zoom to 1.0x."""
        self._frame_idx = 0
        self._angle_deg = 0.0
        self._zoom = 1.0
        self._tgt_zoom = 1.0
        self._update_azimuth_label()
        self.update()

    def _step(self) -> None:
        """Advance animation tick and idle turntable rotation."""
        if not self.isVisible():
            return
        self._tick += 1
        now = time.time()

        # Smooth zoom lerp
        if abs(self._zoom - self._tgt_zoom) > 0.005:
            self._zoom += (self._tgt_zoom - self._zoom) * 0.25

        # Auto-rotate when not dragging and after pause period has expired
        if self._auto_rotate and not self._dragging:
            if (now - self._last_interaction_time) > self._pause_auto_duration:
                # Advance 1 frame every 18 ticks (~21s per 360° turn for majestic cinematic HUD turntable)
                if self._tick % self._rotate_speed_divisor == 0 and self._total_frames > 0:
                    self._frame_idx = (self._frame_idx + 1) % self._total_frames
                    self._angle_deg = (self._frame_idx / self._total_frames) * 360.0
                    self._update_azimuth_label()

        self.update()

    def _update_azimuth_label(self) -> None:
        """Update bearing label."""
        deg = int(round(self._angle_deg)) % 360
        dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        idx = int((deg + 11.25) / 22.5) % 16
        bearing = dirs[idx]
        self._lbl_azimuth.setText(f"AZIMUTH: {deg:03d}° [BEARING: {bearing}]")

    # ── Mouse Interaction ─────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start_x = event.position().x()
            self._drag_start_frame = self._frame_idx
            self._last_mouse_pos = event.position()
            self._last_interaction_time = time.time()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        self._last_mouse_pos = event.position()
        if self._dragging and self._total_frames > 0:
            self._last_interaction_time = time.time()
            dx = event.position().x() - self._drag_start_x
            # 8 pixels of horizontal drag = 1 frame step for snappy responsiveness
            frame_delta = int(round(dx / 8.0))
            self._frame_idx = (self._drag_start_frame + frame_delta) % self._total_frames
            self._angle_deg = (self._frame_idx / self._total_frames) * 360.0
            self._update_azimuth_label()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._last_interaction_time = time.time()
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def wheelEvent(self, event) -> None:
        """Adjust zoom with mouse wheel."""
        self._last_interaction_time = time.time()
        delta = event.angleDelta().y() * 0.0012
        self._tgt_zoom = max(0.65, min(2.4, self._tgt_zoom + delta))
        self.update()

    def mouseDoubleClickEvent(self, event) -> None:
        self.reset_view()

    # ── Paint Event ───────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        if not p.isActive():
            return

        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        W = self.width()
        H = self.height()
        cx = W / 2.0
        cy = H / 2.0
        size_min = min(W, H)

        # 1. Dark Deep-Space Vignette Background
        bg_grad = QRadialGradient(cx, cy, max(W, H) * 0.75)
        bg_grad.setColorAt(0.0, QColor("#030a14"))
        bg_grad.setColorAt(0.55, QColor("#02060c"))
        bg_grad.setColorAt(1.0, QColor("#010307"))
        p.fillRect(self.rect(), QBrush(bg_grad))

        # 2. Draw 360 Turntable Frame
        if self._frames and 0 <= self._frame_idx < len(self._frames):
            frame = self._frames[self._frame_idx]
            # Sizing: fit nicely within widget bounds while scaling with zoom
            base_dim = size_min * 0.98 * self._zoom
            dest_rect = QRectF(cx - base_dim / 2.0, cy - base_dim / 2.0, base_dim, base_dim)
            p.drawPixmap(dest_rect.toRect(), frame)
        else:
            # Fallback placeholder if frames are not rendered yet
            p.setPen(QPen(QColor(0, 210, 255, 150), 1.2))
            p.setFont(QFont("Courier New", 10))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "◈ MARK VII GANTRY 3D\n[LOADING MODEL...]")

        # 3. Sci-Fi Iron Man HUD Reticle & Corner Brackets Overlays
        self._paint_hud_overlays(p, W, H, cx, cy, size_min)

        p.end()

    def _paint_hud_overlays(self, p: QPainter, W: float, H: float,
                            cx: float, cy: float, sz: float) -> None:
        """Paint Iron Man targeting crosshairs, telemetry tags and tech brackets."""
        # Corner Framing Brackets
        c_cyan = QColor("#00d2ff")
        c_cyan_dim = QColor(0, 210, 255, 75)
        c_amber = QColor("#ffaa00")

        p.setBrush(Qt.BrushStyle.NoBrush)

        # 4-corner brackets
        inset = 14.0
        b_len = 18.0
        p.setPen(QPen(c_cyan_dim, 1.2))

        # Top-Left
        p.drawLine(QPointF(inset, inset), QPointF(inset + b_len, inset))
        p.drawLine(QPointF(inset, inset), QPointF(inset, inset + b_len))
        # Top-Right
        p.drawLine(QPointF(W - inset, inset), QPointF(W - inset - b_len, inset))
        p.drawLine(QPointF(W - inset, inset), QPointF(W - inset, inset + b_len))
        # Bottom-Left
        p.drawLine(QPointF(inset, H - inset), QPointF(inset + b_len, H - inset))
        p.drawLine(QPointF(inset, H - inset), QPointF(inset, H - inset - b_len))
        # Bottom-Right
        p.drawLine(QPointF(W - inset, H - inset), QPointF(W - inset - b_len, H - inset))
        p.drawLine(QPointF(W - inset, H - inset), QPointF(W - inset, H - inset - b_len))

        # Center Targeting Reticle (Iron Man HUD crosshair)
        ret_r = sz * 0.16 * self._zoom
        p.setPen(QPen(QColor(0, 210, 255, 45), 1.0))
        p.drawEllipse(QPointF(cx, cy), ret_r, ret_r)

        # 4 Cardinal Reticle Pips
        pip_len = 7.0
        p.setPen(QPen(QColor(0, 210, 255, 90), 1.2))
        p.drawLine(QPointF(cx - ret_r - pip_len, cy), QPointF(cx - ret_r + pip_len, cy))
        p.drawLine(QPointF(cx + ret_r - pip_len, cy), QPointF(cx + ret_r + pip_len, cy))
        p.drawLine(QPointF(cx, cy - ret_r - pip_len), QPointF(cx, cy - ret_r + pip_len))
        p.drawLine(QPointF(cx, cy + ret_r - pip_len), QPointF(cx, cy + ret_r + pip_len))

        # Center dot
        p.setBrush(QBrush(QColor(0, 210, 255, 120)))
        p.drawEllipse(QPointF(cx, cy), 1.8, 1.8)

        # Telemetry Callout Badges
        p.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        p.setPen(QPen(QColor(0, 210, 255, 100), 1.0))
        p.drawText(QRectF(inset + 4, inset + 26, 180, 16),
                   Qt.AlignmentFlag.AlignLeft, "ARMOR: TITANIUM-GOLD")
        p.drawText(QRectF(inset + 4, inset + 40, 180, 16),
                   Qt.AlignmentFlag.AlignLeft, "SERVO TORQUE: 100% NOM")

        # Live rotation indicator tick bar (horizontal scrubber preview)
        scrub_w = min(140.0, W * 0.35)
        scrub_x = cx - scrub_w / 2.0
        scrub_y = H - 28.0

        p.setPen(QPen(QColor(0, 210, 255, 40), 1.0))
        p.drawLine(QPointF(scrub_x, scrub_y), QPointF(scrub_x + scrub_w, scrub_y))

        # Scrubber marker
        marker_x = scrub_x + (self._frame_idx / max(1, self._total_frames - 1)) * scrub_w
        p.setPen(QPen(QColor(0, 210, 255, 200), 1.5))
        p.drawLine(QPointF(marker_x, scrub_y - 4), QPointF(marker_x, scrub_y + 4))
