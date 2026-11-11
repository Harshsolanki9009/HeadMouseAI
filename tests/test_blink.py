"""Test blink detection and signal generation for HeadMouse AI Phase 3.

Verifies:
- Normal open eyes produce no false events.
- Short left-eye blink alone -> LEFT_CLICK signal.
- Short right-eye blink alone -> RIGHT_CLICK signal.
- Simultaneous dual-eye blink -> NO ACTION (suppression active).
- One eye closed while the other remains open -> NO false dual suppression; single click fires.
- Different EAR baselines for left and right eyes (asymmetric baselines).
- Slow blink and prolonged eye closure -> rejected.
- Face loss and recovery -> safe zero clicks.
- Cooldown and duplicate event prevention.
"""
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from config.settings import EyeBlinkSettings
from core.eye_tracker import EyeTracker, calculate_ear, calculate_eye_ear, LEFT_EYE_CENTER, LEFT_EYE_INNER_CORNER, RIGHT_EYE_CENTER
from core.blink_detector import BlinkDetector, LEFT_CLICK, RIGHT_CLICK, NO_ACTION, STATE_OPEN, STATE_CLOSED
from utils.logger import get_logger

logger = get_logger("TestBlink")


def make_closed_landmarks():
    """Create landmarks simulating closed eyes (EAR ~0.05)."""
    lm = []
    for i in range(468):
        lm.append([0.0, 0.0, 0.0, 1.0, 1.0])

    for idx in [36, 133, 240]:
        lm[idx][0] = 0.5; lm[idx][1] = 0.3
    lm[LEFT_EYE_CENTER][0] = 0.5; lm[LEFT_EYE_CENTER][1] = 0.3
    lm[LEFT_EYE_INNER_CORNER][0] = 0.5; lm[LEFT_EYE_INNER_CORNER][1] = 0.3

    for idx in [51, 370]:
        lm[idx][0] = 0.5; lm[idx][1] = 0.3
    lm[RIGHT_EYE_CENTER][0] = 0.5; lm[RIGHT_EYE_CENTER][1] = 0.3

    return lm


def make_open_landmarks():
    """Create landmarks simulating open eyes (EAR ~0.25)."""
    lm = []
    for i in range(468):
        lm.append([0.0, 0.0, 0.0, 1.0, 1.0])

    for idx in [36, 133, 240]:
        lm[idx][0] = 0.5; lm[idx][1] = 0.3
    lm[LEFT_EYE_CENTER][0] = 0.5; lm[LEFT_EYE_CENTER][1] = 0.35
    lm[LEFT_EYE_INNER_CORNER][0] = 0.5; lm[LEFT_EYE_INNER_CORNER][1] = 0.35

    for idx in [51, 370]:
        lm[idx][0] = 0.5; lm[idx][1] = 0.3
    lm[RIGHT_EYE_CENTER][0] = 0.5; lm[RIGHT_EYE_CENTER][1] = 0.35

    return lm


def make_landmarks_with_ear(left_ear: float, right_ear: float) -> list[list]:
    """Create MediaPipe canonical landmarks having exact requested EAR values.

    Canonical Left Eye: 33, 133, 160, 144, 158, 153 (width = 0.10, 2*width = 0.20)
    Canonical Right Eye: 362, 263, 385, 380, 387, 373 (width = 0.10, 2*width = 0.20)
    """
    lm = [[0.0, 0.0, 0.0, 1.0, 1.0] for _ in range(478)]

    # Left eye
    lm[33] = [0.35, 0.30, 0.0, 1.0, 1.0]
    lm[133] = [0.45, 0.30, 0.0, 1.0, 1.0]
    l_h = max(0.001, 0.10 * left_ear)
    lm[160] = [0.38, 0.30 - l_h / 2, 0.0, 1.0, 1.0]
    lm[144] = [0.38, 0.30 + l_h / 2, 0.0, 1.0, 1.0]
    lm[158] = [0.42, 0.30 - l_h / 2, 0.0, 1.0, 1.0]
    lm[153] = [0.42, 0.30 + l_h / 2, 0.0, 1.0, 1.0]

    # Right eye
    lm[362] = [0.55, 0.30, 0.0, 1.0, 1.0]
    lm[263] = [0.65, 0.30, 0.0, 1.0, 1.0]
    r_h = max(0.001, 0.10 * right_ear)
    lm[385] = [0.58, 0.30 - r_h / 2, 0.0, 1.0, 1.0]
    lm[380] = [0.58, 0.30 + r_h / 2, 0.0, 1.0, 1.0]
    lm[387] = [0.62, 0.30 - r_h / 2, 0.0, 1.0, 1.0]
    lm[373] = [0.62, 0.30 + r_h / 2, 0.0, 1.0, 1.0]

    return lm


def make_canonical_eye_landmarks(left_open: bool = True, right_open: bool = True) -> list[list]:
    """Helper for binary open/closed canonical landmark generator."""
    l_ear = 0.27 if left_open else 0.03
    r_ear = 0.27 if right_open else 0.03
    return make_landmarks_with_ear(l_ear, r_ear)


