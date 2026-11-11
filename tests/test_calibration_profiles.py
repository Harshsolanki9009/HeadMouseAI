"""Comprehensive automated tests for Phase 8: Smart Calibration and Personalization System.

Tests cover:
1. Nose calibration, center mapping, and recalibration.
2. Eye baseline calibration and independent left/right wink sensitivity.
3. Gesture calibration (mouth geometry and eyebrow baselines).
4. Settings validation, boundary checking, and NaN/Inf rejection.
5. User profile persistence, loading, and factory reset to defaults.
6. Calibration wizard navigation, cancellation safety, and profile application.
"""

from __future__ import annotations

import math
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

# Ensure QApplication exists for GUI testing
app = QApplication.instance()
if app is None:
    app = QApplication([])

from config.settings import (
    AppSettings,
    EyeBlinkSettings,
    NoseTrackingSettings,
    ZoomSettings,
    validate_calibration_data,
)
from core.blink_detector import BlinkDetector, SingleEyeTracker
from core.gesture_zoom import GestureZoomTracker, MODE_NONE, MODE_SCROLL, MODE_ZOOM, STATE_NORMAL, STATE_RAISED
from core.nose_tracker import NoseTracker
from gui.dialogs.calibration_wizard import CalibrationWizard, SAMPLE_FRAMES_PER_STEP
from gui.widgets.settings_tab import SettingsTabWidget
from gui.worker import VisionWorker


# ===================================================================== #
# 1. NOSE CALIBRATION TESTS
# ===================================================================== #
def test_nose_tracker_calibration_and_center_mapping():
    """Verify nose neutral calibration calculates correct median and centers relative movement."""
    tracker = NoseTracker(smoothing_strength=1.0, dead_zone=0.0)

    # Initially uncalibrated (neutral at 0.5, 0.5)
    assert not tracker.is_calibrated
    assert tracker.neutral_x == 0.5
    assert tracker.neutral_y == 0.5

    # Accumulate 10 calibration frames with nose offset to (0.55, 0.45)
    tracker.start_calibration(frames=10)
    assert tracker.is_calibrating

    for _ in range(10):
        # MediaPipe normalized coordinates (nx, ny_camera): note ny_adjusted = 1.0 - ny_camera
        done = tracker.add_calibration_sample({"has_face": True, "landmarks": [None, [0.55, 0.55]]})

    assert done
    assert tracker.is_calibrated
    assert not tracker.is_calibrating
    assert pytest.approx(tracker.neutral_x, abs=0.001) == 0.55
    # ny_camera = 0.55 -> ny_adjusted = 1.0 - 0.55 = 0.45
    assert pytest.approx(tracker.neutral_y, abs=0.001) == 0.45

    # Moving exactly at neutral position produces (0, 0) relative displacement
    tracker.update({"has_face": True, "landmarks": [None, [0.55, 0.55]]})
    rel_dx, rel_dy = tracker.get_relative_position(smoothed=False)
    assert pytest.approx(rel_dx, abs=1e-5) == 0.0
    assert pytest.approx(rel_dy, abs=1e-5) == 0.0

    # Moving to (0.60, 0.50) gives positive dx and positive dy (upward in adjusted coordinates)
    tracker.update({"has_face": True, "landmarks": [None, [0.60, 0.50]]})
    rel_dx, rel_dy = tracker.get_relative_position(smoothed=False)
    assert pytest.approx(rel_dx, abs=0.001) == 0.05
    assert pytest.approx(rel_dy, abs=0.001) == 0.05


def test_nose_tracker_set_neutral_and_recalibration():
    """Verify explicit neutral center setter and clean recalibration cycle."""
    tracker = NoseTracker()
    tracker.set_neutral(0.48, 0.52)
    assert tracker.is_calibrated
    assert tracker.neutral_x == 0.48
    assert tracker.neutral_y == 0.52

    # Reject invalid coordinates outside physiological bounds
    tracker.set_neutral(0.05, 0.95)  # Out of range
    assert tracker.neutral_x == 0.48  # Kept prior valid values

    # Recalibrate
    tracker.reset()
    assert not tracker.is_calibrated
    assert tracker.neutral_x == 0.5


