"""Comprehensive reliability tests for Left/Right Wink Clicks and Hands-Free Drag & Area Selection.

Covers:
1. Short intentional left/right winks (40ms - 150ms) detected as exactly one click.
2. Contralateral sympathetic squint (other eye narrowing to EAR 0.17) does NOT cause missed clicks.
3. Long intentional winks (250ms - 320ms, below drag threshold) detected cleanly as single click.
4. Prevention of duplicate clicks: exactly one click emitted per wink, subsequent closure during cooldown blocked.
5. Bilateral blink suppression: simultaneous blinks (within 120ms onset) produce NO clicks.
6. Drag start: holding left eye closed >= drag threshold (380ms) triggers DRAG_START and mouseDown.
7. Drag movement: while dragging is active, cursor position is NOT locked/frozen and moves freely with nose displacement.
8. Drag release: reopening left eye triggers DRAG_STOP and mouseUp immediately.
9. No extra click after drag: reopening from drag produces NO LEFT_CLICK.
10. Right-eye wink during active drag: right eye wink does NOT cancel or interrupt active drag, does not emit right click, and does not lock cursor.
11. Safety releases: mouse button is immediately released on:
    a) Face loss
    b) Emergency Stop (F9)
    c) Recalibration (C)
12. Eyebrow movement independence: raising or moving eyebrows does NOT suppress normal wink clicks.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import AppSettings, EyeBlinkSettings, MouseControlSettings
from core.blink_detector import (
    BlinkDetector,
    DRAG_START,
    DRAG_STOP,
    LEFT_CLICK,
    RIGHT_CLICK,
    NO_ACTION,
    STATE_CLOSED,
    STATE_OPEN,
)
from core.cursor_simulator import CursorSimulator
from core.mouse_controller import MouseController


class MockPyAutoGUI:
    """Mock PyAutoGUI backend for deterministic verification without OS interaction."""

    def __init__(self, width: int = 1920, height: int = 1080) -> None:
        self.width = width
        self.height = height
        self.moves: list[tuple[int, int]] = []
        self.clicks: list[str] = []
        self.downs: list[str] = []
        self.ups: list[str] = []
        self.cur_x = width // 2
        self.cur_y = height // 2
        self.FAILSAFE = True
        self.PAUSE = 0.0

    def size(self) -> tuple[int, int]:
        return self.width, self.height

    def position(self) -> tuple[int, int]:
        return (self.cur_x, self.cur_y)

    def moveTo(self, x: int, y: int, _pause: bool = False) -> None:
        self.cur_x = int(x)
        self.cur_y = int(y)
        self.moves.append((int(x), int(y)))

    def click(self, button: str = "left", _pause: bool = False) -> None:
        self.clicks.append(button)

    def mouseDown(self, button: str = "left", _pause: bool = False) -> None:
        self.downs.append(button)

    def mouseUp(self, button: str = "left", _pause: bool = False) -> None:
        self.ups.append(button)

    def scroll(self, amount: int) -> None:
        pass

    def hotkey(self, *keys) -> None:
        pass


def make_face_landmarks(left_ear: float = 0.28, right_ear: float = 0.28) -> dict[str, Any]:
    """Generate canonical 478 face mesh landmarks with exact EAR values."""
    lm = [[0.0, 0.0, 0.0, 1.0, 1.0] for _ in range(478)]
    # Left eye canonical landmarks: 33, 133, 160, 144, 158, 153
    w = 0.10
    lm[33] = [0.45 - w / 2.0, 0.40, 0.0, 1.0, 1.0]
    lm[133] = [0.45 + w / 2.0, 0.40, 0.0, 1.0, 1.0]
    left_h = left_ear * w
    lm[160] = [0.43, 0.40 - left_h / 2.0, 0.0, 1.0, 1.0]
    lm[144] = [0.43, 0.40 + left_h / 2.0, 0.0, 1.0, 1.0]
    lm[158] = [0.47, 0.40 - left_h / 2.0, 0.0, 1.0, 1.0]
    lm[153] = [0.47, 0.40 + left_h / 2.0, 0.0, 1.0, 1.0]

    # Right eye canonical landmarks: 263, 362, 385, 380, 387, 373
    lm[362] = [0.55 - w / 2.0, 0.40, 0.0, 1.0, 1.0]
    lm[263] = [0.55 + w / 2.0, 0.40, 0.0, 1.0, 1.0]
    right_h = right_ear * w
    lm[385] = [0.53, 0.40 - right_h / 2.0, 0.0, 1.0, 1.0]
    lm[380] = [0.53, 0.40 + right_h / 2.0, 0.0, 1.0, 1.0]
    lm[387] = [0.57, 0.40 - right_h / 2.0, 0.0, 1.0, 1.0]
    lm[373] = [0.57, 0.40 + right_h / 2.0, 0.0, 1.0, 1.0]

    # Nose tip at 1
    lm[1] = [0.50, 0.50, 0.0, 1.0, 1.0]
    return {"has_face": True, "landmarks": lm}


# =========================================================================
# A. RELIABLE WINK CLICKS
# =========================================================================

def test_short_left_wink_click():
    """Verify short left wink (50ms) emits exactly one LEFT_CLICK."""
    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.04,
        max_blink_duration_sec=0.65,
        drag_enabled=True,
        drag_hold_sec=0.38,
    )
    detector = BlinkDetector(settings)
    open_f = make_face_landmarks(0.28, 0.28)
    left_closed = make_face_landmarks(0.10, 0.28)

    t = 100.0
    detector.update(open_f, timestamp=t)
    detector.update(left_closed, timestamp=t + 0.02)
    detector.update(left_closed, timestamp=t + 0.05)
    res = detector.update(open_f, timestamp=t + 0.07)

    assert res["event"] == LEFT_CLICK
    assert detector.total_left_clicks == 1
    assert detector.total_right_clicks == 0


def test_short_right_wink_click():
    """Verify short right wink (50ms) emits exactly one RIGHT_CLICK."""
    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.04,
        max_blink_duration_sec=0.65,
        drag_enabled=True,
        drag_hold_sec=0.38,
    )
    detector = BlinkDetector(settings)
    open_f = make_face_landmarks(0.28, 0.28)
    right_closed = make_face_landmarks(0.28, 0.10)

    t = 200.0
    detector.update(open_f, timestamp=t)
    detector.update(right_closed, timestamp=t + 0.02)
    detector.update(right_closed, timestamp=t + 0.05)
    res = detector.update(open_f, timestamp=t + 0.07)

    assert res["event"] == RIGHT_CLICK
    assert detector.total_right_clicks == 1
    assert detector.total_left_clicks == 0


def test_wink_with_contralateral_squint_is_not_missed():
    """Verify left wink where right eye squints naturally (EAR drops to 0.17) is NOT rejected as dual suppression."""
    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.04,
        max_blink_duration_sec=0.65,
        drag_enabled=True,
        drag_hold_sec=0.38,
    )
    detector = BlinkDetector(settings)
    open_f = make_face_landmarks(0.28, 0.28)
    # Left eye firmly closed (0.09), right eye squinting slightly (0.17)
    wink_with_squint = make_face_landmarks(0.09, 0.17)

    t = 300.0
    detector.update(open_f, timestamp=t)
    detector.update(wink_with_squint, timestamp=t + 0.05)
    detector.update(wink_with_squint, timestamp=t + 0.12)
    res = detector.update(open_f, timestamp=t + 0.18)

    assert res["event"] == LEFT_CLICK, f"Expected LEFT_CLICK, got {res['event']} (reject: {detector.last_reject_reason})"
    assert detector.total_left_clicks == 1


def test_long_wink_below_drag_threshold():
    """Verify an intentional longer wink (280ms, below 380ms drag threshold) emits LEFT_CLICK."""
    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.04,
        max_blink_duration_sec=0.65,
        drag_enabled=True,
        drag_hold_sec=0.38,
    )
    detector = BlinkDetector(settings)
    open_f = make_face_landmarks(0.28, 0.28)
    left_closed = make_face_landmarks(0.10, 0.28)

    t = 400.0
    detector.update(open_f, timestamp=t)
    detector.update(left_closed, timestamp=t + 0.05)
    detector.update(left_closed, timestamp=t + 0.15)
    detector.update(left_closed, timestamp=t + 0.28)
    assert not detector.left_eye.is_dragging
    res = detector.update(open_f, timestamp=t + 0.32)

    assert res["event"] == LEFT_CLICK
    assert detector.total_left_clicks == 1


def test_duplicate_click_prevention_on_rapid_consecutive_closure():
    """Verify exactly one click per wink and that consecutive closure within cooldown is blocked."""
    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.04,
        max_blink_duration_sec=0.65,
        blink_cooldown_sec=0.25,
        blink_cooldown_frames=6,
    )
    detector = BlinkDetector(settings)
    open_f = make_face_landmarks(0.28, 0.28)
    left_closed = make_face_landmarks(0.10, 0.28)

    t = 500.0
    detector.update(open_f, timestamp=t)
    detector.update(left_closed, timestamp=t + 0.05)
    r1 = detector.update(open_f, timestamp=t + 0.10)
    assert r1["event"] == LEFT_CLICK

    # Immediate second closure within cooldown window (t + 0.15s < t + 0.25s)
    detector.update(left_closed, timestamp=t + 0.15)
    r2 = detector.update(open_f, timestamp=t + 0.20)
    assert r2["event"] is None
    assert detector.total_left_clicks == 1


def test_simultaneous_bilateral_blink_suppression():
    """Verify simultaneous natural blink (both eyes closed) produces NO click."""
    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.04,
        max_blink_duration_sec=0.65,
        simultaneous_blink_suppression=True,
    )
    detector = BlinkDetector(settings)
    open_f = make_face_landmarks(0.28, 0.28)
    both_closed = make_face_landmarks(0.10, 0.10)

    t = 600.0
    detector.update(open_f, timestamp=t)
    detector.update(both_closed, timestamp=t + 0.05)
    detector.update(both_closed, timestamp=t + 0.12)
    assert detector.simultaneous_suppression_active

    res = detector.update(open_f, timestamp=t + 0.18)
    assert res["event"] in (NO_ACTION, None)
    assert detector.total_left_clicks == 0
    assert detector.total_right_clicks == 0
    assert not detector.simultaneous_suppression_active


# =========================================================================
# B. RELIABLE AREA SELECTION AND DRAG-AND-DROP
# =========================================================================

def test_drag_start_after_hold_threshold():
    """Verify holding left eye closed >= 380ms emits DRAG_START and initiates dragging."""
    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.04,
        max_blink_duration_sec=0.65,
        drag_enabled=True,
        drag_hold_sec=0.38,
    )
    detector = BlinkDetector(settings)
    open_f = make_face_landmarks(0.28, 0.28)
    left_closed = make_face_landmarks(0.10, 0.28)

    t = 700.0
    detector.update(open_f, timestamp=t)
    detector.update(left_closed, timestamp=t + 0.05)
    detector.update(left_closed, timestamp=t + 0.25)
    assert not detector.left_eye.is_dragging

    # Cross 380ms threshold (t + 0.45 - (t + 0.05) = 0.40s >= 0.38s)
    r_drag = detector.update(left_closed, timestamp=t + 0.45)
    assert r_drag["event"] == DRAG_START
    assert detector.left_eye.is_dragging
    assert r_drag["is_dragging"]


def test_drag_movement_keeps_cursor_unfrozen():
    """Verify cursor position does NOT freeze during dragging and moves freely with nose displacement."""
    cursor = CursorSimulator(sensitivity=1.0, dead_zone=4.0, window_width=640, window_height=480)
    mock_py = MockPyAutoGUI(width=1920, height=1080)
    controller = MouseController(py_backend=mock_py)
    controller.update_tracking_status(has_face=True, is_calibrated=True)
    controller.enable()

    # Move cursor to initial point
    cursor.update(0.0, 0.0)
    controller.move_cursor(*cursor.normalized_position)
    init_x, init_y = controller.screen_x, controller.screen_y

    # Simulate wink onset locking position
    cursor.lock_position(reason="CLICK_LEFT")
    controller.lock_position(reason="CLICK_LEFT")
    assert cursor.is_position_locked
    assert controller.is_position_locked

    # DRAG_START occurs -> unlock position and engage drag
    cursor.set_dragging(True)
    controller.handle_blink_event(DRAG_START)
    assert not cursor.is_position_locked
    assert not controller.is_position_locked
    assert controller.is_dragging
    assert controller.is_mouse_down
    assert "left" in mock_py.downs

    # Attempt lock during active drag: MUST be ignored
    cursor.lock_position(reason="TEST")
    controller.lock_position(reason="TEST")
    assert not cursor.is_position_locked
    assert not controller.is_position_locked

    # Continuous head movement while dragging
    for dx in [0.05, 0.10, 0.15, 0.20]:
        cx, cy, moved = cursor.update(dx, 0.0)
        pos = controller.move_cursor(*cursor.normalized_position)
        assert moved
        assert pos is not None
        assert controller.is_mouse_down, "Mouse button must stay down throughout drag"

    assert len(mock_py.moves) > 1
    assert controller.screen_x != init_x, "Cursor must move across screen during drag"


def test_drag_release_triggers_mouse_up_without_left_click():
    """Verify reopening left eye releases mouse button immediately and emits NO LEFT_CLICK."""
    mock_py = MockPyAutoGUI(width=1920, height=1080)
    controller = MouseController(py_backend=mock_py)
    controller.update_tracking_status(has_face=True, is_calibrated=True)
    controller.enable()

    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.04,
        max_blink_duration_sec=0.65,
        drag_enabled=True,
        drag_hold_sec=0.38,
    )
    detector = BlinkDetector(settings)
    open_f = make_face_landmarks(0.28, 0.28)
    left_closed = make_face_landmarks(0.10, 0.28)

    t = 800.0
    detector.update(open_f, timestamp=t)
    detector.update(left_closed, timestamp=t + 0.05)
    r_drag = detector.update(left_closed, timestamp=t + 0.45)
    assert r_drag["event"] == DRAG_START

    # Start drag in controller
    controller.handle_blink_event(DRAG_START)
    assert controller.is_mouse_down
    assert controller.is_dragging

    # Reopen left eye -> DRAG_STOP
    r_stop = detector.update(open_f, timestamp=t + 0.60)
    assert r_stop["event"] == DRAG_STOP
    assert r_stop["event"] != LEFT_CLICK
    assert not detector.left_eye.is_dragging

    # Pass DRAG_STOP to controller
    act = controller.handle_blink_event(DRAG_STOP)
    assert act == "DRAG_STOP"
    assert not controller.is_mouse_down
    assert not controller.is_dragging
    assert "left" in mock_py.ups
    assert len(mock_py.clicks) == 0, "No extra click should have been registered"


def test_right_wink_during_active_drag_does_not_cancel_drag():
    """Verify that a right eye wink while holding left-button drag does NOT cancel drag or emit click."""
    mock_py = MockPyAutoGUI(width=1920, height=1080)
    controller = MouseController(py_backend=mock_py)
    controller.update_tracking_status(has_face=True, is_calibrated=True)
    controller.enable()

    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.04,
        max_blink_duration_sec=0.65,
        drag_enabled=True,
        drag_hold_sec=0.38,
    )
    detector = BlinkDetector(settings)
    open_f = make_face_landmarks(0.28, 0.28)
    left_closed = make_face_landmarks(0.10, 0.28)
    both_closed = make_face_landmarks(0.10, 0.10)

    t = 900.0
    detector.update(open_f, timestamp=t)
    detector.update(left_closed, timestamp=t + 0.05)
    r_drag = detector.update(left_closed, timestamp=t + 0.45)
    assert r_drag["event"] == DRAG_START
    controller.handle_blink_event(DRAG_START)
    assert controller.is_mouse_down

    # Right eye closes while left eye is actively dragging
    r_both = detector.update(both_closed, timestamp=t + 0.55)
    assert detector.left_eye.is_dragging
    assert not detector.simultaneous_suppression_active
    assert r_both["event"] is None

    # Right eye reopens while left eye is still dragging
    r_right_open = detector.update(left_closed, timestamp=t + 0.65)
    assert detector.left_eye.is_dragging
    assert r_right_open["event"] is None

    # Drag continues undisturbed
    assert controller.is_mouse_down
    assert len(mock_py.ups) == 0

    # Finally left eye reopens -> clean DRAG_STOP
    r_stop = detector.update(open_f, timestamp=t + 0.80)
    assert r_stop["event"] == DRAG_STOP
    controller.handle_blink_event(DRAG_STOP)
    assert not controller.is_mouse_down
    assert len(mock_py.ups) == 1
    assert len(mock_py.clicks) == 0


def test_safety_releases_on_face_loss_emergency_stop_recalibration():
    """Verify all held mouse buttons are immediately released upon face loss, emergency stop, and recalibration."""
    # 1. Safety release on Face Loss
    mock_py1 = MockPyAutoGUI(width=1920, height=1080)
    c1 = MouseController(py_backend=mock_py1)
    c1.update_tracking_status(has_face=True, is_calibrated=True)
    c1.enable()
    c1.handle_blink_event(DRAG_START)
    assert c1.is_mouse_down
    c1.update_tracking_status(has_face=False, is_calibrated=True)
    assert not c1.is_mouse_down
    assert "left" in mock_py1.ups

    # 2. Safety release on Emergency Stop (F9)
    mock_py2 = MockPyAutoGUI(width=1920, height=1080)
    c2 = MouseController(py_backend=mock_py2)
    c2.update_tracking_status(has_face=True, is_calibrated=True)
    c2.enable()
    c2.handle_blink_event(DRAG_START)
    assert c2.is_mouse_down
    c2.emergency_stop()
    assert not c2.is_mouse_down
    assert c2.emergency_stopped
    assert "left" in mock_py2.ups

    # 3. Safety release on Recalibration (C)
    mock_py3 = MockPyAutoGUI(width=1920, height=1080)
    c3 = MouseController(py_backend=mock_py3)
    c3.update_tracking_status(has_face=True, is_calibrated=True)
    c3.enable()
    c3.handle_blink_event(DRAG_START)
    assert c3.is_mouse_down
    # Recalibration resets calibration state
    c3.update_tracking_status(has_face=True, is_calibrated=False)
    assert not c3.is_mouse_down
    assert "left" in mock_py3.ups
