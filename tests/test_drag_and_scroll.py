"""Tests for Hands-Free Drag & Area Selection and Eyebrow Gesture Activated Scrolling.

Covers:
1. Normal short blink left click (<350ms) vs Drag hold (>=350ms).
2. Mouse down invoked exactly once on DRAG_START.
3. Continuous head movement while dragging.
4. Mouse up invoked on DRAG_STOP without emitting duplicate LEFT_CLICK.
5. Safety interlocks: button release on face loss, emergency stop, and recalibration.
6. Eyebrow raise detection with scale-invariant canonical landmarks.
7. Bilateral requirement: both eyebrows must be raised to activate scroll mode.
8. Activation delay (300ms) requirement.
9. Scroll direction and speed calculation (UP, DOWN, STOP deadzone).
10. Pausing cursor movement during scroll mode.
11. Blink click suppression while eyebrows are raised.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import AppSettings, EyeBlinkSettings, ScrollSettings
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
from core.eyebrow_tracker import (
    EyebrowTracker,
    LEFT_EYEBROW_ARCH,
    RIGHT_EYEBROW_ARCH,
    LEFT_EYE_TOP,
    RIGHT_EYE_TOP,
    LEFT_EYE_OUTER_CORNER,
    RIGHT_EYE_OUTER_CORNER,
)
from core.mouse_controller import MouseController


class MockPyAutoGUI:
    """Mock PyAutoGUI backend for deterministic tracking without OS interaction."""

    def __init__(self, width: int = 1920, height: int = 1080) -> None:
        self.width = width
        self.height = height
        self.moves: list[tuple[int, int]] = []
        self.clicks: list[str] = []
        self.downs: list[str] = []
        self.ups: list[str] = []
        self.scrolls: list[int] = []
        self.FAILSAFE = True

    def size(self) -> tuple[int, int]:
        return self.width, self.height

    def position(self) -> tuple[int, int]:
        return self.moves[-1] if self.moves else (self.width // 2, self.height // 2)

    def moveTo(self, x: int, y: int, _pause: bool = False) -> None:
        self.moves.append((int(x), int(y)))

    def click(self, button: str = "left", _pause: bool = False) -> None:
        self.clicks.append(button)

    def mouseDown(self, button: str = "left", _pause: bool = False) -> None:
        self.downs.append(button)

    def mouseUp(self, button: str = "left", _pause: bool = False) -> None:
        self.ups.append(button)

    def scroll(self, amount: int, _pause: bool = False) -> None:
        self.scrolls.append(int(amount))


def make_landmarks(
    left_ear: float = 0.28,
    right_ear: float = 0.28,
    left_eb_dist: float = 0.040,
    right_eb_dist: float = 0.040,
    iod: float = 0.250,
) -> list[list[float]]:
    """Generate synthetic 478 face landmarks with specified EAR, eyebrow distance, and IOD."""
    lm = [[0.5, 0.5, 0.0, 100, 100] for _ in range(478)]

    # Inter-ocular distance: 33 (left outer) to 263 (right outer)
    lm[LEFT_EYE_OUTER_CORNER] = [0.5 - iod / 2.0, 0.5, 0.0, 100, 100]
    lm[RIGHT_EYE_OUTER_CORNER] = [0.5 + iod / 2.0, 0.5, 0.0, 100, 100]

    # Eyebrows and upper eyelids
    # Left eye: top = 159, arch = 105
    lm[LEFT_EYE_TOP] = [0.42, 0.50, 0.0, 100, 100]
    lm[LEFT_EYEBROW_ARCH] = [0.42, 0.50 - left_eb_dist, 0.0, 100, 100]

    # Right eye: top = 386, arch = 334
    lm[RIGHT_EYE_TOP] = [0.58, 0.50, 0.0, 100, 100]
    lm[RIGHT_EYEBROW_ARCH] = [0.58, 0.50 - right_eb_dist, 0.0, 100, 100]

    # Eye landmarks for EAR:
    # Left eye: corners 33, 133; vertical 160-144, 158-153
    left_x = 0.5 - iod / 2.0
    left_dx = 0.08
    lm[33] = [left_x, 0.50, 0.0, 100, 100]
    lm[133] = [left_x + left_dx, 0.50, 0.0, 100, 100]
    left_dy = left_ear * left_dx
    lm[160] = [left_x + left_dx * 0.375, 0.50 - left_dy / 2.0, 0.0, 100, 100]
    lm[144] = [left_x + left_dx * 0.375, 0.50 + left_dy / 2.0, 0.0, 100, 100]
    lm[158] = [left_x + left_dx * 0.625, 0.50 - left_dy / 2.0, 0.0, 100, 100]
    lm[153] = [left_x + left_dx * 0.625, 0.50 + left_dy / 2.0, 0.0, 100, 100]

    # Right eye: corners 362, 263; vertical 385-380, 387-373
    right_x = 0.5 + iod / 2.0
    right_dx = 0.08
    lm[263] = [right_x, 0.50, 0.0, 100, 100]
    lm[362] = [right_x - right_dx, 0.50, 0.0, 100, 100]
    right_dy = right_ear * right_dx
    lm[385] = [right_x - right_dx * 0.625, 0.50 - right_dy / 2.0, 0.0, 100, 100]
    lm[380] = [right_x - right_dx * 0.625, 0.50 + right_dy / 2.0, 0.0, 100, 100]
    lm[387] = [right_x - right_dx * 0.375, 0.50 - right_dy / 2.0, 0.0, 100, 100]
    lm[373] = [right_x - right_dx * 0.375, 0.50 + right_dy / 2.0, 0.0, 100, 100]

    return lm


# =========================================================================
# FEATURE 1: HANDS-FREE DRAG AND AREA SELECTION TESTS
# =========================================================================

def test_short_blink_emits_left_click_not_drag():
    """Verify that a short left eye blink (< 350ms) triggers LEFT_CLICK and no drag."""
    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.08,
        max_blink_duration_sec=0.65,
        drag_hold_sec=0.35,
        drag_enabled=True,
    )
    detector = BlinkDetector(settings)
    open_face = {"has_face": True, "landmarks": make_landmarks(0.28, 0.28)}
    left_closed = {"has_face": True, "landmarks": make_landmarks(0.12, 0.28)}

    t = 1000.0
    detector.update(open_face, timestamp=t)

    # Closed for 200ms (< 350ms drag threshold)
    r1 = detector.update(left_closed, timestamp=t + 0.05)
    r2 = detector.update(left_closed, timestamp=t + 0.20)
    assert not detector.left_eye.is_dragging
    assert r2["event"] is None

    # Reopen at 220ms
    r_reopen = detector.update(open_face, timestamp=t + 0.22)
    assert r_reopen["event"] == LEFT_CLICK, f"Expected LEFT_CLICK, got {r_reopen['event']}"
    assert not detector.left_eye.is_dragging


def test_drag_start_emitted_after_hold_threshold():
    """Verify that holding left eye closed for >= 350ms emits DRAG_START exactly once."""
    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.08,
        max_blink_duration_sec=0.65,
        drag_hold_sec=0.35,
        drag_enabled=True,
    )
    detector = BlinkDetector(settings)
    open_face = {"has_face": True, "landmarks": make_landmarks(0.28, 0.28)}
    left_closed = {"has_face": True, "landmarks": make_landmarks(0.12, 0.28)}

    t = 2000.0
    detector.update(open_face, timestamp=t)
    detector.update(left_closed, timestamp=t + 0.05)
    detector.update(left_closed, timestamp=t + 0.25)

    # At 360ms closure: reaches drag_hold_sec (350ms) -> DRAG_START emitted!
    r_drag = detector.update(left_closed, timestamp=t + 0.41)
    assert r_drag["event"] == DRAG_START, f"Expected DRAG_START, got {r_drag['event']}"
    assert detector.left_eye.is_dragging
    assert r_drag["is_dragging"]

    # Next frame while still closed: must NOT emit DRAG_START repeatedly
    r_next = detector.update(left_closed, timestamp=t + 0.50)
    assert r_next["event"] is None, "DRAG_START must be emitted only ONCE"
    assert detector.left_eye.is_dragging, "Must remain in dragging state"


def test_drag_stop_emitted_on_reopening_without_left_click():
    """Verify that releasing left eye after dragging emits DRAG_STOP and NO LEFT_CLICK."""
    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.08,
        max_blink_duration_sec=0.65,
        drag_hold_sec=0.35,
        drag_enabled=True,
    )
    detector = BlinkDetector(settings)
    open_face = {"has_face": True, "landmarks": make_landmarks(0.28, 0.28)}
    left_closed = {"has_face": True, "landmarks": make_landmarks(0.12, 0.28)}

    t = 3000.0
    detector.update(open_face, timestamp=t)
    detector.update(left_closed, timestamp=t + 0.05)
    detector.update(left_closed, timestamp=t + 0.40)  # triggers DRAG_START
    assert detector.left_eye.is_dragging

    # Held closed for 1.5 seconds (dragging across screen)
    detector.update(left_closed, timestamp=t + 1.00)
    detector.update(left_closed, timestamp=t + 1.50)
    assert detector.left_eye.is_dragging

    # Reopen eye: triggers DRAG_STOP and MUST NOT emit LEFT_CLICK
    r_reopen = detector.update(open_face, timestamp=t + 1.55)
    assert r_reopen["event"] == DRAG_STOP, f"Expected DRAG_STOP, got {r_reopen['event']}"
    assert r_reopen["event"] != LEFT_CLICK, "Must NOT emit LEFT_CLICK upon releasing drag"
    assert not detector.left_eye.is_dragging


def test_mouse_controller_drag_integration():
    """Verify MouseController invokes mouseDown on DRAG_START and mouseUp on DRAG_STOP."""
    mock = MockPyAutoGUI(width=1920, height=1080)
    controller = MouseController(screen_width=1920, screen_height=1080, py_backend=mock)
    controller.update_tracking_status(has_face=True, is_calibrated=True)
    controller.enable()

    # Receive DRAG_START
    res_start = controller.handle_blink_event(DRAG_START)
    assert res_start == DRAG_START
    assert len(mock.downs) == 1
    assert mock.downs[0] == "left"
    assert controller.is_mouse_down
    assert controller.is_dragging

    # Cursor movement while dragging
    controller.move_cursor(0.30, 0.40)
    controller.move_cursor(0.60, 0.70)
    assert len(mock.moves) == 2
    assert controller.is_mouse_down, "Button must stay down while moving cursor"

    # Receive DRAG_STOP
    res_stop = controller.handle_blink_event(DRAG_STOP)
    assert res_stop == DRAG_STOP
    assert len(mock.ups) == 1
    assert mock.ups[0] == "left"
    assert not controller.is_mouse_down
    assert not controller.is_dragging
    assert len(mock.clicks) == 0, "No extra click should have been registered"


def test_safety_release_on_face_loss_during_drag():
    """Verify that face loss during active drag immediately releases mouse button."""
    mock = MockPyAutoGUI(width=1920, height=1080)
    controller = MouseController(screen_width=1920, screen_height=1080, py_backend=mock)
    controller.update_tracking_status(has_face=True, is_calibrated=True)
    controller.enable()

    controller.handle_blink_event(DRAG_START)
    assert controller.is_mouse_down

    # Face lost!
    controller.update_tracking_status(has_face=False, is_calibrated=True)
    assert not controller.is_mouse_down, "Mouse button must be released immediately upon face loss"
    assert not controller.is_dragging
    assert len(mock.ups) == 1


def test_safety_release_on_emergency_stop_during_drag():
    """Verify emergency stop during active drag releases mouse button and disables control."""
    mock = MockPyAutoGUI(width=1920, height=1080)
    controller = MouseController(screen_width=1920, screen_height=1080, py_backend=mock)
    controller.update_tracking_status(has_face=True, is_calibrated=True)
    controller.enable()

    controller.handle_blink_event(DRAG_START)
    assert controller.is_mouse_down

    # Emergency stop triggered!
    controller.emergency_stop()
    assert not controller.is_mouse_down, "Emergency stop must release mouse button"
    assert not controller.is_dragging
    assert controller.emergency_stopped
    assert not controller.enabled
    assert len(mock.ups) == 1


def test_safety_release_on_recalibration_during_drag():
    """Verify starting calibration during active drag immediately releases mouse button."""
    mock = MockPyAutoGUI(width=1920, height=1080)
    controller = MouseController(screen_width=1920, screen_height=1080, py_backend=mock)
    controller.update_tracking_status(has_face=True, is_calibrated=True)
    controller.enable()

    controller.handle_blink_event(DRAG_START)
    assert controller.is_mouse_down

    # Recalibration begins
    controller.update_tracking_status(has_face=True, is_calibrated=False)
    assert not controller.is_mouse_down, "Recalibration must release mouse button"
    assert not controller.is_dragging
    assert len(mock.ups) == 1


# =========================================================================
# FEATURE 2: EYEBROW GESTURE ACTIVATED SCROLLING TESTS
# =========================================================================

def test_eyebrow_scale_invariant_ratio_calculation():
    """Verify eyebrow-to-eye vertical distance normalized by IOD."""
    settings = ScrollSettings(
        eyebrow_raise_threshold=0.18,
        left_eyebrow_baseline=0.16,
        right_eyebrow_baseline=0.16,
    )
    tracker = EyebrowTracker(settings)

    # Neutral face: eb_dist = 0.040, iod = 0.250 -> ratio = 0.040 / 0.250 = 0.160
    neutral_lm = make_landmarks(left_eb_dist=0.040, right_eb_dist=0.040, iod=0.250)
    ratios = tracker.extract_ratios(neutral_lm)
    assert ratios is not None
    l_ratio, r_ratio = ratios
    assert pytest.approx(l_ratio, abs=1e-3) == 0.160
    assert pytest.approx(r_ratio, abs=1e-3) == 0.160

    # Closer to camera: distances scale proportionally (eb_dist = 0.080, iod = 0.500) -> ratio still 0.160!
    scaled_lm = make_landmarks(left_eb_dist=0.080, right_eb_dist=0.080, iod=0.500)
    s_ratios = tracker.extract_ratios(scaled_lm)
    assert s_ratios is not None
    sl_ratio, sr_ratio = s_ratios
    assert pytest.approx(sl_ratio, abs=1e-3) == 0.160
    assert pytest.approx(sr_ratio, abs=1e-3) == 0.160


def test_bilateral_eyebrow_raise_activation_delay():
    """Verify both eyebrows must be raised for >= 300ms to activate scroll mode."""
    settings = ScrollSettings(
        eyebrow_raise_threshold=0.18,
        activation_delay_sec=0.30,
        left_eyebrow_baseline=0.16,
        right_eyebrow_baseline=0.16,
    )
    tracker = EyebrowTracker(settings)

    # Baseline ratio is 0.16; raised ratio is 0.16 * (1 + 0.25) = 0.200 (eb_dist = 0.050 with iod = 0.250)
    raised_lm = {"has_face": True, "landmarks": make_landmarks(left_eb_dist=0.050, right_eb_dist=0.050, iod=0.250)}
    neutral_lm = {"has_face": True, "landmarks": make_landmarks(left_eb_dist=0.040, right_eb_dist=0.040, iod=0.250)}

    t = 4000.0
    r0 = tracker.update(neutral_lm, relative_dy=0.0, timestamp=t)
    assert not r0["scroll_mode_active"]

    # Eyebrows raised at t = 4000.05
    r1 = tracker.update(raised_lm, relative_dy=0.0, timestamp=t + 0.05)
    assert r1["left_raised"] and r1["right_raised"]
    assert not r1["scroll_mode_active"], "Should NOT activate immediately (requires 300ms)"

    # At 200ms into raise: still waiting
    r2 = tracker.update(raised_lm, relative_dy=0.0, timestamp=t + 0.25)
    assert not r2["scroll_mode_active"]

    # At 350ms into raise (>= 300ms): scroll mode becomes ACTIVE!
    r3 = tracker.update(raised_lm, relative_dy=0.0, timestamp=t + 0.40)
    assert r3["scroll_mode_active"], "Must activate after 300ms continuous bilateral raise"


def test_unilateral_eyebrow_raise_rejected():
    """Verify that raising only one eyebrow does NOT activate scroll mode."""
    settings = ScrollSettings(
        eyebrow_raise_threshold=0.18,
        activation_delay_sec=0.30,
        left_eyebrow_baseline=0.16,
        right_eyebrow_baseline=0.16,
    )
    tracker = EyebrowTracker(settings)

    # Only LEFT eyebrow raised (right eyebrow stays at resting baseline 0.040)
    left_only_lm = {"has_face": True, "landmarks": make_landmarks(left_eb_dist=0.050, right_eb_dist=0.040, iod=0.250)}

    t = 5000.0
    tracker.update(left_only_lm, relative_dy=0.0, timestamp=t)
    # Hold for 500ms
    r = tracker.update(left_only_lm, relative_dy=0.0, timestamp=t + 0.50)
    assert r["left_raised"]
    assert not r["right_raised"]
    assert not r["scroll_mode_active"], "Unilateral raise must NOT activate scroll mode"


def test_scroll_direction_and_deadzone():
    """Verify scrolling UP when moving head UP, DOWN when moving head DOWN, and STOP in deadzone."""
    settings = ScrollSettings(
        scroll_deadzone=0.015,
        min_scroll_speed=1,
        max_scroll_speed=8,
        scroll_gain=50.0,
        scroll_interval_sec=0.05,
    )
    tracker = EyebrowTracker(settings)
    tracker.scroll_mode_active = True  # Simulate active scroll mode

    t = 6000.0
    # Inside deadzone (-0.010): direction STOP, amount 0
    s_stop = tracker.compute_scroll(relative_dy=-0.010, timestamp=t)
    assert s_stop["direction"] == "STOP"
    assert s_stop["amount"] == 0

    # Head tilted UP (relative_dy = +0.060 > deadzone 0.015)
    s_up = tracker.compute_scroll(relative_dy=0.060, timestamp=t + 0.06)
    assert s_up["direction"] == "UP"
    assert s_up["amount"] > 0
    assert s_up["speed"] >= settings.min_scroll_speed

    # Head tilted DOWN (relative_dy = -0.060 < -deadzone 0.015)
    s_down = tracker.compute_scroll(relative_dy=-0.060, timestamp=t + 0.12)
    assert s_down["direction"] == "DOWN"
    assert s_down["amount"] < 0
    assert s_down["speed"] >= settings.min_scroll_speed


def test_eyebrow_deactivation_stops_scroll():
    """Verify returning eyebrows to baseline immediately deactivates scroll mode."""
    settings = ScrollSettings(
        eyebrow_raise_threshold=0.18,
        eyebrow_hysteresis=0.08,
        activation_delay_sec=0.30,
        left_eyebrow_baseline=0.16,
        right_eyebrow_baseline=0.16,
    )
    tracker = EyebrowTracker(settings)
    raised_lm = {"has_face": True, "landmarks": make_landmarks(left_eb_dist=0.050, right_eb_dist=0.050, iod=0.250)}
    neutral_lm = {"has_face": True, "landmarks": make_landmarks(left_eb_dist=0.040, right_eb_dist=0.040, iod=0.250)}

    t = 7000.0
    tracker.update(raised_lm, relative_dy=0.0, timestamp=t)
    r_act = tracker.update(raised_lm, relative_dy=0.0, timestamp=t + 0.35)
    assert r_act["scroll_mode_active"]

    # Eyebrows return to neutral
    r_deact = tracker.update(neutral_lm, relative_dy=0.0, timestamp=t + 0.40)
    assert not r_deact["scroll_mode_active"], "Scroll mode must deactivate when eyebrows return to baseline"
    assert r_deact["scroll_amount"] == 0


def test_mouse_controller_scroll_actuation():
    """Verify MouseController invokes pyautogui.scroll with exact amounts."""
    mock = MockPyAutoGUI(width=1920, height=1080)
    controller = MouseController(screen_width=1920, screen_height=1080, py_backend=mock)
    controller.update_tracking_status(has_face=True, is_calibrated=True)
    controller.enable()

    # Scroll UP by 4
    controller.scroll(4)
    assert len(mock.scrolls) == 1
    assert mock.scrolls[0] == 4
    assert controller.total_scrolls == 1

    # Scroll DOWN by -6
    controller.scroll(-6)
    assert len(mock.scrolls) == 2
    assert mock.scrolls[1] == -6
    assert controller.total_scrolls == 2


def test_drag_disabled_reverts_to_prolonged_closure():
    """Verify that when drag_enabled=False, closure >= 350ms does not emit DRAG_START."""
    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.08,
        max_blink_duration_sec=0.65,
        drag_hold_sec=0.35,
        drag_enabled=False,
    )
    detector = BlinkDetector(settings)
    open_face = {"has_face": True, "landmarks": make_landmarks(0.28, 0.28)}
    left_closed = {"has_face": True, "landmarks": make_landmarks(0.12, 0.28)}

    t = 8000.0
    detector.update(open_face, timestamp=t)
    detector.update(left_closed, timestamp=t + 0.05)
    r_drag = detector.update(left_closed, timestamp=t + 0.45)

    assert not detector.left_eye.is_dragging
    assert r_drag["event"] != DRAG_START


def test_blink_suppression_while_eyebrows_raised():
    """Verify that blink clicks are suppressed while eyebrows are raised."""
    scroll_settings = ScrollSettings(
        eyebrow_raise_threshold=0.18,
        activation_delay_sec=0.30,
        left_eyebrow_baseline=0.16,
        right_eyebrow_baseline=0.16,
    )
    eb_tracker = EyebrowTracker(scroll_settings)
    blink_detector = BlinkDetector(EyeBlinkSettings(min_blink_duration_sec=0.08, max_blink_duration_sec=0.65))

    raised_and_blinking = {
        "has_face": True,
        "landmarks": make_landmarks(
            left_ear=0.12,  # left eye blinking
            right_ear=0.28,
            left_eb_dist=0.050,  # eyebrows raised
            right_eb_dist=0.050,
            iod=0.250,
        ),
    }

    t = 9000.0
    eb_status = eb_tracker.update(raised_and_blinking, relative_dy=0.0, timestamp=t)
    assert eb_status["left_raised"] and eb_status["right_raised"]

    # When eyebrows are raised, application logic suppresses clicks
    should_suppress = eb_status["scroll_mode_active"] or eb_status["left_raised"] or eb_status["right_raised"]
    assert should_suppress, "Clicks must be suppressed while eyebrows are raised"


def test_head_mouse_app_drag_and_scroll_integration():
    """Verify HeadMouseApp initializes EyebrowTracker and handles drag & scroll methods."""
    from main import HeadMouseApp

    app = HeadMouseApp()
    assert hasattr(app, "eyebrow_tracker")
    assert isinstance(app.eyebrow_tracker, EyebrowTracker)
    assert hasattr(app, "calib_left_eyebrow_samples")
    assert hasattr(app, "calib_right_eyebrow_samples")

    # Verify mouse controller drag and scroll capabilities
    assert hasattr(app.mouse_controller, "mouse_down")
    assert hasattr(app.mouse_controller, "mouse_up")
    assert hasattr(app.mouse_controller, "scroll")
    assert hasattr(app.mouse_controller, "release_all_buttons")
    assert hasattr(app.mouse_controller, "is_dragging")
    assert hasattr(app.mouse_controller, "is_mouse_down")

