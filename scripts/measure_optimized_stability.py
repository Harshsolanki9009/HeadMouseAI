"""HeadMouseAI Phase 9: Continuous Operation and Memory Leak Stability Benchmark.

Runs live camera capture and the optimized vision pipeline for 30 seconds.
Tracks frame rates, read times, inference times, pipeline latency, CPU usage,
and RAM working set (RSS) at periodic intervals to verify memory stability.
"""

from __future__ import annotations

import gc
import json
import os
import sys
import time

import cv2
import numpy as np
import psutil

# Ensure project root in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.settings import AppSettings
from core.camera import CameraCapture
from core.face_landmarker import FaceLandmarkerWrapper
from core.nose_tracker import NoseTracker
from core.eye_tracker import EyeTracker
from core.blink_detector import BlinkDetector
from core.gesture_zoom import GestureZoomTracker


def run_benchmark(duration_sec: float = 30.0) -> dict:
    process = psutil.Process()
    gc.collect()

    initial_ram_mb = process.memory_info().rss / (1024 * 1024)
    print(f"Initial Process RAM: {initial_ram_mb:.2f} MB")

    # Initialize camera using DirectShow backend
    camera = CameraCapture(index=0, width=640, height=480)
    try:
        camera.initialize()
    except Exception as e:
        print(f"Camera 0 failed: {e}. Trying camera 1...")
        camera = CameraCapture(index=1, width=640, height=480)
        camera.initialize()

    print(f"Camera opened: {camera.resolution} on index {camera.index}")

    landmarker = FaceLandmarkerWrapper()
    nose_tracker = NoseTracker()
    eye_tracker = EyeTracker()
    blink_detector = BlinkDetector()
    gesture_zoom = GestureZoomTracker()

    read_times: list[float] = []
    inference_times: list[float] = []
    pipeline_times: list[float] = []
    ram_checkpoints: list[dict] = []
    cpu_samples: list[float] = []

    start_time = time.monotonic()
    last_checkpoint_time = start_time
    last_cpu_time = start_time
    frame_count = 0

    print(f"Starting {duration_sec}-second continuous operation test...")

    try:
        while True:
            now = time.monotonic()
            elapsed = now - start_time
            if elapsed >= duration_sec:
                break

            t0 = time.perf_counter()
            frame = camera.read_frame()
            t_read = (time.perf_counter() - t0) * 1000.0

            if frame is None:
                time.sleep(0.005)
                continue

            frame_count += 1
            read_times.append(t_read)

            # Mirror frame
            frame = cv2.flip(frame, 1)

            # Single BGR -> RGB conversion
            t_pipe0 = time.perf_counter()
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            t_inf0 = time.perf_counter()
            landmarks_data = landmarker.detect_landmarks(rgb_frame, is_rgb=True)
            t_inf = (time.perf_counter() - t_inf0) * 1000.0
            inference_times.append(t_inf)

            # Downstream trackers
            nose_tracker.update(landmarks_data)
            eye_state = eye_tracker.update(landmarks_data)
            blink_detector.update(landmarks_data, eye_state, timestamp=now)
            gesture_zoom.update(landmarks_data, relative_dy=0.0, timestamp=now)

            t_pipe = (time.perf_counter() - t_pipe0) * 1000.0
            pipeline_times.append(t_pipe)

            # Sample CPU every 1 second
            if now - last_cpu_time >= 1.0:
                last_cpu_time = now
                cpu_samples.append(process.cpu_percent(interval=None))

            # Sample RAM every 5 seconds
            if now - last_checkpoint_time >= 5.0:
                last_checkpoint_time = now
                current_ram = process.memory_info().rss / (1024 * 1024)
                ram_checkpoints.append({
                    "elapsed_sec": round(elapsed, 1),
                    "frame": frame_count,
                    "ram_mb": round(current_ram, 2),
                })
                print(f"  [{elapsed:4.1f}s] Frame: {frame_count:4d} | RAM: {current_ram:6.2f} MB | Last Inf: {t_inf:5.2f} ms")

    finally:
        camera.close()

    total_duration = time.monotonic() - start_time
    effective_fps = frame_count / total_duration if total_duration > 0 else 0.0
    final_ram_mb = process.memory_info().rss / (1024 * 1024)
    ram_drift = final_ram_mb - initial_ram_mb

    results = {
        "duration_sec": round(total_duration, 2),
        "total_frames": frame_count,
        "effective_fps": round(effective_fps, 2),
        "frame_read_ms": {
            "avg": round(float(np.mean(read_times)), 2) if read_times else 0.0,
            "p50": round(float(np.percentile(read_times, 50)), 2) if read_times else 0.0,
            "p95": round(float(np.percentile(read_times, 95)), 2) if read_times else 0.0,
        },
        "inference_ms": {
            "avg": round(float(np.mean(inference_times)), 2) if inference_times else 0.0,
            "p50": round(float(np.percentile(inference_times, 50)), 2) if inference_times else 0.0,
            "p95": round(float(np.percentile(inference_times, 95)), 2) if inference_times else 0.0,
        },
        "total_processing_ms": {
            "avg": round(float(np.mean(pipeline_times)), 2) if pipeline_times else 0.0,
            "p95": round(float(np.percentile(pipeline_times, 95)), 2) if pipeline_times else 0.0,
        },
        "cpu_percent": {
            "avg": round(float(np.mean(cpu_samples)), 2) if cpu_samples else 0.0,
            "peak": round(float(np.max(cpu_samples)), 2) if cpu_samples else 0.0,
        },
        "ram_mb": {
            "initial": round(initial_ram_mb, 2),
            "final": round(final_ram_mb, 2),
            "drift": round(ram_drift, 2),
            "checkpoints": ram_checkpoints,
        },
    }

    print("\n" + "=" * 60)
    print("PHASE 9 BENCHMARK RESULTS")
    print("=" * 60)
    print(f"Total Frames Processed : {results['total_frames']}")
    print(f"Effective Processing   : {results['effective_fps']} FPS")
    print(f"Frame Read Time        : avg {results['frame_read_ms']['avg']} ms (p95: {results['frame_read_ms']['p95']} ms)")
    print(f"MediaPipe Inference    : avg {results['inference_ms']['avg']} ms (p95: {results['inference_ms']['p95']} ms)")
    print(f"Processing Pipeline    : avg {results['total_processing_ms']['avg']} ms (p95: {results['total_processing_ms']['p95']} ms)")
    print(f"CPU Utilization        : avg {results['cpu_percent']['avg']} % (peak: {results['cpu_percent']['peak']} %)")
    print(f"RAM Working Set        : initial {results['ram_mb']['initial']} MB -> final {results['ram_mb']['final']} MB (drift: {results['ram_mb']['drift']:+.2f} MB)")
    print("=" * 60)

    return results


if __name__ == "__main__":
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    res = run_benchmark(duration_sec=dur)
    with open("benchmark_results.json", "w") as f:
        json.dump(res, f, indent=2)
