"""Profile HeadMouse AI Phase 2 pipeline latency and breakdown after optimizations."""
from __future__ import annotations

import sys
import time
from pathlib import Path
import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.camera import CameraCapture
from core.face_landmarker import FaceLandmarkerWrapper
from core.nose_tracker import NoseTracker
from core.cursor_simulator import CursorSimulator
from config.settings import get_settings
from main import draw_landmarks, draw_simulated_cursor


def profile_pipeline(num_frames: int = 50) -> dict[str, float]:
    settings = get_settings()
    cam_w = getattr(settings.gui, "camera_view_width", 640)
    cam_h = getattr(settings.gui, "camera_view_height", 480)

    print("Initializing components for post-optimization profiling...")
    cam = CameraCapture(index=settings.camera.camera_index, width=cam_w, height=cam_h)
    cam.initialize(brightness=settings.camera.brightness, exposure=settings.camera.exposure, focus=settings.camera.focus)
    landmarker = FaceLandmarkerWrapper()
    tracker = NoseTracker(smoothing_strength=settings.nose_tracking.smoothing_strength, dead_zone=settings.nose_tracking.dead_zone)
    cursor = CursorSimulator(sensitivity=settings.nose_tracking.sensitivity, dead_zone=settings.nose_tracking.dead_zone, max_velocity=settings.nose_tracking.max_velocity, window_width=cam_w, window_height=cam_h)

    # Warmup
    for _ in range(5):
        f = cam.read_frame()
        if f is not None:
            landmarker.detect_landmarks(f)

    # Profiling records
    times_cam = []
    times_flip = []
    times_infer = []
    times_tracking = []
    times_draw = []
    times_imshow = []
    times_total = []

    print(f"Profiling {num_frames} live frames...")
    for i in range(num_frames):
        t0 = time.perf_counter()

        # 1. Camera read
        t_c0 = time.perf_counter()
        frame = cam.read_frame()
        t_c1 = time.perf_counter()

        if frame is None:
            continue

        # 2. Flip
        t_fl0 = time.perf_counter()
        frame = cv2.flip(frame, 1)
        t_fl1 = time.perf_counter()

        # 3. MediaPipe Inference
        t_inf0 = time.perf_counter()
        lms_data = landmarker.detect_landmarks(frame)
        t_inf1 = time.perf_counter()

        # 4. Tracking & Simulator
        t_tr0 = time.perf_counter()
        tracker.update(lms_data)
        rel_dx, rel_dy = tracker.get_relative_position(smoothed=True)
        cx, cy, moved = cursor.update(rel_dx, rel_dy)
        norm_cx, norm_cy = cursor.normalized_position
        t_tr1 = time.perf_counter()

        # 5. Drawing overlays
        t_dr0 = time.perf_counter()
        lms_list = lms_data.get("landmarks", [])
        if len(lms_list) > 0:
            frame = draw_landmarks(frame, lms_list)
        draw_simulated_cursor(frame, cx, cy, moved, norm_cx, norm_cy)
        t_dr1 = time.perf_counter()

        # 6. imshow & waitKey
        t_sh0 = time.perf_counter()
        cv2.imshow("Profile Preview", frame)
        cv2.waitKey(1)
        t_sh1 = time.perf_counter()

        t_end = time.perf_counter()

        times_cam.append((t_c1 - t_c0) * 1000.0)
        times_flip.append((t_fl1 - t_fl0) * 1000.0)
        times_infer.append((t_inf1 - t_inf0) * 1000.0)
        times_tracking.append((t_tr1 - t_tr0) * 1000.0)
        times_draw.append((t_dr1 - t_dr0) * 1000.0)
        times_imshow.append((t_sh1 - t_sh0) * 1000.0)
        times_total.append((t_end - t0) * 1000.0)

    cam.close()
    cv2.destroyAllWindows()

    results = {
        "Camera Capture": float(np.mean(times_cam)),
        "Frame Flip": float(np.mean(times_flip)),
        "MediaPipe Inference": float(np.mean(times_infer)),
        "Tracking + Cursor": float(np.mean(times_tracking)),
        "Drawing Overlays": float(np.mean(times_draw)),
        "cv2.imshow + waitKey": float(np.mean(times_imshow)),
        "Total Frame Time": float(np.mean(times_total)),
        "Effective FPS": 1000.0 / float(np.mean(times_total)) if np.mean(times_total) > 0 else 0.0,
    }

    print("\n" + "=" * 50)
    print("POST-OPTIMIZATION RESULTS (Average ms per frame):")
    print("=" * 50)
    for k, v in results.items():
        if "FPS" in k:
            print(f"  {k:26s}: {v:.1f}")
        else:
            print(f"  {k:26s}: {v:.2f} ms")
    print("=" * 50)
    return results


if __name__ == "__main__":
    profile_pipeline(50)
