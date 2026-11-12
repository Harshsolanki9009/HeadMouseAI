"""Hardware-accelerated, jitter-free live video preview widget with blurred background fill."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPaintEvent
from PySide6.QtWidgets import QSizePolicy, QWidget


class VideoWidget(QWidget):
    """Renders real-time camera frames with stable aspect-ratio scaling,

    smooth blurred ambient background fill for unused space, and subtle status overlays.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_image: Optional[QImage] = None
        self._cached_bg_image: Optional[QImage] = None
        self._mode: str = "NORMAL"
        self._fps_text: str = ""
        self._emergency_stopped: bool = False
        self._is_dragging: bool = False
        self._position_locked: bool = False
        self._action_banner: Optional[str] = None
        self._is_live: bool = False

        self.setMinimumSize(480, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # WA_OpaquePaintEvent disables background erase, eliminating white/black flickering
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

    def update_frame(self, image: QImage) -> None:
        """Receive a new frame from VisionWorker and pre-cache blurred ambient background."""
        self._current_image = image
        self._is_live = True

        # Pre-cache soft blurred background fill (fast 2-step downscale/smooth scale, <0.2ms)
        try:
            if not image.isNull() and image.width() > 0 and image.height() > 0:
                tiny = image.scaled(
                    48, 36, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation
                )
                self._cached_bg_image = tiny.scaled(
                    96, 72, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
            else:
                self._cached_bg_image = None
        except Exception:
            self._cached_bg_image = None

        self.update()

    def update_telemetry(self, telemetry: dict) -> None:
        """Update live telemetry overlays with stable formatting."""
        self._mode = telemetry.get("mode") or "NORMAL"
        fps = telemetry.get("fps")
        fps = 0.0 if fps is None else float(fps)
        lat = telemetry.get("latency_ms")
        lat = 0.0 if lat is None else float(lat)
        self._fps_text = f"{fps:.1f} FPS | {lat:.0f}ms"
        self._emergency_stopped = telemetry.get("emergency_stopped", False)
        self._is_dragging = telemetry.get("is_dragging", False)
        self._position_locked = telemetry.get("position_locked", False)

        # Dynamic action banner
        last_zoom = telemetry.get("last_zoom_action")
        last_scroll = telemetry.get("last_scroll_action")
        head_dir = telemetry.get("head_direction") or "NEUTRAL"
        if self._mode == "ZOOM":
            act = telemetry.get("gesture_action") or last_zoom
            if act and act in ("ZOOM_IN", "ZOOM_OUT"):
                self._action_banner = f"Zoom Mode: {act}"
            elif head_dir != "NEUTRAL":
                self._action_banner = f"Zoom Mode: Tilting {head_dir}"
            else:
                self._action_banner = "Zoom Mode: Active (Tilt Head)"
        elif self._mode == "SCROLL":
            act = telemetry.get("gesture_action") or last_scroll
            if act and act in ("SCROLL_UP", "SCROLL_DOWN"):
                self._action_banner = f"Scroll Mode: {act}"
            elif head_dir != "NEUTRAL":
                self._action_banner = f"Scroll Mode: Tilting {head_dir}"
            else:
                self._action_banner = "Scroll Mode: Active (Tilt Head)"
        elif last_zoom:
            self._action_banner = f"Zoom: {last_zoom}"
        elif last_scroll:
            self._action_banner = f"Scroll: {last_scroll}"
        else:
            self._action_banner = None

        self.update()

    def clear_frame(self) -> None:
        """Clear camera display to placeholder."""
        self._current_image = None
        self._cached_bg_image = None
        self._fps_text = ""
        self._action_banner = None
        self._is_live = False
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        """Render frame with blurred ambient background fill, sharp centered video, and clean overlays."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._current_image is not None and not self._current_image.isNull():
            img_w = self._current_image.width()
            img_h = self._current_image.height()

            if img_w > 0 and img_h > 0:
                # 1. Fill unused pillarbox background with cached softly blurred frame
                if self._cached_bg_image is not None and not self._cached_bg_image.isNull():
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                    painter.drawImage(self.rect(), self._cached_bg_image)
                    # Subtle dark obsidian overlay for visual depth and contrast balance
                    painter.fillRect(self.rect(), QColor(16, 17, 20, 200))
                else:
                    # Clean dark obsidian fallback
                    painter.fillRect(self.rect(), QColor("#101114"))

                # 2. Calculate aspect-ratio preserving centered rect (original feed never stretched)
                scale = min(self.width() / img_w, self.height() / img_h)
                target_w = int(img_w * scale)
                target_h = int(img_h * scale)
                target_x = (self.width() - target_w) // 2
                target_y = (self.height() - target_h) // 2
                target_rect = QRect(target_x, target_y, target_w, target_h)

                # 3. Subtle dark perimeter outline around the sharp center feed
                painter.setPen(QColor(0, 0, 0, 160))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(target_rect.adjusted(-1, -1, 1, 1))

                # 4. Draw original sharp camera feed centered
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                painter.drawImage(target_rect, self._current_image)

                # 5. Subtle 1px inner border around the active frame
                painter.setPen(QColor(255, 255, 255, 30))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(target_rect)

                # 6. Action Banner Overlay (Top Center)
                if self._emergency_stopped:
                    self._draw_banner(painter, "Emergency Stop Engaged", QColor(220, 38, 38, 240), QColor("#FFFFFF"))
                elif self._action_banner:
                    if "Zoom" in self._action_banner:
                        bg = QColor(37, 99, 235, 230)
                    elif "Scroll" in self._action_banner:
                        bg = QColor(5, 150, 105, 230)
                    else:
                        bg = QColor(79, 70, 229, 230)
                    self._draw_banner(painter, self._action_banner, bg, QColor("#FFFFFF"))
                elif self._position_locked:
                    self._draw_banner(painter, "Click Position Locked", QColor(217, 119, 6, 225), QColor("#FFFFFF"))

                # 7. Live Indicator Badge (Top Left of video stream)
                badge_live = QRect(target_x + 12, target_y + 12, 68, 24)
                painter.setBrush(QColor(16, 17, 20, 220))
                painter.setPen(QColor(167, 176, 188, 60))
                painter.drawRoundedRect(badge_live, 5, 5)

                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor("#10B981"))
                painter.drawEllipse(QPoint(target_x + 22, target_y + 24), 3, 3)

                painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
                painter.setPen(QColor("#F5F5F5"))
                painter.drawText(QRect(target_x + 28, target_y + 12, 48, 24), Qt.AlignmentFlag.AlignCenter, "LIVE")

                # 8. FPS & Latency Overlay Badge (Bottom Left, Tabular Monospace)
                if self._fps_text:
                    painter.setFont(QFont("Consolas", 9, QFont.Weight.Medium))
                    metrics = painter.fontMetrics()
                    fps_w = max(110, metrics.horizontalAdvance(self._fps_text) + 16)
                    badge_rect = QRect(target_x + 12, target_y + target_h - 34, fps_w, 22)
                    painter.setBrush(QColor(16, 17, 20, 220))
                    painter.setPen(QColor(167, 176, 188, 60))
                    painter.drawRoundedRect(badge_rect, 5, 5)
                    painter.setPen(QColor("#A7B0BC"))
                    painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, self._fps_text)

        else:
            # Clean, refined Obsidian Chrome offline placeholder card with dark metallic gradient
            grad = QLinearGradient(0, 0, 0, self.height())
            grad.setColorAt(0.0, QColor("#101114"))
            grad.setColorAt(1.0, QColor("#181A1F"))
            painter.fillRect(self.rect(), grad)

            card_w = min(420, max(260, self.width() - 40))
            card_h = min(150, max(110, self.height() - 40))
            card_x = (self.width() - card_w) // 2
            card_y = (self.height() - card_h) // 2
            card_rect = QRect(card_x, card_y, card_w, card_h)

            painter.setBrush(QColor("#1A1C22"))
            painter.setPen(QColor("#353942"))
            painter.drawRoundedRect(card_rect, 10, 10)

            # Subtle specular top rim on card
            painter.setPen(QColor(167, 176, 188, 50))
            painter.drawLine(card_x + 10, card_y + 1, card_x + card_w - 10, card_y + 1)

            painter.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
            painter.setPen(QColor("#F5F5F5"))
            painter.drawText(
                QRect(card_x, card_y + 25, card_w, 30),
                Qt.AlignmentFlag.AlignCenter,
                "Camera Preview Offline",
            )

            painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Normal))
            painter.setPen(QColor("#A1A1AA"))
            painter.drawText(
                QRect(card_x, card_y + 65, card_w, 45),
                Qt.AlignmentFlag.AlignCenter,
                "Click 'Start Tracking' to begin camera stream\nPress [F8] or [M] to enable cursor control",
            )

    def _draw_banner(self, painter: QPainter, text: str, bg_color: QColor, text_color: QColor) -> None:
        """Render a restrained, modern pill notification at top center."""
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        metrics = painter.fontMetrics()
        text_width = metrics.horizontalAdvance(text)
        banner_w = text_width + 28
        banner_h = 28
        banner_x = (self.width() - banner_w) // 2
        banner_y = 14

        rect = QRect(banner_x, banner_y, banner_w, banner_h)
        painter.setBrush(bg_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 5, 5)

        painter.setPen(text_color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
