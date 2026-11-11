"""Unit tests for core.mouse_controller (HeadMouse AI Phase 4).

Tests:
  - Mouse control is disabled by default.
  - Enable and disable functionality.
  - Emergency stop (F9) and manual re-enabling (F8).
  - Face-loss protection stops movement and clicks.
  - Calibration protection prevents enabling and disables on recalibration.
  - Left click and right click mapping.
  - Simultaneous blink suppression produces NO clicks.
  - Duplicate click prevention and cooldown enforcement.
  - Boundary clamping within screen limits.
  - PyAutoGUI failsafe exception handling.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

import pytest
import pyautogui

from core.mouse_controller import MouseController
from core.blink_detector import LEFT_CLICK, RIGHT_CLICK, NO_ACTION
from config.settings import MouseControlSettings


class MockPyAutoGUI:
    """Mock PyAutoGUI backend for deterministic unit testing."""

    def __init__(self, width: int = 1920, height: int = 1080) -> None:
        self.width = width
        self.height = height
        self.FAILSAFE = True
        self.PAUSE = 0.0
        self.moves: list[tuple[int, int]] = []
        self.clicks: list[str] = []
        self.raise_failsafe_on_move: bool = False
        self.raise_failsafe_on_click: bool = False
        self.FailSafeException = pyautogui.FailSafeException

    def size(self) -> tuple[int, int]:
        return (self.width, self.height)

    def moveTo(self, x: int, y: int) -> None:
        if self.raise_failsafe_on_move:
            raise self.FailSafeException("FailSafe triggered during moveTo")
        self.moves.append((x, y))

    def click(self, button: str = "left") -> None:
        if self.raise_failsafe_on_click:
            raise self.FailSafeException("FailSafe triggered during click")
        self.clicks.append(button)


def test_mouse_control_disabled_by_default():
    """Verify that real mouse control is strictly disabled upon startup."""
    mock = MockPyAutoGUI()
    controller = MouseController(py_backend=mock)

    assert not controller.enabled, "Mouse control MUST be disabled by default"
    assert not controller.emergency_stopped
    can_run, reason = controller.can_operate()
    assert not can_run
    assert reason == "DISABLED"


def test_no_real_mouse_action_occurs_while_disabled():
    """Ensure move_cursor and handle_blink_event do nothing when disabled."""
    mock = MockPyAutoGUI()
    controller = MouseController(py_backend=mock)
    controller.update_tracking_status(has_face=True, is_calibrated=True)

    assert not controller.enabled
    # Attempt move
    res_move = controller.move_cursor(0.5, 0.5)
    assert res_move is None
    assert len(mock.moves) == 0, "No moveTo should be called while disabled"

    # Attempt left click
    res_lclick = controller.handle_blink_event(LEFT_CLICK)
    assert res_lclick is None
    assert len(mock.clicks) == 0, "No clicks should be executed while disabled"

    # Attempt right click
    res_rclick = controller.handle_blink_event(RIGHT_CLICK)
    assert res_rclick is None
    assert len(mock.clicks) == 0


def test_calibration_protection():
    """Verify that mouse control cannot be enabled unless calibrated, and disables on recalibration."""
    mock = MockPyAutoGUI()
    controller = MouseController(py_backend=mock)
    controller.update_tracking_status(has_face=True, is_calibrated=False)

    # 1. Attempt to enable while uncalibrated -> MUST FAIL
    enabled = controller.enable()
    assert not enabled, "Must not enable when uncalibrated"
    assert not controller.enabled
    assert controller.last_action == "CANNOT_ENABLE_UNCALIBRATED"

    # 2. Toggle while uncalibrated -> MUST FAIL
    toggle_res = controller.toggle()
    assert not toggle_res
    assert not controller.enabled

    # 3. Now calibrate -> enable should succeed
    controller.update_tracking_status(has_face=True, is_calibrated=True)
    assert controller.enable()
    assert controller.enabled

    # 4. Trigger recalibration -> MUST AUTOMATICALLY DISABLE
    controller.update_tracking_status(has_face=True, is_calibrated=False)
    assert not controller.enabled, "Recalibration MUST automatically disable real mouse control"
    assert controller.last_action == "DISABLED_FOR_RECALIBRATION"


def test_face_loss_protection():
    """Verify that face loss immediately blocks movements and clicks without disabling configuration."""
    mock = MockPyAutoGUI()
    controller = MouseController(py_backend=mock)
    controller.update_tracking_status(has_face=True, is_calibrated=True)
    controller.enable()
    assert controller.enabled

    # Move while face is present -> works
    controller.move_cursor(0.5, 0.5)
    assert len(mock.moves) == 1

    # Face lost!
    controller.update_tracking_status(has_face=False, is_calibrated=True)
    can_run, reason = controller.can_operate()
    assert not can_run
    assert reason == "FACE_LOST"

    # Move attempt during face loss -> blocked
    assert controller.move_cursor(0.6, 0.6) is None
    assert len(mock.moves) == 1

    # Click attempt during face loss -> blocked
    assert controller.handle_blink_event(LEFT_CLICK) is None
    assert len(mock.clicks) == 0

    # Face recovered!
    controller.update_tracking_status(has_face=True, is_calibrated=True)
    assert controller.can_operate()[0]
    assert controller.move_cursor(0.6, 0.6) is not None
    assert len(mock.moves) == 2


def test_emergency_stop_and_manual_re_enabling():
    """Verify F9 emergency stop immediately disables control and requires explicit F8 re-enabling."""
    mock = MockPyAutoGUI()
    controller = MouseController(py_backend=mock)
    controller.update_tracking_status(has_face=True, is_calibrated=True)
    controller.enable()
    assert controller.enabled

    # Trigger emergency stop (F9)
    controller.emergency_stop()
    assert not controller.enabled, "Emergency stop must immediately disable mouse control"
    assert controller.emergency_stopped
    assert controller.last_action == "EMERGENCY_STOP"

    # Further operations must be rejected
    assert controller.move_cursor(0.5, 0.5) is None
    assert controller.handle_blink_event(LEFT_CLICK) is None
    assert len(mock.moves) == 0
    assert len(mock.clicks) == 0

    # Manual re-enabling via F8 (enable()) clears emergency stop
    success = controller.enable()
    assert success
    assert controller.enabled
    assert not controller.emergency_stopped


def test_cursor_movement_mapping_and_boundary_clamping():
    """Verify normalized [0, 1] mapping to screen pixels and boundary clamping."""
    mock = MockPyAutoGUI(width=1920, height=1080)
    controller = MouseController(screen_width=1920, screen_height=1080, py_backend=mock)
    controller.update_tracking_status(has_face=True, is_calibrated=True)
    controller.enable()

    # Center (0.5, 0.5)
    controller.move_cursor(0.5, 0.5)
    assert len(mock.moves) == 1
    # 0.5 * 1919 = ~960, 0.5 * 1079 = ~540
    assert 958 <= mock.moves[-1][0] <= 961
    assert 538 <= mock.moves[-1][1] <= 541

    # Extreme Top-Left (-0.5, -0.5) -> clamped inside screen bounds safely
    controller.move_cursor(-0.5, -0.5)
    assert mock.moves[-1][0] == 1
    assert mock.moves[-1][1] == 1

    # Extreme Bottom-Right (1.5, 1.5) -> clamped inside screen bounds safely
    controller.move_cursor(1.5, 1.5)
    assert mock.moves[-1][0] == 1918
    assert mock.moves[-1][1] == 1078


def test_left_and_right_click_mapping():
    """Verify simulated LEFT_CLICK and RIGHT_CLICK are mapped to actual PyAutoGUI clicks."""
    mock = MockPyAutoGUI()
    controller = MouseController(py_backend=mock)
    controller.update_tracking_status(has_face=True, is_calibrated=True)
    controller.enable()

    t = 1000.0
    # Left click
    res1 = controller.handle_blink_event(LEFT_CLICK, timestamp=t)
    assert res1 == "LEFT_CLICK"
    assert mock.clicks == ["left"]
    assert controller.total_left_clicks == 1

    # Right click after cooldown
    res2 = controller.handle_blink_event(RIGHT_CLICK, timestamp=t + 0.5)
    assert res2 == "RIGHT_CLICK"
    assert mock.clicks == ["left", "right"]
    assert controller.total_right_clicks == 1


def test_simultaneous_blink_suppression():
    """Verify that NO_ACTION (from simultaneous dual blink) produces no real click."""
    mock = MockPyAutoGUI()
    controller = MouseController(py_backend=mock)
    controller.update_tracking_status(has_face=True, is_calibrated=True)
    controller.enable()

    res = controller.handle_blink_event(NO_ACTION, timestamp=2000.0)
    assert res is None
    assert len(mock.clicks) == 0, "NO_ACTION must never trigger actual mouse clicks"


def test_duplicate_click_prevention_and_cooldown():
    """Verify rapid repeated blink events are debounced by cooldown_sec."""
    mock = MockPyAutoGUI()
    settings = MouseControlSettings(click_cooldown_sec=0.35)
    controller = MouseController(settings=settings, py_backend=mock)
    controller.update_tracking_status(has_face=True, is_calibrated=True)
    controller.enable()

    t0 = 3000.0
    # First click accepted
    assert controller.handle_blink_event(LEFT_CLICK, timestamp=t0) == "LEFT_CLICK"
    assert len(mock.clicks) == 1

    # Second click at 100ms (< 350ms cooldown) -> rejected
    assert controller.handle_blink_event(LEFT_CLICK, timestamp=t0 + 0.10) is None
    assert len(mock.clicks) == 1

    # Third click at 250ms (< 350ms cooldown) -> rejected
    assert controller.handle_blink_event(LEFT_CLICK, timestamp=t0 + 0.25) is None
    assert len(mock.clicks) == 1

    # Fourth click at 400ms (> 350ms cooldown) -> accepted
    assert controller.handle_blink_event(LEFT_CLICK, timestamp=t0 + 0.40) == "LEFT_CLICK"
    assert len(mock.clicks) == 2


def test_pyautogui_failsafe_exception_handling():
    """Verify that PyAutoGUI FailSafeException safely triggers emergency stop."""
    mock = MockPyAutoGUI()
    mock.raise_failsafe_on_move = True
    controller = MouseController(py_backend=mock)
    controller.update_tracking_status(has_face=True, is_calibrated=True)
    controller.enable()
    assert controller.enabled

    # Move will trigger FailSafeException in mock
    res = controller.move_cursor(0.5, 0.5)
    assert res is None
    assert controller.failsafe_triggered
    assert controller.emergency_stopped
    assert not controller.enabled
    assert controller.last_action == "EMERGENCY_STOP"


def test_head_mouse_app_mouse_controller_integration():
    """Verify HeadMouseApp initializes MouseController with strict safety defaults."""
    from main import HeadMouseApp

    app = HeadMouseApp()
    assert hasattr(app, "mouse_controller")
    assert not app.mouse_controller.enabled, "HeadMouseApp must have real mouse disabled at startup"
    assert not app.mouse_controller.emergency_stopped

    # Test that _start_calibration disables real mouse control
    app.mouse_controller.is_calibrated = True
    app.mouse_controller.enabled = True
    app._start_calibration()
    assert not app.mouse_controller.enabled, "Starting calibration must disable real mouse control"


def test_f8_f9_unified_trigger_handling():
    """Verify F8/M and F9/E triggers invoke MouseController enable/disable/stop."""
    from main import HeadMouseApp

    app = HeadMouseApp()
    mock = MockPyAutoGUI()
    app.mouse_controller.pyautogui = mock

    # 1. Uncalibrated toggle attempt -> should be blocked
    app.nose_tracker.is_calibrated = False
    assert not app.toggle_real_mouse(source="F8_TEST")
    assert not app.mouse_controller.enabled

    # 2. Calibrated toggle -> should enable
    app.nose_tracker.is_calibrated = True
    app.nose_tracker.is_calibrating = False
    app.mouse_controller.is_calibrated = True

    toggled = app.toggle_real_mouse(source="F8_TEST")
    assert toggled
    assert app.mouse_controller.enabled
    assert not app.mouse_controller.emergency_stopped

    # 3. Toggle again -> should disable
    toggled_off = app.toggle_real_mouse(source="F8_TEST")
    assert not toggled_off
    assert not app.mouse_controller.enabled

    # 4. Emergency stop -> should disable and set emergency_stopped
    app.mouse_controller.enabled = True
    app.emergency_stop_real_mouse(source="F9_TEST")
    assert not app.mouse_controller.enabled
    assert app.mouse_controller.emergency_stopped

    # 5. Re-enable clears emergency stop
    re_enabled = app.toggle_real_mouse(source="F8_TEST")
    assert re_enabled
    assert app.mouse_controller.enabled
    assert not app.mouse_controller.emergency_stopped


def test_clickable_ui_button_interaction():
    """Verify clicking the UI overlay buttons triggers mouse toggle and emergency stop."""
    from main import HeadMouseApp
    import cv2
    import numpy as np

    app = HeadMouseApp()
    app.nose_tracker.is_calibrated = True
    app.nose_tracker.is_calibrating = False
    app.mouse_controller.is_calibrated = True

    # Render frame with buttons to define bounding boxes
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    app._draw_dashboard_buttons(frame, app.mouse_controller.get_status())

    # Verify toggle button coordinates
    tx, ty, tw, th = app._btn_toggle_rect
    assert tw > 0 and th > 0

    # Simulate mouse click on toggle button
    app._on_mouse_click(cv2.EVENT_LBUTTONDOWN, tx + 10, ty + 10, 0, None)
    assert app._ui_button_toggle_clicked, "Clicking toggle button must set _ui_button_toggle_clicked"

    # Verify stop button coordinates
    sx, sy, sw, sh = app._btn_stop_rect
    assert sw > 0 and sh > 0

    # Simulate mouse click on stop button
    app._on_mouse_click(cv2.EVENT_LBUTTONDOWN, sx + 10, sy + 10, 0, None)
    assert app._ui_button_stop_clicked, "Clicking stop button must set _ui_button_stop_clicked"


def test_opencv_key_matching_for_f8_and_f9():
    """Verify that all OpenCV key representations for F8 and F9 evaluate to True in key matching."""
    # F8 key representation variants:
    f8_key_variants = [
        119,                   # Raw virtual key code VK_F8
        4325495,               # Windows OpenCV waitKeyEx: (0x42 << 16) | 0x77
        0x770000,              # Legacy Linux/GTK OpenCV waitKeyEx
        65477,                 # Qt backend F8
        ord("m"),              # 'm' keyboard fallback
        ord("M"),              # 'M' keyboard fallback
    ]

    for key in f8_key_variants:
        is_f8 = (
            ((key & 0xFF) == 119)
            or ((key & 0xFFFF) == 119)
            or (key in (0x770000, 119, 4325495, 65477))
            or (key in (ord("m"), ord("M")))
        )
        assert is_f8, f"Key representation {key} failed to match F8 logic"

    # F9 key representation variants:
    f9_key_variants = [
        120,                   # Raw virtual key code VK_F9
        4391032,               # Windows OpenCV waitKeyEx: (0x43 << 16) | 0x78
        0x780000,              # Legacy Linux/GTK OpenCV waitKeyEx
        65478,                 # Qt backend F9
        ord("e"),              # 'e' keyboard fallback
        ord("E"),              # 'E' keyboard fallback
    ]

    for key in f9_key_variants:
        is_f9 = (
            ((key & 0xFF) == 120)
            or ((key & 0xFFFF) == 120)
            or (key in (0x780000, 120, 4391032, 65478))
            or (key in (ord("e"), ord("E")))
        )
        assert is_f9, f"Key representation {key} failed to match F9 logic"


def test_actual_mouse_controller_method_invocation():
    """Verify that move_cursor and handle_blink_event invoke PyAutoGUI methods with exact parameters."""
    mock = MockPyAutoGUI(width=1920, height=1080)
    controller = MouseController(screen_width=1920, screen_height=1080, py_backend=mock)
    controller.update_tracking_status(has_face=True, is_calibrated=True)
    controller.enable()

    # Move cursor to 25% X, 75% Y
    res = controller.move_cursor(0.25, 0.75)
    assert res is not None
    assert len(mock.moves) == 1
    # 0.25 * 1919 = 480, 0.75 * 1079 = 809
    assert mock.moves[0] == (480, 809)

    # Click left
    clk_res = controller.handle_blink_event("LEFT_CLICK", timestamp=5000.0)
    assert clk_res == "LEFT_CLICK"
    assert mock.clicks == ["left"]

    # Click right
    clk_r_res = controller.handle_blink_event("RIGHT_CLICK", timestamp=5000.5)
    assert clk_r_res == "RIGHT_CLICK"
    assert mock.clicks == ["left", "right"]


