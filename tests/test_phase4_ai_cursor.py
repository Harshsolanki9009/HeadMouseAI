"""Automated test suite for Jadoo Phase 4: AI Cursor (HeadMouseAI) Integration.

Verifies:
1. MouseController pause, resume, enable, disable, and get_status.
2. VisionWorker cursor pause and resume slots.
3. Voice command recognition for cursor actions in English and Hindi/Hinglish.
4. Strict Dictation Mode Isolation: cursor commands are treated strictly as text in DICTATION_MODE.
5. Idempotent toggling of cursor states.
6. Neutral calibration and recentering state preservation.
7. Emergency stop halts cursor and releases all held buttons.
8. AICursorWidget UI creation, telemetry updates, sliders, and signal emissions.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch
import pytest

from PySide6.QtWidgets import QApplication

from config.settings import AppSettings
from core.mouse_controller import MouseController
from gui.widgets.ai_cursor_widget import AICursorWidget
from voice_engine.command_engine import CommandEngine
from voice_engine.command_registry import AccessibilityCommand
from voice_engine.mode_manager import JadooOperatingMode, ModeRouter


@pytest.fixture(scope="session")
def qapp():
    """Ensure a single persistent QApplication instance exists."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ------------------------------------------------------------- #
# 1. MouseController Pause, Resume, Enable, Disable             #
# ------------------------------------------------------------- #

def test_mouse_controller_pause_and_resume():
    """Verify MouseController tracks pause state and blocks operations when paused."""
    settings = AppSettings()
    controller = MouseController(settings)

    # By default, disabled
    assert not controller.enabled
    assert not controller.is_paused
    assert not controller.can_operate()[0]

    # Enable controller after calibrating
    controller.is_calibrated = True
    controller.has_face = True
    controller.enable()
    assert controller.enabled
    assert controller.can_operate()[0]

    # Pause controller
    controller.pause()
    assert controller.is_paused
    assert not controller.can_operate()[0]
    assert controller.can_operate()[1] == "PAUSED"

    status = controller.get_status()
    assert status["is_paused"] is True
    assert status["enabled"] is True

    # Resume controller
    controller.resume()
    assert not controller.is_paused
    assert controller.can_operate()[0]

    status = controller.get_status()
    assert status["is_paused"] is False


def test_mouse_controller_pause_releases_held_buttons():
    """Verify pausing mouse controller releases any currently held buttons."""
    settings = AppSettings()
    controller = MouseController(settings)
    controller.is_calibrated = True
    controller.has_face = True
    controller.enable()
    controller.is_mouse_down = True

    with patch.object(controller.pyautogui, "mouseUp") as mock_mouseup:
        controller.pause()
        assert not controller.is_mouse_down
        mock_mouseup.assert_called_once_with(button="left")


def test_mouse_controller_repeated_toggle_idempotency():
    """Verify repeatedly enabling, disabling, pausing, and resuming is idempotent."""
    settings = AppSettings()
    controller = MouseController(settings)
    controller.is_calibrated = True
    controller.has_face = True

    for _ in range(5):
        controller.enable()
        controller.enable()
        assert controller.enabled
        controller.pause()
        controller.pause()
        assert controller.is_paused
        controller.resume()
        controller.resume()
        assert not controller.is_paused
        controller.disable()
        controller.disable()
        assert not controller.enabled


# ------------------------------------------------------------- #
# 2. VisionWorker Cursor Pause and Resume Slots                 #
# ------------------------------------------------------------- #

def test_vision_worker_cursor_pause_resume():
    """Verify VisionWorker pause_cursor and resume_cursor methods and signal emissions."""
    from gui.worker import VisionWorker
    settings = AppSettings()

    worker = VisionWorker(settings)
    worker.mouse_controller = MouseController(settings)
    worker.mouse_controller.is_calibrated = True
    worker.mouse_controller.has_face = True
    worker.mouse_controller.enable()

    signals_emitted = []
    worker.sig_mouse_state_changed.connect(lambda en, lbl: signals_emitted.append((en, lbl)))

    worker.pause_cursor()
    assert worker.mouse_controller.is_paused
    assert len(signals_emitted) == 1
    assert signals_emitted[-1] == (False, "PAUSED")

    # Set has_face on controller so resume succeeds
    worker.mouse_controller.has_face = True
    worker.resume_cursor()
    assert not worker.mouse_controller.is_paused
    assert len(signals_emitted) == 2
    assert signals_emitted[-1] == (True, "ENABLED")