# ===================================================================== #
# 2. EYE CALIBRATION & INDEPENDENT SENSITIVITY TESTS
# ===================================================================== #
def test_eye_tracker_baseline_calibration_and_thresholds():
    """Verify open-eye baseline calibration adjusts closing/opening Schmitt thresholds."""
    tracker = SingleEyeTracker(name="left", initial_baseline=0.28, sensitivity=0.75)
    # Default initial baseline
    assert pytest.approx(tracker.baseline_ear, abs=0.001) == 0.28
    initial_close = tracker.threshold_close
    initial_open = tracker.threshold_open
    assert initial_close < initial_open

    # User with smaller resting eyes (baseline = 0.22)
    tracker.set_baseline(0.22)
    assert pytest.approx(tracker.baseline_ear, abs=0.001) == 0.22
    # Thresholds should scale down proportionally
    assert tracker.threshold_close < initial_close
    assert tracker.threshold_open < initial_open

    # User with larger resting eyes (baseline = 0.35)
    tracker.set_baseline(0.35)
    assert pytest.approx(tracker.baseline_ear, abs=0.001) == 0.35
    assert tracker.threshold_close > initial_close


def test_independent_left_right_wink_sensitivity():
    """Verify left and right eyes can have independent sensitivities."""
    settings = EyeBlinkSettings(
        left_baseline_ear=0.30,
        right_baseline_ear=0.30,
        left_sensitivity=0.85,  # Higher sensitivity (lighter closure triggers click)
        right_sensitivity=0.60, # Lower sensitivity (firmer closure required)
    )
    detector = BlinkDetector(settings)
    assert detector.left_eye.sensitivity == 0.85
    assert detector.right_eye.sensitivity == 0.60

    # Left eye close threshold should be higher (closer to baseline) than right eye
    assert detector.left_eye.threshold_close > detector.right_eye.threshold_close

    # Dynamic update of sensitivities
    detector.set_sensitivities(left_sensitivity=0.70, right_sensitivity=0.80)
    assert detector.left_eye.sensitivity == 0.70
    assert detector.right_eye.sensitivity == 0.80
    assert detector.left_eye.threshold_close < detector.right_eye.threshold_close


# ===================================================================== #
# 3. GESTURE CALIBRATION TESTS (MOUTH & EYEBROWS)
# ===================================================================== #
def test_gesture_zoom_baseline_calibration():
    """Verify gesture tracker calibrates mouth width and eyebrow baselines via medians."""
    settings = ZoomSettings(
        left_eyebrow_baseline=0.16,
        right_eyebrow_baseline=0.16,
        mouth_width_baseline=0.52,
    )
    tracker = GestureZoomTracker(settings)

    # Calibrate with custom user samples
    leb_samples = [0.18, 0.19, 0.185, 0.192, 0.188]
    reb_samples = [0.175, 0.180, 0.178, 0.182, 0.179]
    mw_samples = [0.55, 0.56, 0.54, 0.555, 0.548]

    tracker.calibrate_baseline(leb_samples, reb_samples, mw_samples)
    assert tracker.is_calibrated
    assert pytest.approx(tracker.left_eyebrow_baseline, abs=0.005) == 0.188
    assert pytest.approx(tracker.right_eyebrow_baseline, abs=0.005) == 0.179
    assert pytest.approx(tracker.mouth_width_baseline, abs=0.005) == 0.55


def test_gesture_zoom_and_scroll_sensitivity():
    """Verify scroll and zoom sensitivities scale step amounts correctly."""
    tracker = GestureZoomTracker()
    tracker.set_sensitivities(scroll_sensitivity=2.0, scroll_step=3)
    assert tracker.scroll_step == 3
    assert tracker.scroll_sensitivity == 2.0


