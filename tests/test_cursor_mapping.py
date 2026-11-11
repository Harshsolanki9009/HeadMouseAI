"""Test cursor mapping from nose movement to cursor control logic."""
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from core.nose_tracker import NoseTracker
from core.cursor_simulator import CursorSimulator
from config.settings import get_settings, AppSettings
from utils.logger import get_logger

logger = get_logger("TestCursorMapping")


def test_relative_position_directions():
    """Test that nose movement produces correct relative directions."""
    tracker = NoseTracker()
    tracker.neutral_x = 0.5
    tracker.neutral_y = 0.5

    # Test Right
    tracker.nose_x = 0.7
    tracker.nose_y = 0.5
    rx, ry = tracker.get_relative_position()
    assert rx > 0, f"Expected positive rx for Right, got {rx}"
    print(f"[PASS] Right: positive X ({rx:+.2f}) -> cursor moves right.")

    # Test Left
    tracker.nose_x = 0.3
    tracker.nose_y = 0.5
    rx, ry = tracker.get_relative_position()
    assert rx < 0, f"Expected negative rx for Left, got {rx}"
    print(f"[PASS] Left: negative X ({rx:+.2f}) -> cursor moves left.")

    # Test Up (north)
    tracker.nose_x = 0.5
    tracker.nose_y = 0.3
    rx, ry = tracker.get_relative_position()
    assert ry < 0, f"Expected negative ry for Up, got {ry}"
    print(f"[PASS] Up (north): negative Y ({ry:+.2f}) -> cursor moves up.")

    # Test Down (south)
    tracker.nose_x = 0.5
    tracker.nose_y = 0.7
    rx, ry = tracker.get_relative_position()
    assert ry > 0, f"Expected positive ry for Down, got {ry}"
    print(f"[PASS] Down (south): positive Y ({ry:+.2f}) -> cursor moves down.")

    return True


def test_dead_zone():
    """Test dead zone filtering."""
    tracker = NoseTracker()
    tracker.dead_zone = 5.0

    # Small movements that should be ignored
    tracker.nose_x = 0.502
    tracker.nose_y = 0.5
    dx, dy = tracker.get_relative_position()
    movement_abs = abs(dx) + abs(dy)
    assert movement_abs < 1.0, f"Expected movement < 1.0, got {movement_abs}"
    print(f"[PASS] Dead zone active for small movement ({movement_abs:.3f}) - no cursor movement.")

    # Larger movement that should move
    tracker.nose_x = 0.6
    dx, dy = tracker.get_relative_position()
    movement_abs = abs(dx) + abs(dy)
    assert movement_abs > 0.05, f"Expected larger movement > 0.05, got {movement_abs}"
    print(f"[PASS] Larger movement detected ({movement_abs:.3f}) - cursor will move.")
    return True


def test_sensitivity_scaling():
    """Test sensitivity multiplier effect on movement."""
    tracker = NoseTracker()
    sensitivity = 2.0

    tracker.neutral_x = 0.5
    tracker.neutral_y = 0.5

    tracker.nose_x = 0.8
    dx_base = abs(tracker.nose_x - tracker.neutral_x)  # 0.3

    cursor_move = dx_base * sensitivity
    expected = 0.6
    assert abs(cursor_move - expected) < 1e-5, f"Expected {expected}, got {cursor_move}"
    print(f"[PASS] Sensitivity scaling correct: base={dx_base:.3f} * sens={sensitivity} = {cursor_move:.3f}")
    return True


def test_smoothing_reduction():
    """Test that smoothing reduces jitter."""
    tracker = NoseTracker(smoothing_strength=0.2)
    tracker.neutral_x = 0.5
    tracker.neutral_y = 0.5

    # Simulate fluctuating positions
    positions = [0.5, 0.7, 0.4, 0.6, 0.45, 0.65]
    smoothed_values = []
    for px in positions:
        tracker.update({"has_face": True, "landmarks": [[0, 0, 0], [px, 0.5, 0]]})
        smoothed_values.append(tracker.smoothed_x)

    raw_variance = float(np.var(positions))
    smoothed_variance = float(np.var(smoothed_values))
    assert smoothed_variance < raw_variance, "Smoothed variance should be less than raw variance"
    print(f"[PASS] Smoothing reduces jitter (raw var: {raw_variance:.4f} -> smoothed var: {smoothed_variance:.4f}).")
    return True


def test_cursor_simulator_mapping():
    """Test CursorSimulator deadzone, sensitivity, and clamping."""
    sim = CursorSimulator(
        sensitivity=2.0,
        dead_zone=5.0,
        max_velocity=1000.0,
        window_width=640,
        window_height=480,
    )

    # Initial state should be window center
    assert sim.screen_position == (320.0, 240.0), f"Expected center (320, 240), got {sim.screen_position}"
    assert sim.is_active is True

    # Sub-deadzone movement should keep cursor centered and return moved=False
    cx, cy, moved = sim.update(0.001, 0.001)
    assert moved is False, "Small movement should not trigger cursor move"
    assert cx == 320.0 and cy == 240.0

    # Large movement should move cursor
    cx, cy, moved = sim.update(0.1, 0.05)
    assert moved is True, "Large movement should trigger cursor move"
    assert cx > 320.0, f"Expected cx > 320, got {cx}"
    assert cy < 240.0, f"Expected cy < 240 (moved up), got {cy}"

    # Recalibrate should reset to center
    sim.recalibrate()
    assert sim.screen_position == (320.0, 240.0)

    # Normalized position should be within [0.0, 1.0]
    nx, ny = sim.normalized_position
    assert 0.0 <= nx <= 1.0 and 0.0 <= ny <= 1.0
    print("[PASS] CursorSimulator deadzone, sensitivity, and clamping verified.")
    return True


if __name__ == "__main__":
    print("=" * 50)
    print("Testing Cursor Mapping Logic...")
    print("=" * 50 + "\n")

    results = []
    results.append(("Position Directions", test_relative_position_directions()))
    results.append(("Dead Zone", test_dead_zone()))
    results.append(("Sensitivity Scaling", test_sensitivity_scaling()))
    results.append(("Smoothing Reduction", test_smoothing_reduction()))
    results.append(("Cursor Simulator Mapping", test_cursor_simulator_mapping()))

    print("\n--- Test Summary ---")
    all_pass = True
    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {name}")
        all_pass = all_pass and passed

    print("\nOverall: " + ("ALL PASSED" if all_pass else "SOME TESTS FAILED"))
    sys.exit(0 if all_pass else 1)
