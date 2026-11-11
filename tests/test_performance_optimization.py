"""Automated verification tests for Phase 9: Performance Optimization.

Tests cover:
1. Low-latency camera bounded buffering and clean resource teardown.
2. FaceLandmarker zero-copy single-conversion pipeline (is_rgb=True).
3. Telemetry payload completeness including live performance & resource metrics.
4. TelemetryCardsWidget Section 4: Performance & Resources rendering.
5. Adaptive performance controls (resolution, performance profile, refresh rate) in SettingsTab.
6. Dynamic settings propagation into VisionWorker.
7. VisionWorker multi-cycle thread start/stop clean lifecycle.
"""

from __future__ import annotations

import time
from collections import deque
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

# Ensure QApplication exists for UI tests
app = QApplication.instance()
if app is None:
    app = QApplication([])

from config.settings import AppSettings
from core.camera import CameraCapture
from core.face_landmarker import FaceLandmarkerWrapper
from gui.widgets.settings_tab import SettingsTabWidget
from gui.widgets.telemetry_cards import TelemetryCardsWidget
from gui.worker import VisionWorker


# ===================================================================== #
# 1. Camera Capture Bounded Buffering & Teardown
# ===================================================================== #
def test_camera_bounded_buffering_and_resolution():
    """Verify camera frame buffer does not exceed maxlen=2 to prevent memory bloat."""
    cam = CameraCapture(index=0, width=640, height=480)
    assert isinstance(cam.frames, deque)
    assert cam.frames.maxlen == 2

    # Mock video capture
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    mock_cap.read.return_value = (True, dummy_frame)
    cam._cap = mock_cap
    cam.is_running = True

    # Read 10 frames into camera
    for _ in range(10):
        frame = cam.read_frame()
        assert frame is not None

    # Buffer must strictly contain at most 2 frames
    assert len(cam.frames) == 2
    assert cam.frame_count == 10

    # Resolution property
    mock_cap.get.side_effect = lambda prop: 640.0 if prop == 3 else 480.0
    assert cam.resolution == "640x480"
    assert cam.actual_width == 640
    assert cam.actual_height == 480

    # Dynamic resolution change
    cam.set_resolution(1280, 720)
    assert cam.width == 1280
    assert cam.height == 720

    # Clean release
    cam.close()
    assert not cam.is_running
    assert cam._cap is None
    assert len(cam.frames) == 0


# ===================================================================== #
# 2. FaceLandmarker Zero-Copy Pipeline
# ===================================================================== #
def test_face_landmarker_zero_copy_flag():
    """Verify detect_landmarks avoids cv2.cvtColor when is_rgb=True."""
    landmarker = FaceLandmarkerWrapper()
    dummy_rgb = np.zeros((480, 640, 3), dtype=np.uint8)

    with patch("cv2.cvtColor") as mock_cvt:
        # With is_rgb=True, cv2.cvtColor must NOT be called
        res_rgb = landmarker.detect_landmarks(dummy_rgb, is_rgb=True)
        mock_cvt.assert_not_called()
        assert isinstance(res_rgb, dict)
        assert "has_face" in res_rgb

    with patch("cv2.cvtColor", wraps=lambda img, code: img) as mock_cvt:
        # With is_rgb=False (default), cv2.cvtColor SHOULD be called
        res_bgr = landmarker.detect_landmarks(dummy_rgb, is_rgb=False)
        mock_cvt.assert_called_once()
        assert isinstance(res_bgr, dict)


# ===================================================================== #
# 3. Telemetry Performance Metrics Completeness
# ===================================================================== #
def test_telemetry_payload_performance_fields():
    """Verify VisionWorker telemetry dictionary contains all Phase 9 performance metrics."""
    worker = VisionWorker(settings=AppSettings())

    worker.pipeline_fps = 24.5
    worker.last_inference_ms = 11.2
    worker._current_cpu_percent = 14.8
    worker._current_ram_mb = 158.4

    mouse_status = {
        "enabled": False,
        "emergency_stopped": False,
        "is_mouse_down": False,
        "screen_x": 500,
        "screen_y": 400,
    }
    blink_state = {"left_ear": 0.28, "right_ear": 0.27, "event": None}
    gesture_status = {"mouth_width_ratio": 0.52}

    t = worker._build_telemetry(
        has_face=True,
        is_calibrated=True,
        blink_state=blink_state,
        gesture_status=gesture_status,
        mouse_status=mouse_status,
        rel_dx=0.0,
        rel_dy=0.0,
        norm_cx=0.5,
        norm_cy=0.5,
        latency_ms=18.4,
        now_mono=time.monotonic(),
    )

    # Check that all performance metrics are present and well-formed
    assert "fps" in t and t["fps"] == 24.5
    assert "latency_ms" in t and t["latency_ms"] == 18.4
    assert "inference_ms" in t and t["inference_ms"] == 11.2
    assert "cpu_percent" in t and t["cpu_percent"] == 14.8
    assert "ram_mb" in t and t["ram_mb"] == 158.4
    assert "camera_resolution" in t
    assert "tracking_status" in t and t["tracking_status"] == "OPTIMAL"