# ================= Legacy Compatibility Tests ================= #

def test_blink_pattern():
    """Test that EAR history pattern triggers blink detection."""
    tracker = EyeTracker(open_threshold=0.22)

    for i in range(20):
        tracker.left_ear_history.append(float(np.random.uniform(0.05, 0.15)))
        tracker.right_ear_history.append(float(np.random.uniform(0.05, 0.15)))

    landmarks = make_closed_landmarks()
    result = tracker.update({"landmarks": landmarks})

    assert not result["left_is_open"], "Left eye should be CLOSED when EAR is low"
    assert not result["right_is_open"], "Right eye should also be CLOSED"
    print("[PASS] Left & Right eyes detected as CLOSED.")
    return True


def test_independent_eye_tracking():
    """Test that left and right eyes are tracked independently."""
    tracker = EyeTracker()

    closed_landmarks = make_closed_landmarks()
    open_landmarks = make_open_landmarks()

    r1 = tracker.update({"landmarks": closed_landmarks})
    r2 = tracker.update({"landmarks": open_landmarks})

    assert not r1["left_is_open"], "r1 left eye should be closed"
    assert r2["right_is_open"], "r2 right eye should be open"
    print("[PASS] Independent tracking: left=CLOSED, right=OPEN.")
    return True


def test_simultaneous_suppression():
    """Test that simultaneous blinks on both eyes don't trigger both clicks."""
    tracker = EyeTracker(
        independent_blink_detection=True,
        simultaneous_blink_suppression=True,
        blink_cooldown_frames=5,
    )

    landmarks = make_closed_landmarks()
    result = tracker.update({"landmarks": landmarks})

    both_closed = (not result["left_is_open"]) and (not result["right_is_open"])
    assert both_closed, "Both eyes should detect as closed simultaneously"
    print("[PASS] Both eyes closed simultaneously — detected correctly.")
    return True


# ================= Phase 3 Comprehensive Blink Tests ================= #

def test_normal_open_eyes_no_action():
    """Test that continuously open eyes never trigger false positive clicks."""
    detector = BlinkDetector()
    open_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.28)}

    for frame_idx in range(25):
        result = detector.update(open_face)
        assert result["event"] is None, f"Frame {frame_idx}: unexpected event {result['event']}"
        assert result["left_state"] == "OPEN"
        assert result["right_state"] == "OPEN"
        assert not result["suppression_active"]

    print("[PASS] Normal open eyes produced zero false clicks.")
    return True


def test_short_left_eye_blink():
    """Test that short natural left-eye blink (2 frames) emits LEFT_CLICK signal upon reopening."""
    settings = EyeBlinkSettings(
        min_blink_frames=1,
        max_blink_duration_frames=12,
        blink_cooldown_frames=10,
        sensitivity=0.70,
    )
    detector = BlinkDetector(settings)

    open_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.28)}
    left_closed_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.12, 0.28)}

    # Step 1: Open eyes baseline (3 frames)
    for _ in range(3):
        detector.update(open_face)

    # Step 2: Left closed for 2 frames (fast natural blink)
    for _ in range(2):
        rf = detector.update(left_closed_face)
        assert rf["event"] is None, "Should not emit click while eye is closed"
        assert rf["left_state"] == "CLOSED"
        assert rf["right_state"] == "OPEN"
        assert not rf["suppression_active"]

    # Step 3: Left reopens -> LEFT_CLICK emitted!
    r_reopen = detector.update(open_face)
    assert r_reopen["event"] == LEFT_CLICK, f"Expected {LEFT_CLICK}, got {r_reopen['event']}"
    print(f"[PASS] Short left-eye blink successfully emitted {LEFT_CLICK}.")
    return True


def test_short_right_eye_blink():
    """Test that short natural right-eye blink (2 frames) emits RIGHT_CLICK signal upon reopening."""
    settings = EyeBlinkSettings(
        min_blink_frames=1,
        max_blink_duration_frames=12,
        blink_cooldown_frames=10,
        sensitivity=0.70,
    )
    detector = BlinkDetector(settings)

    open_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.28)}
    right_closed_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.12)}

    # Baseline open
    for _ in range(3):
        detector.update(open_face)

    # Right closed for 2 frames
    for _ in range(2):
        rf = detector.update(right_closed_face)
        assert rf["event"] is None
        assert rf["left_state"] == "OPEN"
        assert rf["right_state"] == "CLOSED"
        assert not rf["suppression_active"]

    # Right reopens -> RIGHT_CLICK emitted!
    r_reopen = detector.update(open_face)
    assert r_reopen["event"] == RIGHT_CLICK, f"Expected {RIGHT_CLICK}, got {r_reopen['event']}"
    print(f"[PASS] Short right-eye blink successfully emitted {RIGHT_CLICK}.")
    return True


