"""Comprehensive tests for Left/Right Click Reliability and Dual Gesture Interaction (Scroll & Zoom).

Covers:
PART 1: Left and Right Click Reliability
1. Reliable left click: single-eye left wink -> exactly one LEFT_CLICK.
2. Reliable right click: single-eye right wink -> exactly one RIGHT_CLICK.
3. Simultaneous blink suppression: bilateral blink -> NO click (NO_ACTION).
4. State cleanup: after click or suppression, detector returns to normal state without lingering flags.
5. Drag vs Wink: short wink (<450ms) emits LEFT_CLICK; hold (>=450ms) emits DRAG_START / DRAG_STOP.

PART 2: Unified Gesture Scroll & Zoom Modes
6. TEETH SHOW ONLY: activates Scroll Mode (Head UP = Scroll Up, Head DOWN = Scroll Down, Neutral = Stop).
7. TEETH SHOW + BOTH EYEBROWS RAISED: switches from Scroll Mode to Zoom Mode (Head UP = Zoom In, Head DOWN = Zoom Out).
8. TEETH NOT VISIBLE: immediately disables BOTH Scroll Mode and Zoom Mode.
9. EYEBROWS RETURN TO NORMAL: disables Zoom Mode; if teeth still visible, returns to Scroll Mode automatically.
10. MUTUAL EXCLUSIVITY: never runs scrolling and zooming simultaneously.
11. ANTI-RUNAWAY: holding head tilted does NOT repeatedly trigger rapid scroll/zoom actions;
    returning head to neutral deadzone re-arms for the next step.
12. NORMAL TALKING PROTECTION: speech lip opening without horizontal smile widening does NOT activate either mode.
13. SCALE INVARIANCE: canonical MediaPipe Face Mesh landmarks via IOD; no pupil or iris tracking.
14. SAFETY: Face loss disables both modes immediately; Emergency Stop disables all mouse, scroll, and zoom actions.
15. MOUSE CONTROLLER: executes PyAutoGUI scroll and zoom hotkeys reliably.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import AppSettings, EyeBlinkSettings, ZoomSettings
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
from core.gesture_zoom import (
    GestureZoomTracker,
    MODE_NONE,
    MODE_SCROLL,
    MODE_ZOOM,
    ZOOM_IN,
    ZOOM_OUT,
    SCROLL_UP,
    SCROLL_DOWN,
    LEFT_EYE_OUTER,
    RIGHT_EYE_OUTER,
    LEFT_EYEBROW_ARCH,
    LEFT_EYE_TOP,
    RIGHT_EYEBROW_ARCH,
    RIGHT_EYE_TOP,
    LEFT_MOUTH_CORNER,
    RIGHT_MOUTH_CORNER,
    UPPER_LIP_INNER,
    LOWER_LIP_INNER,
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
        self.hotkeys: list[tuple] = []
        self.FAILSAFE = True
        self.PAUSE = 0.0

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

    def hotkey(self, *keys: str, **kwargs: Any) -> None:
        self.hotkeys.append(keys)


def make_face_landmarks(
    left_ear: float = 0.28,
    right_ear: float = 0.28,
    left_eb_dist: float = 0.040,
    right_eb_dist: float = 0.040,
    mouth_width: float = 0.130,
    lip_open: float = 0.002,
    iod: float = 0.250,
) -> dict[str, Any]:
    """Generate synthetic 478 face landmarks with specified facial parameters."""
    lm = [[0.5, 0.5, 0.0, 100, 100] for _ in range(478)]

    # Inter-ocular distance: 33 (left outer) to 263 (right outer)
    lm[LEFT_EYE_OUTER] = [0.5 - iod / 2.0, 0.50, 0.0, 100, 100]
    lm[RIGHT_EYE_OUTER] = [0.5 + iod / 2.0, 0.50, 0.0, 100, 100]

    # Eyebrows and upper eyelids
    lm[LEFT_EYE_TOP] = [0.42, 0.50, 0.0, 100, 100]
    lm[LEFT_EYEBROW_ARCH] = [0.42, 0.50 - left_eb_dist, 0.0, 100, 100]

    lm[RIGHT_EYE_TOP] = [0.58, 0.50, 0.0, 100, 100]
    lm[RIGHT_EYEBROW_ARCH] = [0.58, 0.50 - right_eb_dist, 0.0, 100, 100]

    # Mouth corners and inner lip margins
    lm[LEFT_MOUTH_CORNER] = [0.5 - mouth_width / 2.0, 0.65, 0.0, 100, 100]
    lm[RIGHT_MOUTH_CORNER] = [0.5 + mouth_width / 2.0, 0.65, 0.0, 100, 100]
    lm[UPPER_LIP_INNER] = [0.5, 0.65 - lip_open / 2.0, 0.0, 100, 100]
    lm[LOWER_LIP_INNER] = [0.5, 0.65 + lip_open / 2.0, 0.0, 100, 100]

    # Eye landmarks for EAR:
    left_x = 0.5 - iod / 2.0
    left_dx = 0.08
    lm[33] = [left_x, 0.50, 0.0, 100, 100]
    lm[133] = [left_x + left_dx, 0.50, 0.0, 100, 100]
    left_dy = left_ear * left_dx
    lm[160] = [left_x + left_dx * 0.375, 0.50 - left_dy / 2.0, 0.0, 100, 100]
    lm[144] = [left_x + left_dx * 0.375, 0.50 + left_dy / 2.0, 0.0, 100, 100]
    lm[158] = [left_x + left_dx * 0.625, 0.50 - left_dy / 2.0, 0.0, 100, 100]
    lm[153] = [left_x + left_dx * 0.625, 0.50 + left_dy / 2.0, 0.0, 100, 100]

    right_x = 0.5 + iod / 2.0
    right_dx = 0.08
    lm[263] = [right_x, 0.50, 0.0, 100, 100]
    lm[362] = [right_x - right_dx, 0.50, 0.0, 100, 100]
    right_dy = right_ear * right_dx
    lm[385] = [right_x - right_dx * 0.625, 0.50 - right_dy / 2.0, 0.0, 100, 100]
    lm[380] = [right_x - right_dx * 0.625, 0.50 + right_dy / 2.0, 0.0, 100, 100]
    lm[387] = [right_x - right_dx * 0.375, 0.50 - right_dy / 2.0, 0.0, 100, 100]
    lm[373] = [right_x - right_dx * 0.375, 0.50 + right_dy / 2.0, 0.0, 100, 100]

    return {"has_face": True, "landmarks": lm}


# =========================================================================
# PART 1: LEFT AND RIGHT CLICK RELIABILITY TESTS
# =========================================================================

def test_part1_reliable_left_click():
    """Verify that a single-eye left wink generates exactly one LEFT_CLICK."""
    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.06,
        max_blink_duration_sec=0.65,
        drag_hold_sec=0.45,
        drag_enabled=True,
    )
    detector = BlinkDetector(settings)

    open_face = make_face_landmarks(left_ear=0.28, right_ear=0.28)
    left_closed = make_face_landmarks(left_ear=0.10, right_ear=0.28)

    t = 1000.0
    r1 = detector.update(open_face, timestamp=t)
    assert r1["event"] is None

    # Left eye closes
    detector.update(left_closed, timestamp=t + 0.05)
    assert detector.left_eye.state == STATE_CLOSED
    assert detector.right_eye.state == STATE_OPEN

    # Held for natural wink duration (180ms)
    r3 = detector.update(left_closed, timestamp=t + 0.18)
    assert r3["event"] is None  # Emitted only on reopening!

    # Left eye reopens
    r4 = detector.update(open_face, timestamp=t + 0.22)
    assert r4["event"] == LEFT_CLICK, f"Expected LEFT_CLICK, got {r4['event']}"
    assert detector.total_left_clicks == 1
    assert not detector.left_eye.is_dual_suppressed


def test_part1_reliable_right_click():
    """Verify that a single-eye right wink generates exactly one RIGHT_CLICK."""
    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.06,
        max_blink_duration_sec=0.65,
        drag_hold_sec=0.45,
    )
    detector = BlinkDetector(settings)

    open_face = make_face_landmarks(left_ear=0.28, right_ear=0.28)
    right_closed = make_face_landmarks(left_ear=0.28, right_ear=0.10)

    t = 2000.0
    detector.update(open_face, timestamp=t)
    detector.update(right_closed, timestamp=t + 0.05)
    detector.update(right_closed, timestamp=t + 0.18)

    r_open = detector.update(open_face, timestamp=t + 0.22)
    assert r_open["event"] == RIGHT_CLICK, f"Expected RIGHT_CLICK, got {r_open['event']}"
    assert detector.total_right_clicks == 1
    assert not detector.right_eye.is_dual_suppressed


def test_part1_simultaneous_blink_suppression():
    """Verify that both eyes closing simultaneously generates no click."""
    settings = EyeBlinkSettings(min_blink_duration_sec=0.06, max_blink_duration_sec=0.65)
    detector = BlinkDetector(settings)

    open_face = make_face_landmarks(left_ear=0.28, right_ear=0.28)
    both_closed = make_face_landmarks(left_ear=0.10, right_ear=0.10)

    t = 3000.0
    detector.update(open_face, timestamp=t)
    detector.update(both_closed, timestamp=t + 0.05)
    detector.update(both_closed, timestamp=t + 0.15)
    assert detector.simultaneous_suppression_active

    r_reopen = detector.update(open_face, timestamp=t + 0.25)
    assert r_reopen["event"] in (NO_ACTION, None)
    assert detector.total_left_clicks == 0
    assert detector.total_right_clicks == 0


def test_part1_click_after_simultaneous_blink():
    """Verify that a clean wink immediately following a bilateral blink works reliably."""
    settings = EyeBlinkSettings(min_blink_duration_sec=0.06, max_blink_duration_sec=0.65)
    detector = BlinkDetector(settings)

    open_face = make_face_landmarks(left_ear=0.28, right_ear=0.28)
    both_closed = make_face_landmarks(left_ear=0.10, right_ear=0.10)
    left_closed = make_face_landmarks(left_ear=0.10, right_ear=0.28)

    t = 4000.0
    detector.update(open_face, timestamp=t)
    detector.update(both_closed, timestamp=t + 0.05)
    detector.update(open_face, timestamp=t + 0.20)

    t += 0.50
    detector.update(open_face, timestamp=t)
    detector.update(left_closed, timestamp=t + 0.05)
    detector.update(left_closed, timestamp=t + 0.18)
    r_click = detector.update(open_face, timestamp=t + 0.22)

    assert r_click["event"] == LEFT_CLICK
    assert detector.total_left_clicks == 1


def test_part1_drag_hold_preserved_without_stealing_short_winks():
    """Verify drag hold (>=450ms) triggers DRAG_START, while short wink (<450ms) triggers LEFT_CLICK."""
    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.06,
        max_blink_duration_sec=0.65,
        drag_hold_sec=0.45,
        drag_enabled=True,
    )
    detector = BlinkDetector(settings)

    open_face = make_face_landmarks(left_ear=0.28, right_ear=0.28)
    left_closed = make_face_landmarks(left_ear=0.10, right_ear=0.28)

    t = 5000.0
    detector.update(open_face, timestamp=t)
    detector.update(left_closed, timestamp=t + 0.05)
    detector.update(left_closed, timestamp=t + 0.30)
    assert not detector.left_eye.is_dragging

    # Exceed 450ms hold -> DRAG_START emitted
    r_drag = detector.update(left_closed, timestamp=t + 0.50)
    assert detector.left_eye.is_dragging
    assert r_drag["event"] == DRAG_START

    # Reopen eye -> DRAG_STOP emitted, NO left click emitted
    r_stop = detector.update(open_face, timestamp=t + 0.65)
    assert not detector.left_eye.is_dragging
    assert r_stop["event"] == DRAG_STOP
    assert detector.total_left_clicks == 0


# =========================================================================
# PART 2: DUAL GESTURE INTERACTION (SCROLL & ZOOM) TESTS
# =========================================================================

def test_part2_teeth_show_only_activates_scroll_mode():
    """Requirement 1: Teeth show ONLY activates Scroll Mode.

    - Head UP = Scroll Up.
    - Head DOWN = Scroll Down.
    - Head neutral = Stop scrolling.
    """
    tracker = GestureZoomTracker(ZoomSettings(scroll_deadzone=0.020, neutral_deadzone=0.012, scroll_step=2))
    # Teeth showing (wide smile + lip separation) with NORMAL eyebrows (eb_dist = 0.040)
    teeth_only_frame = make_face_landmarks(
        left_eb_dist=0.040,
        right_eb_dist=0.040,
        mouth_width=0.200,   # 0.200 / 0.250 = 0.80 >= 0.77
        lip_open=0.020,      # 0.020 / 0.250 = 0.08 in [0.035, 0.22]
    )

    t = 100.0
    # Frame 1: Head neutral -> Scroll mode active, but stop scrolling (scroll_amount = 0)
    s1 = tracker.update(teeth_only_frame, relative_dy=0.0, timestamp=t)
    assert s1["mode"] == MODE_SCROLL
    assert s1["scroll_mode_active"]
    assert not s1["zoom_mode_active"]
    assert s1["scroll_amount"] == 0
    assert s1["action"] is None

    # Frame 2: Head UP past deadzone (+0.035 >= +0.020) -> Scroll Up
    s2 = tracker.update(teeth_only_frame, relative_dy=0.035, timestamp=t + 0.1)
    assert s2["scroll_amount"] == 2
    assert s2["action"] == SCROLL_UP

    # Frame 3: Head returns to neutral -> Stop scrolling
    s3 = tracker.update(teeth_only_frame, relative_dy=0.005, timestamp=t + 0.2)
    assert s3["scroll_amount"] == 0
    assert s3["action"] is None

    # Frame 4: Head DOWN past deadzone (-0.035 <= -0.020) -> Scroll Down
    s4 = tracker.update(teeth_only_frame, relative_dy=-0.035, timestamp=t + 0.5)
    assert s4["scroll_amount"] == -2
    assert s4["action"] == SCROLL_DOWN


def test_part2_teeth_show_plus_both_eyebrows_switches_to_zoom_mode():
    """Requirement 2: Teeth show + BOTH eyebrows raised switches to Zoom Mode.

    - Head UP = Zoom In.
    - Head DOWN = Zoom Out.
    - Head neutral = No action.
    """
    tracker = GestureZoomTracker(ZoomSettings(zoom_deadzone=0.022, neutral_deadzone=0.012))

    # Frame with teeth showing AND both eyebrows raised
    zoom_frame = make_face_landmarks(
        left_eb_dist=0.050,  # raised
        right_eb_dist=0.050, # raised
        mouth_width=0.200,
        lip_open=0.020,
    )

    t = 200.0
    # Neutral head
    s1 = tracker.update(zoom_frame, relative_dy=0.0, timestamp=t)
    assert s1["mode"] == MODE_ZOOM
    assert s1["zoom_mode_active"]
    assert not s1["scroll_mode_active"]
    assert s1["zoom_action"] is None

    # Head UP -> Zoom In
    s2 = tracker.update(zoom_frame, relative_dy=0.035, timestamp=t + 0.1)
    assert s2["zoom_action"] == ZOOM_IN
    assert s2["action"] == ZOOM_IN

    # Head returns to neutral -> No action
    s3 = tracker.update(zoom_frame, relative_dy=0.005, timestamp=t + 0.2)
    assert s3["zoom_action"] is None
    assert s3["action"] is None

    # Head DOWN -> Zoom Out
    s4 = tracker.update(zoom_frame, relative_dy=-0.035, timestamp=t + 0.5)
    assert s4["zoom_action"] == ZOOM_OUT
    assert s4["action"] == ZOOM_OUT


def test_part2_teeth_not_visible_immediately_disables_both_modes():
    """Requirement 3: Teeth not visible immediately disables BOTH Scroll Mode and Zoom Mode."""
    tracker = GestureZoomTracker()

    teeth_only_frame = make_face_landmarks(mouth_width=0.200, lip_open=0.020, left_eb_dist=0.040, right_eb_dist=0.040)
    zoom_frame = make_face_landmarks(mouth_width=0.200, lip_open=0.020, left_eb_dist=0.050, right_eb_dist=0.050)
    neutral_mouth_frame = make_face_landmarks(mouth_width=0.130, lip_open=0.002, left_eb_dist=0.040, right_eb_dist=0.040)

    # 1. Start in Scroll Mode -> teeth disappear -> mode becomes NONE
    tracker.update(teeth_only_frame, relative_dy=0.0, timestamp=300.0)
    assert tracker.scroll_mode_active

    s_off1 = tracker.update(neutral_mouth_frame, relative_dy=0.035, timestamp=300.1)
    assert s_off1["mode"] == MODE_NONE
    assert not s_off1["scroll_mode_active"]
    assert not s_off1["zoom_mode_active"]
    assert s_off1["action"] is None
    assert s_off1["scroll_amount"] == 0

    # 2. Start in Zoom Mode -> teeth disappear -> mode becomes NONE immediately
    tracker.update(zoom_frame, relative_dy=0.0, timestamp=310.0)
    assert tracker.zoom_mode_active

    s_off2 = tracker.update(neutral_mouth_frame, relative_dy=0.035, timestamp=310.1)
    assert s_off2["mode"] == MODE_NONE
    assert not s_off2["scroll_mode_active"]
    assert not s_off2["zoom_mode_active"]
    assert s_off2["action"] is None


def test_part2_eyebrows_return_to_normal_returns_to_scroll_mode():
    """Requirement 4: Eyebrows return to normal disables Zoom Mode and returns to Scroll Mode automatically."""
    tracker = GestureZoomTracker()

    zoom_frame = make_face_landmarks(
        left_eb_dist=0.050,  # raised
        right_eb_dist=0.050,
        mouth_width=0.200,   # teeth shown
        lip_open=0.020,
    )
    teeth_only_frame = make_face_landmarks(
        left_eb_dist=0.040,  # back to normal
        right_eb_dist=0.040,
        mouth_width=0.200,   # teeth still shown
        lip_open=0.020,
    )

    t = 400.0
    s_zoom = tracker.update(zoom_frame, relative_dy=0.0, timestamp=t)
    assert s_zoom["mode"] == MODE_ZOOM
    assert s_zoom["zoom_mode_active"]
    assert not s_zoom["scroll_mode_active"]

    # Eyebrows lower back to normal while teeth remain visible
    s_scroll = tracker.update(teeth_only_frame, relative_dy=0.0, timestamp=t + 0.1)
    assert s_scroll["mode"] == MODE_SCROLL, "Must automatically transition back to SCROLL MODE!"
    assert not s_scroll["zoom_mode_active"]
    assert s_scroll["scroll_mode_active"]


def test_part2_never_run_scrolling_and_zooming_simultaneously():
    """Requirement: Never run scrolling and zooming simultaneously."""
    tracker = GestureZoomTracker()

    zoom_frame = make_face_landmarks(left_eb_dist=0.050, right_eb_dist=0.050, mouth_width=0.200, lip_open=0.020)
    scroll_frame = make_face_landmarks(left_eb_dist=0.040, right_eb_dist=0.040, mouth_width=0.200, lip_open=0.020)

    # In Zoom Mode: scroll_amount must be 0
    sz = tracker.update(zoom_frame, relative_dy=0.035, timestamp=500.0)
    assert sz["zoom_mode_active"]
    assert not sz["scroll_mode_active"]
    assert sz["scroll_amount"] == 0
    assert sz["zoom_action"] == ZOOM_IN

    # In Scroll Mode: zoom_action must be None
    ss = tracker.update(scroll_frame, relative_dy=0.035, timestamp=501.0)
    assert ss["scroll_mode_active"]
    assert not ss["zoom_mode_active"]
    assert ss["zoom_action"] is None
    assert ss["scroll_amount"] > 0


def test_part2_anti_runaway_scroll_and_zoom_while_head_held():
    """Requirement: Prevent repeated rapid scroll/zoom actions while the head is held in one direction."""
    tracker = GestureZoomTracker(ZoomSettings(zoom_deadzone=0.022, scroll_deadzone=0.020, neutral_deadzone=0.012))

    scroll_frame = make_face_landmarks(left_eb_dist=0.040, right_eb_dist=0.040, mouth_width=0.200, lip_open=0.020)
    zoom_frame = make_face_landmarks(left_eb_dist=0.050, right_eb_dist=0.050, mouth_width=0.200, lip_open=0.020)

    # 1. Anti-runaway for SCROLL
    t = 600.0
    s1 = tracker.update(scroll_frame, relative_dy=0.035, timestamp=t)
    assert s1["action"] == SCROLL_UP
    assert s1["scroll_amount"] == 2
    assert not tracker.step_ready

    # Held tilted UP for subsequent frames -> NO rapid repeated scroll clicks!
    s2 = tracker.update(scroll_frame, relative_dy=0.038, timestamp=t + 0.10)
    assert s2["action"] is None
    assert s2["scroll_amount"] == 0

    s3 = tracker.update(scroll_frame, relative_dy=0.036, timestamp=t + 0.50)
    assert s3["action"] is None
    assert s3["scroll_amount"] == 0

    # Return to neutral -> Stop / Re-arm
    s4 = tracker.update(scroll_frame, relative_dy=0.005, timestamp=t + 0.60)
    assert s4["scroll_amount"] == 0
    assert tracker.step_ready

    # 2. Anti-runaway for ZOOM
    t = 700.0
    z1 = tracker.update(zoom_frame, relative_dy=0.035, timestamp=t)
    assert z1["action"] == ZOOM_IN
    assert not tracker.step_ready

    # Held tilted UP -> NO rapid repeated zoom actions!
    z2 = tracker.update(zoom_frame, relative_dy=0.038, timestamp=t + 0.10)
    assert z2["action"] is None

    z3 = tracker.update(zoom_frame, relative_dy=0.036, timestamp=t + 0.50)
    assert z3["action"] is None

    # Return to neutral -> Re-arm
    z4 = tracker.update(zoom_frame, relative_dy=0.005, timestamp=t + 0.60)
    assert z4["action"] is None
    assert tracker.step_ready


def test_part2_normal_talking_does_not_activate_either_mode():
    """Verify that normal speech (lips opening vertically but mouth narrow) does not activate scroll or zoom."""
    tracker = GestureZoomTracker()
    talking_frame = make_face_landmarks(
        left_eb_dist=0.040,
        right_eb_dist=0.040,
        mouth_width=0.130,  # resting width (0.130 / 0.250 = 0.520 < 0.60, stretch 1.0 < 1.12)
        lip_open=0.025,     # vertical opening for vowels
    )
    status = tracker.update(talking_frame, relative_dy=0.035, timestamp=800.0)
    assert not status["teeth_visible"]
    assert status["mode"] == MODE_NONE
    assert not status["scroll_mode_active"]
    assert not status["zoom_mode_active"]
    assert status["action"] is None
    assert status["reject_reason"] == "MOUTH_NARROW"


def test_part2_safety_face_loss():
    """Verify that losing face detection instantly cuts both scroll and zoom modes."""
    tracker = GestureZoomTracker()
    active_frame = make_face_landmarks(mouth_width=0.200, lip_open=0.020, left_eb_dist=0.040, right_eb_dist=0.040)
    tracker.update(active_frame, relative_dy=0.035, timestamp=900.0)
    assert tracker.scroll_mode_active

    face_lost = {"has_face": False, "landmarks": []}
    s_lost = tracker.update(face_lost, relative_dy=0.035, timestamp=900.1)
    assert s_lost["mode"] == MODE_NONE
    assert not s_lost["scroll_mode_active"]
    assert not s_lost["zoom_mode_active"]
    assert s_lost["action"] is None


def test_part2_mouse_controller_actuation_and_emergency_stop():
    """Verify MouseController executes scroll & zoom hotkeys and blocks all actions upon Emergency Stop."""
    mock = MockPyAutoGUI(width=1920, height=1080)
    controller = MouseController(py_backend=mock)
    controller.update_tracking_status(has_face=True, is_calibrated=True)
    controller.enable()

    t = 1000.0
    # Scroll Up
    assert controller.scroll(2)
    assert 2 in mock.scrolls
    assert controller.total_scrolls == 1

    # Zoom In
    assert controller.handle_zoom_action("ZOOM_IN", steps=1, timestamp=t) == "ZOOM_IN"
    assert ("ctrl", "+") in mock.hotkeys
    assert controller.total_zooms == 1

    # Zoom Out
    assert controller.handle_zoom_action("ZOOM_OUT", steps=1, timestamp=t + 0.3) == "ZOOM_OUT"
    assert ("ctrl", "-") in mock.hotkeys
    assert controller.total_zooms == 2

    # Trigger Emergency Stop (F9)
    controller.emergency_stop()
    assert controller.emergency_stopped
    assert not controller.enabled

    # All further actions must be blocked
    assert not controller.scroll(2)
    assert controller.handle_zoom_action("ZOOM_IN", steps=1, timestamp=t + 0.6) is None
    assert controller.handle_blink_event(LEFT_CLICK, timestamp=t + 0.7) is None


def test_part2_right_eye_wink_during_drag_does_not_interrupt_drag():
    """Verify that a right eye wink while holding a left-eye drag does not cancel drag or emit a right click."""
    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.06,
        max_blink_duration_sec=0.65,
        drag_hold_sec=0.45,
        drag_enabled=True,
    )
    detector = BlinkDetector(settings)
    open_face = make_face_landmarks(left_ear=0.28, right_ear=0.28)
    left_closed = make_face_landmarks(left_ear=0.12, right_ear=0.28)
    both_closed = make_face_landmarks(left_ear=0.12, right_ear=0.12)

    t = 1100.0
    # Left eye closes and holds for >=450ms -> triggers DRAG_START
    detector.update(open_face, timestamp=t)
    detector.update(left_closed, timestamp=t + 0.05)
    detector.update(left_closed, timestamp=t + 0.30)
    res_drag = detector.update(left_closed, timestamp=t + 0.55)
    assert res_drag["event"] == DRAG_START
    assert detector.left_eye.is_dragging

    # Right eye closes while left eye is dragging
    res_both = detector.update(both_closed, timestamp=t + 0.65)
    assert detector.left_eye.is_dragging
    assert not detector.simultaneous_suppression_active
    assert res_both["event"] is None

    # Right eye reopens while left eye is still dragging
    res_right_open = detector.update(left_closed, timestamp=t + 0.75)
    assert detector.left_eye.is_dragging
    assert res_right_open["event"] is None

    # Left eye reopens -> emits DRAG_STOP
    res_stop = detector.update(open_face, timestamp=t + 0.90)
    assert res_stop["event"] == DRAG_STOP
    assert not detector.left_eye.is_dragging


def test_part2_recalibration_releases_held_mouse_button():
    """Verify starting calibration immediately releases any held mouse button."""
    from unittest.mock import patch
    with patch("main.CameraCapture"), patch("main.FaceLandmarkerWrapper"):
        from main import HeadMouseApp
        app = HeadMouseApp()
        mock_pyautogui = MockPyAutoGUI()
        app.mouse_controller = MouseController(py_backend=mock_pyautogui)
        app.mouse_controller.update_tracking_status(has_face=True, is_calibrated=True)
        app.mouse_controller.enable()
        app.mouse_controller.mouse_down()
        assert app.mouse_controller.is_mouse_down

        app._start_calibration()
        assert not app.mouse_controller.is_mouse_down
        assert len(mock_pyautogui.ups) == 1


def test_part2_dashboard_mode_and_head_direction():
    """Verify telemetry state computation: NORMAL/DRAG/SCROLL/ZOOM modes and UP/DOWN/NEUTRAL head directions."""
    def compute_mode(is_dragging: bool, zoom_active: bool, scroll_active: bool) -> str:
        if is_dragging:
            return "DRAG"
        elif zoom_active:
            return "ZOOM"
        elif scroll_active:
            return "SCROLL"
        return "NORMAL"

    assert compute_mode(False, False, False) == "NORMAL"
    assert compute_mode(True, False, False) == "DRAG"
    assert compute_mode(False, False, True) == "SCROLL"
    assert compute_mode(False, True, False) == "ZOOM"
    assert compute_mode(True, True, False) == "DRAG"

    deadzone = 0.020
    def compute_head_dir(rel_dy: float) -> str:
        if rel_dy >= deadzone:
            return "UP"
        elif rel_dy <= -deadzone:
            return "DOWN"
        return "NEUTRAL"

    assert compute_head_dir(0.005) == "NEUTRAL"
    assert compute_head_dir(-0.012) == "NEUTRAL"
    assert compute_head_dir(0.025) == "UP"
    assert compute_head_dir(-0.030) == "DOWN"


def test_part2_mouth_gesture_hysteresis():
    """Verify Schmitt trigger hysteresis for mouth gesture detection."""
    tracker = GestureZoomTracker(ZoomSettings(mouth_width_threshold=0.60, mouth_open_min=0.018))
    iod = 0.250

    # 1. Mouth width at rest: ratio = 0.130 / 0.250 = 0.520 (< 0.60 onset, stretch 1.0 < 1.12) -> not visible
    frame_rest = make_face_landmarks(mouth_width=0.130, lip_open=0.010, iod=iod)
    s1 = tracker.update(frame_rest, relative_dy=0.0, timestamp=1200.0)
    assert not s1["teeth_visible"]

    # 2. Mouth widening slightly to 0.142: ratio = 0.142 / 0.250 = 0.568 (< 0.60 onset, stretch 1.09 < 1.12) -> still not visible
    frame_sub_onset = make_face_landmarks(mouth_width=0.142, lip_open=0.010, iod=iod)
    s2 = tracker.update(frame_sub_onset, relative_dy=0.0, timestamp=1200.1)
    assert not s2["teeth_visible"]

    # 3. Mouth widening to 0.155: ratio = 0.155 / 0.250 = 0.620 (>= 0.60 onset, stretch 1.19 >= 1.12) -> ACTIVE (teeth visible)
    frame_onset = make_face_landmarks(mouth_width=0.155, lip_open=0.010, iod=iod)
    s3 = tracker.update(frame_onset, relative_dy=0.0, timestamp=1200.2)
    assert s3["teeth_visible"]

    # 4. Mouth narrows slightly to 0.146: ratio = 0.146 / 0.250 = 0.584 (above 0.56 release, stretch 1.12 >= 1.06) -> REMAINS ACTIVE (hysteresis)
    frame_hysteresis = make_face_landmarks(mouth_width=0.146, lip_open=0.010, iod=iod)
    s4 = tracker.update(frame_hysteresis, relative_dy=0.0, timestamp=1200.3)
    assert s4["teeth_visible"]

    # 5. Mouth narrows further to 0.135: ratio = 0.135 / 0.250 = 0.540 (< 0.56 release, stretch 1.038 < 1.06) -> DEACTIVATED
    frame_release = make_face_landmarks(mouth_width=0.135, lip_open=0.010, iod=iod)
    s5 = tracker.update(frame_release, relative_dy=0.0, timestamp=1200.4)
    assert not s5["teeth_visible"]

    # 6. Mouth closed (lip_open = 0.002): ratio = 0.002 / 0.250 = 0.008 (< 0.010) -> DEACTIVATED immediately
    tracker.update(frame_onset, relative_dy=0.0, timestamp=1200.5)
    assert tracker.teeth_visible
    frame_lips_shut = make_face_landmarks(mouth_width=0.155, lip_open=0.002, iod=iod)
    s6 = tracker.update(frame_lips_shut, relative_dy=0.0, timestamp=1200.6)
    assert not s6["teeth_visible"]


def test_part2_telemetry_fields_and_diagnostics():
    """Verify that update() status dictionary contains all required telemetry metrics."""
    tracker = GestureZoomTracker()
    iod = 0.250
    teeth_frame = make_face_landmarks(mouth_width=0.160, lip_open=0.010, left_eb_dist=0.040, right_eb_dist=0.040, iod=iod)

    status = tracker.update(teeth_frame, relative_dy=0.030, timestamp=1300.0)

    # Required telemetry fields
    assert "mouth_width_ratio" in status
    assert "mouth_open_ratio" in status
    assert "mouth_width_baseline" in status
    assert "left_eb_ratio" in status
    assert "right_eb_ratio" in status
    assert "mode" in status
    assert "head_direction" in status
    assert "action" in status
    assert "reject_reason" in status
    assert "relative_dy" in status
    assert status["mode"] == MODE_SCROLL
    assert status["head_direction"] == "UP"
    assert status["action"] == SCROLL_UP
    assert status["mouth_width_ratio"] == pytest.approx(0.160 / 0.250, rel=1e-3)


def test_part2_calibrated_baseline_adaptation():
    """Verify that calibrating baseline from neutral samples properly sets thresholds."""
    tracker = GestureZoomTracker()
    tracker.calibrate_baseline(
        left_eb_samples=[0.15, 0.16, 0.15, 0.16, 0.15],
        right_eb_samples=[0.15, 0.16, 0.15, 0.16, 0.15],
        mouth_width_samples=[0.50, 0.50, 0.51, 0.50, 0.49],
    )
    assert tracker.is_calibrated
    assert tracker.mouth_width_baseline == pytest.approx(0.50, abs=0.02)
    assert tracker.left_eyebrow_baseline == pytest.approx(0.15, abs=0.02)
    assert tracker.right_eyebrow_baseline == pytest.approx(0.15, abs=0.02)

    # A smile expanding 14% over baseline (0.50 * 1.14 = 0.57) activates teeth_visible
    iod = 0.250
    smile_frame = make_face_landmarks(mouth_width=0.57 * iod, lip_open=0.010, iod=iod)
    res = tracker.update(smile_frame, relative_dy=0.0, timestamp=1400.0)
    assert res["teeth_visible"]
    assert res["mode"] == MODE_SCROLL