# ===================================================================== #
# 4. SETTINGS VALIDATION & PHYSIOLOGICAL SAFETY CHECKS
# ===================================================================== #
def test_settings_validation_valid_and_invalid():
    """Verify AppSettings.validate catches out-of-range, NaN, and corrupt parameters."""
    cfg = AppSettings()
    # Default configuration must be 100% valid
    errors = cfg.validate()
    assert len(errors) == 0, f"Default settings should be valid, got errors: {errors}"

    # Invalid nose sensitivity
    cfg.nose_tracking.sensitivity = -2.0
    errors = cfg.validate()
    assert any("Nose sensitivity" in e for e in errors)
    cfg.nose_tracking.sensitivity = 1.0

    # Invalid dead zone
    cfg.nose_tracking.dead_zone = 150.0
    errors = cfg.validate()
    assert any("Dead zone" in e for e in errors)
    cfg.nose_tracking.dead_zone = 4.0

    # NaN detection
    cfg.eye_blink.left_baseline_ear = float("nan")
    errors = cfg.validate()
    assert any("Left baseline EAR" in e for e in errors)
    cfg.eye_blink.left_baseline_ear = 0.28

    # Infinite value detection
    cfg.mouse.cursor_speed = float("inf")
    errors = cfg.validate()
    assert any("Cursor speed" in e for e in errors)
    cfg.mouse.cursor_speed = 3


def test_validate_calibration_data():
    """Verify validate_calibration_data rejects physiologically impossible baselines."""
    # Valid calibration data
    valid_data = {
        "neutral_x": 0.51,
        "neutral_y": 0.49,
        "left_baseline_ear": 0.29,
        "right_baseline_ear": 0.28,
        "mouth_width_baseline": 0.54,
        "left_eyebrow_baseline": 0.16,
        "right_eyebrow_baseline": 0.16,
    }
    is_valid, msg = validate_calibration_data(valid_data)
    assert is_valid
    assert msg == ""

    # Eye closed during resting calibration (EAR too low)
    invalid_eyes = dict(valid_data, left_baseline_ear=0.08)
    is_valid, msg = validate_calibration_data(invalid_eyes)
    assert not is_valid
    assert "left eye baseline EAR" in msg

    # Head turned completely away from camera (extreme neutral_x)
    invalid_nose = dict(valid_data, neutral_x=0.95)
    is_valid, msg = validate_calibration_data(invalid_nose)
    assert not is_valid
    assert "neutral_x" in msg

    # Mouth wide open/yawn during neutral mouth calibration
    invalid_mouth = dict(valid_data, mouth_width_baseline=0.98)
    is_valid, msg = validate_calibration_data(invalid_mouth)
    assert not is_valid
    assert "mouth width baseline" in msg


# ===================================================================== #
# 5. USER PROFILES PERSISTENCE & FACTORY RESET
# ===================================================================== #
def test_settings_persistence_and_reset_to_defaults(tmp_path: Path):
    """Verify settings save, profile export/import, and factory reset."""
    custom_profile_file = tmp_path / "user_profile.toml"

    cfg = AppSettings()
    cfg.nose_tracking.sensitivity = 3.5
    cfg.nose_tracking.dead_zone = 8.0
    cfg.eye_blink.left_sensitivity = 0.82
    cfg.eye_blink.right_sensitivity = 0.78
    cfg.zoom.scroll_step = 4

    # Save to custom profile
    assert cfg.save_profile(custom_profile_file)
    assert custom_profile_file.is_file()

    # Load back from profile
    loaded = AppSettings.load_profile(custom_profile_file)
    assert pytest.approx(loaded.nose_tracking.sensitivity, abs=0.01) == 3.5
    assert pytest.approx(loaded.nose_tracking.dead_zone, abs=0.01) == 8.0
    assert pytest.approx(loaded.eye_blink.left_sensitivity, abs=0.01) == 0.82
    assert pytest.approx(loaded.eye_blink.right_sensitivity, abs=0.01) == 0.78
    assert loaded.zoom.scroll_step == 4

    # Reset to defaults
    with patch.object(loaded, "save"):
        loaded.reset_to_defaults()
        assert loaded.nose_tracking.sensitivity == 1.0
        assert loaded.nose_tracking.dead_zone == 4.0
        assert loaded.eye_blink.left_sensitivity == 0.75
        assert loaded.eye_blink.right_sensitivity == 0.75
        assert loaded.zoom.scroll_step == 2