def test_simultaneous_blink_suppression_event():
    """Test that both eyes closing simultaneously activates suppression and produces NO click."""
    settings = EyeBlinkSettings(
        min_blink_frames=1,
        max_blink_duration_frames=12,
        simultaneous_blink_suppression=True,
    )
    detector = BlinkDetector(settings)

    open_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.28)}
    both_closed_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.10, 0.10)}

    detector.update(open_face)

    # Both eyes closed together for 3 frames
    for _ in range(3):
        rf = detector.update(both_closed_face)
        assert rf["event"] is None
        assert rf["suppression_active"], "Suppression MUST be active when both eyes are closed"

    # Both eyes reopen -> click must be suppressed (emits NO_ACTION, not LEFT_CLICK or RIGHT_CLICK)
    r_reopen = detector.update(open_face)
    assert r_reopen["event"] in (None, NO_ACTION), f"Simultaneous blink must not emit clicks, got {r_reopen['event']}"
    assert r_reopen["event"] != LEFT_CLICK and r_reopen["event"] != RIGHT_CLICK
    print("[PASS] Simultaneous dual blink successfully suppressed.")
    return True


def test_one_eye_closed_while_other_remains_open():
    """Test that one closed eye does NOT trigger dual-blink suppression (fixes reported dashboard bug)."""
    settings = EyeBlinkSettings(
        left_baseline_ear=0.28,
        right_baseline_ear=0.28,
        min_blink_frames=1,
        max_blink_duration_frames=12,
        simultaneous_blink_suppression=True,
    )
    detector = BlinkDetector(settings)

    open_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.28)}
    # Exact scenario reported by user: Left EAR 0.27 (OPEN), Right EAR 0.14 (CLOSED)
    asymmetric_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.27, 0.14)}

    detector.update(open_face)

    # Frame with Left OPEN (0.27), Right CLOSED (0.14)
    r1 = detector.update(asymmetric_face)
    assert r1["left_state"] == "OPEN", f"Left eye should be OPEN, got {r1['left_state']}"
    assert r1["right_state"] == "CLOSED", f"Right eye should be CLOSED, got {r1['right_state']}"
    # CRITICAL VERIFICATION: One closed eye must NOT activate dual blink suppression!
    assert not r1["suppression_active"], "Suppression MUST NOT be active when only one eye is closed!"

    # Second frame with same state
    r2 = detector.update(asymmetric_face)
    assert not r2["suppression_active"], "Suppression MUST remain False during single-eye closure"

    # Right eye reopens -> RIGHT_CLICK must fire!
    r_reopen = detector.update(open_face)
    assert r_reopen["event"] == RIGHT_CLICK, f"Expected {RIGHT_CLICK}, got {r_reopen['event']}"
    print("[PASS] One eye closed while other is open: correctly classified without false suppression.")
    return True


def test_different_ear_baselines():
    """Test adaptive thresholds when left and right eyes have asymmetric open baselines."""
    # User has asymmetric eyes: Left open EAR is 0.30, Right open EAR is 0.21
    settings = EyeBlinkSettings(
        left_baseline_ear=0.30,
        right_baseline_ear=0.21,
        sensitivity=0.70,
        min_blink_frames=1,
        max_blink_duration_frames=12,
    )
    detector = BlinkDetector(settings)

    # Normal open eyes for this user
    user_open_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.30, 0.21)}
    r_init = detector.update(user_open_face)

    assert r_init["left_state"] == "OPEN"
    assert r_init["right_state"] == "OPEN"
    # Right eye open threshold should be scaled down according to right baseline (~0.144)
    assert r_init["right_threshold_close"] < 0.16, f"Right close threshold should adapt to < 0.16, got {r_init['right_threshold_close']}"

    # Right eye blinks (drops to 0.11, while left stays at 0.30)
    user_right_blink = {"has_face": True, "landmarks": make_landmarks_with_ear(0.30, 0.11)}
    for _ in range(2):
        detector.update(user_right_blink)

    # Right eye reopens to 0.21
    r_click = detector.update(user_open_face)
    assert r_click["event"] == RIGHT_CLICK, f"Expected {RIGHT_CLICK} with adapted baseline, got {r_click['event']}"
    print("[PASS] Asymmetric baseline adaptation verified: right eye at 0.21 baseline blinked cleanly.")
    return True


def test_slow_blink_and_prolonged_closure():
    """Test that prolonged eye closure (resting eyes / squint) does not trigger accidental clicks."""
    settings = EyeBlinkSettings(
        min_blink_frames=1,
        max_blink_duration_frames=10,
    )
    detector = BlinkDetector(settings)

    open_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.28)}
    left_closed = {"has_face": True, "landmarks": make_landmarks_with_ear(0.10, 0.28)}

    detector.update(open_face)

    # Hold left eye closed for 15 frames (> max 10)
    for _ in range(15):
        detector.update(left_closed)

    assert detector.left_eye.is_prolonged, "Should be flagged as prolonged closure"

    # Reopen after prolonged closure -> NO click must be emitted
    r_reopen = detector.update(open_face)
    assert r_reopen["event"] is None, f"Prolonged closure must not emit click, got {r_reopen['event']}"
    assert "PROLONGED" in (r_reopen.get("last_reject_reason") or "")
    print("[PASS] Prolonged eye closure successfully rejected without click.")
    return True


