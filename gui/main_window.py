"""Main Desktop Window for HeadMouseAI Application — Redesigned SaaS Experience."""

from __future__ import annotations

import ctypes
import time
from typing import Optional

from PySide6.QtCore import QTimer, Qt, Slot
from PySide6.QtGui import QCloseEvent, QIcon, QKeyEvent, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config.settings import AppSettings, get_settings
from gui.dialogs.calibration_wizard import CalibrationWizard
from gui.styles import LIGHT_SAAS_THEME_QSS
from gui.widgets.control_bar import ControlBarWidget
from gui.widgets.ai_cursor_widget import AICursorWidget
from gui.widgets.jadoo_assistant_widget import JadooAssistantWidget
from gui.widgets.settings_tab import SettingsTabWidget
from gui.widgets.task_agent_widget import TaskAgentWidget
from gui.widgets.telemetry_cards import StatusBadge, TelemetryCardsWidget
from gui.widgets.video_widget import VideoWidget
from gui.widgets.voice_control_widget import VoiceControlWidget
from gui.floating_panel import FloatingControlPanel
from gui.worker import VisionWorker
from jadoo_assistant.assistant_worker import JadooWorker
from task_agent.task_manager import TaskManager
from utils.logger import logger
from utils.resource import get_icon_path
from voice_engine.command_registry import AccessibilityCommand
from voice_engine.keyboard_controller import KeyboardActionController
from voice_engine.text_injector import TextInjector
from voice_engine.voice_worker import VoiceWorker

VK_F8 = 0x77
VK_F9 = 0x78


def is_windows_key_pressed(vk: int) -> bool:
    """Check hardware key state via user32 GetAsyncKeyState on Windows."""
    try:
        if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32"):
            u32 = ctypes.windll.user32
            u32.GetAsyncKeyState.restype = ctypes.c_short
            return bool(u32.GetAsyncKeyState(vk) & 0x8000)
    except Exception:
        pass
    return False


class StatusCard(QFrame):
    """Clean minimalist SaaS status card with subtle state tinting and hover styling."""

    def __init__(
        self, title: str, initial_status: str, initial_state: str = "NORMAL", parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("status_card")
        self._title_text = title

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)

        self.lbl_title = QLabel(title)
        layout.addWidget(self.lbl_title)

        self.lbl_status = QLabel(initial_status)
        layout.addWidget(self.lbl_status)

        self.set_status(initial_status, initial_state)

    def set_status(self, text: str, state: str = "NORMAL") -> None:
        self.lbl_status.setText(text)
        state_u = state.upper()
        if state_u in ("OK", "ACTIVE", "CONNECTED", "ENABLED", "COMPLETE", "CALIBRATED"):
            self.setStyleSheet(
                "QFrame#status_card { background-color: #0F231A; border: 1px solid #065F46; border-radius: 8px; }"
                "QFrame#status_card:hover { border-color: #059669; }"
            )
            self.lbl_title.setStyleSheet("font-size: 11px; font-weight: 600; color: #6EE7B7;")
            self.lbl_status.setStyleSheet("font-size: 13px; font-weight: 700; color: #A7F3D0;")
        elif state_u in ("WARNING", "SEARCHING", "PENDING", "CALIBRATING"):
            self.setStyleSheet(
                "QFrame#status_card { background-color: #261A0C; border: 1px solid #854D0E; border-radius: 8px; }"
                "QFrame#status_card:hover { border-color: #D97706; }"
            )
            self.lbl_title.setStyleSheet("font-size: 11px; font-weight: 600; color: #FCD34D;")
            self.lbl_status.setStyleSheet("font-size: 13px; font-weight: 700; color: #FDE68A;")
        elif state_u in ("ERROR", "STOPPED", "OFFLINE", "EMERGENCY"):
            self.setStyleSheet(
                "QFrame#status_card { background-color: #241114; border: 1px solid #991B1B; border-radius: 8px; }"
                "QFrame#status_card:hover { border-color: #DC2626; }"
            )
            self.lbl_title.setStyleSheet("font-size: 11px; font-weight: 600; color: #FCA5A5;")
            self.lbl_status.setStyleSheet("font-size: 13px; font-weight: 700; color: #FECACA;")
        else:
            self.setStyleSheet(
                "QFrame#status_card { background-color: #1A1C22; border: 1px solid #353942; border-radius: 8px; }"
                "QFrame#status_card:hover { border-color: #4B5260; }"
            )
            self.lbl_title.setStyleSheet("font-size: 11px; font-weight: 600; color: #A7B0BC;")
            self.lbl_status.setStyleSheet("font-size: 13px; font-weight: 700; color: #F5F5F5;")


