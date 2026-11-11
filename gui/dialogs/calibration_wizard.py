"""Professional Beginner-Friendly Smart Calibration and Personalization Wizard for HeadMouseAI.

Provides a 4-step guided personalization experience:
1. Position Yourself (Camera preview & distance guide)
2. Calibrate Head Position (Neutral resting posture capture with median filtering)
3. Eye Controls (Left/right wink click verification & resting baseline)
4. Optional Gestures (Clear explanations of drag, scroll, and zoom)
Followed by a clean Confirmation summary.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
from PySide6.QtCore import QPoint, QRect, Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPaintEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config.settings import AppSettings, get_settings, validate_calibration_data
from utils.logger import logger

TOTAL_STEPS = 5
SAMPLE_FRAMES_PER_STEP = 30


class CalibrationCameraPreview(QWidget):
    """Compact, live camera preview widget for the Calibration Wizard."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_image: Optional[QImage] = None
        self.setFixedSize(260, 195)

    @Slot(QImage)
    def update_frame(self, img: QImage) -> None:
        if img is not None and not img.isNull():
            self._current_image = img
            self.update()

    def clear(self) -> None:
        self._current_image = None
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            w = self.width()
            h = self.height()

            # 1. Dark Container Surface with border
            painter.setBrush(QColor("#101114"))
            painter.setPen(QColor("#2E323A"))
            painter.drawRoundedRect(0, 0, w - 1, h - 1, 8, 8)

            if self._current_image is not None and not self._current_image.isNull():
                # 2. Clip to rounded interior
                clip_path = QPainterPath()
                clip_path.addRoundedRect(1, 1, w - 2, h - 2, 7, 7)
                painter.setClipPath(clip_path)

                img_w = self._current_image.width()
                img_h = self._current_image.height()
                scale = min((w - 4) / img_w, (h - 4) / img_h)
                target_w = int(img_w * scale)
                target_h = int(img_h * scale)
                target_x = (w - target_w) // 2
                target_y = (h - target_h) // 2

                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                painter.drawImage(QRect(target_x, target_y, target_w, target_h), self._current_image)

                # 3. LIVE pill badge overlay
                painter.setClipping(False)
                badge_rect = QRect(8, 8, 56, 20)
                painter.setBrush(QColor(16, 17, 20, 220))
                painter.setPen(QColor(167, 176, 188, 60))
                painter.drawRoundedRect(badge_rect, 4, 4)

                painter.setBrush(QColor("#10B981"))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPoint(16, 18), 3, 3)

                painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                painter.setPen(QColor("#FFFFFF"))
                painter.drawText(QRect(22, 8, 38, 20), Qt.AlignmentFlag.AlignCenter, "LIVE")
            else:
                painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
                painter.setPen(QColor("#71717A"))
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Waiting for Camera…")
        finally:
            painter.end()


class StepIndicator(QFrame):
    """Visual header displaying the guided wizard steps."""

    STEP_TITLES = [
        "1. Position",
        "2. Head Center",
        "3. Eye Controls",
        "4. Gestures",
        "5. Confirmation",
    ]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("step_indicator")
        self.labels: list[QLabel] = []
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        for title in self.STEP_TITLES:
            lbl = QLabel(title)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedHeight(28)
            lbl.setStyleSheet(self._style_pending())
            layout.addWidget(lbl)
            self.labels.append(lbl)

    def set_current_step(self, step_idx: int) -> None:
        """Update indicators for all steps."""
        for i, lbl in enumerate(self.labels):
            if i < step_idx:
                lbl.setStyleSheet(self._style_completed())
            elif i == step_idx:
                lbl.setStyleSheet(self._style_active())
            else:
                lbl.setStyleSheet(self._style_pending())

    def _style_pending(self) -> str:
        return (
            "background-color: #14161A; color: #71717A; border: 1px solid #2E323A; "
            "border-radius: 6px; font-size: 11px; font-weight: 600; padding: 4px 8px;"
        )

    def _style_active(self) -> str:
        return (
            "background-color: #202226; color: #FFFFFF; border: 1px solid #3F434C; "
            "border-top: 2px solid #A7B0BC; border-radius: 6px; font-size: 11px; font-weight: 700; padding: 4px 8px;"
        )

    def _style_completed(self) -> str:
        return (
            "background-color: #12251D; color: #6EE7B7; border: 1px solid #065F46; "
            "border-radius: 6px; font-size: 11px; font-weight: 600; padding: 4px 8px;"
        )