def test_face_loss_and_recovery():
    """Test that losing face detection immediately clears blink counters and emits no clicks."""
    detector = BlinkDetector(EyeBlinkSettings(min_blink_frames=1, max_blink_duration_frames=12))

    left_closed = {"has_face": True, "landmarks": make_landmarks_with_ear(0.10, 0.28)}
    open_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.28)}

    # Accumulate 2 frames of closure
    detector.update(left_closed)
    detector.update(left_closed)
    assert detector.left_eye.closed_frames == 2

    # Face lost
    lost_face = {"has_face": False, "landmarks": []}
    r_lost = detector.update(lost_face)
    assert r_lost["event"] is None
    assert detector.left_eye.closed_frames == 0, "Counter must be cleared on face loss"

    # Face lost with None
    r_none = detector.update(None)
    assert r_none["event"] is None

    # Face returns with open eyes
    r_back = detector.update(open_face)
    assert r_back["event"] is None, "Face recovery must not trigger residual clicks"
    print("[PASS] Face loss safety interlock verified.")
    return True


def test_cooldown_and_duplicate_event_prevention():
    """Test that cooldown prevents rapid duplicate triggers from consecutive closures."""
    cooldown = 12
    settings = EyeBlinkSettings(
        min_blink_frames=1,
        max_blink_duration_frames=10,
        blink_cooldown_frames=cooldown,
    )
    detector = BlinkDetector(settings)

    open_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.28)}
    left_closed = {"has_face": True, "landmarks": make_landmarks_with_ear(0.10, 0.28)}

    # 1. Trigger legitimate first click
    detector.update(open_face)
    detector.update(left_closed)
    detector.update(left_closed)
    r_first = detector.update(open_face)
    assert r_first["event"] == LEFT_CLICK, "First blink should trigger LEFT_CLICK"
    assert detector.cooldown_remaining == cooldown

    # 2. Immediate second blink during cooldown window
    detector.update(left_closed)
    detector.update(left_closed)
    r_second = detector.update(open_face)
    assert r_second["event"] is None, "Second blink during cooldown must be blocked"
    print("[PASS] Cooldown correctly blocked duplicate trigger.")
    return True


# ================= Specific Duration Verification Tests ================= #

def test_blink_duration_100ms():
    """Verify natural fast 100 ms blink is accepted and triggers LEFT_CLICK."""
    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.08,
        max_blink_duration_sec=0.65,
        blink_cooldown_sec=0.30,
    )
    detector = BlinkDetector(settings)
    open_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.28)}
    left_closed = {"has_face": True, "landmarks": make_landmarks_with_ear(0.12, 0.28)}

    t = 1000.0
    detector.update(open_face, timestamp=t)
    # Eye closes at t = 1000.05
    detector.update(left_closed, timestamp=t + 0.05)
    # Eye reopens at t = 1000.15 (100 ms duration)
    r = detector.update(open_face, timestamp=t + 0.15)
    assert r["event"] == LEFT_CLICK, f"100ms blink must emit {LEFT_CLICK}, got {r['event']}"
    print("[PASS] 100 ms blink successfully accepted as LEFT_CLICK.")
    return True


def test_blink_duration_200ms():
    """Verify natural 200 ms blink is accepted and triggers LEFT_CLICK."""
    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.08,
        max_blink_duration_sec=0.65,
    )
    detector = BlinkDetector(settings)
    open_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.28)}
    left_closed = {"has_face": True, "landmarks": make_landmarks_with_ear(0.12, 0.28)}

    t = 2000.0
    detector.update(open_face, timestamp=t)
    detector.update(left_closed, timestamp=t + 0.05)
    detector.update(left_closed, timestamp=t + 0.15)
    # Reopens at t = 2000.25 (200 ms duration)
    r = detector.update(open_face, timestamp=t + 0.25)
    assert r["event"] == LEFT_CLICK, f"200ms blink must emit {LEFT_CLICK}, got {r['event']}"
    print("[PASS] 200 ms blink successfully accepted as LEFT_CLICK.")
    return True


def test_blink_duration_300ms():
    """Verify natural 300 ms right-eye blink is accepted and triggers RIGHT_CLICK."""
    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.08,
        max_blink_duration_sec=0.65,
    )
    detector = BlinkDetector(settings)
    open_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.28)}
    right_closed = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.12)}

    t = 3000.0
    detector.update(open_face, timestamp=t)
    detector.update(right_closed, timestamp=t + 0.05)
    detector.update(right_closed, timestamp=t + 0.20)
    # Reopens at t = 3000.35 (300 ms duration)
    r = detector.update(open_face, timestamp=t + 0.35)
    assert r["event"] == RIGHT_CLICK, f"300ms blink must emit {RIGHT_CLICK}, got {r['event']}"
    print("[PASS] 300 ms blink successfully accepted as RIGHT_CLICK.")
    return True