# ===================================================================== #
# 6. CALIBRATION WIZARD UI & WORKFLOW TESTS
# ===================================================================== #
def test_calibration_wizard_step_transitions_and_sampling():
    """Verify CalibrationWizard transitions through guided steps and collects valid data."""
    with patch("core.camera.cv2.VideoCapture"), patch("core.face_landmarker.tasks.vision.FaceLandmarker.create_from_options"):
        worker = VisionWorker()
        wizard = CalibrationWizard(worker=worker)

        assert wizard.stack.count() == 5
        assert wizard.stack.currentIndex() == 0  # Step 1: Positioning

        # In step 1: Next disabled until face is detected
        wizard.on_telemetry({"has_face": False})
        assert not wizard.btn_next.isEnabled()

        # Face detected: Next unlocks
        wizard.on_telemetry({"has_face": True, "fps": 30.0, "latency_ms": 12.0})
        assert wizard.btn_next.isEnabled()

        # Step 1 -> Step 2 (Head Position / Nose Center)
        wizard.btn_next.click()
        assert wizard.stack.currentIndex() == 1
        assert not wizard.btn_next.isEnabled()  # Disabled until sampled

        # Trigger nose sampling
        wizard._start_sampling(1)
        for _ in range(SAMPLE_FRAMES_PER_STEP):
            wizard.on_telemetry({"has_face": True, "norm_cx": 0.52, "norm_cy": 0.48})
        assert wizard.candidate_nose_x == 0.52
        assert wizard.candidate_nose_y == 0.48
        assert wizard.btn_next.isEnabled()

        # Step 2 -> Step 3 (Eye Controls)
        wizard.btn_next.click()
        assert wizard.stack.currentIndex() == 2
        wizard._start_sampling(2)
        for _ in range(SAMPLE_FRAMES_PER_STEP):
            wizard.on_telemetry({"has_face": True, "left_ear": 0.28, "right_ear": 0.27})
        assert wizard.candidate_left_ear == 0.28
        assert wizard.candidate_right_ear == 0.27
        assert wizard.btn_next.isEnabled()

        # Step 3 -> Step 4 (Optional Gestures)
        wizard.btn_next.click()
        assert wizard.stack.currentIndex() == 3
        assert wizard.btn_next.isEnabled()

        # Step 4 -> Step 5 (Summary & Confirmation)
        wizard.btn_next.click()
        assert wizard.stack.currentIndex() == 4
        assert wizard.btn_next.text() == "Apply & Finish"
        assert wizard.btn_next.isEnabled()

        # Apply profile: applies to worker and updates settings
        applied = []
        wizard.sig_profile_applied.connect(lambda d: applied.append(d))
        wizard.btn_next.click()

        assert len(applied) == 1
        assert applied[0]["neutral_x"] == 0.52
        assert applied[0]["left_baseline_ear"] == 0.28

        wizard.close()
        worker.stop()


def test_calibration_wizard_cancellation_safety():
    """Verify cancelling wizard completely discards candidates without modifying active baselines."""
    with patch("core.camera.cv2.VideoCapture"), patch("core.face_landmarker.tasks.vision.FaceLandmarker.create_from_options"):
        worker = VisionWorker()
        orig_nx = worker.nose_tracker.neutral_x
        orig_lear = worker.settings.eye_blink.left_baseline_ear

        wizard = CalibrationWizard(worker=worker)
        wizard.candidate_nose_x = 0.75
        wizard.candidate_left_ear = 0.38

        # User cancels wizard
        wizard._on_cancel()

        # Active worker and settings baselines remain completely unchanged
        assert worker.nose_tracker.neutral_x == orig_nx
        assert worker.settings.eye_blink.left_baseline_ear == orig_lear

        wizard.close()
        worker.stop()


def test_worker_rejects_corrupted_calibration_data():
    """Verify VisionWorker.apply_calibration_profile rejects corrupted/invalid data."""
    with patch("core.camera.cv2.VideoCapture"), patch("core.face_landmarker.tasks.vision.FaceLandmarker.create_from_options"):
        worker = VisionWorker()
        try:
            # Invalid payload: negative EAR baseline
            bad_data = {"left_baseline_ear": -0.15, "right_baseline_ear": 0.28}
            ok, msg = worker.apply_calibration_profile(bad_data)
            assert not ok
            assert "outside normal range" in msg

            # NaN payload
            nan_data = {"neutral_x": float("nan"), "neutral_y": 0.5}
            ok, msg = worker.apply_calibration_profile(nan_data)
            assert not ok
        finally:
            worker.stop()
