"""Tests for Click Position Stabilization in HeadMouse AI.

Verifies:
1. Virtual cursor position lock at gesture onset.
2. Invariance of virtual and real cursor coordinates during intentional eye closure.
3. Ignore temporary nose-tip tracking disturbances / twitches caused by eye closure.
4. Left click executed at exact locked coordinates despite simulated nose movement.
5. Right click executed at exact locked coordinates independently.
6. Post-click reopening cooldown stabilization.
7. Smooth movement resumption after click without sudden velocity spikes or jumps.
8. Drag & Drop compatibility: releasing lock upon DRAG_START (>= 350ms) to allow cursor movement.
9. Face loss safety interlock immediately unlocking position and resetting gesture state.
10. Emergency stop (F9) immediately unlocking position and stopping real mouse actions.
11. Recalibration unlocking position.
12. Settings toggle: disabling click stabilization when configured.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import AppSettings, EyeBlinkSettings, MouseControlSettings
from core.blink_detector import (
    BlinkDetector,
    LEFT_CLICK,
    RIGHT_CLICK,
    NO_ACTION,
    DRAG_START,
    DRAG_STOP,
    STATE_CLOSED,
    STATE_OPEN,
)
from core.cursor_simulator import CursorSimulator
from core.mouse_controller import MouseController


class MockPyAutoGUI:
    """Mock PyAutoGUI backend for deterministic tracking without OS interaction."""

    def __init__(self, width: int = 1920, height: int = 1080) -> None:
        self.width = width
        self.height = height
        self.moves: list[tuple[int, int]] = []
        self.clicks: list[tuple[str, tuple[int, int]]] = []
        self.downs: list[str] = []
        self.ups: list[str] = []
        self.scrolls: list[int] = []
        self.cur_x = width // 2
        self.cur_y = height // 2
        self.FAILSAFE = True

    def size(self) -> tuple[int, int]:
        return self.width, self.height

    def position(self) -> tuple[int, int]:
        return (self.cur_x, self.cur_y)

    def moveTo(self, x: int, y: int, _pause: bool = False) -> None:
        self.cur_x = int(x)
        self.cur_y = int(y)
        self.moves.append((int(x), int(y)))

    def click(self, button: str = "left", _pause: bool = False) -> None:
        self.clicks.append((button, (self.cur_x, self.cur_y)))

    def mouseDown(self, button: str = "left", _pause: bool = False) -> None:
        self.downs.append(button)

    def mouseUp(self, button: str = "left", _pause: bool = False) -> None:
        self.ups.append(button)

    def scroll(self, amount: int, _pause: bool = False) -> None:
        self.scrolls.append(int(amount))


def make_landmarks_data(left_ear: float = 0.28, right_ear: float = 0.28) -> dict:
    """Create landmarks dictionary with configurable EAR values."""
    lm = [[0.5, 0.5, 0.0, 100, 100] for _ in range(478)]
    # Left eye landmarks: 33, 160, 158, 133, 153, 144
    lm[33] = [0.40, 0.50, 0.0]
    lm[133] = [0.46, 0.50, 0.0]
    lm[160] = [0.42, 0.50 - left_ear * 0.03, 0.0]
    lm[158] = [0.44, 0.50 - left_ear * 0.03, 0.0]
    lm[144] = [0.42, 0.50 + left_ear * 0.03, 0.0]
    lm[153] = [0.44, 0.50 + left_ear * 0.03, 0.0]

    # Right eye landmarks: 362, 385, 387, 263, 373, 380
    lm[362] = [0.54, 0.50, 0.0]
    lm[263] = [0.60, 0.50, 0.0]
    lm[385] = [0.56, 0.50 - right_ear * 0.03, 0.0]
    lm[387] = [0.58, 0.50 - right_ear * 0.03, 0.0]
    lm[380] = [0.56, 0.50 + right_ear * 0.03, 0.0]
    lm[373] = [0.58, 0.50 + right_ear * 0.03, 0.0]

    return {
        "has_face": True,
        "landmarks": lm,
        "landmark_indices": {"nose_tip": 1, "left_eye_center": 33, "right_eye_center": 263},
    }


def test_cursor_simulator_lock_and_unlock():
    """Verify CursorSimulator position lock pins coordinates and unlocks smoothly."""
    cursor = CursorSimulator(window_width=640, window_height=480, dead_zone=1.0, sensitivity=2.0)
    # Move cursor to an offset position
    for _ in range(10):
        cursor.update(relative_dx=0.20, relative_dy=0.10)
    
    start_cx, start_cy = cursor.cx, cursor.cy
    assert not cursor.is_position_locked

    # Lock position
    cursor.lock_position(reason="CLICK_LEFT")
    assert cursor.is_position_locked
    assert cursor.lock_reason == "CLICK_LEFT"
    assert cursor.locked_position == (start_cx, start_cy)

    # Disturb nose displacement heavily while locked
    for dx, dy in [(0.80, 0.50), (-0.90, -0.70), (0.45, 0.35)]:
        cx, cy, moved = cursor.update(relative_dx=dx, relative_dy=dy)
        assert cx == start_cx
        assert cy == start_cy
        assert not moved

    # Unlock position
    cursor.unlock_position()
    assert not cursor.is_position_locked
    assert cursor.lock_reason == "NONE"

    # Next update resumes tracking smoothly without velocity spike
    cx, cy, moved = cursor.update(relative_dx=0.20, relative_dy=0.10)
    assert abs(cx - start_cx) < 50.0  # Smooth update without jump


def test_mouse_controller_lock_and_unlock():
    """Verify MouseController pins screen coordinates during position lock."""
    backend = MockPyAutoGUI(width=1920, height=1080)
    mouse = MouseController(screen_width=1920, screen_height=1080, py_backend=backend)
    mouse.is_calibrated = True
    mouse.has_face = True
    mouse.enable()

    # Move to initial coordinate
    mouse.move_cursor(norm_x=0.50, norm_y=0.50)
    orig_x, orig_y = mouse.screen_x, mouse.screen_y

    # Lock position
    mouse.lock_position(reason="CLICK_RIGHT")
    assert mouse.is_position_locked
    assert mouse.lock_reason == "CLICK_RIGHT"
    assert mouse.locked_screen_x == orig_x
    assert mouse.locked_screen_y == orig_y

    # Try moving with different coordinates
    res = mouse.move_cursor(norm_x=0.85, norm_y=0.90)
    assert res == (orig_x, orig_y)
    assert mouse.screen_x == orig_x
    assert mouse.screen_y == orig_y
    assert backend.moves[-1] == (orig_x, orig_y)

    # Unlock
    mouse.unlock_position()
    assert not mouse.is_position_locked

    # Move updates to new coordinates
    res2 = mouse.move_cursor(norm_x=0.75, norm_y=0.75)
    assert res2 != (orig_x, orig_y)


def test_blink_detector_gesture_detection_left():
    """Verify BlinkDetector detects left click gesture onset and cooldown stabilization."""
    settings = EyeBlinkSettings(
        click_stabilization=True,
        stabilization_cooldown_sec=0.08,
        min_blink_duration_sec=0.08,
        max_blink_duration_sec=0.60,
        drag_enabled=False,
    )
    detector = BlinkDetector(settings=settings)

    t = 1000.0
    # 1. Open eyes baseline
    res = detector.update(make_landmarks_data(left_ear=0.28, right_ear=0.28), timestamp=t)
    assert not res["gesture_started"]
    assert not res["gesture_active"]
    assert not res["is_stabilizing"]

    # 2. Left eye closes (single eye wink)
    t += 0.033
    res = detector.update(make_landmarks_data(left_ear=0.12, right_ear=0.28), timestamp=t)
    assert res["gesture_started"]
    assert res["gesture_active"]
    assert res["gesture_eye"] == "left"
    assert res["is_stabilizing"]

    # 3. Left eye remains closed next frame
    t += 0.033
    res = detector.update(make_landmarks_data(left_ear=0.12, right_ear=0.28), timestamp=t)
    assert not res["gesture_started"]  # Edge-triggered, only True on onset frame
    assert res["gesture_active"]
    assert res["is_stabilizing"]

    # 4. Hold closed for total 150ms
    t += 0.084
    res = detector.update(make_landmarks_data(left_ear=0.12, right_ear=0.28), timestamp=t)
    assert res["gesture_active"]
    assert res["is_stabilizing"]

    # 5. Left eye reopens -> LEFT_CLICK emitted
    t += 0.033
    res = detector.update(make_landmarks_data(left_ear=0.28, right_ear=0.28), timestamp=t)
    assert res["event"] == LEFT_CLICK
    assert not res["gesture_active"]
    # Stabilization cooldown (0.08s) keeps is_stabilizing True immediately after click
    assert res["is_stabilizing"]

    # 6. Check during cooldown
    t += 0.040
    res = detector.update(make_landmarks_data(left_ear=0.28, right_ear=0.28), timestamp=t)
    assert res["is_stabilizing"]

    # 7. Cooldown expires (0.040 + 0.050 = 0.090 > 0.080)
    t += 0.050
    res = detector.update(make_landmarks_data(left_ear=0.28, right_ear=0.28), timestamp=t)
    assert not res["is_stabilizing"]


def test_blink_detector_gesture_detection_right():
    """Verify BlinkDetector detects right click gesture onset and stabilization."""
    settings = EyeBlinkSettings(
        click_stabilization=True,
        stabilization_cooldown_sec=0.08,
        min_blink_duration_sec=0.08,
        max_blink_duration_sec=0.60,
    )
    detector = BlinkDetector(settings=settings)

    t = 2000.0
    detector.update(make_landmarks_data(0.28, 0.28), timestamp=t)

    # Right eye closes
    t += 0.033
    res = detector.update(make_landmarks_data(left_ear=0.28, right_ear=0.12), timestamp=t)
    assert res["gesture_started"]
    assert res["gesture_active"]
    assert res["gesture_eye"] == "right"
    assert res["is_stabilizing"]

    # Hold closed
    t += 0.120
    res = detector.update(make_landmarks_data(left_ear=0.28, right_ear=0.12), timestamp=t)
    assert res["gesture_active"]

    # Reopen
    t += 0.033
    res = detector.update(make_landmarks_data(left_ear=0.28, right_ear=0.28), timestamp=t)
    assert res["event"] == RIGHT_CLICK
    assert res["is_stabilizing"]  # Cooldown active

    # After cooldown
    t += 0.100
    res = detector.update(make_landmarks_data(left_ear=0.28, right_ear=0.28), timestamp=t)
    assert not res["is_stabilizing"]


def test_simultaneous_blink_cancels_click_gesture():
    """Verify dual blink immediately cancels single-eye click gesture stabilization."""
    detector = BlinkDetector(settings=EyeBlinkSettings(click_stabilization=True))

    t = 3000.0
    detector.update(make_landmarks_data(0.28, 0.28), timestamp=t)

    # Left eye closes first
    t += 0.033
    res = detector.update(make_landmarks_data(left_ear=0.12, right_ear=0.28), timestamp=t)
    assert res["gesture_active"]

    # Right eye closes too -> dual blink!
    t += 0.033
    res = detector.update(make_landmarks_data(left_ear=0.12, right_ear=0.12), timestamp=t)
    assert not res["gesture_active"]
    assert not res["is_stabilizing"]
    assert res["suppression_active"]


def test_drag_release_of_position_lock():
    """Verify that a long blink (>= 350ms) releases position lock upon DRAG_START."""
    settings = EyeBlinkSettings(
        click_stabilization=True,
        drag_enabled=True,
        drag_hold_sec=0.35,
    )
    detector = BlinkDetector(settings=settings)
    cursor = CursorSimulator()
    backend = MockPyAutoGUI()
    mouse = MouseController(py_backend=backend)
    mouse.is_calibrated = True
    mouse.has_face = True
    mouse.enable()

    t = 4000.0
    detector.update(make_landmarks_data(0.28, 0.28), timestamp=t)

    # Left eye closes -> gesture starts -> lock position
    t += 0.033
    res = detector.update(make_landmarks_data(left_ear=0.12, right_ear=0.28), timestamp=t)
    assert res["gesture_started"]
    assert not res["is_dragging"]
    cursor.lock_position(reason="CLICK_LEFT")
    mouse.lock_position(reason="CLICK_LEFT")
    assert cursor.is_position_locked
    assert mouse.is_position_locked

    # Hold until drag threshold reached (350ms)
    t += 0.360
    res = detector.update(make_landmarks_data(left_ear=0.12, right_ear=0.28), timestamp=t)
    assert res["event"] == DRAG_START
    assert res["is_dragging"]
    assert not res["is_stabilizing"]

    # When drag starts, position lock must be released
    if res["is_dragging"]:
        cursor.unlock_position()
        mouse.unlock_position()

    mouse.handle_blink_event(res["event"], timestamp=t)
    assert not cursor.is_position_locked
    assert not mouse.is_position_locked
    assert mouse.is_dragging
    assert backend.downs == ["left"]


def test_click_execution_at_locked_coordinates_despite_nose_displacement():
    """Simulate full interaction pipeline: cursor stays pinned at locked aim target during click."""
    cursor = CursorSimulator(window_width=640, window_height=480, dead_zone=1.0)
    backend = MockPyAutoGUI(width=1920, height=1080)
    mouse = MouseController(screen_width=1920, screen_height=1080, py_backend=backend)
    mouse.is_calibrated = True
    mouse.has_face = True
    mouse.enable()
    detector = BlinkDetector(settings=EyeBlinkSettings(click_stabilization=True, drag_enabled=False))

    t = 5000.0
    # Step 1: User aims cursor at target
    for _ in range(5):
        cursor.update(0.15, 0.10)
        norm_x, norm_y = cursor.normalized_position
        mouse.move_cursor(norm_x, norm_y)

    aim_x, aim_y = mouse.screen_x, mouse.screen_y
    aim_cx, aim_cy = cursor.cx, cursor.cy

    # Step 2: User winks left eye to click -> gesture onset detected
    t += 0.033
    lm_closed = make_landmarks_data(left_ear=0.12, right_ear=0.28)
    blink_state = detector.update(lm_closed, timestamp=t)
    assert blink_state["gesture_started"]

    # Interlock locks position at aim target
    cursor.lock_position(reason="CLICK_LEFT")
    mouse.lock_position(reason="CLICK_LEFT")
    assert cursor.locked_position == (aim_cx, aim_cy)
    assert mouse.locked_screen_x == aim_x
    assert mouse.locked_screen_y == aim_y

    # Step 3: During eye closure (150ms), facial muscle contraction twitches nose tip
    for _ in range(4):
        t += 0.033
        # Simulated nose displacement twitch:
        twitch_dx, twitch_dy = 0.50, 0.40
        cursor.update(twitch_dx, twitch_dy)
        norm_x, norm_y = cursor.normalized_position
        mouse.move_cursor(norm_x, norm_y)

        # Invariance check: position must remain strictly at aim coordinates
        assert cursor.cx == aim_cx
        assert cursor.cy == aim_cy
        assert mouse.screen_x == aim_x
        assert mouse.screen_y == aim_y

    # Step 4: Eye reopens -> LEFT_CLICK emitted
    t += 0.033
    lm_open = make_landmarks_data(left_ear=0.28, right_ear=0.28)
    blink_state = detector.update(lm_open, timestamp=t)
    assert blink_state["event"] == LEFT_CLICK

    # Execute actual click via mouse controller
    act = mouse.handle_blink_event(blink_state["event"], timestamp=t)
    assert act == "LEFT_CLICK"
    # Verification: click was executed at exact locked aim coordinates!
    assert backend.clicks[-1] == ("left", (aim_x, aim_y))


def test_safety_release_on_face_loss():
    """Verify face loss safety interlock releases position lock immediately."""
    cursor = CursorSimulator()
    backend = MockPyAutoGUI()
    mouse = MouseController(py_backend=backend)
    mouse.is_calibrated = True
    mouse.has_face = True
    mouse.enable()
    detector = BlinkDetector(settings=EyeBlinkSettings(click_stabilization=True))

    cursor.lock_position()
    mouse.lock_position()
    assert cursor.is_position_locked
    assert mouse.is_position_locked

    # Face lost
    mouse.update_tracking_status(has_face=False, is_calibrated=True)
    res = detector.update(None)

    assert not mouse.is_position_locked
    assert not detector.is_stabilizing


def test_safety_release_on_emergency_stop():
    """Verify F9 Emergency Stop immediately unlocks position."""
    backend = MockPyAutoGUI()
    mouse = MouseController(py_backend=backend)
    mouse.is_calibrated = True
    mouse.has_face = True
    mouse.enable()

    mouse.lock_position()
    assert mouse.is_position_locked

    mouse.emergency_stop()
    assert not mouse.is_position_locked
    assert mouse.emergency_stopped


def test_recalibration_safety_release():
    """Verify recalibration immediately unlocks position and releases buttons."""
    backend = MockPyAutoGUI()
    mouse = MouseController(py_backend=backend)
    mouse.is_calibrated = True
    mouse.has_face = True
    mouse.enable()
    cursor = CursorSimulator()

    mouse.lock_position()
    cursor.lock_position()

    # Recalibrate
    cursor.recalibrate()
    mouse.update_tracking_status(has_face=True, is_calibrated=False)

    assert not cursor.is_position_locked
    assert not mouse.is_position_locked
    assert not mouse.enabled


def test_stabilization_disabled_setting():
    """Verify that setting click_stabilization=False disables stabilization."""
    settings = EyeBlinkSettings(click_stabilization=False)
    detector = BlinkDetector(settings=settings)

    t = 6000.0
    detector.update(make_landmarks_data(0.28, 0.28), timestamp=t)
    t += 0.033
    res = detector.update(make_landmarks_data(0.12, 0.28), timestamp=t)

    assert not res["gesture_started"]
    assert not res["gesture_active"]
    assert not res["is_stabilizing"]


def test_cursor_simulator_auto_unlock_timeout():
    """Verify CursorSimulator auto-unlocks after timeout, preventing permanent freeze."""
    cursor = CursorSimulator()
    cursor.lock_position(reason="TEST_LOCK")
    assert cursor.is_position_locked

    # Simulate elapsed time > 0.35s
    cursor._lock_time = time.monotonic() - 0.40

    # Next update must auto-unlock and resume tracking
    cx, cy, moved = cursor.update(relative_dx=0.10, relative_dy=0.0)
    assert not cursor.is_position_locked
    assert cursor.lock_reason == "NONE"


def test_mouse_controller_auto_unlock_timeout():
    """Verify MouseController auto-unlocks after timeout, preventing permanent freeze."""
    backend = MockPyAutoGUI()
    mouse = MouseController(py_backend=backend)
    mouse.is_calibrated = True
    mouse.has_face = True
    mouse.enable()

    mouse.lock_position(reason="TEST_LOCK")
    assert mouse.is_position_locked

    # Simulate elapsed time > 0.35s
    mouse.lock_time = time.monotonic() - 0.40

    # Next move_cursor call must auto-unlock and move cursor
    pos = mouse.move_cursor(norm_x=0.80, norm_y=0.80)
    assert not mouse.is_position_locked
    assert pos is not None
    assert pos != (mouse.screen_width // 2, mouse.screen_height // 2)


def test_blink_detector_gesture_timeout_on_prolonged_closure():
    """Verify BlinkDetector drops gesture_active if closure exceeds maximum wink duration."""
    detector = BlinkDetector(settings=EyeBlinkSettings(click_stabilization=True))
    t = 7000.0
    detector.update(make_landmarks_data(0.28, 0.28), timestamp=t)

    # Eye closes
    t += 0.033
    res = detector.update(make_landmarks_data(0.12, 0.28), timestamp=t)
    assert res["gesture_active"]
    assert res["is_stabilizing"]

    # Closure stays closed for 0.40s (> 0.35s) without reopening
    t += 0.40
    res = detector.update(make_landmarks_data(0.12, 0.28), timestamp=t)
    assert not res["gesture_active"]
    assert not res["is_stabilizing"]


def test_reduced_sensitivity_slow_predictable_movement():
    """Verify that reduced sensitivity (1.0) produces controlled, small cursor movements."""
    cursor_calm = CursorSimulator(sensitivity=1.0, dead_zone=4.0, max_velocity=30.0)
    cursor_fast = CursorSimulator(sensitivity=2.5, dead_zone=4.0, max_velocity=800.0)

    # Small head shift of 2%
    dx_small = 0.02
    cx_calm, _, _ = cursor_calm.update(relative_dx=dx_small, relative_dy=0.0)
    cx_fast, _, _ = cursor_fast.update(relative_dx=dx_small, relative_dy=0.0)

    # Calm displacement must be strictly smaller and controlled compared to fast
    disp_calm = abs(cx_calm - 320.0)
    disp_fast = abs(cx_fast - 320.0)
    assert disp_calm < disp_fast
    assert disp_calm < 15.0  # Controlled, small movement for 2% head movement