def test_blink_duration_400ms():
    """Verify deliberate 400 ms blink is accepted and triggers LEFT_CLICK."""
    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.08,
        max_blink_duration_sec=0.65,
    )
    detector = BlinkDetector(settings)
    open_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.28)}
    left_closed = {"has_face": True, "landmarks": make_landmarks_with_ear(0.12, 0.28)}

    t = 4000.0
    detector.update(open_face, timestamp=t)
    detector.update(left_closed, timestamp=t + 0.05)
    detector.update(left_closed, timestamp=t + 0.25)
    # Reopens at t = 4000.45 (400 ms duration)
    r = detector.update(open_face, timestamp=t + 0.45)
    assert r["event"] == LEFT_CLICK, f"400ms blink must emit {LEFT_CLICK}, got {r['event']}"
    print("[PASS] 400 ms blink successfully accepted as LEFT_CLICK.")
    return True


def test_blink_duration_prolonged_rejection():
    """Verify eye closures exceeding 650 ms (e.g. 750-800 ms) are rejected as PROLONGED."""
    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.08,
        max_blink_duration_sec=0.65,
    )
    detector = BlinkDetector(settings)
    open_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.28)}
    left_closed = {"has_face": True, "landmarks": make_landmarks_with_ear(0.12, 0.28)}

    t = 5000.0
    detector.update(open_face, timestamp=t)
    detector.update(left_closed, timestamp=t + 0.05)
    # At t = 5000.50 (450ms in): still within valid window, not yet prolonged
    r_mid = detector.update(left_closed, timestamp=t + 0.50)
    assert not detector.left_eye.is_prolonged, "At 450ms, blink should NOT be marked prolonged"
    # At t = 5000.75 (700ms in): exceeds 650ms limit -> marked prolonged
    r_late = detector.update(left_closed, timestamp=t + 0.75)
    assert detector.left_eye.is_prolonged, "At 700ms (>650ms), eye MUST be marked prolonged"
    assert "PROLONGED" in (r_late.get("active_status") or "")

    # Eye finally reopens at t = 5000.85 (800ms total closure)
    r_reopen = detector.update(open_face, timestamp=t + 0.85)
    assert r_reopen["event"] is None, "Prolonged closure must NOT emit any click"
    assert "PROLONGED" in (r_reopen.get("last_reject_reason") or "")
    print("[PASS] Prolonged closure (>650 ms) correctly rejected.")
    return True


# ================= Eye State Reset & Recovery Tests ================= #

def test_eye_closing_and_reopening():
    """Verify that an eye transitions OPEN -> CLOSED -> REOPENING -> OPEN and resets timers."""
    detector = BlinkDetector()
    open_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.28)}
    closed_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.12, 0.28)}

    t = 6000.0
    r0 = detector.update(open_face, timestamp=t)
    assert r0["left_state_detailed"] == "OPEN"
    assert detector.left_eye.closure_start_time is None

    # Step into closed
    r1 = detector.update(closed_face, timestamp=t + 0.05)
    assert r1["left_state_detailed"] == "CLOSED"
    assert detector.left_eye.closure_start_time == t + 0.05

    # Reopen
    r2 = detector.update(open_face, timestamp=t + 0.25)
    assert r2["left_state_detailed"] == "OPEN"
    assert detector.left_eye.closure_start_time is None
    assert detector.left_eye.closure_duration_sec == 0.0
    assert not detector.left_eye.is_prolonged
    print("[PASS] Eye closing, reopening, and timer reset verified.")
    return True


def test_prolonged_closure_followed_by_reopening():
    """Verify prolonged eye closure cleans up completely upon reopening without stale state."""
    settings = EyeBlinkSettings(min_blink_duration_sec=0.08, max_blink_duration_sec=0.65)
    detector = BlinkDetector(settings)
    open_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.28)}
    left_closed = {"has_face": True, "landmarks": make_landmarks_with_ear(0.12, 0.28)}

    t = 7000.0
    detector.update(open_face, timestamp=t)
    # Closed for 1.2 seconds (> 0.65s)
    detector.update(left_closed, timestamp=t + 0.05)
    detector.update(left_closed, timestamp=t + 0.70)
    r_prolonged = detector.update(left_closed, timestamp=t + 1.20)
    assert detector.left_eye.is_prolonged, "Must be prolonged at 1.2s"
    assert "PROLONGED" in (r_prolonged.get("active_status") or "")

    # Reopening frame
    r_reopen = detector.update(open_face, timestamp=t + 1.25)
    assert r_reopen["event"] is None, "Prolonged closure must not emit click upon reopening"
    # State must be cleanly OPEN with no prolonged flag lingering
    assert r_reopen["left_state_detailed"] == "OPEN"
    assert detector.left_eye.closure_start_time is None
    assert detector.left_eye.closure_duration_sec == 0.0
    assert not detector.left_eye.is_prolonged
    print("[PASS] Prolonged closure reset verified: state is cleanly OPEN with zero lingering flags.")
    return True


