"""Modern interactive control bar for HeadMouseAI."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget


class ControlBarWidget(QWidget):
    """Bottom control bar hosting primary action buttons and hotkey reminders."""

    sig_start_requested = Signal()
    sig_stop_requested = Signal()
    sig_mouse_toggle_requested = Signal()
    sig_emergency_requested = Signal()
    sig_calibrate_requested = Signal()
    sig_reset_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tracking_active: bool = False
        self._real_mouse_enabled: bool = False
        self._init_ui()

    def _init_ui(self) -> None:
        self.setStyleSheet("QPushButton { padding: 4px 8px; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # 1. Start / Stop Tracking
        self.btn_toggle_tracking = QPushButton("Start Tracking")
        self.btn_toggle_tracking.setObjectName("btn_start")
        self.btn_toggle_tracking.setFixedHeight(32)
        self.btn_toggle_tracking.setMinimumWidth(108)
        self.btn_toggle_tracking.clicked.connect(self._on_toggle_tracking)
        layout.addWidget(self.btn_toggle_tracking)

        # 2. Real Mouse Control Toggle (F8)
        self.btn_mouse_toggle = QPushButton("Enable Real Mouse [F8]")
        self.btn_mouse_toggle.setObjectName("btn_mouse_toggle")
        self.btn_mouse_toggle.setFixedHeight(32)
        self.btn_mouse_toggle.setMinimumWidth(168)
        self.btn_mouse_toggle.setEnabled(False)
        self.btn_mouse_toggle.clicked.connect(self.sig_mouse_toggle_requested.emit)
        layout.addWidget(self.btn_mouse_toggle)

        # 3. Emergency Stop (F9)
        self.btn_emergency = QPushButton("Emergency Stop [F9]")
        self.btn_emergency.setObjectName("btn_emergency")
        self.btn_emergency.setFixedHeight(32)
        self.btn_emergency.setMinimumWidth(150)
        self.btn_emergency.clicked.connect(self.sig_emergency_requested.emit)
        layout.addWidget(self.btn_emergency)

        # 4. Calibration (C)
        self.btn_calibrate = QPushButton("Calibrate [C]")
        self.btn_calibrate.setObjectName("btn_calibrate")
        self.btn_calibrate.setFixedHeight(32)
        self.btn_calibrate.setMinimumWidth(96)
        self.btn_calibrate.setEnabled(False)
        self.btn_calibrate.clicked.connect(self.sig_calibrate_requested.emit)
        layout.addWidget(self.btn_calibrate)

        # 5. Reset Trackers (R)
        self.btn_reset = QPushButton("Reset [R]")
        self.btn_reset.setObjectName("btn_reset")
        self.btn_reset.setFixedHeight(32)
        self.btn_reset.setMinimumWidth(76)
        self.btn_reset.clicked.connect(self.sig_reset_requested.emit)
        layout.addWidget(self.btn_reset)

        # Explicit tab navigation traversal order
        self.btn_toggle_tracking.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_mouse_toggle.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_emergency.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_calibrate.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_reset.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        QWidget.setTabOrder(self.btn_toggle_tracking, self.btn_mouse_toggle)
        QWidget.setTabOrder(self.btn_mouse_toggle, self.btn_calibrate)
        QWidget.setTabOrder(self.btn_calibrate, self.btn_reset)
        QWidget.setTabOrder(self.btn_reset, self.btn_emergency)

        layout.addStretch(1)

        # Shortcut Legend
        self.lbl_legend = QLabel("[F8/M] Mouse  ·  [F9] Stop  ·  [C] Calib  ·  [R] Reset")
        self.lbl_legend.setStyleSheet("color: #A1A1AA; font-size: 11px; font-weight: 500;")
        layout.addWidget(self.lbl_legend)

    def _on_toggle_tracking(self) -> None:
        """Handle Start/Stop tracking click."""
        if not self._tracking_active:
            self.sig_start_requested.emit()
        else:
            self.sig_stop_requested.emit()

    def set_tracking_state(self, is_active: bool) -> None:
        """Update button labels and visual styling when tracking starts or stops."""
        self._tracking_active = is_active
        if is_active:
            self.btn_toggle_tracking.setText("Stop Tracking")
            self.btn_toggle_tracking.setObjectName("btn_stop")
            self.btn_mouse_toggle.setEnabled(True)
            self.btn_calibrate.setEnabled(True)
        else:
            self.btn_toggle_tracking.setText("Start Tracking")
            self.btn_toggle_tracking.setObjectName("btn_start")
            self.btn_mouse_toggle.setEnabled(False)
            self.btn_calibrate.setEnabled(False)
            self.set_mouse_state(False, "DISABLED")

        # Refresh style
        self.btn_toggle_tracking.setStyle(self.btn_toggle_tracking.style())

    def set_mouse_state(self, is_enabled: bool, state_label: str) -> None:
        """Update F8 button state text and styling."""
        self._real_mouse_enabled = is_enabled
        if is_enabled:
            self.btn_mouse_toggle.setText("Disable Real Mouse [F8]")
            self.btn_mouse_toggle.setStyleSheet(
                "QPushButton#btn_mouse_toggle { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #059669, stop:1 #064E3B); "
                "border: 1px solid #10B981; color: #FFFFFF; font-weight: 600; border-radius: 6px; }"
                "QPushButton#btn_mouse_toggle:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #10B981, stop:1 #059669); border-color: #34D399; }"
                "QPushButton#btn_mouse_toggle:focus { outline: none; border: 2px solid #6EE7B7; }"
            )
        else:
            self.btn_mouse_toggle.setText("Enable Real Mouse [F8]")
            self.btn_mouse_toggle.setStyleSheet("")