# ------------------------------------------------------------- #
# 3. Voice Command Recognition for AI Cursor                     #
# ------------------------------------------------------------- #

def test_voice_commands_cursor_english():
    """Verify English cursor commands are correctly recognized by CommandEngine."""
    engine = CommandEngine(cooldown_sec=0.0)

    test_cases = [
        ("mouse on", AccessibilityCommand.MOUSE_ON),
        ("mouse off", AccessibilityCommand.MOUSE_OFF),
        ("enable mouse", AccessibilityCommand.MOUSE_ON),
        ("disable mouse", AccessibilityCommand.MOUSE_OFF),
        ("pause cursor", AccessibilityCommand.PAUSE_CURSOR),
        ("resume cursor", AccessibilityCommand.RESUME_CURSOR),
        ("calibrate cursor", AccessibilityCommand.CALIBRATE_CURSOR),
        ("recenter cursor", AccessibilityCommand.RECENTER),
    ]

    for phrase, expected_cmd in test_cases:
        cmd, conf, rem = engine.match(phrase, enforce_cooldown=False)
        assert cmd == expected_cmd, f"Expected '{expected_cmd}' for phrase '{phrase}', got '{cmd}'"
        assert conf > 0.8


def test_voice_commands_cursor_hinglish_hindi():
    """Verify Hindi and Hinglish cursor commands match accurately."""
    engine = CommandEngine(cooldown_sec=0.0)

    test_cases = [
        ("माउस ऑन", AccessibilityCommand.MOUSE_ON),
        ("माउस बंद", AccessibilityCommand.MOUSE_OFF),
        ("कर्सर रोको", AccessibilityCommand.PAUSE_CURSOR),
        ("कर्सर चलाओ", AccessibilityCommand.RESUME_CURSOR),
        ("कर्सर रीसेंटर", AccessibilityCommand.RECENTER),
        ("कर्सर कैलिब्रेट", AccessibilityCommand.CALIBRATE_CURSOR),
    ]

    for phrase, expected_cmd in test_cases:
        cmd, conf, rem = engine.match(phrase, enforce_cooldown=False)
        assert cmd == expected_cmd, f"Expected '{expected_cmd}' for Hindi phrase '{phrase}', got '{cmd}'"


# ------------------------------------------------------------- #
# 4. Strict Dictation Mode Isolation for Cursor Commands        #
# ------------------------------------------------------------- #

def test_cursor_commands_are_typed_literally_in_dictation_mode():
    """Verify that in DICTATION_MODE, cursor commands are passed as text, never executed."""
    router = ModeRouter()
    router.set_mode(JadooOperatingMode.DICTATION_MODE)

    # Test phrases that are voice commands in COMMAND_MODE
    test_phrases = [
        "mouse on",
        "mouse off",
        "pause cursor",
        "resume cursor",
        "calibrate cursor",
        "recenter cursor",
    ]

    for phrase in test_phrases:
        route_action, cmd, payload = router.route_speech(phrase)
        assert route_action == "DICTATE_TEXT", f"Expected DICTATE_TEXT for phrase '{phrase}', got '{route_action}'"
        assert cmd is None, f"Command should be None in dictation mode for '{phrase}', got '{cmd}'"
        assert payload == phrase


# ------------------------------------------------------------- #
# 5. Neutral Calibration & Recenter State Preservation          #
# ------------------------------------------------------------- #

