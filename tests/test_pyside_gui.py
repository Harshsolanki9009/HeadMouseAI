"""Automated tests for PySide6 GUI architecture and resource locator."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QWidget

# Ensure QApplication instance exists for widget testing
app = QApplication.instance()
if app is None:
    app = QApplication([])

from config.settings import AppSettings
from gui.main_window import MainWindow
from gui.widgets.control_bar import ControlBarWidget
from gui.widgets.settings_tab import SettingsTabWidget
from gui.widgets.splash_screen import SplashScreen
from gui.widgets.telemetry_cards import StatusBadge, TelemetryCardsWidget
from gui.widgets.video_widget import VideoWidget
from gui.worker import VisionWorker
from utils.resource import get_config_path, get_icon_path, get_model_path, get_resource_path


def test_resource_locator():
    """Verify resource path resolution in development and standalone modes."""
    model_path = get_model_path("face_landmarker.task")
    assert model_path.is_file(), f"Model file must exist at {model_path}"
    assert model_path.stat().st_size > 1_000_000

    config_path = get_config_path("config.toml")
    assert config_path.is_file(), f"Config file must exist at {config_path}"

    icon_path = get_icon_path("app_icon.png")
    assert icon_path.is_file(), f"Icon must exist at {icon_path}"


def test_video_widget():
    """Verify VideoWidget lifecycle, frame updates, and telemetry banners."""
    vw = VideoWidget()
    assert vw.minimumWidth() >= 480
    assert vw.minimumHeight() >= 360

    # Feed dummy 64x64 QImage
    img = QImage(64, 64, QImage.Format.Format_RGB888)
    img.fill(Qt.GlobalColor.blue)
    vw.update_frame(img)
    assert vw._current_image is not None

    # Telemetry overlays
    vw.update_telemetry({
        "mode": "SCROLL",
        "fps": 32.5,
        "latency_ms": 15.0,
        "gesture_action": "SCROLL_UP",
        "gesture_step_ready": False,
    })
    assert "SCROLL" in vw._mode
    assert "32.5 FPS" in vw._fps_text

    vw.clear_frame()
    assert vw._current_image is None


def test_status_badge():
    """Verify StatusBadge semantic styling."""
    badge = StatusBadge("TEST")
    badge.set_state("OK", "ACTIVE")
    assert "ECFDF5" in badge.styleSheet() or "059669" in badge.styleSheet()

    badge.set_state("ERROR", "EMERGENCY_STOP")
    assert "FEF2F2" in badge.styleSheet() or "DC2626" in badge.styleSheet()

    badge.set_state("WARNING", "CALIBRATING")
    assert "FFFBEB" in badge.styleSheet() or "D97706" in badge.styleSheet()


def test_telemetry_cards():
    """Verify TelemetryCardsWidget updates all metrics without error."""
    tc = TelemetryCardsWidget()
    tc.update_telemetry({
        "mode": "ZOOM",
        "emergency_stopped": False,
        "real_mouse_enabled": True,
        "has_face": True,
        "is_calibrated": True,
        "is_calibrating": False,
        "screen_x": 960,
        "screen_y": 540,
        "rel_dx": 0.012,
        "rel_dy": -0.024,
        "position_locked": False,
        "is_dragging": False,
        "left_ear": 0.28,
        "right_ear": 0.28,
        "left_eye_state": "OPEN",
        "right_eye_state": "OPEN",
        "blink_event": "LEFT_CLICK",
        "suppression_active": False,
        "teeth_visible": True,
        "left_eb_state": "RAISED",
        "right_eb_state": "RAISED",
        "head_direction": "UP",
        "gesture_action": "ZOOM_IN",
        "mouth_width_ratio": 0.62,
        "mouth_width_baseline": 0.52,
        "mouth_open_ratio": 0.025,
        "gesture_reject_reason": "NONE",
    })
    assert tc.badge_mode.text() == "ZOOM"
    assert "ENABLED" in tc.badge_real_mouse.text()
    assert tc.lbl_screen_pos.text() == "(960, 540)"
    assert tc.badge_click_event.text() == "LEFT_CLICK"
    assert tc.badge_teeth.text() == "SHOWN"


def test_control_bar():
    """Verify ControlBarWidget toggles and signal emissions."""
    bar = ControlBarWidget()
    events = []
    bar.sig_start_requested.connect(lambda: events.append("START"))
    bar.sig_stop_requested.connect(lambda: events.append("STOP"))
    bar.sig_mouse_toggle_requested.connect(lambda: events.append("MOUSE_TOGGLE"))
    bar.sig_emergency_requested.connect(lambda: events.append("EMERGENCY"))

    bar._on_toggle_tracking()
    assert "START" in events

    bar.set_tracking_state(True)
    bar._on_toggle_tracking()
    assert "STOP" in events

    bar.btn_mouse_toggle.click()
    assert "MOUSE_TOGGLE" in events

    bar.btn_emergency.click()
    assert "EMERGENCY" in events


def test_settings_tab():
    """Verify SettingsTabWidget slider changes emit dynamic settings diffs."""
    tab = SettingsTabWidget()
    changes = []
    tab.sig_settings_changed.connect(lambda d: changes.append(d))

    tab.slider_sens.setValue(80)  # 8.0
    assert any(c.get("sensitivity") == 8.0 for c in changes)

    tab.slider_deadzone.setValue(15)
    assert any(c.get("dead_zone") == 15.0 for c in changes)


def test_vision_worker_safety_controls():
    """Verify VisionWorker safety controls (emergency stop, mouse enable/disable, cleanup)."""
    with patch("core.camera.cv2.VideoCapture"), patch("core.face_landmarker.tasks.vision.FaceLandmarker.create_from_options"):
        worker = VisionWorker()
        assert not worker.mouse_controller.enabled

        # Emergency stop
        worker.trigger_emergency_stop()
        assert worker.mouse_controller.emergency_stopped

        # Cleanup releases mouse buttons
        worker._cleanup()
        assert not worker.mouse_controller.is_mouse_down


def test_main_window_lifecycle():
    """Verify MainWindow initializes tabs, widgets, and shuts down safely."""
    with patch("core.camera.cv2.VideoCapture"), patch("core.face_landmarker.tasks.vision.FaceLandmarker.create_from_options"):
        win = MainWindow()
        assert win.tabs.count() == 4
        assert win.video_widget is not None
        assert win.telemetry_widget is not None
        assert win.control_bar is not None
        assert win.settings_tab is not None

        # Clean close
        win.close()


def test_splash_screen():
    """Verify Obsidian Chrome SplashScreen initializes, updates status text, animates, and closes safely."""
    splash = SplashScreen()
    assert splash.width() == 620
    assert splash.height() == 360
    assert splash._raw_chrome is not None
    assert not splash._raw_chrome.isNull()

    splash.set_status("Loading subsystems...")
    assert splash._status_text == "Loading subsystems..."

    splash._on_spinner_tick()
    assert splash._spinner_angle > 0.0

    # Verify animation timeline ticks smoothly
    splash._start_time = 0.0
    splash._on_anim_tick()
    assert splash._elapsed_ms >= 0.0

    # Verify paint event renders without raising exceptions
    splash.repaint()

    # Verify finish_and_show transition to target window
    target = QWidget()
    splash.finish_and_show(target)
    assert splash._fade_out_anim is not None

    splash.close()
    target.close()


def test_video_widget_blurred_background():
    """Verify VideoWidget pre-caches blurred background for pillarbox filling."""
    vw = VideoWidget()
    img = QImage(640, 480, QImage.Format.Format_RGB888)
    img.fill(Qt.GlobalColor.cyan)
    vw.update_frame(img)

    assert vw._current_image is not None
    assert vw._cached_bg_image is not None
    assert vw._cached_bg_image.width() == 96
    assert vw._cached_bg_image.height() == 72

    vw.clear_frame()
    assert vw._current_image is None
    assert vw._cached_bg_image is None


def test_welcome_dialog():
    """Verify WelcomeDialog lifecycle, preferences, and signal emission."""
    from gui.dialogs.welcome_dialog import WelcomeDialog

    settings = AppSettings()
    dlg = WelcomeDialog(settings)
    assert dlg.windowTitle() == "Welcome to HeadMouseAI"
    assert dlg.chk_dont_show.isChecked()

    events = []
    dlg.sig_start_calibration.connect(lambda: events.append("CALIBRATE"))
    dlg._on_calibrate_clicked()
    assert "CALIBRATE" in events
    assert settings.gui.first_launch_done is True


def test_keyboard_focus_and_tab_order():
    """Priority 1: Verify interactive controls have keyboard focus policies and proper tab order."""
    bar = ControlBarWidget()
    assert bar.btn_toggle_tracking.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert bar.btn_mouse_toggle.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert bar.btn_calibrate.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert bar.btn_reset.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert bar.btn_emergency.focusPolicy() == Qt.FocusPolicy.StrongFocus

    settings_tab = SettingsTabWidget()
    assert settings_tab.slider_sens.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert settings_tab.slider_deadzone.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert settings_tab.slider_smooth.focusPolicy() == Qt.FocusPolicy.StrongFocus


def test_calibration_wizard_camera_preview():
    """Priority 1: Verify compact live camera preview embedded in CalibrationWizard."""
    from gui.dialogs.calibration_wizard import CalibrationCameraPreview, CalibrationWizard

    preview = CalibrationCameraPreview()
    assert preview.width() == 260
    assert preview.height() == 195

    # Feed test frame
    test_img = QImage(320, 240, QImage.Format.Format_RGB888)
    test_img.fill(Qt.GlobalColor.green)
    preview.update_frame(test_img)
    assert preview._current_image is not None
    assert not preview._current_image.isNull()

    preview.clear()
    assert preview._current_image is None

    # Verify wizard routes frames to preview widgets across steps
    wizard = CalibrationWizard(worker=None)
    assert hasattr(wizard, "cam_preview_step1")
    assert hasattr(wizard, "cam_preview_step2")
    assert hasattr(wizard, "cam_preview_step3")

    wizard._on_frame_ready(test_img)
    assert wizard.cam_preview_step1._current_image is not None

    wizard.close()


def test_reset_confirmation_dialog():
    """Priority 1: Verify reset action prompts confirmation before wiping state."""
    from PySide6.QtWidgets import QMessageBox

    with patch("core.camera.cv2.VideoCapture"), patch("core.face_landmarker.tasks.vision.FaceLandmarker.create_from_options"):
        win = MainWindow()

        # Mock nose tracker reset
        win.worker.nose_tracker.reset = MagicMock()

        # Case A: User clicks 'No' (cancels reset)
        with patch("gui.main_window.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
            win._on_reset_requested(confirm=True)
            win.worker.nose_tracker.reset.assert_not_called()

        # Case B: User clicks 'Yes' (confirms reset)
        with patch("gui.main_window.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            win._on_reset_requested(confirm=True)
            win.worker.nose_tracker.reset.assert_called_once()

        win.close()


def test_tabular_numerals_styling():
    """Priority 1: Verify dynamic telemetry labels use monospace/tabular fonts."""
    with patch("core.camera.cv2.VideoCapture"), patch("core.face_landmarker.tasks.vision.FaceLandmarker.create_from_options"):
        win = MainWindow()
        assert "Consolas" in win.lbl_dash_fps.styleSheet() or "monospace" in win.lbl_dash_fps.styleSheet()
        assert "Consolas" in win.lbl_dash_inf.styleSheet() or "monospace" in win.lbl_dash_inf.styleSheet()
        assert "Consolas" in win.lbl_dash_lear.styleSheet() or "monospace" in win.lbl_dash_lear.styleSheet()
        assert "Consolas" in win.lbl_dash_rear.styleSheet() or "monospace" in win.lbl_dash_rear.styleSheet()
        assert "Consolas" in win.lbl_dash_sys.styleSheet() or "monospace" in win.lbl_dash_sys.styleSheet()

        tc = win.telemetry_widget
        assert "Consolas" in tc.lbl_eyebrows.styleSheet() or "monospace" in tc.lbl_eyebrows.styleSheet()
        win.close()