class MainWindow(QMainWindow):
    """Primary application desktop window featuring a clean minimalist SaaS interface."""

    def __init__(self, settings: Optional[AppSettings] = None) -> None:
        super().__init__()
        self.settings: AppSettings = settings if settings is not None else get_settings()

        self.setWindowTitle("HeadMouseAI — Hands-Free Desktop Controller")
        self.resize(1240, 820)
        self.setMinimumSize(960, 680)

        # Set Window Icon with full multi-resolution support
        app_icon = QIcon()
        ico_path = get_icon_path("app_icon.ico")
        png_path = get_icon_path("app_icon.png")
        if ico_path.is_file():
            app_icon.addFile(str(ico_path))
        if png_path.is_file():
            app_icon.addFile(str(png_path))
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)

        self.setStyleSheet(LIGHT_SAAS_THEME_QSS)

        # Subsystems
        self.worker: Optional[VisionWorker] = None
        self.voice_worker: Optional[VoiceWorker] = None
        self.jadoo_worker: Optional[JadooWorker] = None
        self.text_injector: Optional[TextInjector] = None
        self.jadoo_widget: Optional[JadooAssistantWidget] = None
        self.ai_cursor_widget: Optional[AICursorWidget] = None
        self.task_agent_widget: Optional[TaskAgentWidget] = None
        self.task_manager: Optional[TaskManager] = None
        self.keyboard_controller: KeyboardActionController = KeyboardActionController()
        self.floating_panel: Optional[FloatingControlPanel] = None
        self._prev_f8: bool = False
        self._prev_f9: bool = False
        self._last_f8_trigger_time: float = 0.0
        self._last_f9_trigger_time: float = 0.0
        self._calib_dialog: Optional[CalibrationWizard] = None
        self._diagnostics_visible: bool = False

        self._init_ui()
        self._init_worker()
        self._init_hotkeys()

        # Check for first launch onboarding guide
        if not getattr(self.settings.gui, "first_launch_done", False):
            QTimer.singleShot(400, self._show_first_launch_welcome)

    def _init_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(14, 8, 14, 8)
        main_layout.setSpacing(8)

        # ---------------- Top Header ---------------- #
        hdr = QWidget()
        hdr.setObjectName("header_widget")
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(16, 10, 16, 10)
        hdr_layout.setSpacing(12)

        # Brand Icon
        lbl_logo = QLabel()
        icon_path = get_icon_path("app_icon.png")
        if icon_path.is_file():
            pix = QPixmap(str(icon_path)).scaled(
                32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            lbl_logo.setPixmap(pix)
            lbl_logo.setFixedSize(32, 32)
            hdr_layout.addWidget(lbl_logo)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        lbl_brand = QLabel("HeadMouseAI")
        lbl_brand.setStyleSheet("font-size: 17px; font-weight: 700; color: #F5F5F5; letter-spacing: -0.3px;")
        title_box.addWidget(lbl_brand)

        lbl_subtitle = QLabel("Hands-Free AI Desktop Controller")
        lbl_subtitle.setStyleSheet("font-size: 12px; color: #A1A1AA; font-weight: 500;")
        title_box.addWidget(lbl_subtitle)
        hdr_layout.addLayout(title_box)

        hdr_layout.addStretch(1)

        # Quick Status Pills in Header
        self.hdr_badge_camera = StatusBadge("OFFLINE")
        self.hdr_badge_camera.setFixedWidth(92)
        hdr_layout.addWidget(self.hdr_badge_camera)

        self.hdr_badge_tracking = StatusBadge("STOPPED")
        self.hdr_badge_tracking.setFixedWidth(92)
        hdr_layout.addWidget(self.hdr_badge_tracking)

        self.hdr_badge_mouse = StatusBadge("MOUSE OFF")
        self.hdr_badge_mouse.setFixedWidth(96)
        hdr_layout.addWidget(self.hdr_badge_mouse)

        self.hdr_badge_voice = StatusBadge("VOICE: IDLE")
        self.hdr_badge_voice.setFixedWidth(100)
        hdr_layout.addWidget(self.hdr_badge_voice)

        self.hdr_badge_jadoo = StatusBadge("JADOO IDLE")
        self.hdr_badge_jadoo.setFixedWidth(100)
        hdr_layout.addWidget(self.hdr_badge_jadoo)

        main_layout.addWidget(hdr)

        # ---------------- Tabbed Navigation (Clean Top Bar) ---------------- #
        # Exactly: Dashboard | Live Tracking | Settings | Help
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Tab 1: Dashboard
        tab_dash = self._create_dashboard_tab()
        self.tabs.addTab(tab_dash, "Dashboard")

        # Tab 2: Live Tracking
        tab_live = self._create_live_tracking_tab()
        self.tabs.addTab(tab_live, "Live Tracking")

        # Tab 3: Settings
        self.settings_tab = SettingsTabWidget(self.settings)
        self.settings_tab.sig_settings_changed.connect(self._on_settings_changed)
        self.settings_tab.sig_camera_changed.connect(self._on_camera_changed)
        self.settings_tab.sig_toggle_mesh.connect(self._on_toggle_mesh)
        self.settings_tab.sig_toggle_cursor.connect(self._on_toggle_cursor)
        self.settings_tab.sig_run_wizard.connect(self._on_calibrate_requested)
        self.settings_tab.sig_voice_mic_changed.connect(self._on_voice_mic_changed)
        self.settings_tab.sig_voice_model_changed.connect(self._on_voice_model_changed)
        self.settings_tab.sig_voice_lang_changed.connect(self._on_voice_lang_changed)
        self.settings_tab.sig_voice_enabled_changed.connect(self._on_voice_enabled_changed)
        self.settings_tab.sig_voice_threshold_changed.connect(self._on_voice_threshold_changed)
        self.settings_tab.sig_groq_key_changed.connect(self._on_groq_key_changed)
        self.settings_tab.sig_gemini_key_changed.connect(self._on_gemini_key_changed)
        self.settings_tab.sig_stt_mode_changed.connect(self._on_stt_mode_changed)
        self.settings_tab.sig_tts_toggled.connect(self._on_tts_toggled)
        self.tabs.addTab(self.settings_tab, "Settings")

        # Tab 4: Help
        tab_help = self._create_help_tab()
        self.tabs.addTab(tab_help, "Help")

        main_layout.addWidget(self.tabs, 1)

        # ---------------- Status Bar ---------------- #
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.lbl_status = QLabel("System Ready | Real Mouse: DISABLED (Press F8 to enable)")
        self.lbl_status.setStyleSheet("color: #A1A1AA; font-weight: 500;")
        self.status_bar.addWidget(self.lbl_status)

    def _create_dashboard_tab(self) -> QWidget:
        """Create clean minimalist Dashboard tab with status cards, preview, and expandable details."""
        container = QWidget()
        v_layout = QVBoxLayout(container)
        v_layout.setContentsMargins(10, 8, 10, 6)
        v_layout.setSpacing(8)

        # 1. Simple Status Panel (4 prominent status cards)
        panel_status = QHBoxLayout()
        panel_status.setSpacing(10)

        self.card_cam = StatusCard("Camera Stream", "Offline", "OFFLINE")
        panel_status.addWidget(self.card_cam)

        self.card_face = StatusCard("Face Detection", "Searching...", "WARNING")
        panel_status.addWidget(self.card_face)

        self.card_calib = StatusCard("Calibration", "Ready", "OK")
        panel_status.addWidget(self.card_calib)

        self.card_mouse = StatusCard("Mouse Control", "Disabled [F8]", "NORMAL")
        panel_status.addWidget(self.card_mouse)

        v_layout.addLayout(panel_status)

        # 2. Main Camera Preview (Large, stable, proper aspect ratio, minimal overlays)
        self.video_widget = VideoWidget()
        v_layout.addWidget(self.video_widget, 1)

        # 3. Main Controls Bar
        self.control_bar = ControlBarWidget()
        self.control_bar.sig_start_requested.connect(self._on_start_tracking)
        self.control_bar.sig_stop_requested.connect(self._on_stop_tracking)
        self.control_bar.sig_mouse_toggle_requested.connect(self._on_toggle_real_mouse)
        self.control_bar.sig_emergency_requested.connect(self._on_emergency_stop)
        self.control_bar.sig_calibrate_requested.connect(self._on_calibrate_requested)
        self.control_bar.sig_reset_requested.connect(self._on_reset_requested)
        v_layout.addWidget(self.control_bar)

        # 4. Jadoo Voice Subsystem Card
        self.voice_widget = VoiceControlWidget()
        self.voice_widget.sig_toggle_dictation.connect(self._on_toggle_dictation)
        self.voice_widget.sig_insert_text.connect(self._on_insert_dictation_text)
        self.voice_widget.sig_language_changed.connect(self._on_voice_lang_changed)
        self.voice_widget.set_language(getattr(self.settings.voice, "language", "en"))
        v_layout.addWidget(self.voice_widget)

        # 5. Jadoo AI Assistant Widget
        self.jadoo_widget = JadooAssistantWidget(self.settings, self)
        self.jadoo_widget.sig_ask_query.connect(self._on_jadoo_ask)
        self.jadoo_widget.sig_insert_response.connect(self._on_jadoo_insert_text)
        v_layout.addWidget(self.jadoo_widget)

        # 6. Jadoo AI Cursor Control Card (HeadMouseAI)
        self.ai_cursor_widget = AICursorWidget(self.settings, self)
        self.ai_cursor_widget.sig_cursor_on.connect(self._on_ai_cursor_on)
        self.ai_cursor_widget.sig_cursor_off.connect(self._on_ai_cursor_off)
        self.ai_cursor_widget.sig_cursor_pause.connect(self._on_ai_cursor_pause)
        self.ai_cursor_widget.sig_cursor_resume.connect(self._on_ai_cursor_resume)
        self.ai_cursor_widget.sig_calibrate.connect(self._on_calibrate_requested)
        self.ai_cursor_widget.sig_recenter.connect(lambda: self._on_reset_requested(confirm=False))
        self.ai_cursor_widget.sig_open_settings.connect(lambda: self.tabs.setCurrentIndex(2))
        self.ai_cursor_widget.sig_sensitivity_changed.connect(self._on_cursor_sensitivity_changed)
        self.ai_cursor_widget.sig_smoothing_changed.connect(self._on_cursor_smoothing_changed)
        v_layout.addWidget(self.ai_cursor_widget)

        # 7. Autonomous AI Computer Task Agent Widget
        self.task_agent_widget = TaskAgentWidget(None, self)
        v_layout.addWidget(self.task_agent_widget)

        # 8. Expandable Advanced Details Section
        exp_header = QHBoxLayout()
        self.btn_toggle_diagnostics = QPushButton("▼ Show Advanced Details")
        self.btn_toggle_diagnostics.setFixedHeight(28)
        self.btn_toggle_diagnostics.setStyleSheet(
            "QPushButton { background-color: #202226; color: #A1A1AA; border: 1px solid #2E323A; "
            "border-radius: 6px; font-size: 11px; font-weight: 600; padding: 2px 14px; }"
            "QPushButton:hover { background-color: #292C32; color: #F5F5F5; border-color: #3F434C; }"
        )
        self.btn_toggle_diagnostics.clicked.connect(self._toggle_advanced_details)
        exp_header.addWidget(self.btn_toggle_diagnostics)
        exp_header.addStretch(1)
        v_layout.addLayout(exp_header)

        # Diagnostics Container (collapsed by default)
        self.diagnostics_container = QFrame()
        self.diagnostics_container.setStyleSheet(
            "QFrame { background-color: #181A1F; border: 1px solid #2E323A; border-radius: 8px; padding: 8px; }"
        )
        diag_grid = QGridLayout(self.diagnostics_container)
        diag_grid.setContentsMargins(10, 8, 10, 8)
        diag_grid.setHorizontalSpacing(16)
        diag_grid.setVerticalSpacing(6)

        diag_grid.addWidget(self._make_diag_lbl("Pipeline FPS:"), 0, 0)
        self.lbl_dash_fps = QLabel("0.0 FPS")
        self.lbl_dash_fps.setStyleSheet("font-weight: 600; color: #60A5FA; font-family: 'Consolas', 'Cascadia Code', monospace;")
        diag_grid.addWidget(self.lbl_dash_fps, 0, 1)

        diag_grid.addWidget(self._make_diag_lbl("Inference Latency:"), 0, 2)
        self.lbl_dash_inf = QLabel("0.0 ms")
        self.lbl_dash_inf.setStyleSheet("font-weight: 600; color: #34D399; font-family: 'Consolas', 'Cascadia Code', monospace;")
        diag_grid.addWidget(self.lbl_dash_inf, 0, 3)

        diag_grid.addWidget(self._make_diag_lbl("Left Eye EAR:"), 1, 0)
        self.lbl_dash_lear = QLabel("0.00 [OPEN]")
        self.lbl_dash_lear.setStyleSheet("color: #E4E4E7; font-family: 'Consolas', 'Cascadia Code', monospace; font-weight: 600;")
        diag_grid.addWidget(self.lbl_dash_lear, 1, 1)

        diag_grid.addWidget(self._make_diag_lbl("Right Eye EAR:"), 1, 2)
        self.lbl_dash_rear = QLabel("0.00 [OPEN]")
        self.lbl_dash_rear.setStyleSheet("color: #E4E4E7; font-family: 'Consolas', 'Cascadia Code', monospace; font-weight: 600;")
        diag_grid.addWidget(self.lbl_dash_rear, 1, 3)

        diag_grid.addWidget(self._make_diag_lbl("System Load:"), 2, 0)
        self.lbl_dash_sys = QLabel("CPU: 0% | RAM: 0 MB")
        self.lbl_dash_sys.setStyleSheet("color: #A1A1AA; font-family: 'Consolas', 'Cascadia Code', monospace; font-weight: 500;")
        diag_grid.addWidget(self.lbl_dash_sys, 2, 1)

        diag_grid.addWidget(self._make_diag_lbl("Active Mode:"), 2, 2)
        self.lbl_dash_mode = QLabel("NORMAL")
        self.lbl_dash_mode.setStyleSheet("font-weight: 600; color: #F5F5F5;")
        diag_grid.addWidget(self.lbl_dash_mode, 2, 3)

        self.diagnostics_container.setVisible(False)
        v_layout.addWidget(self.diagnostics_container)

        # Wrap in clean, seamless scroll area so content adjusts cleanly at all sizes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll.setWidget(container)

        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)
        return tab

    def _create_live_tracking_tab(self) -> QWidget:
        """Create dedicated Live Tracking tab with full-width diagnostic cards."""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        # Full detailed telemetry sidebar
        self.telemetry_widget = TelemetryCardsWidget()
        self.telemetry_widget.setMinimumWidth(420)
        layout.addWidget(self.telemetry_widget, 0)

        # Informational companion panel explaining live metrics
        info_panel = QFrame()
        info_panel.setStyleSheet(
            "QFrame { background-color: #202226; border: 1px solid #2E323A; border-radius: 8px; padding: 16px; }"
        )
        iv = QVBoxLayout(info_panel)
        iv.setSpacing(12)

        lbl_t_title = QLabel("Live Diagnostic Monitoring")
        lbl_t_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #F5F5F5;")
        iv.addWidget(lbl_t_title)

        lbl_desc = QLabel(
            "This tab provides comprehensive, real-time diagnostic signals for tracking performance:<br><br>"
            "• <b style='color: #F5F5F5;'>Head Tracking</b>: Shows raw and smoothed displacement deltas from your neutral head center.<br>"
            "• <b style='color: #F5F5F5;'>Eye Wink States</b>: Displays real-time Eye Aspect Ratios (EAR) and classified click events.<br>"
            "• <b style='color: #F5F5F5;'>Facial Geometry</b>: Displays normalized mouth width and eyebrow elevation ratios.<br>"
            "• <b style='color: #F5F5F5;'>Performance</b>: Real-time FPS, MediaPipe inference time in milliseconds, and memory usage.<br><br>"
            "All data on this screen updates at the configured refresh rate with zero jitter or UI layout shifts."
        )
        lbl_desc.setTextFormat(Qt.TextFormat.RichText)
        lbl_desc.setStyleSheet("color: #A1A1AA; font-size: 13px; line-height: 1.6;")
        lbl_desc.setWordWrap(True)
        iv.addWidget(lbl_desc)
        iv.addStretch(1)

        layout.addWidget(info_panel, 1)
        return tab

    def _make_diag_lbl(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #A1A1AA; font-size: 11px; font-weight: 600;")
        return lbl

    def _toggle_advanced_details(self) -> None:
        """Toggle visibility of the Advanced Details section on the dashboard."""
        self._diagnostics_visible = not self._diagnostics_visible
        self.diagnostics_container.setVisible(self._diagnostics_visible)
        if self._diagnostics_visible:
            self.btn_toggle_diagnostics.setText("▲ Hide Advanced Details")
        else:
            self.btn_toggle_diagnostics.setText("▼ Show Advanced Details")

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab change cleanly with zero visual artifacts or widget stacking."""
        pass

    def _show_first_launch_welcome(self) -> None:
        """Display first-launch welcome modal if not previously dismissed."""
        from gui.dialogs.welcome_dialog import WelcomeDialog

        dlg = WelcomeDialog(self.settings, self)
        dlg.sig_start_calibration.connect(self._on_calibrate_requested)
        dlg.exec()

    def _create_help_tab(self) -> QWidget:
        """Create clean structured SaaS interaction reference guide."""
        tab = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        title = QLabel("HeadMouseAI Hands-Free Gesture Guide")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #F5F5F5;")
        layout.addWidget(title)

        body = QLabel(
            "<table width='100%' cellpadding='10' style='border-collapse: separate; border-spacing: 12px;'>"
            "<tr>"
            "<td style='background-color: #202226; border: 1px solid #2E323A; border-radius: 8px; padding: 14px; vertical-align: top; width: 50%;'>"
            "<h4 style='color: #60A5FA; margin-top: 0; font-size: 14px;'>Cursor Navigation</h4>"
            "<p style='color: #A1A1AA; line-height: 1.5; font-size: 12px;'>"
            "• <b style='color: #F5F5F5;'>Head Movement</b>: Move your nose tip smoothly. The mouse cursor tracks your motion smoothly with dead zone filtering.<br>"
            "• <b style='color: #F5F5F5;'>Resting Dead Zone</b>: Natural head micro-tremors within the neutral zone are filtered to prevent pointer drift.<br>"
            "• <b style='color: #F5F5F5;'>Click Stabilization</b>: Pointer freezes automatically during a wink click to ensure pinpoint accuracy."
            "</p>"
            "</td>"
            "<td style='background-color: #202226; border: 1px solid #2E323A; border-radius: 8px; padding: 14px; vertical-align: top; width: 50%;'>"
            "<h4 style='color: #34D399; margin-top: 0; font-size: 14px;'>Left & Right Clicking</h4>"
            "<p style='color: #A1A1AA; line-height: 1.5; font-size: 12px;'>"
            "• <b style='color: #F5F5F5;'>Left Click</b>: Quick left-eye wink (40ms – 650ms). Triggers exactly one left click.<br>"
            "• <b style='color: #F5F5F5;'>Right Click</b>: Quick right-eye wink (40ms – 650ms). Triggers exactly one right click.<br>"
            "• <b style='color: #F5F5F5;'>Blink Filtering</b>: Blinking both eyes together naturally never triggers accidental clicks."
            "</p>"
            "</td>"
            "</tr>"
            "<tr>"
            "<td style='background-color: #202226; border: 1px solid #2E323A; border-radius: 8px; padding: 14px; vertical-align: top;'>"
            "<h4 style='color: #FBBF24; margin-top: 0; font-size: 14px;'>Hands-Free Drag & Drop</h4>"
            "<p style='color: #A1A1AA; line-height: 1.5; font-size: 12px;'>"
            "• <b style='color: #F5F5F5;'>Hold to Grab</b>: Close and hold your left eye for >0.38s. Mouse button engages.<br>"
            "• <b style='color: #F5F5F5;'>Move to Drag</b>: Move your head to drag items, highlight text, or resize windows.<br>"
            "• <b style='color: #F5F5F5;'>Release to Drop</b>: Wink your left eye again to release the mouse button."
            "</p>"
            "</td>"
            "<td style='background-color: #202226; border: 1px solid #2E323A; border-radius: 8px; padding: 14px; vertical-align: top;'>"
            "<h4 style='color: #818CF8; margin-top: 0; font-size: 14px;'>Hands-Free Scroll & Zoom</h4>"
            "<p style='color: #A1A1AA; line-height: 1.5; font-size: 12px;'>"
            "• <b style='color: #F5F5F5;'>Scroll Mode</b>: Smile or show teeth. Tilt head UP to scroll up, DOWN to scroll down.<br>"
            "• <b style='color: #F5F5F5;'>Zoom Mode</b>: Smile + RAISE BOTH EYEBROWS. Tilt head UP to zoom in, DOWN to zoom out.<br>"
            "• <b style='color: #F5F5F5;'>Exit Mode</b>: Simply close your mouth to immediately return to normal cursor movement."
            "</p>"
            "</td>"
            "</tr>"
            "</table>"
            "<br>"
            "<div style='background-color: #202226; border: 1px solid #2E323A; border-radius: 8px; padding: 16px;'>"
            "<h4 style='color: #F87171; margin-top: 0; font-size: 14px;'>Keyboard Shortcuts & Emergency Failsafes</h4>"
            "<table width='100%' style='color: #A1A1AA; font-size: 12px; line-height: 1.7;'>"
            "<tr><td style='color: #F5F5F5; font-family: Consolas, monospace; width: 140px;'><b>[F8] or [M]</b></td><td>Toggle Real Mouse Control ON/OFF (Disabled by default for safety).</td></tr>"
            "<tr><td style='color: #FCA5A5; font-family: Consolas, monospace;'><b>[F9] or [E]</b></td><td><b style='color: #F87171;'>EMERGENCY STOP</b>: Instantly halts cursor, releases all held buttons, and disables mouse actuation.</td></tr>"
            "<tr><td style='color: #F5F5F5; font-family: Consolas, monospace;'><b>[C]</b></td><td>Launch Calibration Wizard to calibrate head posture and eye controls.</td></tr>"
            "<tr><td style='color: #F5F5F5; font-family: Consolas, monospace;'><b>[R]</b></td><td>Reset internal trackers and state machines to defaults.</td></tr>"
            "<tr><td style='color: #F5F5F5; font-family: Consolas, monospace;'><b>[Escape]</b></td><td>Safely exit the HeadMouseAI application.</td></tr>"
            "<tr><td style='color: #F5F5F5; font-family: Consolas, monospace;'><b>[Ctrl+Space]</b></td><td>Focus Jadoo AI Assistant input for conversational queries or Hinglish rewrite.</td></tr>"
            "<tr><td style='color: #F5F5F5; font-family: Consolas, monospace;'><b>[Ctrl+Shift+D]</b></td><td>Toggle Hands-Free Dictation Mode ON/OFF.</td></tr>"
            "<tr><td style='color: #6EE7B7; font-family: Consolas, monospace;'><b>'Hey Jadoo'</b></td><td>Hands-free voice wake word to activate Jadoo AI Assistant from speech.</td></tr>"
            "<tr><td style='color: #A7B0BC; font-family: Consolas, monospace;'><b>Corner Failsafe</b></td><td>Moving the physical mouse cursor to any screen corner immediately disengages automation.</td></tr>"
            "</table>"
            "</div>"
        )
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setWordWrap(True)
        layout.addWidget(body)
        layout.addStretch(1)

        scroll.setWidget(container)
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)
        return tab

    def _init_worker(self) -> None:
        """Create and connect the VisionWorker and VoiceWorker threads."""
        self.worker = VisionWorker(self.settings, self)
        self.worker.sig_frame_ready.connect(self.video_widget.update_frame)
        self.worker.sig_telemetry.connect(self._on_telemetry_received)
        self.worker.sig_mouse_state_changed.connect(self._on_mouse_state_changed)
        self.worker.sig_calibration_progress.connect(self._on_calibration_progress)
        self.worker.sig_calibration_complete.connect(self._on_calibration_complete)
        self.worker.sig_status_message.connect(self._on_status_message)
        self.worker.sig_alert.connect(self._on_alert_received)

        # Initialize Jadoo VoiceWorker thread
        self.voice_worker = VoiceWorker(self.settings, self)
        self.text_injector = TextInjector(restore_clipboard=self.settings.voice.restore_clipboard)
        self.voice_worker.sig_status.connect(self._on_voice_status_changed)
        self.voice_worker.sig_audio_level.connect(self.voice_widget.update_audio_level)
        self.voice_worker.sig_transcription.connect(self._on_voice_transcription)
        self.voice_worker.sig_command.connect(self._on_voice_command)
        self.voice_worker.sig_error.connect(self._on_voice_error)
        self.voice_worker.sig_dictation_state.connect(self.voice_widget.set_dictating_state)
        self.voice_worker.sig_wake_word.connect(self._on_wake_word_detected)
        self.voice_worker.sig_engine_used.connect(self.voice_widget.set_engine)

        # Initialize dashboard engine badge to reflect configured provider & key state
        stt_mode = getattr(self.settings.jadoo, "stt_mode", "cloud_first") if hasattr(self.settings, "jadoo") else "cloud_first"
        if stt_mode == "offline":
            self.voice_widget.set_engine("LOCAL WHISPER")
        elif not self.voice_worker.whisper.groq_client.is_configured:
            self.voice_widget.set_engine("API KEY MISSING")
        else:
            self.voice_widget.set_engine("LOCAL WHISPER")

        if getattr(self.settings.voice, "enabled", True):
            self.voice_worker.start()

        # Initialize Jadoo AI Assistant worker
        self.jadoo_worker = JadooWorker(self.settings, self)
        self.jadoo_worker.sig_jadoo_status.connect(self._on_jadoo_status_changed)
        if self.jadoo_widget:
            self.jadoo_worker.sig_jadoo_response.connect(self.jadoo_widget.set_response)
            self.jadoo_worker.sig_jadoo_error.connect(self.jadoo_widget.set_error)
        self.jadoo_worker.sig_speaking_state.connect(self._on_jadoo_speaking_state)
        self.jadoo_worker.start()

        # Initialize Always-On-Top Floating Accessibility Control Panel
        self.floating_panel = FloatingControlPanel(self.settings, None)
        self.voice_worker.sig_dictation_state.connect(self.floating_panel.update_dictation_state)
        self.voice_worker.sig_mode_changed.connect(self.floating_panel.update_mode_badge)

        self.floating_panel.sig_command_requested.connect(self._on_voice_command)
        self.floating_panel.sig_toggle_dictation.connect(self._on_panel_toggle_dictation)
        self.floating_panel.sig_toggle_listening.connect(self._on_panel_toggle_listening)
        self.floating_panel.sig_toggle_mouse.connect(self._on_toggle_real_mouse)
        self.floating_panel.sig_scroll.connect(self._on_panel_scroll)
        self.floating_panel.sig_stop_all.connect(self._on_emergency_stop)
        self.floating_panel.sig_open_assistant.connect(self._on_ctrl_space_pressed)

        # Wire Floating Panel Phase 4 AI Cursor signals
        self.floating_panel.sig_cursor_on.connect(self._on_ai_cursor_on)
        self.floating_panel.sig_cursor_off.connect(self._on_ai_cursor_off)
        self.floating_panel.sig_cursor_pause.connect(self._on_ai_cursor_pause)
        self.floating_panel.sig_cursor_resume.connect(self._on_ai_cursor_resume)
        self.floating_panel.sig_calibrate_cursor.connect(self._on_calibrate_requested)
        self.floating_panel.sig_recenter_cursor.connect(lambda: self._on_reset_requested(confirm=False))

        # Initialize TaskManager (Phase 5 Autonomous Task Agent)
        gemini_client = getattr(self.jadoo_worker, "gemini", None) if hasattr(self, "jadoo_worker") and self.jadoo_worker else None
        self.task_manager = TaskManager(
            gemini_client=gemini_client,
            vision_worker=self.worker,
            keyboard_controller=self.keyboard_controller,
            parent=self,
        )
        if self.task_agent_widget:
            self.task_agent_widget.task_manager = self.task_manager
            self.task_agent_widget._connect_manager()

        # Connect Task Agent signals to UI updates
        self.task_manager.sig_status_changed.connect(self._on_task_status_changed)
        self.task_manager.sig_task_completed.connect(self._on_task_completed)

        # Wire Floating Panel Phase 5 Task Agent signals
        self.floating_panel.sig_submit_task.connect(self._on_submit_task)
        self.floating_panel.sig_stop_task.connect(self._on_stop_task)

        if hasattr(self, "settings_tab") and self.settings_tab:
            self.settings_tab.sig_show_floating_panel.connect(self._toggle_floating_panel_visibility)
            self.settings_tab.sig_floating_panel_toggled.connect(self._on_settings_panel_toggled)

        if getattr(self.settings.accessibility, "auto_show_panel", True):
            self.floating_panel.show()

    def _init_hotkeys(self) -> None:
        """Initialize unified window shortcuts and background hardware polling."""
        # 1. Window-level shortcuts (reliable regardless of which child widget has focus)
        self.shortcut_f8 = QShortcut(QKeySequence(Qt.Key.Key_F8), self)
        self.shortcut_f8.setContext(Qt.ShortcutContext.WindowShortcut)
        self.shortcut_f8.activated.connect(self._on_toggle_real_mouse)

        self.shortcut_m = QShortcut(QKeySequence(Qt.Key.Key_M), self)
        self.shortcut_m.setContext(Qt.ShortcutContext.WindowShortcut)
        self.shortcut_m.activated.connect(self._on_toggle_real_mouse)

        self.shortcut_f9 = QShortcut(QKeySequence(Qt.Key.Key_F9), self)
        self.shortcut_f9.setContext(Qt.ShortcutContext.WindowShortcut)
        self.shortcut_f9.activated.connect(self._on_emergency_stop)

        self.shortcut_e = QShortcut(QKeySequence(Qt.Key.Key_E), self)
        self.shortcut_e.setContext(Qt.ShortcutContext.WindowShortcut)
        self.shortcut_e.activated.connect(self._on_emergency_stop)

        self.shortcut_c = QShortcut(QKeySequence(Qt.Key.Key_C), self)
        self.shortcut_c.setContext(Qt.ShortcutContext.WindowShortcut)
        self.shortcut_c.activated.connect(self._on_calibrate_requested)

        self.shortcut_r = QShortcut(QKeySequence(Qt.Key.Key_R), self)
        self.shortcut_r.setContext(Qt.ShortcutContext.WindowShortcut)
        self.shortcut_r.activated.connect(self._on_reset_requested)

        # Dictation shortcut: Ctrl+Shift+D
        self.shortcut_dictation = QShortcut(QKeySequence("Ctrl+Shift+D"), self)
        self.shortcut_dictation.setContext(Qt.ShortcutContext.WindowShortcut)
        self.shortcut_dictation.activated.connect(self._on_toggle_dictation)

        # Jadoo Assistant shortcut: Ctrl+Space
        self.shortcut_ctrl_space = QShortcut(QKeySequence("Ctrl+Space"), self)
        self.shortcut_ctrl_space.setContext(Qt.ShortcutContext.WindowShortcut)
        self.shortcut_ctrl_space.activated.connect(self._on_ctrl_space_pressed)

        self.shortcut_esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.shortcut_esc.setContext(Qt.ShortcutContext.WindowShortcut)
        self.shortcut_esc.activated.connect(self.close)

        # 2. Global hardware hotkey polling (user32 GetAsyncKeyState for background actuation)
        self.hotkey_timer = QTimer(self)
        self.hotkey_timer.timeout.connect(self._poll_global_hotkeys)
        self.hotkey_timer.start(16)  # ~60 Hz

    def _poll_global_hotkeys(self) -> None:
        """Poll physical F8 / F9 keys globally so shortcuts work even when window is not focused."""
        # When window is focused, QShortcut handles the event cleanly inside Qt.
        # Global polling handles background actuation when window is unfocused.
        if self.isActiveWindow():
            self._prev_f8 = is_windows_key_pressed(VK_F8)
            self._prev_f9 = is_windows_key_pressed(VK_F9)
            return

        f8_down = is_windows_key_pressed(VK_F8)
        if f8_down and not self._prev_f8:
            logger.info("Global Hotkey F8 triggered (unfocused).")
            self._on_toggle_real_mouse()
        self._prev_f8 = f8_down

        f9_down = is_windows_key_pressed(VK_F9)
        if f9_down and not self._prev_f9:
            logger.warning("Global Hotkey F9 Emergency Stop triggered (unfocused).")
            self._on_emergency_stop()
        self._prev_f9 = f9_down

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle active window shortcut keys with auto-repeat suppression."""
        if event.isAutoRepeat():
            event.accept()
            return
        k = event.key()
        if k in (Qt.Key.Key_F8, Qt.Key.Key_M):
            self._on_toggle_real_mouse()
        elif k in (Qt.Key.Key_F9, Qt.Key.Key_E):
            self._on_emergency_stop()
        elif k == Qt.Key.Key_C:
            self._on_calibrate_requested()
        elif k == Qt.Key.Key_R:
            self._on_reset_requested()
        elif k == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    @Slot()
    def _on_start_tracking(self) -> None:
        if self.worker and not self.worker.isRunning():
            self.worker.start()
            self.control_bar.set_tracking_state(True)
            self.hdr_badge_tracking.set_state("ACTIVE", "TRACKING")
            self.card_cam.set_status("Connected", "OK")
            self.card_face.set_status("Searching...", "WARNING")
            self.lbl_status.setText("Tracking Active | Calibrating Neutral Center...")
            logger.info("Tracking started from GUI.")

    @Slot()
    def _on_stop_tracking(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.stop_tracking()
            self.video_widget.clear_frame()
            self.control_bar.set_tracking_state(False)
            self.hdr_badge_camera.set_state("NORMAL", "OFFLINE")
            self.hdr_badge_tracking.set_state("NORMAL", "STOPPED")
            self.hdr_badge_mouse.set_state("DISABLED", "MOUSE OFF")
            self.card_cam.set_status("Offline", "OFFLINE")
            self.card_face.set_status("Offline", "OFFLINE")
            self.card_mouse.set_status("Disabled [F8]", "NORMAL")
            self.lbl_status.setText("Tracking Stopped | Real Mouse: DISABLED")
            logger.info("Tracking stopped from GUI.")

    @Slot()
    def _on_toggle_real_mouse(self) -> None:
        """Debounced real mouse toggle handler."""
        now_mono = time.monotonic()
        if now_mono - self._last_f8_trigger_time < 0.35:
            return
        self._last_f8_trigger_time = now_mono

        if self.worker:
            self.worker.toggle_real_mouse()

    @Slot()
    def _on_emergency_stop(self) -> None:
        """Debounced emergency stop handler."""
        now_mono = time.monotonic()
        if now_mono - self._last_f9_trigger_time < 0.35:
            return
        self._last_f9_trigger_time = now_mono

        if self.worker:
            self.worker.trigger_emergency_stop()
        if self.jadoo_worker:
            self.jadoo_worker.abort()
        if hasattr(self, "task_manager") and self.task_manager:
            self.task_manager.stop_task()
        if self.voice_worker and self.voice_worker.is_dictating:
            self.voice_worker.set_dictating(False)
        if hasattr(self, "floating_panel") and self.floating_panel:
            self.floating_panel.update_mode_badge("STOPPED")

    @Slot(bool, str)
    def _on_mouse_state_changed(self, enabled: bool, state_label: str) -> None:
        """Immediately update all UI indicators when mouse state changes."""
        self.control_bar.set_mouse_state(enabled, state_label)
        if hasattr(self, "floating_panel") and self.floating_panel:
            self.floating_panel.update_mouse_state(enabled, state_label)
        if hasattr(self, "ai_cursor_widget") and self.ai_cursor_widget:
            self.ai_cursor_widget.update_mouse_state(enabled, state_label)
        if state_label == "EMERGENCY_STOP":
            self.hdr_badge_mouse.set_state("EMERGENCY_STOP", "EMERGENCY")
            self.card_mouse.set_status("Emergency Stop", "ERROR")
            self.lbl_status.setText("EMERGENCY STOP ACTIVATED! (Press F8 to re-enable)")
        elif enabled:
            self.hdr_badge_mouse.set_state("ENABLED", "MOUSE ON")
            self.card_mouse.set_status("Active [F8]", "OK")
            self.lbl_status.setText("Real Mouse Control: ENABLED (Press F8 or M to disable)")
        else:
            self.hdr_badge_mouse.set_state("DISABLED", "MOUSE OFF")
            self.card_mouse.set_status("Disabled [F8]", "NORMAL")
            self.lbl_status.setText("Real Mouse Control: DISABLED (Press F8 or M to enable)")

    @Slot()
    def _on_calibrate_requested(self) -> None:
        if self.worker:
            self._calib_dialog = CalibrationWizard(worker=self.worker, parent=self)
            self._calib_dialog.exec()
            self._calib_dialog = None
            self.settings_tab.populate_from_settings(self.settings)

    @Slot()
    def _on_reset_requested(self, confirm: bool = True) -> None:
        if not self.worker:
            return
        if confirm:
            reply = QMessageBox.question(
                self,
                "Reset Tracking Confirmation",
                "Are you sure you want to reset all tracking baselines, smoothers, and gesture state machines to their defaults?\n\nThis will clear current cursor calibration.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.worker.nose_tracker.reset()
        if hasattr(self.worker.cursor, "recalibrate"):
            self.worker.cursor.recalibrate()
        elif hasattr(self.worker.cursor, "reset"):
            self.worker.cursor.reset()
        self.worker.blink_detector.reset()
        self.worker.gesture_zoom.reset()
        self.lbl_status.setText("Trackers Reset to Defaults.")
        logger.info("Trackers reset confirmed and executed from GUI.")

    @Slot(dict)
    def _on_telemetry_received(self, t: dict) -> None:
        self.video_widget.update_telemetry(t)
        self.telemetry_widget.update_telemetry(t)
        if hasattr(self, "ai_cursor_widget") and self.ai_cursor_widget:
            self.ai_cursor_widget.update_telemetry(t)

        # Header status pills
        has_face = bool(t.get("has_face", False))
        self.hdr_badge_camera.set_state("OK" if has_face else "NORMAL", "CAMERA ON" if has_face else "NO FACE")
        self.hdr_badge_tracking.set_state("ACTIVE", "TRACKING")

        # 4 Dashboard Status Cards
        self.card_cam.set_status("Connected", "OK")
        if has_face:
            self.card_face.set_status("Detected (Locked)", "OK")
        else:
            self.card_face.set_status("Searching...", "WARNING")

        if t.get("is_calibrated", False):
            self.card_calib.set_status("Complete", "OK")
        else:
            self.card_calib.set_status("Pending", "WARNING")

        if t.get("emergency_stopped", False):
            self.hdr_badge_mouse.set_state("EMERGENCY_STOP", "STOPPED")
            self.card_mouse.set_status("Emergency Stop", "ERROR")
        elif t.get("real_mouse_enabled", False):
            self.hdr_badge_mouse.set_state("ENABLED", "MOUSE ON")
            self.card_mouse.set_status("Active [F8]", "OK")
        else:
            self.hdr_badge_mouse.set_state("DISABLED", "MOUSE OFF")
            self.card_mouse.set_status("Disabled [F8]", "NORMAL")

        # Expandable diagnostics updates
        fps = t.get("fps", 0.0)
        lat = t.get("latency_ms", 0.0)
        inf = t.get("inference_ms", 0.0)
        self.lbl_dash_fps.setText(f"{fps:.1f} FPS ({lat:.0f} ms latency)")
        self.lbl_dash_inf.setText(f"{inf:.1f} ms")

        l_ear = t.get("left_ear", 0.0)
        r_ear = t.get("right_ear", 0.0)
        l_st = t.get("left_eye_state", "OPEN")
        r_st = t.get("right_eye_state", "OPEN")
        self.lbl_dash_lear.setText(f"{l_ear:.2f} [{l_st}]")
        self.lbl_dash_rear.setText(f"{r_ear:.2f} [{r_st}]")

        cpu = t.get("cpu_percent", 0.0)
        ram = t.get("ram_mb", 0.0)
        self.lbl_dash_sys.setText(f"CPU: {cpu:.1f}% | RAM: {ram:.0f} MB")
        self.lbl_dash_mode.setText(t.get("mode", "NORMAL"))

    @Slot(float)
    def _on_calibration_progress(self, ratio: float) -> None:
        if self._calib_dialog and hasattr(self._calib_dialog, "update_progress"):
            self._calib_dialog.update_progress(ratio)

    @Slot()
    def _on_calibration_complete(self) -> None:
        if self._calib_dialog:
            self._calib_dialog.accept()
        self.lbl_status.setText("Calibration Complete | Ready (Press F8 to Enable Real Mouse)")
        self.card_calib.set_status("Complete", "OK")

    @Slot(str, str)
    def _on_status_message(self, level: str, msg: str) -> None:
        self.lbl_status.setText(f"[{level}] {msg}")

    @Slot(str, str)
    def _on_alert_received(self, title: str, body: str) -> None:
        QMessageBox.warning(self, title, body)

    @Slot(dict)
    def _on_settings_changed(self, diff: dict) -> None:
        if self.worker:
            self.worker.update_dynamic_settings(diff)

    @Slot(int)
    def _on_camera_changed(self, idx: int) -> None:
        if self.worker:
            self.worker.request_camera_switch(idx)

    @Slot(bool)
    def _on_toggle_mesh(self, show: bool) -> None:
        if self.worker:
            self.worker.set_show_mesh(show)

    @Slot(bool)
    def _on_toggle_cursor(self, show: bool) -> None:
        if self.worker:
            self.worker.set_show_cursor(show)

    # ---------------- Voice Engine Handlers ---------------- #
    @Slot()
    def _on_toggle_dictation(self) -> None:
        """Toggle dictation on/off."""
        if self.voice_worker:
            self.voice_worker.toggle_dictation()

    @Slot(str)
    def _on_insert_dictation_text(self, text: str) -> None:
        """Inject dictation text into active target window."""
        if self.text_injector and text:
            ok = self.text_injector.inject_text(text)
            if ok:
                self.lbl_status.setText(f"Inserted dictation ({len(text)} chars) at cursor.")

    @Slot(str)
    def _on_voice_status_changed(self, status: str) -> None:
        """Update UI badges with voice engine status."""
        self.voice_widget.set_status(status)
        st_u = status.upper()
        if "DICTAT" in st_u:
            self.hdr_badge_voice.set_state("ACTIVE", "DICTATING")
        elif "TRANSCRIB" in st_u:
            self.hdr_badge_voice.set_state("WARNING", "TRANSCRIBING")
        elif "LISTEN" in st_u or "READY" in st_u:
            self.hdr_badge_voice.set_state("OK", "VOICE ON")
        elif "MIC" in st_u or "ERR" in st_u:
            self.hdr_badge_voice.set_state("ERROR", "MIC ERR")
        else:
            self.hdr_badge_voice.set_state("NORMAL", "VOICE IDLE")

    @Slot(str, str)
    def _on_voice_transcription(self, text: str, lang: str) -> None:
        """Handle new transcribed speech chunk."""
        self.voice_widget.append_text(text)
        self.lbl_status.setText(f"Dictation [{lang}]: {text[:40]}...")

    @Slot(str)
    def _on_voice_command(self, cmd_name: str) -> None:
        """Dispatch verified voice command from strict allowlist."""
        logger.info(f"MainWindow executing voice command: '{cmd_name}'")
        self.lbl_status.setText(f"Voice Command Executed: [{cmd_name.upper()}]")

        norm_name = cmd_name.strip().lower()
        acc_cmd: Optional[AccessibilityCommand] = None
        try:
            acc_cmd = AccessibilityCommand(norm_name)
        except ValueError:
            pass

        # 1. Text & Keyboard editing actions
        if acc_cmd in (
            AccessibilityCommand.BACKSPACE,
            AccessibilityCommand.DELETE_WORD,
            AccessibilityCommand.CLEAR_FIELD,
            AccessibilityCommand.SELECT_ALL,
            AccessibilityCommand.COPY,
            AccessibilityCommand.PASTE,
            AccessibilityCommand.ENTER,
            AccessibilityCommand.NEW_LINE,
            AccessibilityCommand.TAB,
            AccessibilityCommand.UNDO,
            AccessibilityCommand.REDO,
        ):
            self.keyboard_controller.execute_command(acc_cmd)
            self._speak_feedback(acc_cmd.value.replace("_", " "))

        # 2. Mouse & Navigation actions
        elif acc_cmd == AccessibilityCommand.MOUSE_ON or norm_name in ("mouse_on", "enable_mouse"):
            if self.worker:
                self.worker.set_real_mouse_enabled(True)
            self._speak_feedback("Mouse on")

        elif acc_cmd == AccessibilityCommand.MOUSE_OFF or norm_name in ("mouse_off", "disable_mouse"):
            if self.worker:
                self.worker.set_real_mouse_enabled(False)
            self._speak_feedback("Mouse off")

        elif acc_cmd == AccessibilityCommand.PAUSE_CURSOR or norm_name == "pause_cursor":
            if self.worker:
                self.worker.pause_cursor()
            self._speak_feedback("Cursor paused")

        elif acc_cmd == AccessibilityCommand.RESUME_CURSOR or norm_name == "resume_cursor":
            if self.worker:
                self.worker.resume_cursor()
            self._speak_feedback("Cursor resumed")

        elif acc_cmd == AccessibilityCommand.CALIBRATE_CURSOR or norm_name in ("calibrate_cursor", "calibrate"):
            self._on_calibrate_requested()
            self._speak_feedback("Calibrating")

        elif acc_cmd == AccessibilityCommand.SCROLL_UP or norm_name == "scroll_up":
            if self.worker and self.worker.mouse_controller:
                self.worker.mouse_controller.scroll(120)

        elif acc_cmd == AccessibilityCommand.SCROLL_DOWN or norm_name == "scroll_down":
            if self.worker and self.worker.mouse_controller:
                self.worker.mouse_controller.scroll(-120)

        elif acc_cmd == AccessibilityCommand.RECENTER or norm_name in ("recenter", "center"):
            self._on_reset_requested(confirm=False)
            self._speak_feedback("Recentered")

        # 3. Dictation controls
        elif acc_cmd == AccessibilityCommand.TYPING_ON or norm_name in ("start_dictation", "typing_on"):
            if self.voice_worker:
                self.voice_worker.set_dictating(True)
            self._speak_feedback("Typing on")

        elif acc_cmd == AccessibilityCommand.TYPING_OFF or norm_name in ("stop_dictation", "typing_off"):
            if self.voice_worker:
                self.voice_worker.set_dictating(False)
            self._speak_feedback("Typing off")

        # 4. Safety & Stops
        elif acc_cmd in (AccessibilityCommand.EMERGENCY_STOP, AccessibilityCommand.STOP_ALL) or norm_name in ("emergency_stop", "stop_all"):
            self._on_emergency_stop()
            self._speak_feedback("Emergency stop")

        elif norm_name == "stop":
            if self.worker and self.worker.isRunning():
                self._on_stop_tracking()
            self._speak_feedback("Stopped")

        # 5. Autonomous Task Agent Actions
        elif acc_cmd == AccessibilityCommand.START_TASK or norm_name in ("start_task", "run_task", "start_agent"):
            if hasattr(self, "task_manager") and self.task_manager:
                if self.task_manager.current_plan:
                    self.task_manager.start_task()
                    self._speak_feedback("Task started")
                elif self.task_agent_widget and self.task_agent_widget.inp_instruction.text().strip():
                    self.task_manager.submit_instruction(self.task_agent_widget.inp_instruction.text().strip())
                    self._speak_feedback("Task submitted")

        elif acc_cmd == AccessibilityCommand.PAUSE_TASK or norm_name in ("pause_task", "hold_task"):
            if hasattr(self, "task_manager") and self.task_manager:
                self.task_manager.pause_task()
                self._speak_feedback("Task paused")

        elif acc_cmd == AccessibilityCommand.RESUME_TASK or norm_name in ("resume_task", "continue_task"):
            if hasattr(self, "task_manager") and self.task_manager:
                self.task_manager.resume_task()
                self._speak_feedback("Task resumed")

        elif acc_cmd == AccessibilityCommand.STOP_TASK or norm_name in ("stop_task", "abort_task", "cancel_task"):
            if hasattr(self, "task_manager") and self.task_manager:
                self.task_manager.stop_task()
                self._speak_feedback("Task stopped")

    # ---------------- AI Cursor Handlers (Phase 4) ---------------- #
    @Slot()
    def _on_ai_cursor_on(self) -> None:
        """Start tracking and enable real mouse control."""
        if self.worker:
            if not self.worker.isRunning():
                self._on_start_tracking()
            self.worker.set_real_mouse_enabled(True)
            self.worker.resume_cursor()
        if self.ai_cursor_widget:
            self.ai_cursor_widget.update_cursor_status("ACTIVE")
        if self.floating_panel:
            self.floating_panel.update_ai_cursor_status("ACTIVE")
        self._speak_feedback("AI Cursor on")
        self.lbl_status.setText("AI Cursor: ENABLED")

    @Slot()
    def _on_ai_cursor_off(self) -> None:
        """Disable real mouse control while leaving tracking optionally active."""
        if self.worker:
            self.worker.set_real_mouse_enabled(False)
        if self.ai_cursor_widget:
            self.ai_cursor_widget.update_cursor_status("OFF")
        if self.floating_panel:
            self.floating_panel.update_ai_cursor_status("OFF")
        self._speak_feedback("AI Cursor off")
        self.lbl_status.setText("AI Cursor: DISABLED")

    @Slot()
    def _on_ai_cursor_pause(self) -> None:
        """Pause cursor movement."""
        if self.worker:
            self.worker.pause_cursor()
        if self.ai_cursor_widget:
            self.ai_cursor_widget.set_cursor_paused(True)
        if self.floating_panel:
            self.floating_panel.update_ai_cursor_status("PAUSED")
        self._speak_feedback("Cursor paused")
        self.lbl_status.setText("AI Cursor: PAUSED")

    @Slot()
    def _on_ai_cursor_resume(self) -> None:
        """Resume cursor movement."""
        if self.worker:
            self.worker.resume_cursor()
        if self.ai_cursor_widget:
            self.ai_cursor_widget.set_cursor_paused(False)
        if self.floating_panel:
            self.floating_panel.update_ai_cursor_status("ACTIVE" if self.worker and self.worker.mouse_controller.enabled else "OFF")
        self._speak_feedback("Cursor resumed")
        self.lbl_status.setText("AI Cursor: RESUMED")

    @Slot(float)
    def _on_cursor_sensitivity_changed(self, sens: float) -> None:
        if self.worker:
            self.worker.update_dynamic_settings({"sensitivity": sens})
        self.settings.save()

    @Slot(float)
    def _on_cursor_smoothing_changed(self, smooth: float) -> None:
        if self.worker:
            self.worker.update_dynamic_settings({"smoothing_strength": smooth})
        self.settings.save()

    # ---------------- Task Agent Handlers (Phase 5) ---------------- #
    @Slot(str)
    def _on_submit_task(self, instruction: str) -> None:
        """Submit a task to the Autonomous Task Agent."""
        if hasattr(self, "task_manager") and self.task_manager:
            self.task_manager.submit_instruction(instruction)
            self.lbl_status.setText(f"Task Agent: Planning '{instruction[:30]}...'")

    @Slot()
    def _on_stop_task(self) -> None:
        """Emergency stop the currently running task."""
        if hasattr(self, "task_manager") and self.task_manager:
            self.task_manager.stop_task()
            self.lbl_status.setText("Task Agent: Stopped by user.")

    def _on_task_status_changed(self, status: str) -> None:
        if self.floating_panel:
            self.floating_panel.update_task_status(status)
        self.lbl_status.setText(f"Task Agent: {status}")

    def _on_task_completed(self, report: dict) -> None:
        if self.floating_panel:
            self.floating_panel.update_task_status("COMPLETED")
        summary = report.get("summary", "Done") if isinstance(report, dict) else str(report)
        self.lbl_status.setText(f"Task Agent Completed: {summary[:50]}")
        self._speak_feedback("Task completed successfully")

    def _speak_feedback(self, text: str) -> None:
        """Speak brief TTS audio confirmation if enabled in accessibility settings."""
        if getattr(self.settings.accessibility, "tts_feedback", True):
            if self.jadoo_worker and hasattr(self.jadoo_worker, "tts"):
                try:
                    self.jadoo_worker.tts.speak_async(text)
                except Exception:
                    pass

    @Slot(bool)
    def _on_panel_toggle_dictation(self, active: bool) -> None:
        if self.voice_worker:
            self.voice_worker.set_dictating(active)

    @Slot(bool)
    def _on_panel_toggle_listening(self, active: bool) -> None:
        if self.voice_worker:
            self.voice_worker.set_paused(not active)
        if self.floating_panel:
            self.floating_panel.update_listening_state(active)

    @Slot(int)
    def _on_panel_scroll(self, amount: int) -> None:
        if self.worker and self.worker.mouse_controller:
            self.worker.mouse_controller.scroll(amount)

    @Slot()
    def _toggle_floating_panel_visibility(self) -> None:
        if self.floating_panel:
            if self.floating_panel.isVisible():
                self.floating_panel.hide()
            else:
                self.floating_panel.show()

    @Slot(bool)
    def _on_settings_panel_toggled(self, checked: bool) -> None:
        if self.floating_panel:
            if checked:
                self.floating_panel.show()
            else:
                self.floating_panel.hide()

    @Slot(str)
    def _on_voice_error(self, err_msg: str) -> None:
        """Handle voice error message."""
        logger.warning(f"Voice engine warning/error: {err_msg}")
        self.lbl_status.setText(f"Voice Subsystem: {err_msg}")

    @Slot(int)
    def _on_voice_mic_changed(self, dev_idx: int) -> None:
        if self.voice_worker:
            self.voice_worker.switch_device(dev_idx)

    @Slot(str)
    def _on_voice_model_changed(self, model_name: str) -> None:
        if self.voice_worker:
            self.voice_worker.switch_model(model_name)

    @Slot(str)
    def _on_voice_lang_changed(self, lang: str) -> None:
        if self.voice_worker:
            self.voice_worker.switch_language(lang)
        self.settings.voice.language = lang
        self.settings.save()
        if hasattr(self, "settings_tab") and self.settings_tab:
            self.settings_tab.set_voice_language(lang)
        if hasattr(self, "voice_widget") and self.voice_widget:
            self.voice_widget.set_language(lang)
        self.lbl_status.setText(f"Voice typing language set to: {lang.upper()}")

    @Slot(bool)
    def _on_voice_enabled_changed(self, enabled: bool) -> None:
        if self.voice_worker:
            self.voice_worker.set_paused(not enabled)

    @Slot(float)
    def _on_voice_threshold_changed(self, thresh: float) -> None:
        if self.voice_worker:
            self.voice_worker.set_vad_threshold(thresh)

    # ---------------- Jadoo Assistant Handlers ---------------- #
    @Slot()
    def _on_ctrl_space_pressed(self) -> None:
        """Focus Jadoo query input when [Ctrl+Space] is pressed."""
        self.tabs.setCurrentIndex(0)
        if self.jadoo_widget:
            self.jadoo_widget.focus_query_input()

    @Slot(str, bool, bool)
    def _on_jadoo_ask(self, query: str, include_screen: bool, is_rewrite: bool) -> None:
        """Forward query to background JadooWorker."""
        if self.jadoo_worker:
            self.jadoo_worker.ask(query, include_screen=include_screen, is_rewrite=is_rewrite)

    @Slot(str)
    def _on_jadoo_insert_text(self, text: str) -> None:
        """Inject Jadoo response into active external target window."""
        if self.text_injector and text:
            ok = self.text_injector.inject_text(text)
            if ok:
                self.lbl_status.setText(f"Inserted Jadoo response ({len(text)} chars) at cursor.")

    @Slot(str)
    def _on_wake_word_detected(self, query: str) -> None:
        """Respond to 'Hey Jadoo' wake word event."""
        logger.info(f"MainWindow received wake word event (query='{query}')")
        self.tabs.setCurrentIndex(0)
        if self.jadoo_widget:
            if query.strip():
                self.jadoo_widget.inp_query.setText(query.strip())
                self._on_jadoo_ask(query.strip(), self.jadoo_widget.chk_screen.isChecked(), False)
            else:
                self.jadoo_widget.focus_query_input()
        self.lbl_status.setText("Jadoo: Wake word detected! Listening...")

    @Slot(str)
    def _on_jadoo_status_changed(self, status: str) -> None:
        """Update Jadoo status badge and widget state."""
        if self.jadoo_widget:
            self.jadoo_widget.set_status(status)
        st_u = status.upper()
        if "THINK" in st_u:
            self.hdr_badge_jadoo.set_state("WARNING", "THINKING")
        elif "ONLINE" in st_u:
            self.hdr_badge_jadoo.set_state("OK", "JADOO ON")
        else:
            self.hdr_badge_jadoo.set_state("NORMAL", "JADOO IDLE")

    @Slot(bool)
    def _on_jadoo_speaking_state(self, speaking: bool) -> None:
        """Half-duplex mic muting: pause voice capture while SAPI TTS is speaking."""
        if self.voice_worker:
            if speaking:
                self.voice_worker.set_paused(True)
            elif getattr(self.settings.voice, "enabled", True):
                self.voice_worker.set_paused(False)

    @Slot(str)
    def _on_groq_key_changed(self, key: str) -> None:
        if self.voice_worker:
            self.voice_worker.set_groq_api_key(key)
        mode = getattr(self.settings.jadoo, "stt_mode", "cloud_first") if hasattr(self.settings, "jadoo") else "cloud_first"
        if mode == "offline":
            self.voice_widget.set_engine("LOCAL WHISPER")
        elif not (self.voice_worker and self.voice_worker.whisper.groq_client.is_configured):
            self.voice_widget.set_engine("API KEY MISSING")
        else:
            self.voice_widget.set_engine("LOCAL WHISPER")

    @Slot(str)
    def _on_gemini_key_changed(self, key: str) -> None:
        if self.jadoo_worker:
            self.jadoo_worker.set_gemini_api_key(key)

    @Slot(str)
    def _on_stt_mode_changed(self, mode: str) -> None:
        if self.voice_worker:
            self.voice_worker.set_stt_mode(mode)
        if mode == "offline":
            self.voice_widget.set_engine("LOCAL WHISPER")
        elif not (self.voice_worker and self.voice_worker.whisper.groq_client.is_configured):
            self.voice_widget.set_engine("API KEY MISSING")
        else:
            self.voice_widget.set_engine("LOCAL WHISPER")

    @Slot(bool)
    def _on_tts_toggled(self, enabled: bool) -> None:
        if self.jadoo_worker:
            self.jadoo_worker.set_tts_enabled(enabled)

    def cleanup(self) -> None:
        """Clean shutdown hook: ensures camera, audio, timers, and worker threads are safely stopped."""
        logger.info("MainWindow cleaning up: shutting down workers...")
        if hasattr(self, "hotkey_timer") and self.hotkey_timer.isActive():
            self.hotkey_timer.stop()
        if self.worker and self.worker.isRunning():
            self.worker.stop_tracking()
        if self.voice_worker and self.voice_worker.isRunning():
            self.voice_worker.stop()
        if self.jadoo_worker and self.jadoo_worker.isRunning():
            self.jadoo_worker.stop()
        if hasattr(self, "task_manager") and self.task_manager:
            self.task_manager.cleanup()
        if hasattr(self, "floating_panel") and self.floating_panel:
            self.floating_panel.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Clean shutdown hook: ensures camera and held mouse buttons are safely released."""
        self.cleanup()
        event.accept()

    def close(self) -> bool:
        """Ensure cleanup runs even if window was not shown before close."""
        self.cleanup()
        return super().close()