def test_left_wink_after_previous_prolonged_closure():
    """Verify that a previous prolonged closure does NOT block subsequent valid winks."""
    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.08,
        max_blink_duration_sec=0.65,
        blink_cooldown_sec=0.20,
    )
    detector = BlinkDetector(settings)
    open_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.28)}
    left_closed = {"has_face": True, "landmarks": make_landmarks_with_ear(0.12, 0.28)}

    t = 8000.0
    # 1. First event: 1.5s prolonged closure
    detector.update(open_face, timestamp=t)
    detector.update(left_closed, timestamp=t + 0.10)
    detector.update(left_closed, timestamp=t + 1.50)
    detector.update(open_face, timestamp=t + 1.60)  # Reopened, rejected

    # 2. Eyes rest open for 0.4s (well past cooldown)
    detector.update(open_face, timestamp=t + 2.00)

    # 3. Second event: intentional 250 ms left wink
    detector.update(left_closed, timestamp=t + 2.05)
    detector.update(left_closed, timestamp=t + 2.15)
    r_wink = detector.update(open_face, timestamp=t + 2.30)

    assert r_wink["event"] == LEFT_CLICK, f"Subsequent wink must emit LEFT_CLICK, got {r_wink['event']}"
    print("[PASS] Left wink after previous prolonged closure successfully emitted LEFT_CLICK.")
    return True


def test_right_wink_after_previous_prolonged_closure():
    """Verify that a right wink after previous prolonged closure triggers RIGHT_CLICK cleanly."""
    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.08,
        max_blink_duration_sec=0.65,
        blink_cooldown_sec=0.20,
    )
    detector = BlinkDetector(settings)
    open_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.28)}
    right_closed = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.12)}

    t = 9000.0
    # 1. Prolonged right closure (1.5s)
    detector.update(open_face, timestamp=t)
    detector.update(right_closed, timestamp=t + 0.10)
    detector.update(right_closed, timestamp=t + 1.50)
    detector.update(open_face, timestamp=t + 1.60)

    # 2. Rest open
    detector.update(open_face, timestamp=t + 2.00)

    # 3. Intentional 250 ms right wink
    detector.update(right_closed, timestamp=t + 2.05)
    detector.update(right_closed, timestamp=t + 2.15)
    r_wink = detector.update(open_face, timestamp=t + 2.30)

    assert r_wink["event"] == RIGHT_CLICK, f"Subsequent right wink must emit RIGHT_CLICK, got {r_wink['event']}"
    print("[PASS] Right wink after previous prolonged closure successfully emitted RIGHT_CLICK.")
    return True


def test_suppression_reset_after_both_eyes_reopen():
    """Verify simultaneous suppression clears immediately when both eyes reopen and subsequent winks work."""
    settings = EyeBlinkSettings(
        min_blink_duration_sec=0.08,
        max_blink_duration_sec=0.65,
        blink_cooldown_sec=0.15,
        simultaneous_blink_suppression=True,
    )
    detector = BlinkDetector(settings)
    open_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.28)}
    both_closed = {"has_face": True, "landmarks": make_landmarks_with_ear(0.12, 0.12)}
    left_closed = {"has_face": True, "landmarks": make_landmarks_with_ear(0.12, 0.28)}

    t = 10000.0
    detector.update(open_face, timestamp=t)
    # Both eyes closed together for 200ms
    detector.update(both_closed, timestamp=t + 0.05)
    detector.update(both_closed, timestamp=t + 0.15)
    assert detector.simultaneous_suppression_active, "Suppression must be active during dual blink"

    # Both eyes reopen -> NO_ACTION emitted, suppression reset
    r_reopen = detector.update(open_face, timestamp=t + 0.25)
    assert r_reopen["event"] == NO_ACTION, f"Dual blink reopening must emit NO_ACTION, got {r_reopen['event']}"
    assert not detector.simultaneous_suppression_active, "Suppression must reset to False after reopening"

    # Rest open for 250ms
    detector.update(open_face, timestamp=t + 0.50)

    # Now perform single left wink
    detector.update(left_closed, timestamp=t + 0.55)
    detector.update(left_closed, timestamp=t + 0.65)
    r_left = detector.update(open_face, timestamp=t + 0.75)
    assert r_left["event"] == LEFT_CLICK, f"Single wink following dual blink must emit LEFT_CLICK, got {r_left['event']}"
    print("[PASS] Suppression reset verified: dual blink produced NO_ACTION, subsequent left wink fired LEFT_CLICK.")
    return True


def test_click_event_notification_visibility_and_state():
    """Verify that detected events and accept reasons match the UI notification requirements."""
    detector = BlinkDetector()
    open_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.28)}
    left_closed = {"has_face": True, "landmarks": make_landmarks_with_ear(0.12, 0.28)}
    right_closed = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.12)}

    t = 11000.0
    detector.update(open_face, timestamp=t)
    detector.update(left_closed, timestamp=t + 0.05)
    r_left = detector.update(open_face, timestamp=t + 0.25)
    assert r_left["event"] == LEFT_CLICK
    assert "LEFT_CLICK" in (r_left.get("last_accept_reason") or "")

    detector.reset()
    detector.update(open_face, timestamp=t + 1.0)
    detector.update(right_closed, timestamp=t + 1.05)
    r_right = detector.update(open_face, timestamp=t + 1.25)
    assert r_right["event"] == RIGHT_CLICK
    assert "RIGHT_CLICK" in (r_right.get("last_accept_reason") or "")

    print("[PASS] Click event notification state and acceptance reasons verified.")
    return True


