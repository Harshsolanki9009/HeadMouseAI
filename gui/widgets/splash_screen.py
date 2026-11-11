"""Professional OBSIDIAN CHROME startup splash screen for HeadMouseAI.

Design Identity:
- Deep black & charcoal obsidian surfaces (#151619 -> #0B0C0E)
- Precision 1px metallic borders (#24262B) with top chrome specular rim
- Right column: Flowing 3D sculptural chrome mobius loop ribbons with realistic reflections
- Left column: HeadMouseAI identity, tagline, minimal specular progress groove,
  real-time initialization telemetry, and elegant 'A Product by ACROPOLIANS' branding.
- Non-blocking 60 FPS cubic ease-out animation sequence with selective repainting.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect, QWidget

from utils.resource import get_icon_path, get_image_path


def _ease_out_cubic(x: float) -> float:
    """Standard cubic ease-out curve for restrained, natural motion."""
    x = max(0.0, min(1.0, x))
    return 1.0 - pow(1.0 - x, 3)


class SplashScreen(QWidget):
    """Custom frameless startup splash screen with OBSIDIAN CHROME aesthetic,

    flowing 3D chrome sculptural artwork, and ACROPOLIANS corporate branding.
    """

    sig_finished = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.SplashScreen
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(620, 360)

        self._status_text: str = "Initializing AI vision models..."
        self._start_time: Optional[float] = None
        self._elapsed_ms: float = 0.0
        self._spinner_angle: float = 0.0

        # Load official application squircle icon
        self._raw_icon: Optional[QPixmap] = None
        icon_path = get_icon_path("app_icon.png")
        if icon_path.is_file():
            self._raw_icon = QPixmap(str(icon_path))

        # Load 3D Chrome Sculpture artwork
        self._raw_chrome: Optional[QPixmap] = None
        chrome_path = get_image_path("splash_chrome_sculpture.png")
        if chrome_path.is_file():
            self._raw_chrome = QPixmap(str(chrome_path))

        # Center on primary monitor with taskbar awareness
        screen = QApplication.primaryScreen()
        if screen is not None:
            geom = screen.availableGeometry()
            self.move(
                (geom.width() - self.width()) // 2,
                (geom.height() - self.height()) // 2,
            )

        # Window-level fade-in opacity animation
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_anim.setDuration(320)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 60 FPS lightweight animation timer (16ms)
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._on_anim_tick)

    def show_animated(self) -> None:
        """Show splash screen and begin startup timeline."""
        self._start_time = time.perf_counter()
        self._elapsed_ms = 0.0
        self.show()
        self._fade_anim.start()
        self._anim_timer.start()

    def set_status(self, text: str) -> None:
        """Update current subsystem initialization status message."""
        self._status_text = text
        self.update(QRect(40, 205, 280, 30))
        QApplication.processEvents()

    def _on_spinner_tick(self) -> None:
        """Legacy tick hook maintained for backward compatibility with automated tests."""
        self._spinner_angle = (self._spinner_angle + 6.0) % 360.0

    def _on_anim_tick(self) -> None:
        """Advance internal animation timeline at ~60 FPS with selective repainting."""
        if self._start_time is None:
            self._start_time = time.perf_counter()
        self._elapsed_ms = (time.perf_counter() - self._start_time) * 1000.0
        self._on_spinner_tick()

        # During entrance reveal (~first 850ms), repaint whole surface for smooth easing
        if self._elapsed_ms < 850.0:
            self.update()
        else:
            # Once elements have settled, repaint only the active 2px loading groove & status text (zero CPU)
            self.update(QRect(40, 190, 260, 48))

    def finish_and_show(self, target_window: QWidget) -> None:
        """Smoothly fade out splash screen and present the main application window."""
        self._fade_anim.stop()
        self._fade_out_anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_out_anim.setDuration(220)
        self._fade_out_anim.setStartValue(self._opacity_effect.opacity())
        self._fade_out_anim.setEndValue(0.0)
        self._fade_out_anim.setEasingCurve(QEasingCurve.Type.InCubic)

        def _on_fade_out_end() -> None:
            self._anim_timer.stop()
            self.close()
            target_window.show()
            target_window.raise_()
            target_window.activateWindow()
            self.sig_finished.emit()

        self._fade_out_anim.finished.connect(_on_fade_out_end)
        self._fade_out_anim.start()

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint Obsidian Chrome surface, flowing 3D sculpture, typography, and ACROPOLIANS branding."""
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

            w = self.width()
            h = self.height()
            t = self._elapsed_ms

            # 1. Base Container Clip Path (Rounded Rect r = 14)
            outer_path = QPainterPath()
            outer_path.addRoundedRect(0, 0, w - 1, h - 1, 14, 14)
            painter.setClipPath(outer_path)

            # 2. Obsidian Surface Background (#151619 -> #0B0C0E)
            bg_grad = QLinearGradient(0, 0, w, h)
            bg_grad.setColorAt(0.0, QColor("#151619"))  # Charcoal surface
            bg_grad.setColorAt(0.55, QColor("#0F1013")) # Intermediate dark slate
            bg_grad.setColorAt(1.0, QColor("#0B0C0E"))  # Deep black
            painter.fillRect(self.rect(), bg_grad)

            # Subtle charcoal secondary texture pane on left
            left_pane_w = 340
            left_grad = QLinearGradient(0, 0, left_pane_w, 0)
            left_grad.setColorAt(0.0, QColor(255, 255, 255, 5))
            left_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.fillRect(QRect(0, 0, left_pane_w, h), left_grad)

            # --- Easing Timeline Calculations ---
            # Chrome artwork: t = 60..480ms (scale 0.94 -> 1.0, opacity 0.0 -> 1.0)
            chrome_p = _ease_out_cubic((t - 60.0) / 420.0) if t > 60.0 else 0.0
            chrome_scale = 0.94 + 0.06 * chrome_p
            chrome_alpha = chrome_p

            # Icon: t = 120..420ms (scale 0.88 -> 1.0, opacity 0.0 -> 1.0)
            icon_p = _ease_out_cubic((t - 120.0) / 300.0) if t > 120.0 else 0.0
            icon_scale = 0.88 + 0.12 * icon_p
            icon_alpha = icon_p

            # Title: t = 220..540ms (opacity 0.0 -> 1.0, dy +8px -> 0px)
            title_p = _ease_out_cubic((t - 220.0) / 320.0) if t > 220.0 else 0.0
            title_dy = (1.0 - title_p) * 8.0
            title_alpha = title_p

            # Tagline: t = 320..620ms (opacity 0.0 -> 1.0, dy +4px -> 0px)
            tagline_p = _ease_out_cubic((t - 320.0) / 300.0) if t > 320.0 else 0.0
            tagline_dy = (1.0 - tagline_p) * 4.0
            tagline_alpha = tagline_p

            # Progress & telemetry: t = 380..680ms
            load_p = _ease_out_cubic((t - 380.0) / 300.0) if t > 380.0 else 0.0
            load_alpha = load_p

            # ACROPOLIANS Branding: t = 480..780ms
            brand_p = _ease_out_cubic((t - 480.0) / 300.0) if t > 480.0 else 0.0
            brand_alpha = brand_p

            # 3. Right Side: 3D Chrome Sculpture Artwork (Flowing Metallic Ribbons)
            if self._raw_chrome is not None and chrome_alpha > 0.01:
                art_x = 310
                art_y = 10
                art_w = 300
                art_h = 340

                painter.save()
                painter.setOpacity(chrome_alpha)

                cw = int(art_w * chrome_scale)
                ch = int(art_h * chrome_scale)
                cx = art_x + (art_w - cw) // 2
                cy = art_y + (art_h - ch) // 2

                scaled_chrome = self._raw_chrome.scaled(
                    cw, ch, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
                painter.drawPixmap(cx, cy, scaled_chrome)
                painter.restore()

            # 4. Left Side: HeadMouseAI Application Icon
            if self._raw_icon is not None and icon_alpha > 0.01:
                base_size = 46
                cur_size = int(base_size * icon_scale)
                icon_x = 42 + (base_size - cur_size) // 2
                icon_y = int(36 + (base_size - cur_size) // 2)

                painter.save()
                painter.setOpacity(icon_alpha)

                # Subtle metallic frame ring behind icon
                painter.setPen(QPen(QColor("#24262B"), 1))
                painter.setBrush(QColor("#0B0C0E"))
                painter.drawRoundedRect(40, 34, 50, 50, 10, 10)

                scaled_icon = self._raw_icon.scaled(
                    cur_size, cur_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
                painter.drawPixmap(icon_x, icon_y, scaled_icon)
                painter.restore()

            # 5. Left Side: Application Title "HeadMouseAI"
            if title_alpha > 0.01:
                painter.save()
                painter.setOpacity(title_alpha)
                title_font = QFont("Segoe UI", 22, QFont.Weight.Bold)
                title_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.4)
                painter.setFont(title_font)
                painter.setPen(QColor("#E8EAED"))  # Chrome highlight
                painter.drawText(
                    QRect(42, int(100 + title_dy), 300, 36),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    "HeadMouseAI",
                )
                painter.restore()

            # 6. Left Side: Tagline "Hands-Free Control. Limitless Possibilities."
            if tagline_alpha > 0.01:
                painter.save()
                painter.setOpacity(tagline_alpha)
                tag_font = QFont("Segoe UI", 9, QFont.Weight.Medium)
                painter.setFont(tag_font)
                painter.setPen(QColor("#858B95"))  # Muted silver
                painter.drawText(
                    QRect(42, int(140 + tagline_dy), 300, 22),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    "Hands-Free Control. Limitless Possibilities.",
                )
                painter.restore()

            # 7. Left Side: Minimal Elegant Loading Progress Indicator
            if load_alpha > 0.01:
                painter.save()
                painter.setOpacity(load_alpha)

                track_w = 230
                track_h = 2
                track_x = 42
                track_y = 196

                # Background Groove (#24262B secondary)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor("#24262B"))
                painter.drawRoundedRect(track_x, track_y, track_w, track_h, 1, 1)

                # Specular Metallic Silver / Chrome Traveling Pulse
                pulse_w = 60
                travel_cycle = track_w + pulse_w
                travel_x = track_x - pulse_w + int((t * 0.14) % travel_cycle)

                painter.setClipRect(track_x, track_y, track_w, track_h)
                pulse_grad = QLinearGradient(travel_x, track_y, travel_x + pulse_w, track_y)
                pulse_grad.setColorAt(0.0, QColor(133, 139, 149, 0))   # Transparent muted silver
                pulse_grad.setColorAt(0.4, QColor(192, 197, 204, 220)) # Metallic silver
                pulse_grad.setColorAt(0.6, QColor(255, 255, 255, 255)) # Chrome specular highlight
                pulse_grad.setColorAt(1.0, QColor(133, 139, 149, 0))   # Transparent

                painter.setBrush(pulse_grad)
                painter.drawRect(travel_x, track_y, pulse_w, track_h)
                painter.setClipping(False)

                # 8. Subsystem Initialization Status Telemetry
                stat_font = QFont("Segoe UI", 8, QFont.Weight.Medium)
                painter.setFont(stat_font)
                painter.setPen(QColor("#858B95"))
                painter.drawText(
                    QRect(42, 210, 280, 20),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    self._status_text,
                )
                painter.restore()

            # 9. Left Side: Subtle Structural Hairline Separator
            if brand_alpha > 0.01:
                painter.save()
                painter.setOpacity(brand_alpha * 0.7)
                painter.setPen(QPen(QColor("#24262B"), 1))
                painter.drawLine(42, 276, 110, 276)
                painter.restore()

            # 10. Left Side: Company Branding "A Product by ACROPOLIANS"
            if brand_alpha > 0.01:
                painter.save()
                painter.setOpacity(brand_alpha)

                brand_font = QFont("Segoe UI", 8, QFont.Weight.DemiBold)
                brand_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.6)
                painter.setFont(brand_font)

                prefix = "A Product by "
                brand = "ACROPOLIANS"

                fm = painter.fontMetrics()
                y_pos = 302
                start_x = 42

                # Prefix in muted silver #858B95
                painter.setPen(QColor("#858B95"))
                painter.drawText(start_x, y_pos, prefix)

                # Brand in metallic silver / chrome highlight #E8EAED
                prefix_w = fm.horizontalAdvance(prefix)
                painter.setPen(QColor("#E8EAED"))
                painter.drawText(start_x + prefix_w, y_pos, brand)

                painter.restore()

            # 11. Outer Precision Border & Subtle Specular Top Highlight
            painter.setClipping(False)
            # 1px border (#24262B)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QColor("#24262B"))
            painter.drawRoundedRect(0, 0, w - 1, h - 1, 14, 14)

            # Subtle metallic highlight along top edge
            top_highlight = QLinearGradient(0, 0, w, 0)
            top_highlight.setColorAt(0.0, QColor(192, 197, 204, 0))
            top_highlight.setColorAt(0.3, QColor(232, 234, 237, 70))
            top_highlight.setColorAt(0.7, QColor(192, 197, 204, 30))
            top_highlight.setColorAt(1.0, QColor(192, 197, 204, 0))
            painter.setPen(QPen(top_highlight, 1))
            painter.drawRoundedRect(1, 1, w - 3, h - 3, 13, 13)

        finally:
            painter.end()
