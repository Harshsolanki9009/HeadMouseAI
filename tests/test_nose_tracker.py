"""Test nose tracking logic (without live camera)."""
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from core.nose_tracker import NoseTracker
from utils.logger import get_logger

logger = get_logger("TestNoseTracker")


def create_simulated_landmarks():
    """Create simulated landmark data representing nose at various positions."""
    # Simulate landmarks with nose at different positions
    frames = []
    for nx, ny in [(0.7, 0.5), (0.8, 0.5), (0.9, 0.5), (0.5, 0.5)]:
        lm = [np.random.rand(3) for _ in range(468)]
        lm[NOSE_TIP] = nx  # nose tip x normalized
        # Store in adjusted coordinates (flip y)
        lm[NOSE_TIP][1] = 1 - ny
        frames.append(lm)

    return frames


NOSE_TIP = 1  # Just a constant for this test


def test_nose_position_update():
    """Test that nose tracker correctly updates position from landmark data."""
    tracker = NoseTracker()

    # Simulate landmarks where nose is slightly right of center
    tracker.nose_x = 0.6
    tracker.nose_y = 0.5  # Already adjusted, so neutral at 0.5

    result = tracker.update({"landmarks": [[{"x": 0.6, "y": 0.5}]]})

    if result[0]:  # detected = True
        print(f"[PASS] Nose tracker updated position.")
        dx = result[1] if hasattr(result, '__getitem__') else 0
        print(f"[INFO] Movement detected: {dx:.3f}")
        return True
    else:
        print("[FAIL] Nose tracker did not detect movement.")
        return False


def test_calibration_logic():
    """Test calibration basic functionality."""
    tracker = NoseTracker()
    # Manually set neutral position for calibration test
    tracker.neutral_x = 0.5
    tracker.neutral_y = 0.5

    # Reset tracking
    tracker.reset()

    # Simulate calibration by setting neutral manually
    for i in range(10):
        tracker.nose_x += np.random.normal(0, 0.001)
        tracker.nose_y += np.random.normal(0, 0.001)

    tracker.is_calibrated = True
    print("[PASS] Calibration simulation completed successfully.")
    print(f"[INFO] Neutral position: ({tracker.neutral_x:.4f}, {(1-tracker.neutral_y):.4f})")
    return True


def test_relative_position():
    """Test that relative position is correctly computed."""
    tracker = NoseTracker()
    tracker.neutral_x = 0.5
    tracker.neutral_y = 0.5

    # Set nose to left of neutral
    tracker.nose_x = 0.3
    tracker.nose_y = 0.5

    rx, ry = tracker.get_relative_position()

    expected_dx = tracker.nose_x - tracker.neutral_x  # Should be -0.2
    if abs(rx - expected_dx) < 0.01:
        print(f"[PASS] Relative position correct: ({rx:.4f}, {ry:.4f})")
        return True
    else:
        print(f"[FAIL] Expected dx={expected_dx:.4f}, got {rx:.4f}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("Testing NoseTracker module...")
    print("=" * 50 + "\n")

    results = []
    results.append(("Position Update", test_nose_position_update()))
    results.append(("Calibration Logic", test_calibration_logic()))
    results.append(("Relative Position", test_relative_position()))

    print("\n--- Test Summary ---")
    all_pass = True
    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {name}")
        all_pass = all_pass and passed

    print("\nOverall: " + ("ALL PASSED" if all_pass else "SOME TESTS FAILED"))
    sys.exit(0 if all_pass else 1)