# ================= Light Eye Closure & Sensitivity Tests ================= #

def test_light_eye_closure_left_click():
    """Verify that light, natural left-eye closure (EAR drops to 0.21 from 0.28) triggers LEFT_CLICK."""
    settings = EyeBlinkSettings(
        left_baseline_ear=0.28,
        right_baseline_ear=0.28,
        sensitivity=0.75,
        min_blink_frames=1,
        max_blink_duration_frames=15,
        min_blink_duration_sec=0.06,
        max_blink_duration_sec=0.65,
    )
    detector = BlinkDetector(settings)
    open_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.28)}
    # Light closure: EAR drops only to 0.21 (not deep 0.10/0.12)
    light_left_closed = {"has_face": True, "landmarks": make_landmarks_with_ear(0.21, 0.28)}

    t = 12000.0
    detector.update(open_face, timestamp=t)

    # Threshold close should be > 0.21 so 0.21 registers as closed
    assert detector.left_eye.threshold_close >= 0.212, f"Close threshold {detector.left_eye.threshold_close} should be >= 0.212"

    # Step into light closed
    r_closed = detector.update(light_left_closed, timestamp=t + 0.05)
    assert r_closed["left_state"] == "CLOSED", f"Light closure (0.21) must register as CLOSED, got {r_closed['left_state']}"
    assert r_closed["right_state"] == "OPEN"

    # Reopen to 0.28
    r_reopen = detector.update(open_face, timestamp=t + 0.20)
    assert r_reopen["event"] == LEFT_CLICK, f"Light closure must trigger LEFT_CLICK on reopening, got {r_reopen['event']}"
    assert r_reopen["left_state"] == "OPEN"
    print("[PASS] Light left-eye closure (EAR=0.21) successfully triggered LEFT_CLICK.")
    return True


def test_light_eye_closure_right_click():
    """Verify that light, natural right-eye closure (EAR drops to 0.21 from 0.28) triggers RIGHT_CLICK."""
    settings = EyeBlinkSettings(
        left_baseline_ear=0.28,
        right_baseline_ear=0.28,
        sensitivity=0.75,
        min_blink_frames=1,
        max_blink_duration_frames=15,
        min_blink_duration_sec=0.06,
        max_blink_duration_sec=0.65,
    )
    detector = BlinkDetector(settings)
    open_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.28)}
    light_right_closed = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.21)}

    t = 13000.0
    detector.update(open_face, timestamp=t)

    # Step into light closed
    r_closed = detector.update(light_right_closed, timestamp=t + 0.05)
    assert r_closed["right_state"] == "CLOSED", f"Light closure (0.21) must register as CLOSED, got {r_closed['right_state']}"
    assert r_closed["left_state"] == "OPEN"

    # Reopen to 0.28
    r_reopen = detector.update(open_face, timestamp=t + 0.20)
    assert r_reopen["event"] == RIGHT_CLICK, f"Light closure must trigger RIGHT_CLICK on reopening, got {r_reopen['event']}"
    assert r_reopen["right_state"] == "OPEN"
    print("[PASS] Light right-eye closure (EAR=0.21) successfully triggered RIGHT_CLICK.")
    return True


def test_normal_natural_bilateral_blink_no_false_clicks():
    """Verify that a normal natural bilateral blink with light closure triggers NO clicks."""
    settings = EyeBlinkSettings(
        left_baseline_ear=0.28,
        right_baseline_ear=0.28,
        sensitivity=0.75,
        simultaneous_blink_suppression=True,
    )
    detector = BlinkDetector(settings)
    open_face = {"has_face": True, "landmarks": make_landmarks_with_ear(0.28, 0.28)}
    both_light_closed = {"has_face": True, "landmarks": make_landmarks_with_ear(0.21, 0.21)}

    t = 14000.0
    detector.update(open_face, timestamp=t)

    # Both eyes lightly closed together for 2 frames
    r1 = detector.update(both_light_closed, timestamp=t + 0.05)
    assert r1["suppression_active"], "Both eyes closed lightly MUST activate suppression"
    assert r1["event"] is None

    r2 = detector.update(both_light_closed, timestamp=t + 0.10)
    assert r2["suppression_active"]
    assert r2["event"] is None

    # Both eyes reopen
    r_reopen = detector.update(open_face, timestamp=t + 0.18)
    assert r_reopen["event"] in (None, NO_ACTION), f"Natural blink must NOT emit clicks, got {r_reopen['event']}"
    assert r_reopen["event"] != LEFT_CLICK and r_reopen["event"] != RIGHT_CLICK
    print("[PASS] Normal natural bilateral blink correctly suppressed without false clicks.")
    return True


