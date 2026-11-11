"""First-launch Welcome & Onboarding Dialog for HeadMouseAI.

Provides new users with a beginner-friendly overview of camera positioning,
mouse safety mechanisms (F8/F9), and voluntary guided calibration.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config.settings import AppSettings
from gui.styles import LIGHT_SAAS_THEME_QSS
from utils.resource import get_icon_path


class WelcomeDialog(QDialog):
    """Clean, minimalist SaaS welcome modal shown on first application launch."""

    sig_start_calibration = Signal()

    def __init__(self, settings: AppSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Welcome to HeadMouseAI")
        self.setFixedSize(660, 560)
        self.setModal(True)
        self.setStyleSheet(LIGHT_SAAS_THEME_QSS)

        # Set Window Icon
        icon_path = get_icon_path("app_icon.png")
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # ---------------- Top Header Banner ---------------- #
        header = QHBoxLayout()
        header.setSpacing(14)

        lbl_logo = QLabel()
        icon_path = get_icon_path("app_icon.png")
        if icon_path.is_file():
            pix = QPixmap(str(icon_path)).scaled(
                44, 44, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            lbl_logo.setPixmap(pix)
            lbl_logo.setFixedSize(44, 44)
        header.addWidget(lbl_logo)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_title = QLabel("Welcome to HeadMouseAI")
        lbl_title.setStyleSheet("font-size: 20px; font-weight: 700; color: #F5F5F5;")
        title_box.addWidget(lbl_title)

        lbl_subtitle = QLabel("Hands-Free AI Desktop Controller — Getting Started Guide")
        lbl_subtitle.setStyleSheet("font-size: 13px; color: #A1A1AA;")
        title_box.addWidget(lbl_subtitle)
        header.addLayout(title_box)
        header.addStretch(1)
        layout.addLayout(header)

        # ---------------- 3 Guided Overview Cards ---------------- #

        # Card 1: Camera Setup & Positioning
        card1 = self._create_card(
            title="1. Camera Setup & Positioning",
            accent_color="#60A5FA",
            bg_tint="#162032",
            border_color="#1E3A8A",
            content=(
                "• <b>Positioning</b>: Place your webcam directly in front of you at eye level (~50–70 cm away).<br>"
                "• <b>Lighting</b>: Ensure even, front-facing room lighting. Avoid bright backlights or window glare.<br>"
                "• <b>Posture</b>: Sit in a comfortable, relaxed resting position with your head facing forward."
            ),
        )
        layout.addWidget(card1)

        # Card 2: Mouse Control & Safety
        card2 = self._create_card(
            title="2. Mouse Activation & Emergency Safety",
            accent_color="#34D399",
            bg_tint="#12251D",
            border_color="#065F46",
            content=(
                "• <b>Safety Default</b>: Real mouse cursor control is <b>DISABLED by default</b> upon startup.<br>"
                "• <b>Toggle Control [F8]</b>: Press <b>F8</b> at any time to enable or disable actual mouse control.<br>"
                "• <b>Emergency Stop [F9]</b>: Press <b>F9</b> instantly halts all pointer movement and clicks.<br>"
                "• <b>Face-Loss Interlock</b>: The cursor automatically freezes if you turn away or leave the frame."
            ),
        )
        layout.addWidget(card2)

        # Card 3: Calibration Walkthrough
        card3 = self._create_card(
            title="3. Smart Guided Calibration",
            accent_color="#A78BFA",
            bg_tint="#1E1A33",
            border_color="#4C1D95",
            content=(
                "• HeadMouseAI adapts to your natural resting head posture and eye geometry.<br>"
                "• The quick 4-step wizard guides you through head positioning, wink clicks, and optional gestures.<br>"
                "• You can run calibration right now or anytime later by pressing <b>[C]</b> on the dashboard."
            ),
        )
        layout.addWidget(card3)

        layout.addStretch(1)

        # ---------------- Footer Controls ---------------- #
        footer = QHBoxLayout()
        footer.setSpacing(12)

        self.chk_dont_show = QCheckBox("Don't show this welcome guide again on startup")
        self.chk_dont_show.setChecked(True)
        self.chk_dont_show.setStyleSheet("color: #A1A1AA; font-size: 12px; font-weight: 500;")
        footer.addWidget(self.chk_dont_show)

        footer.addStretch(1)

        btn_explore = QPushButton("Explore Dashboard")
        btn_explore.setFixedHeight(34)
        btn_explore.setStyleSheet(
            "QPushButton { background-color: #202226; color: #A1A1AA; border: 1px solid #2E323A; "
            "border-radius: 6px; padding: 6px 16px; font-weight: 600; font-size: 12px; }"
            "QPushButton:hover { background-color: #292C32; color: #FFFFFF; border-color: #3F434C; }"
            "QPushButton:focus { border: 2px solid #A7B0BC; }"
        )
        btn_explore.clicked.connect(self._on_explore_clicked)
        footer.addWidget(btn_explore)

        btn_calibrate = QPushButton("Start Guided Calibration")
        btn_calibrate.setObjectName("btn_start")
        btn_calibrate.setFixedHeight(34)
        btn_calibrate.clicked.connect(self._on_calibrate_clicked)
        footer.addWidget(btn_calibrate)

        layout.addLayout(footer)

    def _create_card(
        self, title: str, accent_color: str, bg_tint: str, border_color: str, content: str
    ) -> QFrame:
        """Create a stylized information card."""
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background-color: {bg_tint}; border: 1px solid {border_color}; "
            f"border-radius: 8px; padding: 10px 14px; }}"
        )
        cv = QVBoxLayout(card)
        cv.setContentsMargins(8, 6, 8, 6)
        cv.setSpacing(4)

        lbl_head = QLabel(title)
        lbl_head.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {accent_color};")
        cv.addWidget(lbl_head)

        lbl_body = QLabel(content)
        lbl_body.setStyleSheet("font-size: 12px; color: #E4E4E7; line-height: 1.5;")
        lbl_body.setWordWrap(True)
        cv.addWidget(lbl_body)

        return card

    def _persist_preference(self) -> None:
        """Save onboarding completion preference if requested."""
        if self.chk_dont_show.isChecked():
            self.settings.gui.first_launch_done = True
            try:
                self.settings.save()
            except Exception:
                pass

    def _on_explore_clicked(self) -> None:
        """User chose to explore dashboard directly."""
        self._persist_preference()
        self.accept()

    def _on_calibrate_clicked(self) -> None:
        """User chose to launch guided calibration."""
        self._persist_preference()
        self.accept()
        self.sig_start_calibration.emit()
