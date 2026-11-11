"""Performance measurement benchmark for HeadMouseAI (Phase 9).

Measures:
- Camera capture FPS and frame read time.
- MediaPipe FaceLandmarker inference time.
- Tracking pipeline processing time (eyes, nose, gestures, mouse mapping).
- Frame rendering and format conversion time.
- Total frame latency.
- CPU usage and RAM usage (Working Set).
"""

import os
import sys
import time
import psutil
import cv2
import numpy as np

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import AppSettings
from core.camera import CameraCapture
from core.cursor_simulator import CursorSimulator
from core.eye_tracker import EyeTracker
from core.blink_detector import BlinkDetector
from core.face_landmarker import FaceLandmarkerWrapper
from core.gesture_zoom import GestureZoomTracker
from core.mouse_controller import MouseController
from core.nose_tracker import NoseTracker


def run_benchmark(num_frames: int = 100, warm_up: int = 15):
    print(f"Starting performance benchmark ({num_frames} frames, {warm_up} warmup frames)...")
    proc = psutil.Process()
    # Prime CPU percent measurement
    proc.cpu_percent(interval=None)

    settings = AppSettings.load()
    cam = CameraCapture(index=settings.camera.camera_index, width=640, height=480)
    if not cam.initialize():
        print("ERROR: Camera failed to initialize.")
        return

    landmarker = FaceLandmarkerWrapper()
    nose_tracker = NoseTracker(
        smoothing_strength=settings.nose_tracking.smoothing_strength,
        dead_zone=settings.nose_tracking.dead_zone,
    )
    cursor = CursorSimulator(
        sensitivity=settings.nose_tracking.sensitivity,
        dead_zone=settings.nose_tracking.dead_zone,
        window_width=640,
        window_height=480,
    )
    eye_tracker = EyeTracker(
        open_threshold=settings.eye_blink.left_eye_ear_threshold,
        left_threshold=settings.eye_blink.left_eye_ear_threshold,
        right_threshold=settings.eye_blink.right_eye_ear_threshold,
    )
    blink_detector = BlinkDetector(settings.eye_blink)
    gesture_zoom = GestureZoomTracker(settings.zoom)
    mouse_controller = MouseController(settings=settings.mouse)

    cam_read_times = []
    inference_times = []
    tracking_times = []
    conversion_times = []
    total_frame_times = []
    cpu_measurements = []
    ram_measurements = []

    print("Warming up camera and AI pipeline...")
    for _ in range(warm_up):
        frame = cam.read_frame()
        if frame is not None:
            frame = cv2.flip(frame, 1)
            landmarker.detect_landmarks(frame)

    print(f"Collecting baseline telemetry across {num_frames} live frames...")
    start_bench = time.perf_counter()

    for i in range(num_frames):
        t0 = time.perf_counter()

        # 1. Camera Frame Read
        t_cam0 = time.perf_counter()
        frame = cam.read_frame()
        t_cam1 = time.perf_counter()
        if frame is None:
            continue
        cam_read_times.append((t_cam1 - t_cam0) * 1000.0)

        # 2. Mirror Flip
        frame = cv2.flip(frame, 1)

        # 3. MediaPipe Landmark Inference
        t_inf0 = time.perf_counter()
        landmarks_data = landmarker.detect_landmarks(frame)
        t_inf1 = time.perf_counter()
        inference_times.append((t_inf1 - t_inf0) * 1000.0)

        # 4. Feature Tracking Pipeline
        t_track0 = time.perf_counter()
        has_face = bool(landmarks_data.get("has_face", False))
        eye_state = eye_tracker.update(landmarks_data)
        blink_state = blink_detector.update(landmarks_data, eye_state, timestamp=time.monotonic())
        nose_tracker.update(landmarks_data)
        rel_dx, rel_dy = nose_tracker.get_relative_position(smoothed=True)
        cx, cy, moved = cursor.update(rel_dx, rel_dy)
        norm_cx, norm_cy = cursor.normalized_position
        gesture_status = gesture_zoom.update(landmarks_data, relative_dy=rel_dy, timestamp=time.monotonic())
        mouse_controller.update_tracking_status(has_face=has_face, is_calibrated=True)
        t_track1 = time.perf_counter()
        tracking_times.append((t_track1 - t_track0) * 1000.0)

        # 5. UI Frame Preparation (Copy + Drawing + BGR to RGB)
        t_conv0 = time.perf_counter()
        annotated = frame.copy()
        # Simulate landmark dot drawing
        lms = landmarks_data.get("landmarks", [])
        for p_idx in range(0, len(lms), 8):
            lm = lms[p_idx]
            cv2.circle(annotated, (int(lm[0] * 640), int(lm[1] * 480)), 1, (130, 130, 140), -1)
        # BGR to RGB conversion
        rgb_frame = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
        t_conv1 = time.perf_counter()
        conversion_times.append((t_conv1 - t_conv0) * 1000.0)

        t_end = time.perf_counter()
        total_frame_times.append((t_end - t0) * 1000.0)

        if i % 20 == 0:
            cpu_measurements.append(proc.cpu_percent(interval=None))
            ram_measurements.append(proc.memory_info().rss / (1024 * 1024))

    elapsed_total = time.perf_counter() - start_bench
    effective_fps = len(total_frame_times) / elapsed_total if elapsed_total > 0 else 0.0

    cam.close()

    print("\n" + "=" * 50)
    print("      HEADMOUSEAI BASELINE PERFORMANCE REPORT      ")
    print("=" * 50)
    print(f"Total Frames Processed:   {len(total_frame_times)}")
    print(f"Effective Processing FPS: {effective_fps:.2f} FPS")
    print(f"Camera Frame Read Time:   avg {np.mean(cam_read_times):.2f} ms (p95: {np.percentile(cam_read_times, 95):.2f} ms)")
    print(f"MediaPipe Inference Time: avg {np.mean(inference_times):.2f} ms (p95: {np.percentile(inference_times, 95):.2f} ms)")
    print(f"Tracking Pipeline Time:   avg {np.mean(tracking_times):.2f} ms (p95: {np.percentile(tracking_times, 95):.2f} ms)")
    print(f"Frame Conversion Time:    avg {np.mean(conversion_times):.2f} ms (p95: {np.percentile(conversion_times, 95):.2f} ms)")
    print(f"Total Frame Latency:      avg {np.mean(total_frame_times):.2f} ms (p95: {np.percentile(total_frame_times, 95):.2f} ms)")
    print(f"CPU Utilization:          avg {np.mean(cpu_measurements):.1f}% (peak: {np.max(cpu_measurements):.1f}%)")
    print(f"RAM Working Set:          avg {np.mean(ram_measurements):.1f} MB (peak: {np.max(ram_measurements):.1f} MB)")
    print("=" * 50)


if __name__ == "__main__":
    run_benchmark(num_frames=100, warm_up=15)