# ===================================================================== #
# 4. TelemetryCardsWidget Performance Section Rendering
# ===================================================================== #
def test_telemetry_cards_widget_performance_section():
    """Verify TelemetryCardsWidget correctly updates Section 4 labels without errors."""
    widget = TelemetryCardsWidget()

    telemetry_data = {
        "has_face": True,
        "fps": 28.6,
        "latency_ms": 22.1,
        "inference_ms": 10.4,
        "cpu_percent": 16.5,
        "ram_mb": 154.2,
        "camera_resolution": "640x480",
        "tracking_status": "OPTIMAL",
        "screen_x": 960,
        "screen_y": 540,
        "rel_dx": 0.05,
        "rel_dy": -0.02,
        "left_ear": 0.29,
        "right_ear": 0.28,
        "mode": "NORMAL",
    }

    widget.update_telemetry(telemetry_data)

    assert "28.6 FPS" in widget.lbl_fps_lat.text()
    assert "22.1 ms" in widget.lbl_fps_lat.text()
    assert "10.4 ms" in widget.lbl_inference.text()
    assert widget.badge_tracking_quality.text() == "OPTIMAL"
    assert "16.5 %" in widget.lbl_cpu.text()
    assert "154.2 MB" in widget.lbl_ram.text()
    assert widget.lbl_res.text() == "640x480"


# ===================================================================== #
# 5. Adaptive Controls in SettingsTab
# ===================================================================== #
def test_settings_tab_adaptive_controls():
    """Verify SettingsTab exposes and signals adaptive performance options."""
    settings = AppSettings()
    tab = SettingsTabWidget(settings=settings)

    emitted_diffs: list[dict] = []
    tab.sig_settings_changed.connect(lambda d: emitted_diffs.append(d))

    # Switch resolution to 1280x720
    idx_720 = tab.combo_resolution.findData("1280x720")
    assert idx_720 >= 0
    tab.combo_resolution.setCurrentIndex(idx_720)
    assert any("camera_resolution" in d for d in emitted_diffs)
    assert emitted_diffs[-1]["camera_resolution"] == "1280x720"

    # Switch performance profile to high performance
    idx_perf = tab.combo_perf_mode.findData("performance")
    assert idx_perf >= 0
    tab.combo_perf_mode.setCurrentIndex(idx_perf)
    assert any("performance_mode" in d for d in emitted_diffs)
    assert emitted_diffs[-1]["performance_mode"] == "performance"

    # Switch UI refresh rate to 30 Hz
    idx_hz = tab.combo_refresh_rate.findData(30)
    assert idx_hz >= 0
    tab.combo_refresh_rate.setCurrentIndex(idx_hz)
    assert any("ui_refresh_hz" in d for d in emitted_diffs)
    assert emitted_diffs[-1]["ui_refresh_hz"] == 30


# ===================================================================== #
# 6. Worker Dynamic Settings Application
# ===================================================================== #
def test_worker_dynamic_settings_performance():
    """Verify VisionWorker receives and applies performance parameters dynamically."""
    worker = VisionWorker(settings=AppSettings())

    diff = {
        "camera_resolution": "1280x720",
        "performance_mode": "performance",
        "ui_refresh_hz": 30,
    }
    worker.update_dynamic_settings(diff)

    assert worker.settings.camera.width == 1280
    assert worker.settings.camera.height == 720
    assert worker.settings.gui.performance_mode == "performance"
    assert worker.settings.gui.ui_refresh_hz == 30


# ===================================================================== #
# 7. VisionWorker Start/Stop Thread Lifecycle
# ===================================================================== #
def test_worker_clean_lifecycle_and_shutdown():
    """Verify VisionWorker starts, runs gracefully, and shuts down without leaking threads."""
    with patch("core.camera.cv2.VideoCapture"), patch("core.face_landmarker.tasks.vision.FaceLandmarker.create_from_options"):
        worker = VisionWorker(settings=AppSettings())

        # Mock camera to deliver frames cleanly and avoid real hardware acquisition
        mock_cam = MagicMock()
        mock_cam.initialize.return_value = True
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cam.read_frame.return_value = dummy_frame
        mock_cam.is_camera_available.return_value = True
        mock_cam.resolution = "640x480"
        worker.camera = mock_cam

        # Start worker thread
        worker.start()
        assert worker.isRunning()

        # Let worker execute briefly
        time.sleep(0.1)

        # Signal stop and wait for join
        worker.stop()
        terminated = worker.wait(3000)

        assert terminated, "Worker thread failed to terminate within 3.0 seconds."
        assert not worker.isRunning()
        mock_cam.close.assert_called_once()