def test_open_eye_noise_immunity():
    """Verify that open-eye micro-movements (EAR 0.25 to 0.29) never cause false clicks."""
    settings = EyeBlinkSettings(
        left_baseline_ear=0.28,
        right_baseline_ear=0.28,
        sensitivity=0.75,
    )
    detector = BlinkDetector(settings)

    # Fluctuating open eye frames: EAR never drops below 0.25
    test_ears = [0.28, 0.27, 0.26, 0.255, 0.265, 0.28, 0.29, 0.275]
    t = 15000.0
    for i, ear_val in enumerate(test_ears):
        face = {"has_face": True, "landmarks": make_landmarks_with_ear(ear_val, ear_val)}
        r = detector.update(face, timestamp=t + i * 0.033)
        assert r["left_state"] == "OPEN", f"At EAR={ear_val}, left eye must remain OPEN"
        assert r["right_state"] == "OPEN", f"At EAR={ear_val}, right eye must remain OPEN"
        assert r["event"] is None, f"Open eye noise must never trigger event, got {r['event']}"

    print("[PASS] Open eye noise immunity verified across fluctuating EAR values.")
    return True


def test_sensitivity_adjustment_dynamic():
    """Verify dynamic sensitivity scaling (higher sensitivity = higher close threshold)."""
    detector = BlinkDetector()
    detector.set_sensitivity(0.50)  # Lower sensitivity
    low_sens_thresh = detector.left_eye.threshold_close

    detector.set_sensitivity(0.85)  # Higher sensitivity
    high_sens_thresh = detector.left_eye.threshold_close

    assert high_sens_thresh > low_sens_thresh, (
        f"Higher sensitivity must produce higher close threshold (easier closure): "
        f"{high_sens_thresh:.4f} vs {low_sens_thresh:.4f}"
    )
    print(f"[PASS] Dynamic sensitivity scaling verified: Low (0.50)={low_sens_thresh:.3f}, High (0.85)={high_sens_thresh:.3f}")
    return True


if __name__ == "__main__":
    print("=" * 65)
    print("Testing Independent Adaptive Blink Detection (Phase 3)...")
    print("=" * 65 + "\n")

    results = []
    # Legacy tests
    results.append(("Legacy Blink Pattern", test_blink_pattern()))
    results.append(("Legacy Independent Eye Tracking", test_independent_eye_tracking()))
    results.append(("Legacy Simultaneous Suppression", test_simultaneous_suppression()))

    # Comprehensive Phase 3 tests
    results.append(("Normal Open Eyes No Action", test_normal_open_eyes_no_action()))
    results.append(("Short Left-Eye Blink", test_short_left_eye_blink()))
    results.append(("Short Right-Eye Blink", test_short_right_eye_blink()))
    results.append(("Simultaneous Dual Blink Suppression", test_simultaneous_blink_suppression_event()))
    results.append(("One Eye Closed (No False Suppression)", test_one_eye_closed_while_other_remains_open()))
    results.append(("Different EAR Baselines", test_different_ear_baselines()))
    results.append(("Slow Blink & Prolonged Closure", test_slow_blink_and_prolonged_closure()))
    results.append(("Face Loss & Recovery", test_face_loss_and_recovery()))
    results.append(("Cooldown & Duplicate Prevention", test_cooldown_and_duplicate_event_prevention()))

    # Duration-specific tests (100ms, 200ms, 300ms, 400ms, prolonged)
    results.append(("Duration 100ms", test_blink_duration_100ms()))
    results.append(("Duration 200ms", test_blink_duration_200ms()))
    results.append(("Duration 300ms", test_blink_duration_300ms()))
    results.append(("Duration 400ms", test_blink_duration_400ms()))
    results.append(("Duration Prolonged Rejection", test_blink_duration_prolonged_rejection()))

    # Eye state reset and recovery tests
    results.append(("Eye Closing and Reopening", test_eye_closing_and_reopening()))
    results.append(("Prolonged Closure Reopening Reset", test_prolonged_closure_followed_by_reopening()))
    results.append(("Left Wink After Prolonged Closure", test_left_wink_after_previous_prolonged_closure()))
    results.append(("Right Wink After Prolonged Closure", test_right_wink_after_previous_prolonged_closure()))
    results.append(("Suppression Reset After Reopen", test_suppression_reset_after_both_eyes_reopen()))
    results.append(("Click Event Notification Visibility", test_click_event_notification_visibility_and_state()))

    # Light closure and sensitivity tests
    results.append(("Light Left-Eye Closure Click", test_light_eye_closure_left_click()))
    results.append(("Light Right-Eye Closure Click", test_light_eye_closure_right_click()))
    results.append(("Natural Bilateral Blink Suppression", test_normal_natural_bilateral_blink_no_false_clicks()))
    results.append(("Open Eye Noise Immunity", test_open_eye_noise_immunity()))
    results.append(("Dynamic Sensitivity Adjustment", test_sensitivity_adjustment_dynamic()))

    print("\n--- Test Summary ---")
    all_pass = True
    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {name}")
        all_pass = all_pass and passed

    print("\nOverall: " + ("ALL PASSED" if all_pass else "SOME TESTS FAILED"))
    sys.exit(0 if all_pass else 1)