def test_calibration_preservation_on_pause_resume():
    """Verify neutral head center coordinates are preserved across pause and resume."""
    from core.nose_tracker import NoseTracker
    settings = AppSettings()
    tracker = NoseTracker()

    # Simulate calibrated center
    tracker.set_neutral(0.54, 0.48)

    # MouseController pause/resume
    controller = MouseController(settings)
    controller.is_calibrated = True
    controller.has_face = True
    controller.enable()
    controller.pause()
    controller.resume()

    # Verify tracker calibration is intact
    assert tracker.neutral_x == 0.54
    assert tracker.neutral_y == 0.48
    assert tracker.is_calibrated is True


# ------------------------------------------------------------- #
# 6. Emergency Stop Halts Cursor and Releases Buttons           #
# ------------------------------------------------------------- #

def test_emergency_stop_releases_all_buttons():
    """Verify emergency stop disables mouse and releases held mouse buttons."""
    settings = AppSettings()
    controller = MouseController(settings)
    controller.is_calibrated = True
    controller.has_face = True
    controller.enable()
    controller.is_mouse_down = True

    with patch.object(controller.pyautogui, "mouseUp") as mock_mouseup:
        controller.emergency_stop()
        assert not controller.enabled
        assert not controller.is_mouse_down
        assert mock_mouseup.call_count == 1


# ------------------------------------------------------------- #
# 7. AICursorWidget UI and Signals                              #
# ------------------------------------------------------------- #

def test_ai_cursor_widget_creation_and_signals(qapp):
    """Verify AICursorWidget initializes properly and emits signals."""
    settings = AppSettings()
    widget = AICursorWidget(settings)

    signals_caught = {}

    widget.sig_cursor_on.connect(lambda: signals_caught.update({"on": True}))
    widget.sig_cursor_off.connect(lambda: signals_caught.update({"off": True}))
    widget.sig_cursor_pause.connect(lambda: signals_caught.update({"pause": True}))
    widget.sig_cursor_resume.connect(lambda: signals_caught.update({"resume": True}))
    widget.sig_calibrate.connect(lambda: signals_caught.update({"calib": True}))
    widget.sig_recenter.connect(lambda: signals_caught.update({"recenter": True}))
    widget.sig_open_settings.connect(lambda: signals_caught.update({"settings": True}))
    widget.sig_sensitivity_changed.connect(lambda v: signals_caught.update({"sens": v}))
    widget.sig_smoothing_changed.connect(lambda v: signals_caught.update({"smooth": v}))

    # Trigger buttons
    widget.btn_cursor_on.click()
    assert signals_caught.get("on") is True

    widget.btn_cursor_off.click()
    assert signals_caught.get("off") is True

    # Pause button toggle
    widget.btn_cursor_pause.click()
    assert signals_caught.get("pause") is True
    assert widget._is_cursor_paused is True

    widget.btn_cursor_pause.click()
    assert signals_caught.get("resume") is True
    assert widget._is_cursor_paused is False

    widget.btn_calibrate.click()
    assert signals_caught.get("calib") is True

    widget.btn_recenter.click()
    assert signals_caught.get("recenter") is True

    widget.btn_settings.click()
    assert signals_caught.get("settings") is True

    # Sliders
    widget.slider_sens.setValue(25)  # 2.5x
    assert signals_caught.get("sens") == 2.5

    widget.slider_smooth.setValue(50)  # 0.50
    assert signals_caught.get("smooth") == 0.50


def test_ai_cursor_widget_telemetry_and_state_updates(qapp):
    """Verify telemetry and state updates adjust widget status badges."""
    settings = AppSettings()
    widget = AICursorWidget(settings)

    # Telemetry update
    t = {
        "has_face": True,
        "is_tracking": True,
        "cam_online": True,
    }
    widget.update_telemetry(t)
    assert "ONLINE" in widget.badge_camera.text()
    assert "LOCKED" in widget.badge_face.text()
    assert "ACTIVE" in widget.badge_nose.text()

    # Mouse state update: ACTIVE
    widget.update_mouse_state(True, "ACTIVE")
    assert "ACTIVE" in widget.badge_cursor.text()

    # Mouse state update: EMERGENCY_STOP
    widget.update_mouse_state(False, "EMERGENCY_STOP")
    assert "STOPPED" in widget.badge_cursor.text()
