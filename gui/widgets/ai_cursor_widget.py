"""AI Cursor (HeadMouseAI) Control Card for Jadoo Dashboard.

Provides high-contrast controls for turning AI Cursor ON/OFF, pausing/resuming,
re-centering, neutral calibration, live status badges (Camera, Face, Nose, Cursor),
real-time sensitivity and smoothing sliders, and quick access to HeadMouseAI settings.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from config.settings import AppSettings, get_settings
from gui.styles import (
    INK_CANVAS,
    INK_COOL_GRAY,
    INK_ELEVATED,
    INK_GRAPHITE,
    INK_MUTED_AMBER,
    INK_MUTED_CRIMSON,
    INK_MUTED_SLATE,
    INK_PURE_WHITE,
    INK_SAGE_GRAY,
    INK_SILVER_GRAY,
    INK_SOFT_IVORY,
)
from utils.logger import logger


class AICursorWidget(QFrame):
    """Dedicated Jadoo AI Cursor Control Card."""

    sig_cursor_on = Signal()
    sig_cursor_off = Signal()
    sig_cursor_pause = Signal()
    sig_cursor_resume = Signal()
    sig_calibrate = Signal()
    sig_recenter = Signal()
    sig_open_settings = Signal()
    sig_sensitivity_changed = Signal(float)
    sig_smoothing_changed = Signal(float)

    def __init__(self, settings: Optional[AppSettings] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.settings: AppSettings = settings if settings is not None else get_settings()
        self._is_cursor_active: bool = False
        self._is_cursor_paused: bool = False

        self.setObjectName("AICursorCard")
        self.setStyleSheet(f"""
            QFrame#AICursorCard {{
                background-color: {INK_GRAPHITE};
                border: 1px solid {INK_COOL_GRAY};
                border-radius: 10px;
                padding: 10px;
            }}
        """)

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(10)

        # ---------------- 1. Header & Live Status Badges ---------------- #
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        lbl_title = QLabel("✦ Jadoo AI Cursor (HeadMouseAI)")
        lbl_title.setStyleSheet(f"font-size: 13px; font-weight: 800; color: {INK_SOFT_IVORY}; letter-spacing: 0.5px;")
        header_row.addWidget(lbl_title)
        header_row.addStretch(1)

        # Camera Status
        self.badge_camera = QLabel("CAM: OFF")
        self.badge_camera.setStyleSheet(self._badge_style("#64748B", "#1E293B", "#334155"))
        header_row.addWidget(self.badge_camera)

        # Face Detection Status
        self.badge_face = QLabel("FACE: NONE")
        self.badge_face.setStyleSheet(self._badge_style("#64748B", "#1E293B", "#334155"))
        header_row.addWidget(self.badge_face)

        # Nose Tracking Status
        self.badge_nose = QLabel("NOSE: IDLE")
        self.badge_nose.setStyleSheet(self._badge_style("#64748B", "#1E293B", "#334155"))
        header_row.addWidget(self.badge_nose)

        # Cursor Master Status
        self.badge_cursor = QLabel("CURSOR: OFF")
        self.badge_cursor.setStyleSheet(self._badge_style("#94A3B8", "#1E2330", "#334155"))
        header_row.addWidget(self.badge_cursor)

        main_layout.addLayout(header_row)

        # ---------------- 2. Action Buttons Grid ---------------- #
        btn_grid = QGridLayout()
        btn_grid.setContentsMargins(0, 0, 0, 0)
        btn_grid.setSpacing(8)

        self.btn_cursor_on = QPushButton("AI Cursor ON")
        self.btn_cursor_on.setFixedHeight(36)
        self.btn_cursor_on.setStyleSheet(self._btn_style(accent="#10B981", active=False))
        self.btn_cursor_on.clicked.connect(self._on_btn_cursor_on_clicked)
        btn_grid.addWidget(self.btn_cursor_on, 0, 0)

        self.btn_cursor_off = QPushButton("AI Cursor OFF")
        self.btn_cursor_off.setFixedHeight(36)
        self.btn_cursor_off.setStyleSheet(self._btn_style(accent="#EF4444", active=False))
        self.btn_cursor_off.clicked.connect(self._on_btn_cursor_off_clicked)
        btn_grid.addWidget(self.btn_cursor_off, 0, 1)

        self.btn_cursor_pause = QPushButton("Pause Cursor")
        self.btn_cursor_pause.setFixedHeight(36)
        self.btn_cursor_pause.setStyleSheet(self._btn_style(accent="#F59E0B", active=False))
        self.btn_cursor_pause.clicked.connect(self._on_btn_cursor_pause_clicked)
        btn_grid.addWidget(self.btn_cursor_pause, 0, 2)

        self.btn_recenter = QPushButton("Recenter [R]")
        self.btn_recenter.setFixedHeight(36)
        self.btn_recenter.setStyleSheet(self._btn_style(accent="#8B5CF6", active=False))
        self.btn_recenter.clicked.connect(self.sig_recenter.emit)
        btn_grid.addWidget(self.btn_recenter, 0, 3)

        self.btn_calibrate = QPushButton("Calibrate [C]")
        self.btn_calibrate.setFixedHeight(36)
        self.btn_calibrate.setStyleSheet(self._btn_style(accent="#8B5CF6", active=False))
        self.btn_calibrate.clicked.connect(self.sig_calibrate.emit)
        btn_grid.addWidget(self.btn_calibrate, 0, 4)

        self.btn_settings = QPushButton("⚙ HeadMouseAI Settings")
        self.btn_settings.setFixedHeight(36)
        self.btn_settings.setStyleSheet(self._btn_style(accent="#6366F1", active=False))
        self.btn_settings.clicked.connect(self.sig_open_settings.emit)
        btn_grid.addWidget(self.btn_settings, 0, 5)

        main_layout.addLayout(btn_grid)

        # ---------------- 3. Sensitivity & Smoothing Sliders ---------------- #
        slider_frame = QFrame()
        slider_frame.setStyleSheet("""
            QFrame {
                background-color: #0E1017;
                border: 1px solid #232733;
                border-radius: 6px;
                padding: 6px 10px;
            }
        """)
        sl_layout = QHBoxLayout(slider_frame)
        sl_layout.setContentsMargins(6, 4, 6, 4)
        sl_layout.setSpacing(16)

        # Sensitivity Slider
        lbl_sens_title = QLabel("Sensitivity:")
        lbl_sens_title.setStyleSheet("color: #E2E8F0; font-size: 11px; font-weight: 600;")
        sl_layout.addWidget(lbl_sens_title)

        curr_sens = float(getattr(self.settings.nose_tracking, "sensitivity", 1.0))
        self.slider_sens = QSlider(Qt.Orientation.Horizontal)
        self.slider_sens.setRange(2, 30)  # 0.2x to 3.0x (step 0.1)
        self.slider_sens.setValue(int(curr_sens * 10))
        self.slider_sens.setStyleSheet(self._slider_style())
        self.slider_sens.valueChanged.connect(self._on_sens_slider_changed)
        sl_layout.addWidget(self.slider_sens, 1)

        self.lbl_sens_val = QLabel(f"{curr_sens:.1f}x")
        self.lbl_sens_val.setFixedWidth(36)
        self.lbl_sens_val.setStyleSheet("color: #A78BFA; font-family: Consolas, monospace; font-size: 11px; font-weight: 700;")
        sl_layout.addWidget(self.lbl_sens_val)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #2D3342;")
        sl_layout.addWidget(sep)

        # Smoothing Slider
        lbl_smooth_title = QLabel("Smoothing:")
        lbl_smooth_title.setStyleSheet("color: #E2E8F0; font-size: 11px; font-weight: 600;")
        sl_layout.addWidget(lbl_smooth_title)

        curr_smooth = float(getattr(self.settings.nose_tracking, "smoothing_strength", 0.35))
        self.slider_smooth = QSlider(Qt.Orientation.Horizontal)
        self.slider_smooth.setRange(5, 90)  # 0.05 to 0.90 (step 0.05)
        self.slider_smooth.setValue(int(curr_smooth * 100))
        self.slider_smooth.setStyleSheet(self._slider_style())
        self.slider_smooth.valueChanged.connect(self._on_smooth_slider_changed)
        sl_layout.addWidget(self.slider_smooth, 1)

        self.lbl_smooth_val = QLabel(f"{curr_smooth:.2f}")
        self.lbl_smooth_val.setFixedWidth(36)
        self.lbl_smooth_val.setStyleSheet("color: #A78BFA; font-family: Consolas, monospace; font-size: 11px; font-weight: 700;")
        sl_layout.addWidget(self.lbl_smooth_val)

        main_layout.addWidget(slider_frame)

    # ---------------- Style Helpers ---------------- #
    def _badge_style(self, text_color: str, bg_color: str, border_color: str) -> str:
        return f"""
            background-color: {bg_color};
            color: {text_color};
            border: 1px solid {border_color};
            border-radius: 4px;
            padding: 2px 7px;
            font-size: 10px;
            font-weight: 800;
        """

    def _btn_style(self, accent: str = INK_SOFT_IVORY, active: bool = False) -> str:
        bg = INK_CANVAS if not active else INK_COOL_GRAY
        border = INK_COOL_GRAY if not active else accent
        color = INK_SILVER_GRAY if not active else INK_SOFT_IVORY
        return f"""
            QPushButton {{
                background-color: {bg};
                color: {color};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background-color: {INK_ELEVATED};
                border-color: {accent};
                color: {INK_PURE_WHITE};
            }}
            QPushButton:pressed {{
                background-color: {INK_CANVAS};
            }}
            QPushButton:focus {{
                border: 2px solid {INK_SOFT_IVORY};
                outline: none;
            }}
        """

    def _slider_style(self) -> str:
        return f"""
            QSlider::groove:horizontal {{
                height: 4px;
                background: {INK_CANVAS};
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {INK_SILVER_GRAY};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {INK_SOFT_IVORY};
                border: 1px solid {INK_MUTED_SLATE};
                width: 14px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 7px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {INK_PURE_WHITE};
                border-color: {INK_SOFT_IVORY};
            }}
        """

    # ---------------- Button Slot Handlers ---------------- #
    @Slot()
    def _on_btn_cursor_on_clicked(self) -> None:
        self.sig_cursor_on.emit()

    @Slot()
    def _on_btn_cursor_off_clicked(self) -> None:
        self.sig_cursor_off.emit()

    @Slot()
    def _on_btn_cursor_pause_clicked(self) -> None:
        self._is_cursor_paused = not self._is_cursor_paused
        if self._is_cursor_paused:
            self.btn_cursor_pause.setText("Resume Cursor")
            self.btn_cursor_pause.setStyleSheet(self._btn_style(accent="#F59E0B", active=True))
            self.sig_cursor_pause.emit()
        else:
            self.btn_cursor_pause.setText("Pause Cursor")
            self.btn_cursor_pause.setStyleSheet(self._btn_style(accent="#F59E0B", active=False))
            self.sig_cursor_resume.emit()

    @Slot(int)
    def _on_sens_slider_changed(self, val: int) -> None:
        sens = val / 10.0
        self.lbl_sens_val.setText(f"{sens:.1f}x")
        self.settings.nose_tracking.sensitivity = sens
        self.sig_sensitivity_changed.emit(sens)

    @Slot(int)
    def _on_smooth_slider_changed(self, val: int) -> None:
        smooth = val / 100.0
        self.lbl_smooth_val.setText(f"{smooth:.2f}")
        self.settings.nose_tracking.smoothing_strength = smooth
        self.sig_smoothing_changed.emit(smooth)

    # ---------------- Status Updating Slots ---------------- #
    @Slot(dict)
    def update_telemetry(self, t: dict) -> None:
        """Update live telemetry status badges."""
        has_face = bool(t.get("has_face", False))
        is_tracking = bool(t.get("is_tracking", False))
        cam_online = bool(t.get("cam_online", True))

        # Camera
        if cam_online:
            self.badge_camera.setText("CAM: ONLINE")
            self.badge_camera.setStyleSheet(self._badge_style("#34D399", "#064E3B", "#059669"))
        else:
            self.badge_camera.setText("CAM: ERROR")
            self.badge_camera.setStyleSheet(self._badge_style("#FCA5A5", "#7F1D1D", "#DC2626"))

        # Face
        if has_face:
            self.badge_face.setText("FACE: LOCKED")
            self.badge_face.setStyleSheet(self._badge_style("#38BDF8", "#0C4A6E", "#0284C7"))
        else:
            self.badge_face.setText("FACE: SEARCHING")
            self.badge_face.setStyleSheet(self._badge_style("#FCD34D", "#78350F", "#D97706"))

        # Nose Tracking
        if is_tracking and has_face:
            self.badge_nose.setText("NOSE: ACTIVE")
            self.badge_nose.setStyleSheet(self._badge_style("#C4B5FD", "#3B1B6D", "#7C3AED"))
        else:
            self.badge_nose.setText("NOSE: IDLE")
            self.badge_nose.setStyleSheet(self._badge_style("#94A3B8", "#1E2330", "#334155"))

    @Slot(bool, str)
    def update_mouse_state(self, enabled: bool, state_label: str) -> None:
        """Update cursor status based on MouseController and VisionWorker state."""
        self._is_cursor_active = enabled
        if state_label == "EMERGENCY_STOP":
            self.badge_cursor.setText("CURSOR: STOPPED")
            self.badge_cursor.setStyleSheet(self._badge_style("#FCA5A5", "#7F1D1D", "#DC2626"))
            self.btn_cursor_on.setStyleSheet(self._btn_style(accent="#10B981", active=False))
            self.btn_cursor_off.setStyleSheet(self._btn_style(accent="#EF4444", active=True))
        elif self._is_cursor_paused:
            self.badge_cursor.setText("CURSOR: PAUSED")
            self.badge_cursor.setStyleSheet(self._badge_style("#FCD34D", "#78350F", "#D97706"))
        elif enabled:
            self.badge_cursor.setText("CURSOR: ACTIVE")
            self.badge_cursor.setStyleSheet(self._badge_style("#34D399", "#064E3B", "#059669"))
            self.btn_cursor_on.setStyleSheet(self._btn_style(accent="#10B981", active=True))
            self.btn_cursor_off.setStyleSheet(self._btn_style(accent="#EF4444", active=False))
        else:
            self.badge_cursor.setText("CURSOR: OFF")
            self.badge_cursor.setStyleSheet(self._badge_style("#94A3B8", "#1E2330", "#334155"))
            self.btn_cursor_on.setStyleSheet(self._btn_style(accent="#10B981", active=False))
            self.btn_cursor_off.setStyleSheet(self._btn_style(accent="#EF4444", active=False))

    @Slot(str)
    def update_cursor_status(self, status_str: str) -> None:
        """Explicitly set cursor badge status string."""
        st = status_str.upper()
        self.badge_cursor.setText(f"CURSOR: {st}")
        if "ACTIVE" in st or "ON" in st:
            self.badge_cursor.setStyleSheet(self._badge_style("#34D399", "#064E3B", "#059669"))
        elif "PAUSED" in st:
            self.badge_cursor.setStyleSheet(self._badge_style("#FCD34D", "#78350F", "#D97706"))
        elif "STOP" in st or "ERR" in st:
            self.badge_cursor.setStyleSheet(self._badge_style("#FCA5A5", "#7F1D1D", "#DC2626"))
        else:
            self.badge_cursor.setStyleSheet(self._badge_style("#94A3B8", "#1E2330", "#334155"))

    def set_cursor_paused(self, paused: bool) -> None:
        self._is_cursor_paused = paused
        if paused:
            self.btn_cursor_pause.setText("Resume Cursor")
            self.btn_cursor_pause.setStyleSheet(self._btn_style(accent="#F59E0B", active=True))
            self.update_cursor_status("PAUSED")
        else:
            self.btn_cursor_pause.setText("Pause Cursor")
            self.btn_cursor_pause.setStyleSheet(self._btn_style(accent="#F59E0B", active=False))
            if self._is_cursor_active:
                self.update_cursor_status("ACTIVE")
            else:
                self.update_cursor_status("OFF")
