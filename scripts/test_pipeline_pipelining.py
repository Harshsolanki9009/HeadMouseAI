"""Test pipelined camera capture + MediaPipe inference."""

import os
import sys
import time
import threading
import cv2
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.camera import CameraCapture
from core.face_landmarker import FaceLandmarkerWrapper


class PipelinedCamera:
    """Threaded camera that keeps the latest hardware frame ready without blocking inference."""

    def __init__(self, index: int = 1, width: int = 640, height: int = 480):
        self.cam = CameraCapture(index=index, width=width, height=height)
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._latest_frame = None
        self._frame_id = 0
        self._last_consumed_id = -1
        self._new_frame_cond = threading.Condition(self._lock)

    def open(self) -> bool:
        ok = self.cam.initialize()
        if ok:
            self._running = True
            self._thread = threading.Thread(target=self._capture_loop, daemon=True)
            self._thread.start()
        return ok

    def _capture_loop(self):
        while self._running:
            f = self.cam.read_frame()
            if f is not None:
                with self._new_frame_cond:
                    self._latest_frame = f
                    self._frame_id += 1
                    self._new_frame_cond.notify_all()
            else:
                time.sleep(0.005)

    def get_frame(self, timeout: float = 0.05) -> np.ndarray | None:
        with self._new_frame_cond:
            if self._frame_id == self._last_consumed_id:
                # Wait for next fresh frame up to timeout
                self._new_frame_cond.wait(timeout=timeout)
            if self._frame_id != self._last_consumed_id and self._latest_frame is not None:
                self._last_consumed_id = self._frame_id
                return self._latest_frame
            return None

    def close(self):
        self._running = False
        with self._new_frame_cond:
            self._new_frame_cond.notify_all()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self.cam.close()


def benchmark_pipeline(num_frames: int = 100):
    pc = PipelinedCamera(index=1, width=640, height=480)
    if not pc.open():
        print("Failed to open pipelined camera")
        return

    landmarker = FaceLandmarkerWrapper()

    # Warmup
    time.sleep(0.5)

    total_times = []
    inf_times = []
    read_times = []
    t_start = time.perf_counter()

    for _ in range(num_frames):
        t0 = time.perf_counter()

        t_r0 = time.perf_counter()
        frame = pc.get_frame(timeout=0.06)
        t_r1 = time.perf_counter()
        if frame is None:
            continue
        read_times.append((t_r1 - t_r0) * 1000.0)

        frame = cv2.flip(frame, 1)

        t_i0 = time.perf_counter()
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        lm = landmarker.detect_landmarks(rgb)
        t_i1 = time.perf_counter()
        inf_times.append((t_i1 - t_i0) * 1000.0)

        total_times.append((time.perf_counter() - t0) * 1000.0)

    elapsed = time.perf_counter() - t_start
    fps = len(total_times) / elapsed
    pc.close()

    print("\n" + "=" * 50)
    print("      PIPELINED CAMERA BENCHMARK REPORT      ")
    print("=" * 50)
    print(f"Frames:          {len(total_times)}")
    print(f"Effective FPS:   {fps:.2f} FPS")
    print(f"Frame Wait Time: avg {np.mean(read_times):.2f} ms (p95: {np.percentile(read_times, 95):.2f} ms)")
    print(f"Inference Time:  avg {np.mean(inf_times):.2f} ms (p95: {np.percentile(inf_times, 95):.2f} ms)")
    print(f"Total Loop Time: avg {np.mean(total_times):.2f} ms (p95: {np.percentile(total_times, 95):.2f} ms)")
    print("=" * 50)


if __name__ == "__main__":
    benchmark_pipeline(100)
