"""Test calibration module logic (Phase 1 implementation)."""
import sys
import os
import time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from core.nose_tracker import NoseTracker
from config.settings import get_settings, AppSettings
from utils.logger import get_logger

logger = get_logger("TestCalibration")


def test_calibration_initialization():
    """Test that the AppSettings loads defaults correctly."""
    try:
        settings = get_settings()
        assert settings is not None, "Settings object should not be None"
        # Check key fields
        assert hasattr(settings.camera, "camera_index"), "Camera settings missing"
        assert hasattr(settings.nose_tracking, "sensitivity"), "Nose tracking settings missing"
        assert hasattr(settings.eye_blink, "left_eye_ear_threshold"), "Eye blink settings missing"
        print("[PASS] Settings loaded with all required fields.")
        return True
    except Exception as e:
        print(f"[FAIL] Error during settings test: {e}")
        return False


def test_calibration_run():
    """Test running a calibration sequence."""
    tracker = NoseTracker()
    tracker.is_calibrated = False

    print("[INFO] Starting calibration simulation...")
    tracker.calibrate(calibration_points=30)

    if tracker.is_calibrated:
        print(f"[PASS] Calibration completed successfully.")
        print(f"[INFO] Neutral position: ({tracker.neutral_x:.4f}, {(1-tracker.neutral_y):.4f})")
        # Verify neutral is centered around 0.5 for x, 0.5 for y
        if 0.3 < tracker.neutral_x < 0.7:
            print("[PASS] X neutral in expected range [0.3, 0.7].")
        else:
            print(f"[WARN] X neutral {tracker.neutral_x} outside expected range.")

        if 0.3 < (1 - tracker.neutral_y) < 0.7:
            print("[PASS] Y neutral in expected range [0.3, 0.7].")
        else:
            print(f"[WARN] Y neutral {(1-tracker.neutral_y)} outside expected range.")
        return True
    else:
        print("[FAIL] Calibration did not complete successfully.")
        return False


def test_calibration_preserves_state():
    """Test that calibration doesn't leave stale state from previous run."""
    tracker = NoseTracker()

    # Set up a known state before calibration
    tracker.nose_x = 0.8  # Far right of center
    tracker.neutral_x = 0.5

    # Run calibration
    tracker.calibrate(calibration_points=20)

    # After calibration, neutral should be re-centered (around 0.5, 0.5)
    dx_after = tracker.nose_x - tracker.neutral_x  # Should be small now
    dy_after = (1 - tracker.nose_y) - (1 - tracker.neutral_y)

    print(f"[INFO] After calibration: nose at ({tracker.nose_x:.3f}, {(1-tracker.nose_y):.3f}), "
          f"neutral at ({tracker.neutral_x:.3f}, {(1-tracker.neutral_y):.3f})")

    # Movement from original position should now be near zero
    expected_move = abs(0.8 - 0.5)  # Original offset was 0.3
    current_move = abs(dx_after) + abs(dy_after)

    if current_move < expected_move * 0.5:  # Within half the original offset
        print("[PASS] Calibration properly reset cursor movement baseline.")
        return True
    else:
        print(f"[FAIL] Calibration didn't reset movement well enough.")
        print(f"[INFO] Original movement ~{expected_move:.3f} vs current {current_move:.3f}")
        return False


def test_settings_save_load():
    """Test that settings can be saved and loaded correctly."""
    try:
        # Create modified settings
        modified = AppSettings.load()
        modified.nose_tracking.sensitivity = 5.0
        modified.nose_tracking.dead_zone = 10.0
        modified.eye_blink.left_eye_ear_threshold = 0.18
        modified.eye_blink.right_eye_ear_threshold = 0.19

        # Save
        modified.save()

        # Load
        loaded = AppSettings.load()

        if loaded.nose_tracking.sensitivity == 5.0 and \
           loaded.nose_tracking.dead_zone == 10.0 and \
           loaded.eye_blink.left_eye_ear_threshold == 0.18:
            print("[PASS] Settings saved and loaded correctly.")
            return True
        else:
            print("[FAIL] Settings values don't match after load.")
            print(f"  Expected sensitivity=5.0, got {loaded.nose_tracking.sensitivity}")
            print(f"  Expected dead_zone=10.0, got {loaded.nose_tracking.dead_zone}")
            return False
    except Exception as e:
        print(f"[FAIL] Error during save/load: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("Testing Calibration & Settings...")
    print("=" * 50 + "\n")

    results = []
    results.append(("Settings Initialization", test_calibration_initialization()))
    results.append(("Calibration Run", test_calibration_run()))
    results.append(("State Preservation", test_calibration_preserves_state()))
    results.append(("Save/Load Cycle", test_settings_save_load()))

    print("\n--- Test Summary ---")
    all_pass = True
    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {name}")
        all_pass = all_pass and passed

    print("\nOverall: " + ("ALL PASSED" if all_pass else "SOME TESTS FAILED"))
    sys.exit(0 if all_pass else 1)