class CalibrationWizard(QDialog):
    """Beginner-friendly modal wizard guiding users through head and eye personalization."""

    sig_profile_applied = Signal(dict)

    def __init__(self, worker: Any = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.worker = worker
        self.settings: AppSettings = get_settings()

        self.setWindowTitle("HeadMouseAI — Calibration Wizard")
        self.setFixedSize(760, 590)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        # Candidate baselines collected during this session
        self.candidate_nose_x: Optional[float] = None
        self.candidate_nose_y: Optional[float] = None
        self.candidate_left_ear: Optional[float] = None
        self.candidate_right_ear: Optional[float] = None
        self.candidate_mouth_width: Optional[float] = None
        self.candidate_left_eb: Optional[float] = None
        self.candidate_right_eb: Optional[float] = None

        # Verification states
        self.left_click_verified: bool = False
        self.right_click_verified: bool = False

        # Sampling state
        self._sampling_step: Optional[int] = None
        self._step_buffers: dict[int, list] = {
            1: [],  # Nose: list of (x, y)
            2: [],  # Eyes: list of (l_ear, r_ear)
            3: [],  # Mouth: list of mw
            4: [],  # Eyebrows: list of (l_eb, r_eb)
        }

        # Live telemetry cache
        self._last_telemetry: dict[str, Any] = {}

        self._init_ui()

        # Connect to worker telemetry & ensure mouse safety
        if self.worker is not None:
            self.worker.mouse_controller.release_all_buttons()
            self._was_mouse_enabled = self.worker.mouse_controller.enabled
            if self._was_mouse_enabled:
                self.worker.mouse_controller.disable()
            self.worker.sig_telemetry.connect(self.on_telemetry)
            self.worker.sig_frame_ready.connect(self._on_frame_ready)
        else:
            self._was_mouse_enabled = False

        self._update_navigation()

    @Slot(QImage)
    def _on_frame_ready(self, img: QImage) -> None:
        """Route incoming camera frames to the active step's compact preview."""
        curr = self.stack.currentIndex()
        if curr == 0 and hasattr(self, "cam_preview_step1"):
            self.cam_preview_step1.update_frame(img)
        elif curr == 1 and hasattr(self, "cam_preview_step2"):
            self.cam_preview_step2.update_frame(img)
        elif curr == 2 and hasattr(self, "cam_preview_step3"):
            self.cam_preview_step3.update_frame(img)

    def _init_ui(self) -> None:
        self.setStyleSheet(
            "QDialog { background-color: #101114; color: #F5F5F5; font-family: 'Segoe UI', system-ui; }"
            "QLabel { color: #F5F5F5; }"
            "QGroupBox { font-weight: 600; color: #A7B0BC; border: 1px solid #2E323A; "
            "border-radius: 8px; margin-top: 10px; padding-top: 14px; background-color: #181A1F; }"
            "QProgressBar { background-color: #14161A; border: 1px solid #2E323A; border-radius: 6px; text-align: center; color: #F5F5F5; font-weight: 600; min-height: 16px; }"
            "QProgressBar::chunk { background-color: #3B82F6; border-radius: 5px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header Title
        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        title = QLabel("Personalize Head & Eye Controls")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #F5F5F5;")
        subtitle = QLabel("Set up your comfortable resting head position and verify eye click controls.")
        subtitle.setStyleSheet("font-size: 13px; color: #A1A1AA;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        layout.addLayout(title_box)

        # Step Indicator
        self.step_indicator = StepIndicator()
        layout.addWidget(self.step_indicator)

        # Stacked Pages
        self.stack = QStackedWidget()
        self.stack.addWidget(self._create_step1_positioning())
        self.stack.addWidget(self._create_step2_head())
        self.stack.addWidget(self._create_step3_eyes())
        self.stack.addWidget(self._create_step4_gestures())
        self.stack.addWidget(self._create_step5_confirmation())
        layout.addWidget(self.stack, 1)

        # Footer Navigation
        footer = QHBoxLayout()
        footer.setSpacing(10)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.setFixedWidth(90)
        self.btn_cancel.setStyleSheet(
            "QPushButton { background-color: #202226; color: #A1A1AA; border: 1px solid #2E323A; border-radius: 6px; font-weight: 600; }"
            "QPushButton:hover { background-color: #292C32; color: #FFFFFF; border-color: #3F434C; }"
            "QPushButton:focus { border: 2px solid #A7B0BC; }"
        )
        self.btn_cancel.clicked.connect(self._on_cancel)
        footer.addWidget(self.btn_cancel)

        footer.addStretch(1)

        self.btn_back = QPushButton("< Back")
        self.btn_back.setFixedHeight(36)
        self.btn_back.setFixedWidth(100)
        self.btn_back.setStyleSheet(
            "QPushButton { background-color: #202226; color: #A1A1AA; border: 1px solid #2E323A; border-radius: 6px; font-weight: 600; }"
            "QPushButton:hover { background-color: #292C32; color: #FFFFFF; border-color: #3F434C; }"
            "QPushButton:disabled { background-color: #14161A; color: #52525B; border-color: #24262B; }"
            "QPushButton:focus { border: 2px solid #A7B0BC; }"
        )
        self.btn_back.clicked.connect(self._on_back)
        footer.addWidget(self.btn_back)

        self.btn_next = QPushButton("Next >")
        self.btn_next.setFixedHeight(36)
        self.btn_next.setFixedWidth(120)
        self.btn_next.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1E3A8A, stop:1 #172554); "
            "color: #FFFFFF; border: 1px solid #3B82F6; border-radius: 6px; font-weight: 700; }"
            "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563EB, stop:1 #1E3A8A); border-color: #60A5FA; }"
            "QPushButton:disabled { background-color: #14161A; color: #52525B; border-color: #24262B; }"
            "QPushButton:focus { border: 2px solid #93C5FD; }"
        )
        self.btn_next.clicked.connect(self._on_next)
        footer.addWidget(self.btn_next)

        layout.addLayout(footer)

    # ------------------------------------------------------------------ #
    # Step Page Constructors
    # ------------------------------------------------------------------ #
    def _create_step1_positioning(self) -> QWidget:
        """Step 1: Simple face-positioning check with compact live camera preview."""
        w = QWidget()
        h_main = QHBoxLayout(w)
        h_main.setContentsMargins(4, 4, 4, 4)
        h_main.setSpacing(16)

        # Left Column: Instructions & Status
        v_left = QVBoxLayout()
        v_left.setSpacing(12)

        info = QLabel(
            "Welcome! Let's make sure your camera has a clear view of your face:\n\n"
            "• Sit comfortably facing your monitor (about arm's length, 50–70 cm).\n"
            "• Make sure your room has balanced, even lighting.\n"
            "• Look straight ahead at your screen.\n\n"
            "When your face is detected and well-centered in the preview, click 'Next'."
        )
        info.setStyleSheet("color: #A1A1AA; font-size: 13px; line-height: 1.6;")
        info.setWordWrap(True)
        v_left.addWidget(info)

        grp = QGroupBox("Camera & Positioning Status")
        gv = QVBoxLayout(grp)
        gv.setSpacing(10)
        gv.setContentsMargins(14, 18, 14, 14)

        self.lbl_face_status = QLabel("Checking face detection…")
        self.lbl_face_status.setStyleSheet("font-size: 14px; font-weight: 700; color: #FBBF24;")
        gv.addWidget(self.lbl_face_status)

        self.lbl_distance_guide = QLabel("Position yourself about arm's length from the camera.")
        self.lbl_distance_guide.setStyleSheet("font-size: 12px; color: #71717A;")
        gv.addWidget(self.lbl_distance_guide)

        self.lbl_cam_metrics = QLabel("Camera Active")
        self.lbl_cam_metrics.setStyleSheet("font-size: 12px; color: #60A5FA; font-weight: 600;")
        gv.addWidget(self.lbl_cam_metrics)

        v_left.addWidget(grp)
        v_left.addStretch(1)
        h_main.addLayout(v_left, 1)

        # Right Column: Compact Live Camera Preview
        v_right = QVBoxLayout()
        v_right.setSpacing(8)
        lbl_prev_title = QLabel("Webcam View")
        lbl_prev_title.setStyleSheet("font-size: 12px; font-weight: 600; color: #A1A1AA;")
        v_right.addWidget(lbl_prev_title)
        self.cam_preview_step1 = CalibrationCameraPreview()
        v_right.addWidget(self.cam_preview_step1)
        v_right.addStretch(1)
        h_main.addLayout(v_right)

        return w

    def _create_step2_head(self) -> QWidget:
        """Step 2: Guided neutral head posture capture with compact live camera preview."""
        w = QWidget()
        h_main = QHBoxLayout(w)
        h_main.setContentsMargins(4, 4, 4, 4)
        h_main.setSpacing(16)

        # Left Column: Instructions & Controls
        v_left = QVBoxLayout()
        v_left.setSpacing(12)

        info = QLabel(
            "Calibrate your resting head position:\n\n"
            "• Look naturally at the center of your screen.\n"
            "• Keep your neck and shoulders relaxed.\n"
            "• Click 'Start Calibration' and hold still for just one second.\n"
            "• This sets the neutral center for your cursor."
        )
        info.setStyleSheet("color: #A1A1AA; font-size: 13px; line-height: 1.6;")
        info.setWordWrap(True)
        v_left.addWidget(info)

        grp = QGroupBox("Head Position Calibration")
        gv = QVBoxLayout(grp)
        gv.setSpacing(12)
        gv.setContentsMargins(14, 18, 14, 14)

        h_ctrl = QHBoxLayout()
        self.btn_sample_nose = QPushButton("Start Calibration")
        self.btn_sample_nose.setFixedHeight(34)
        self.btn_sample_nose.setFixedWidth(140)
        self.btn_sample_nose.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1E3A8A, stop:1 #172554); "
            "color: #FFFFFF; font-weight: 700; border: 1px solid #3B82F6; border-radius: 6px; }"
            "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563EB, stop:1 #1E3A8A); border-color: #60A5FA; }"
            "QPushButton:focus { border: 2px solid #93C5FD; }"
        )
        self.btn_sample_nose.clicked.connect(lambda: self._start_sampling(1))
        h_ctrl.addWidget(self.btn_sample_nose)

        self.btn_retry_nose = QPushButton("Retry")
        self.btn_retry_nose.setFixedHeight(34)
        self.btn_retry_nose.setFixedWidth(80)
        self.btn_retry_nose.setStyleSheet(
            "QPushButton { background-color: #202226; color: #A1A1AA; border: 1px solid #2E323A; border-radius: 6px; font-weight: 600; }"
            "QPushButton:hover { background-color: #292C32; color: #FFFFFF; border-color: #3F434C; }"
            "QPushButton:focus { border: 2px solid #A7B0BC; }"
        )
        self.btn_retry_nose.clicked.connect(lambda: self._start_sampling(1))
        self.btn_retry_nose.setVisible(False)
        h_ctrl.addWidget(self.btn_retry_nose)

        h_ctrl.addStretch(1)
        gv.addLayout(h_ctrl)

        self.prog_nose = QProgressBar()
        self.prog_nose.setFixedHeight(18)
        self.prog_nose.setValue(0)
        self.prog_nose.setFormat("Ready to calibrate")
        gv.addWidget(self.prog_nose)

        self.lbl_result_nose = QLabel("Click 'Start Calibration' when you are sitting comfortably.")
        self.lbl_result_nose.setStyleSheet("color: #A1A1AA; font-size: 12px; font-weight: 500;")
        gv.addWidget(self.lbl_result_nose)

        v_left.addWidget(grp)
        v_left.addStretch(1)
        h_main.addLayout(v_left, 1)

        # Right Column: Compact Live Camera Preview
        v_right = QVBoxLayout()
        v_right.setSpacing(8)
        lbl_prev_title = QLabel("Webcam View (Hold Still)")
        lbl_prev_title.setStyleSheet("font-size: 12px; font-weight: 600; color: #A1A1AA;")
        v_right.addWidget(lbl_prev_title)
        self.cam_preview_step2 = CalibrationCameraPreview()
        v_right.addWidget(self.cam_preview_step2)
        v_right.addStretch(1)
        h_main.addLayout(v_right)

        return w

    def _create_step3_eyes(self) -> QWidget:
        """Step 3: Beginner-friendly Eye Controls & Wink verification with live preview."""
        w = QWidget()
        h_main = QHBoxLayout(w)
        h_main.setContentsMargins(4, 4, 4, 4)
        h_main.setSpacing(16)

        # Left Column: Instructions & Cards
        v_left = QVBoxLayout()
        v_left.setSpacing(12)

        info = QLabel(
            "Test your eye wink click controls:\n\n"
            "• Left wink = Left click\n"
            "• Right wink = Right click\n"
            "• Natural two-eyed blinking will NEVER trigger unintended clicks.\n"
            "• Try a gentle wink with either eye below to test."
        )
        info.setStyleSheet("color: #A1A1AA; font-size: 13px; line-height: 1.6;")
        info.setWordWrap(True)
        v_left.addWidget(info)

        grp = QGroupBox("Eye Gesture Verification")
        gv = QGridLayout(grp)
        gv.setContentsMargins(14, 18, 14, 14)
        gv.setHorizontalSpacing(14)
        gv.setVerticalSpacing(12)

        # Left Wink Card
        f_left = QFrame()
        f_left.setStyleSheet("background-color: #202226; border: 1px solid #2E323A; border-radius: 6px; padding: 10px;")
        fl_layout = QVBoxLayout(f_left)
        lbl_l_title = QLabel("Left Eye (Left Click)")
        lbl_l_title.setStyleSheet("font-weight: 700; color: #F5F5F5; font-size: 13px;")
        fl_layout.addWidget(lbl_l_title)
        self.lbl_left_wink_status = QLabel("Wink left eye to test")
        self.lbl_left_wink_status.setStyleSheet("color: #A1A1AA; font-size: 12px;")
        fl_layout.addWidget(self.lbl_left_wink_status)
        gv.addWidget(f_left, 0, 0)

        # Right Wink Card
        f_right = QFrame()
        f_right.setStyleSheet("background-color: #202226; border: 1px solid #2E323A; border-radius: 6px; padding: 10px;")
        fr_layout = QVBoxLayout(f_right)
        lbl_r_title = QLabel("Right Eye (Right Click)")
        lbl_r_title.setStyleSheet("font-weight: 700; color: #F5F5F5; font-size: 13px;")
        fr_layout.addWidget(lbl_r_title)
        self.lbl_right_wink_status = QLabel("Wink right eye to test")
        self.lbl_right_wink_status.setStyleSheet("color: #A1A1AA; font-size: 12px;")
        fr_layout.addWidget(self.lbl_right_wink_status)
        gv.addWidget(f_right, 0, 1)

        self.lbl_resting_eyes = QLabel("Eye baselines are monitored automatically. Click 'Next' to continue.")
        self.lbl_resting_eyes.setStyleSheet("color: #34D399; font-size: 12px; font-weight: 600;")
        gv.addWidget(self.lbl_resting_eyes, 1, 0, 1, 2)

        v_left.addWidget(grp)
        v_left.addStretch(1)
        h_main.addLayout(v_left, 1)

        # Right Column: Compact Live Camera Preview
        v_right = QVBoxLayout()
        v_right.setSpacing(8)
        lbl_prev_title = QLabel("Webcam View (Wink Testing)")
        lbl_prev_title.setStyleSheet("font-size: 12px; font-weight: 600; color: #A1A1AA;")
        v_right.addWidget(lbl_prev_title)
        self.cam_preview_step3 = CalibrationCameraPreview()
        v_right.addWidget(self.cam_preview_step3)
        v_right.addStretch(1)
        h_main.addLayout(v_right)

        return w

    def _create_step4_gestures(self) -> QWidget:
        """Step 4: Optional advanced gestures explanation."""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(14)

        info = QLabel(
            "Optional Hands-Free Gestures:\n\n"
            "HeadMouseAI includes optional facial gestures for power users. "
            "These are ready to use with standard default sensitivities:"
        )
        info.setStyleSheet("color: #A1A1AA; font-size: 13px; line-height: 1.5;")
        v.addWidget(info)

        cards_box = QVBoxLayout()
        cards_box.setSpacing(10)

        # Card 1: Drag & Drop
        c1 = QFrame()
        c1.setStyleSheet("background-color: #202226; border: 1px solid #2E323A; border-radius: 8px; padding: 10px;")
        c1_layout = QVBoxLayout(c1)
        c1_title = QLabel("🖱 Hands-Free Drag & Drop")
        c1_title.setStyleSheet("font-weight: 700; color: #60A5FA; font-size: 12px;")
        c1_desc = QLabel("Close and hold your left eye for about 0.4 seconds to grab an item. Move your head to drag, then wink to drop.")
        c1_desc.setStyleSheet("color: #A1A1AA; font-size: 11px;")
        c1_desc.setWordWrap(True)
        c1_layout.addWidget(c1_title)
        c1_layout.addWidget(c1_desc)
        cards_box.addWidget(c1)

        # Card 2: Scroll
        c2 = QFrame()
        c2.setStyleSheet("background-color: #202226; border: 1px solid #2E323A; border-radius: 8px; padding: 10px;")
        c2_layout = QVBoxLayout(c2)
        c2_title = QLabel("📜 Hands-Free Scrolling")
        c2_title.setStyleSheet("font-weight: 700; color: #34D399; font-size: 12px;")
        c2_desc = QLabel("Smile or show teeth, then tilt your head UP or DOWN to scroll web pages and documents smoothly.")
        c2_desc.setStyleSheet("color: #A1A1AA; font-size: 11px;")
        c2_desc.setWordWrap(True)
        c2_layout.addWidget(c2_title)
        c2_layout.addWidget(c2_desc)
        cards_box.addWidget(c2)

        # Card 3: Zoom
        c3 = QFrame()
        c3.setStyleSheet("background-color: #202226; border: 1px solid #2E323A; border-radius: 8px; padding: 10px;")
        c3_layout = QVBoxLayout(c3)
        c3_title = QLabel("🔍 Hands-Free Zoom")
        c3_title.setStyleSheet("font-weight: 700; color: #818CF8; font-size: 12px;")
        c3_desc = QLabel("Smile while raising both eyebrows, then tilt your head UP to zoom in or DOWN to zoom out.")
        c3_desc.setStyleSheet("color: #A1A1AA; font-size: 11px;")
        c3_desc.setWordWrap(True)
        c3_layout.addWidget(c3_title)
        c3_layout.addWidget(c3_desc)
        cards_box.addWidget(c3)

        v.addLayout(cards_box)
        v.addStretch(1)
        return w

    def _create_step5_confirmation(self) -> QWidget:
        """Final confirmation page."""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(14)

        info = QLabel(
            "Calibration Complete!\n\n"
            "Review your setup summary below. Click 'Apply & Finish' to activate your personalized profile."
        )
        info.setStyleSheet("color: #A1A1AA; font-size: 13px; line-height: 1.5;")
        v.addWidget(info)

        grp = QGroupBox("Calibration Summary")
        gv = QGridLayout(grp)
        gv.setContentsMargins(14, 18, 14, 14)
        gv.setHorizontalSpacing(14)
        gv.setVerticalSpacing(10)

        gv.addWidget(self._make_label("Head Position:"), 0, 0)
        self.sum_nose = QLabel("Calibrated & Centered")
        self.sum_nose.setStyleSheet("color: #34D399; font-weight: 600; font-size: 12px;")
        gv.addWidget(self.sum_nose, 0, 1)

        gv.addWidget(self._make_label("Eye Controls:"), 1, 0)
        self.sum_eyes = QLabel("Ready (Left / Right Wink Clicks Active)")
        self.sum_eyes.setStyleSheet("color: #34D399; font-weight: 600; font-size: 12px;")
        gv.addWidget(self.sum_eyes, 1, 1)

        gv.addWidget(self._make_label("Hands-Free Gestures:"), 2, 0)
        self.sum_gestures = QLabel("Ready (Drag, Scroll & Zoom Configured)")
        self.sum_gestures.setStyleSheet("color: #34D399; font-weight: 600; font-size: 12px;")
        gv.addWidget(self.sum_gestures, 2, 1)

        v.addWidget(grp)

        self.lbl_validation_status = QLabel("✔ All settings are verified and ready to apply.")
        self.lbl_validation_status.setStyleSheet("color: #34D399; font-weight: 600; font-size: 13px;")
        v.addWidget(self.lbl_validation_status)

        h_retry = QHBoxLayout()
        self.btn_try_again = QPushButton("Try Again")
        self.btn_try_again.setFixedHeight(34)
        self.btn_try_again.setFixedWidth(110)
        self.btn_try_again.setStyleSheet(
            "QPushButton { background-color: #202226; color: #A1A1AA; border: 1px solid #2E323A; border-radius: 6px; font-weight: 600; }"
            "QPushButton:hover { background-color: #292C32; color: #FFFFFF; border-color: #3F434C; }"
            "QPushButton:focus { border: 2px solid #A7B0BC; }"
        )
        self.btn_try_again.clicked.connect(self._restart_wizard)
        h_retry.addWidget(self.btn_try_again)
        h_retry.addStretch(1)
        v.addLayout(h_retry)

        v.addStretch(1)
        return w

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #A1A1AA; font-weight: 600; font-size: 12px;")
        return lbl

    # ------------------------------------------------------------------ #
    # Live Telemetry & Sampling State Machine
    # ------------------------------------------------------------------ #
    @Slot(dict)
    def on_telemetry(self, t: dict) -> None:
        """Handle 20-30Hz real-time telemetry from VisionWorker."""
        self._last_telemetry = t
        has_face = bool(t.get("has_face", False))
        step_idx = self.stack.currentIndex()

        # Step 1: Live face & distance indicators
        if step_idx == 0:
            fps = t.get("fps", 0.0)
            lat = t.get("latency_ms", 0.0)
            dist_status = t.get("face_distance_status", "OPTIMAL")

            self.lbl_cam_metrics.setText(f"Camera Running: {fps:.1f} FPS ({lat:.0f} ms latency)")
            if has_face:
                if dist_status == "TOO_FAR":
                    self.lbl_face_status.setText("⚠ Face Detected — A bit too far from camera")
                    self.lbl_face_status.setStyleSheet("font-size: 14px; font-weight: 700; color: #FBBF24;")
                    self.lbl_distance_guide.setText("Move a little closer so your face fills the center of the frame.")
                elif dist_status == "TOO_CLOSE":
                    self.lbl_face_status.setText("⚠ Face Detected — A bit too close to camera")
                    self.lbl_face_status.setStyleSheet("font-size: 14px; font-weight: 700; color: #FBBF24;")
                    self.lbl_distance_guide.setText("Move slightly back to a comfortable viewing distance.")
                elif dist_status == "OFF_CENTER":
                    self.lbl_face_status.setText("⚠ Face Detected — Slightly off-center")
                    self.lbl_face_status.setStyleSheet("font-size: 14px; font-weight: 700; color: #FBBF24;")
                    self.lbl_distance_guide.setText("Center your face directly in front of the camera.")
                else:
                    self.lbl_face_status.setText("✔ Face Detected & Perfectly Positioned")
                    self.lbl_face_status.setStyleSheet("font-size: 14px; font-weight: 700; color: #34D399;")
                    self.lbl_distance_guide.setText("Great posture! Click 'Next' when you are ready to continue.")
            else:
                self.lbl_face_status.setText("Looking for your face...")
                self.lbl_face_status.setStyleSheet("font-size: 14px; font-weight: 700; color: #FBBF24;")
                self.lbl_distance_guide.setText("Please make sure your face is visible to the webcam.")
            self._update_navigation()

        # Step 3: Wink live verification feedback & passive baseline gathering
        elif step_idx == 2:
            blink_ev = t.get("blink_event")
            if blink_ev in ("LEFT_CLICK", 1):
                self.left_click_verified = True
                self.lbl_left_wink_status.setText("✔ Left Click Detected!")
                self.lbl_left_wink_status.setStyleSheet("color: #34D399; font-weight: 700; font-size: 12px;")
            elif blink_ev in ("RIGHT_CLICK", 2):
                self.right_click_verified = True
                self.lbl_right_wink_status.setText("✔ Right Click Detected!")
                self.lbl_right_wink_status.setStyleSheet("color: #34D399; font-weight: 700; font-size: 12px;")

            # Passively capture resting EAR baseline when face is steady and eyes are open
            l_ear = t.get("left_ear")
            r_ear = t.get("right_ear")
            if l_ear is not None and r_ear is not None:
                try:
                    le_f = float(l_ear)
                    re_f = float(r_ear)
                    if 0.18 <= le_f <= 0.42 and 0.18 <= re_f <= 0.42:
                        buf_eyes = self._step_buffers[2]
                        if len(buf_eyes) < SAMPLE_FRAMES_PER_STEP:
                            buf_eyes.append((le_f, re_f))
                            if len(buf_eyes) == SAMPLE_FRAMES_PER_STEP:
                                self.candidate_left_ear = round(float(np.median([p[0] for p in buf_eyes])), 4)
                                self.candidate_right_ear = round(float(np.median([p[1] for p in buf_eyes])), 4)
                except (ValueError, TypeError):
                    pass

        # Step 4: Passive mouth & eyebrow baselines
        elif step_idx == 3:
            mw = t.get("mouth_width_ratio")
            if mw is not None:
                try:
                    mw_f = float(mw)
                    if 0.35 <= mw_f <= 0.85:
                        buf_m = self._step_buffers[3]
                        if len(buf_m) < SAMPLE_FRAMES_PER_STEP:
                            buf_m.append(mw_f)
                            if len(buf_m) == SAMPLE_FRAMES_PER_STEP:
                                self.candidate_mouth_width = round(float(np.median(buf_m)), 4)
                except (ValueError, TypeError):
                    pass

            leb = t.get("left_eb_ratio")
            reb = t.get("right_eb_ratio")
            if leb is not None and reb is not None:
                try:
                    leb_f = float(leb)
                    reb_f = float(reb)
                    if 0.08 <= leb_f <= 0.35 and 0.08 <= reb_f <= 0.35:
                        buf_eb = self._step_buffers[4]
                        if len(buf_eb) < SAMPLE_FRAMES_PER_STEP:
                            buf_eb.append((leb_f, reb_f))
                            if len(buf_eb) == SAMPLE_FRAMES_PER_STEP:
                                self.candidate_left_eb = round(float(np.median([p[0] for p in buf_eb])), 4)
                                self.candidate_right_eb = round(float(np.median([p[1] for p in buf_eb])), 4)
                except (ValueError, TypeError):
                    pass

        # Head / Nose Active Sampling
        if self._sampling_step is not None:
            if not has_face:
                self.lbl_result_nose.setText("⚠ Face lost during calibration. Please face the camera.")
                return

            buf = self._step_buffers[self._sampling_step]

            if self._sampling_step == 1:  # Nose calibration
                # IMPORTANT ROOT CAUSE FIX:
                # Extract actual nose landmark coordinates (nose_x, nose_y),
                # NOT virtual cursor screen coordinates (norm_cx, norm_cy).
                nx = t.get("nose_x")
                if nx is None:
                    nx = t.get("norm_cx", 0.5)
                ny = t.get("nose_y")
                if ny is None:
                    ny = t.get("norm_cy", 0.5)

                try:
                    nx = float(nx)
                    ny = float(ny)
                except (TypeError, ValueError):
                    return

                # Reject frames where nose is outside valid physiological boundary [0.15, 0.85]
                if not (0.15 <= nx <= 0.85 and 0.15 <= ny <= 0.85):
                    self.lbl_result_nose.setText("⚠ Head position too far off center. Look at the screen center.")
                    return

                buf.append((nx, ny))
                prog = len(buf) / SAMPLE_FRAMES_PER_STEP
                self.prog_nose.setValue(int(prog * 100))
                self.prog_nose.setFormat(f"Measuring neutral posture... {int(prog * 100)}%")
                if len(buf) >= SAMPLE_FRAMES_PER_STEP:
                    self._finish_step_sampling(1)

            elif self._sampling_step == 2:  # Explicit Eye Sampling (if triggered)
                l_ear = t.get("left_ear")
                r_ear = t.get("right_ear")
                if l_ear is not None and r_ear is not None:
                    try:
                        le = float(l_ear)
                        re = float(r_ear)
                        if 0.18 <= le <= 0.42 and 0.18 <= re <= 0.42:
                            buf.append((le, re))
                            if len(buf) >= SAMPLE_FRAMES_PER_STEP:
                                self._finish_step_sampling(2)
                    except (TypeError, ValueError):
                        pass

            elif self._sampling_step == 3:  # Mouth
                mw = t.get("mouth_width_ratio")
                if mw is not None:
                    try:
                        mw_f = float(mw)
                        if 0.35 <= mw_f <= 0.85:
                            buf.append(mw_f)
                            if len(buf) >= SAMPLE_FRAMES_PER_STEP:
                                self._finish_step_sampling(3)
                    except (TypeError, ValueError):
                        pass

            elif self._sampling_step == 4:  # Eyebrows
                leb = t.get("left_eb_ratio")
                reb = t.get("right_eb_ratio")
                if leb is not None and reb is not None:
                    try:
                        le = float(leb)
                        re = float(reb)
                        if 0.08 <= le <= 0.35 and 0.08 <= re <= 0.35:
                            buf.append((le, re))
                            if len(buf) >= SAMPLE_FRAMES_PER_STEP:
                                self._finish_step_sampling(4)
                    except (TypeError, ValueError):
                        pass

    def _start_sampling(self, step: int) -> None:
        """Begin collecting samples for a specific step."""
        self._sampling_step = step
        self._step_buffers[step].clear()
        if step == 1:
            self.prog_nose.setValue(0)
            self.prog_nose.setFormat("Collecting samples... Hold still.")
            self.lbl_result_nose.setText("Measuring... Keep looking straight ahead.")
            self.btn_sample_nose.setEnabled(False)
            self.btn_retry_nose.setVisible(False)
            self.btn_next.setEnabled(False)

    def _finish_step_sampling(self, step: int) -> None:
        """Process collected samples with robust median filtering."""
        self._sampling_step = None
        buf = self._step_buffers[step]
        if not buf:
            return

        if step == 1:  # Head Center
            med_x = float(np.median([p[0] for p in buf]))
            med_y = float(np.median([p[1] for p in buf]))
            self.candidate_nose_x = round(med_x, 4)
            self.candidate_nose_y = round(med_y, 4)
            self.prog_nose.setValue(100)
            self.prog_nose.setFormat("100% — Captured!")
            self.lbl_result_nose.setText(f"✔ Neutral head position captured successfully! ({self.candidate_nose_x:.3f}, {self.candidate_nose_y:.3f})")
            self.lbl_result_nose.setStyleSheet("color: #34D399; font-size: 12px; font-weight: 600;")
            self.btn_sample_nose.setEnabled(True)
            self.btn_sample_nose.setText("Recalibrate")
            self.btn_retry_nose.setVisible(True)
            self.btn_next.setEnabled(True)

        elif step == 2:  # Eyes
            med_l = float(np.median([p[0] for p in buf]))
            med_r = float(np.median([p[1] for p in buf]))
            self.candidate_left_ear = round(med_l, 4)
            self.candidate_right_ear = round(med_r, 4)
            self.btn_next.setEnabled(True)

        elif step == 3:  # Mouth
            if isinstance(buf[0], (tuple, list)):
                med_mw = float(np.median([p[0] for p in buf]))
            else:
                med_mw = float(np.median(buf))
            self.candidate_mouth_width = round(med_mw, 4)
            self.btn_next.setEnabled(True)

        elif step == 4:  # Eyebrows
            med_leb = float(np.median([p[0] for p in buf]))
            med_reb = float(np.median([p[1] for p in buf]))
            self.candidate_left_eb = round(med_leb, 4)
            self.candidate_right_eb = round(med_reb, 4)
            self.btn_next.setEnabled(True)

        self._update_navigation()

    # ------------------------------------------------------------------ #
    # Navigation & Flow Control
    # ------------------------------------------------------------------ #
    def _update_navigation(self) -> None:
        idx = self.stack.currentIndex()
        self.step_indicator.set_current_step(idx)

        # Back button disabled only on first step
        self.btn_back.setEnabled(idx > 0)

        # Next button logic
        if idx == 0:  # Position check
            has_face = bool(self._last_telemetry.get("has_face", False))
            self.btn_next.setText("Next >")
            self.btn_next.setEnabled(has_face)
        elif idx == 1:  # Head calibration
            self.btn_next.setText("Next >")
            self.btn_next.setEnabled(self.candidate_nose_x is not None and self.candidate_nose_y is not None)
        elif idx == 2:  # Eye controls
            self.btn_next.setText("Next >")
            self.btn_next.setEnabled(True)  # User can verify or proceed with defaults
        elif idx == 3:  # Optional gestures
            self.btn_next.setText("Review Summary >")
            self.btn_next.setEnabled(True)
        elif idx == 4:  # Confirmation & Apply
            self.btn_next.setText("Apply & Finish")
            self.btn_next.setEnabled(True)
            self._update_summary_page()

    def _on_next(self) -> None:
        idx = self.stack.currentIndex()
        if idx < TOTAL_STEPS - 1:
            self.stack.setCurrentIndex(idx + 1)
            self._update_navigation()
        else:
            self._apply_and_save()

    def _on_back(self) -> None:
        idx = self.stack.currentIndex()
        if idx > 0:
            self.stack.setCurrentIndex(idx - 1)
            self._update_navigation()

    def _restart_wizard(self) -> None:
        """Reset wizard to Step 1 for full re-test."""
        self._sampling_step = None
        for buf in self._step_buffers.values():
            buf.clear()
        self.stack.setCurrentIndex(0)
        self._update_navigation()

    def _update_summary_page(self) -> None:
        """Populate the final summary page with human-friendly descriptions."""
        if self.candidate_nose_x is not None and self.candidate_nose_y is not None:
            self.sum_nose.setText(f"Centered ({self.candidate_nose_x:.3f}, {self.candidate_nose_y:.3f})")
        else:
            self.sum_nose.setText("Ready (Preserved from settings)")

        if self.candidate_left_ear is not None and self.candidate_right_ear is not None:
            self.sum_eyes.setText(f"Custom Baselines ({self.candidate_left_ear:.2f} / {self.candidate_right_ear:.2f})")
        else:
            self.sum_eyes.setText("Ready (Balanced Sensitivity)")

        cand_dict = self._build_candidate_dict()
        is_valid, err_msg = validate_calibration_data(cand_dict)
        if is_valid:
            self.lbl_validation_status.setText("✔ All measured baselines are valid and ready to apply.")
            self.lbl_validation_status.setStyleSheet("color: #34D399; font-weight: 600; font-size: 13px;")
            self.btn_next.setEnabled(True)
        else:
            self.lbl_validation_status.setText(f"⚠ Calibration Warning: {err_msg}")
            self.lbl_validation_status.setStyleSheet("color: #F87171; font-weight: 600; font-size: 13px;")
            self.btn_next.setEnabled(False)

    def _build_candidate_dict(self) -> dict[str, Any]:
        """Assemble dictionary of collected candidate baselines."""
        res: dict[str, Any] = {}
        if self.candidate_nose_x is not None and self.candidate_nose_y is not None:
            res["neutral_x"] = self.candidate_nose_x
            res["neutral_y"] = self.candidate_nose_y
        if self.candidate_left_ear is not None and self.candidate_right_ear is not None:
            res["left_baseline_ear"] = self.candidate_left_ear
            res["right_baseline_ear"] = self.candidate_right_ear
        if self.candidate_mouth_width is not None:
            res["mouth_width_baseline"] = self.candidate_mouth_width
        if self.candidate_left_eb is not None and self.candidate_right_eb is not None:
            res["left_eyebrow_baseline"] = self.candidate_left_eb
            res["right_eyebrow_baseline"] = self.candidate_right_eb
        return res

    def _apply_and_save(self) -> None:
        """Apply valid baselines to worker and persist to config.toml."""
        cand_dict = self._build_candidate_dict()
        is_valid, err_msg = validate_calibration_data(cand_dict)
        if not is_valid:
            self.lbl_validation_status.setText(f"Cannot apply invalid calibration: {err_msg}")
            self.lbl_validation_status.setStyleSheet("color: #F87171; font-weight: 600;")
            return

        if self.worker is not None:
            ok, msg = self.worker.apply_calibration_profile(cand_dict)
            if not ok:
                self.lbl_validation_status.setText(f"Worker rejected calibration: {msg}")
                self.lbl_validation_status.setStyleSheet("color: #F87171; font-weight: 600;")
                return

        self.sig_profile_applied.emit(cand_dict)
        logger.info(f"CalibrationWizard applied and saved profile: {cand_dict}")
        self.accept()

    def _on_cancel(self) -> None:
        """Cancel wizard, discard candidate values, and close."""
        self._sampling_step = None
        for buf in self._step_buffers.values():
            buf.clear()
        logger.info("CalibrationWizard cancelled by user. No settings changed.")
        self.reject()

    def _cleanup_worker_connections(self) -> None:
        """Safely disconnect worker signals without stopping worker."""
        if getattr(self, "_worker_connections_cleaned", False):
            return
        self._worker_connections_cleaned = True
        if self.worker is not None:
            try:
                self.worker.sig_telemetry.disconnect(self.on_telemetry)
            except Exception:
                pass
            try:
                self.worker.sig_frame_ready.disconnect(self._on_frame_ready)
            except Exception:
                pass
            if getattr(self, "_was_mouse_enabled", False):
                self.worker.mouse_controller.enable()

    def done(self, r: int) -> None:
        self._cleanup_worker_connections()
        super().done(r)

    def closeEvent(self, event: Any) -> None:
        """Ensure clean disconnection and mouse safety on close."""
        self._cleanup_worker_connections()
        super().closeEvent(event)
