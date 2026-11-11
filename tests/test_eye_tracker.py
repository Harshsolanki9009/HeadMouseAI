"""Test eye tracking and EAR calculation logic for HeadMouse AI Phase 3."""
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from core.eye_tracker import EyeTracker, calculate_ear, calculate_eye_ear
from tests.test_blink import make_canonical_eye_landmarks
from utils.logger import get_logger

logger = get_logger("TestEyeTracker")


def make_synthetic_landmarks(is_open: bool = True) -> list[list]:
    """Create a synthetic landmark array with canonical open or closed eye geometry."""
    lm = []
    for _ in range(468):
        lm.append([0.0, 0.0, 0.0, 1.0, 1.0])

    # Horizontal span (width = 0.30, denom = 2 * 0.30 = 0.60)
    lm[33] = [0.35, 0.30, 0.0, 1.0, 1.0]
    lm[370] = [0.65, 0.30, 0.0, 1.0, 1.0]

    # Vertical span
    if is_open:
        # Height = 0.07 on each pair => num = 0.14 => EAR = 0.233
        lm[36] = [0.45, 0.265, 0.0, 1.0, 1.0]
        lm[133] = [0.45, 0.335, 0.0, 1.0, 1.0]
        lm[240] = [0.55, 0.265, 0.0, 1.0, 1.0]
        lm[51] = [0.55, 0.335, 0.0, 1.0, 1.0]
    else:
        # Height = 0.005 => num = 0.01 => EAR = 0.017
        lm[36] = [0.45, 0.300, 0.0, 1.0, 1.0]
        lm[133] = [0.45, 0.305, 0.0, 1.0, 1.0]
        lm[240] = [0.55, 0.300, 0.0, 1.0, 1.0]
        lm[51] = [0.55, 0.305, 0.0, 1.0, 1.0]

    return lm


def test_ear_calculation_open():
    """Test EAR for open eye shape."""
    landmarks = make_synthetic_landmarks(is_open=True)
    ear = calculate_ear(landmarks)
    assert ear is not None, "EAR should not be None for valid landmarks"
    assert 0.1 < ear < 0.6, f"EAR {ear} not in expected open range [0.1, 0.6]"
    print(f"[PASS] Open eye EAR = {ear:.4f}")
    return True


def test_ear_calculation_closed():
    """Test EAR for closed eye shape."""
    landmarks = make_synthetic_landmarks(is_open=False)
    ear = calculate_ear(landmarks)
    assert ear is not None, "EAR should not be None for valid landmarks"
    assert ear < 0.15, f"Closed EAR {ear} should be < 0.15"
    print(f"[PASS] Closed eye EAR = {ear:.4f}")
    return True


def test_eye_tracker_update():
    """Test EyeTracker.update with synthetic data."""
    tracker = EyeTracker(open_threshold=0.20)

    # Closed eyes
    closed_lm = make_synthetic_landmarks(is_open=False)
    result_closed = tracker.update({"has_face": True, "landmarks": closed_lm})
    assert not result_closed["left_is_open"], "Left eye should be closed"
    assert not result_closed["right_is_open"], "Right eye should be closed"
    print("[PASS] Eyes detected as CLOSED for low-EAR data.")

    # Open eyes
    open_lm = make_synthetic_landmarks(is_open=True)
    result_open = tracker.update({"has_face": True, "landmarks": open_lm})
    assert result_open["left_is_open"], "Left eye should be open"
    assert result_open["right_is_open"], "Right eye should be open"
    print("[PASS] Eyes detected as OPEN for high-EAR data.")

    return True


def test_blink_detection():
    """Test blink pattern detection over multiple frames."""
    tracker = EyeTracker(open_threshold=0.20)

    # Fill history with low EAR values (simulating closed state)
    for _ in range(30):
        tracker.left_ear_history.append(float(np.random.uniform(0.05, 0.10)))
        tracker.right_ear_history.append(float(np.random.uniform(0.05, 0.10)))

    # Simulate current frame with closed eyes
    closed_lm = make_synthetic_landmarks(is_open=False)
    result = tracker.update({"has_face": True, "landmarks": closed_lm})
    assert not result["left_is_open"], "Left eye should remain closed"
    print("[PASS] Blink detection: eye remains CLOSED during sustained closure.")
    return True


def test_independent_tracking():
    """Test that left and right eyes update tracking states."""
    tracker = EyeTracker()

    closed_lm = make_synthetic_landmarks(is_open=False)
    open_lm = make_synthetic_landmarks(is_open=True)

    r1 = tracker.update({"has_face": True, "landmarks": closed_lm})
    r2 = tracker.update({"has_face": True, "landmarks": open_lm})

    assert not r1["left_is_open"], "r1 left should be closed"
    assert r2["right_is_open"], "r2 right should be open"
    print("[PASS] Independent tracking: left=CLOSED, right=OPEN from sequential states.")
    return True


def test_canonical_independent_ear_calculation():
    """Test independent canonical EAR calculation on the same frame."""
    tracker = EyeTracker(open_threshold=0.22)

    # Case A: Left eye open, Right eye closed on the exact same frame
    lm_left_open_right_closed = make_canonical_eye_landmarks(left_open=True, right_open=False)
    res_a = tracker.update({"has_face": True, "landmarks": lm_left_open_right_closed})

    assert res_a["left_is_open"], "Left eye should be OPEN"
    assert not res_a["right_is_open"], "Right eye should be CLOSED"
    assert res_a["left_ear"] > 0.20, f"Left EAR {res_a['left_ear']} should be > 0.20"
    assert res_a["right_ear"] < 0.10, f"Right EAR {res_a['right_ear']} should be < 0.10"

    # Case B: Left eye closed, Right eye open on the exact same frame
    lm_left_closed_right_open = make_canonical_eye_landmarks(left_open=False, right_open=True)
    res_b = tracker.update({"has_face": True, "landmarks": lm_left_closed_right_open})

    assert not res_b["left_is_open"], "Left eye should be CLOSED"
    assert res_b["right_is_open"], "Right eye should be OPEN"
    assert res_b["left_ear"] < 0.10, f"Left EAR {res_b['left_ear']} should be < 0.10"
    assert res_b["right_ear"] > 0.20, f"Right EAR {res_b['right_ear']} should be > 0.20"

    print("[PASS] Canonical independent EAR: same-frame asymmetric eye states verified.")
    return True


if __name__ == "__main__":
    print("=" * 50)
    print("Testing EyeTracker module...")
    print("=" * 50 + "\n")

    results = []
    results.append(("Open EAR", test_ear_calculation_open()))
    results.append(("Closed EAR", test_ear_calculation_closed()))
    results.append(("Tracker Update", test_eye_tracker_update()))
    results.append(("Blink Detection", test_blink_detection()))
    results.append(("Independent Tracking", test_independent_tracking()))
    results.append(("Canonical Independent EAR", test_canonical_independent_ear_calculation()))

    print("\n--- Test Summary ---")
    all_pass = True
    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {name}")
        all_pass = all_pass and passed

    print("\nOverall: " + ("ALL PASSED" if all_pass else "SOME TESTS FAILED"))
    sys.exit(0 if all_pass else 1)
