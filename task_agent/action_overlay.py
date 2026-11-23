"""Visible Desktop Action Overlay and Click Halo Indicator for Jadoo Task Agent.

Renders non-intrusive action status banners and click halo rings directly
on the Windows desktop using a click-through transparent PySide6 overlay.
"""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Slot
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from utils.logger import logger


class ActionOverlay(QWidget):
    """Full-screen click-through overlay showing action banners and click halos."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # Full-screen click-through window
        flags = (
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.setObjectName("ActionOverlay")

        # State
        self._action_text: str = ""
        self._halo_center: Optional[QPoint] = None
        self._halo_radius: int = 15
        self._halo_opacity: float = 0.0

        # Animation timer for click halo
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._step_halo_animation)
        self._anim_start_time: float = 0.0

        # Banner auto-clear timer
        self._banner_clear_timer = QTimer(self)
        self._banner_clear_timer.setSingleShot(True)
        self._banner_clear_timer.timeout.connect(self.clear_action)

        self._fit_to_screen()

    def _fit_to_screen(self) -> None:
        """Position overlay across primary display screen."""
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.geometry()
            self.setGeometry(geom)

    @Slot(str)
    def show_action(self, action_text: str, duration_ms: int = 3500) -> None:
        """Display floating action banner at top-center of the screen."""
        self._fit_to_screen()
        self._action_text = action_text
        self.show()
        self.update()
        if duration_ms > 0:
            self._banner_clear_timer.start(duration_ms)

    @Slot(int, int)
    def trigger_click_halo(self, x: int, y: int) -> None:
        """Trigger visual expanding click halo at target coordinates."""
        self._fit_to_screen()
        self._halo_center = QPoint(x, y)
        self._halo_radius = 12
        self._halo_opacity = 0.9
        self._anim_start_time = time.monotonic()
        self.show()
        self._anim_timer.start(16)  # ~60 Hz animation
        self.update()

    def _step_halo_animation(self) -> None:
        """Step expanding click halo animation."""
        elapsed = time.monotonic() - self._anim_start_time
        if elapsed > 0.35:
            # Animation complete
            self._halo_center = None
            self._halo_opacity = 0.0
            self._anim_timer.stop()
            self.update()
            if not self._action_text:
                self.hide()
        else:
            progress = elapsed / 0.35
            self._halo_radius = int(12 + (progress * 30))
            self._halo_opacity = max(0.0, 0.9 * (1.0 - progress))
            self.update()

    @Slot()
    def clear_action(self) -> None:
        """Clear action text banner."""
        self._action_text = ""
        self.update()
        if not self._halo_center:
            self.hide()

    def paintEvent(self, event) -> None:
        """Paint action banner and click halo."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. Paint Click Halo if active
        if self._halo_center is not None and self._halo_opacity > 0:
            color = QColor(139, 92, 246, int(self._halo_opacity * 255))  # Purple accent
            pen = QPen(color, 3)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(self._halo_center, self._halo_radius, self._halo_radius)

            # Center dot
            painter.setBrush(QColor(196, 181, 253, int(self._halo_opacity * 220)))
            painter.drawEllipse(self._halo_center, 4, 4)

        # 2. Paint Top Action Status Banner
        if self._action_text:
            text = f"✦ JADOO AGENT: {self._action_text}"
            font = QFont("Segoe UI", 11, QFont.Weight.Bold)
            painter.setFont(font)

            # Calculate text width
            metrics = painter.fontMetrics()
            text_width = metrics.horizontalAdvance(text) + 36
            banner_height = 36

            screen_w = self.width()
            banner_x = (screen_w - text_width) // 2
            banner_y = 20

            banner_rect = QRect(banner_x, banner_y, text_width, banner_height)

            # Draw background pill
            painter.setPen(QPen(QColor(124, 58, 237), 2))
            painter.setBrush(QColor(17, 24, 39, 235))
            painter.drawRoundedRect(banner_rect, 18, 18)

            # Draw text
            painter.setPen(QColor(245, 245, 245))
            painter.drawText(banner_rect, Qt.AlignmentFlag.AlignCenter, text)

        painter.end()
