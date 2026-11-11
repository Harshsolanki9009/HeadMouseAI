"""Test threaded camera capture vs synchronous capture."""

import os
import sys
import time
import threading
import cv2
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.camera import CameraCapture


class ThreadedCamera:
    """Non-blocking threaded camera reader."""

    def __init__(self, index: int = 0, width: int = 640, height: int = 480):
        self.cam = CameraCapture(index=index, width=width, height=height)
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._latest_frame = None
        self._new_frame_event = threading.Event()
        self._read_count = 0

    def initialize(self) -> bool:
        ok = self.cam.initialize()
        if ok:
            self._running = True
            self._thread = threading.Thread(target=self._capture_worker, daemon=True)
            self._thread.start()
        return ok

    def _capture_worker(self):
        while self._running:
            frame = self.cam.read_frame()
            if frame is not None:
                with self._lock:
                    self._latest_frame = frame
                    self._read_count += 1
                self._new_frame_event.set()
            else:
                time.sleep(0.005)

    def read_latest_frame(self, wait_timeout: float = 0.05) -> np.ndarray | None:
        """Get latest frame without blocking indefinitely."""
        if not self._new_frame_event.wait(timeout=wait_timeout):
            with self._lock:
                return self._latest_frame
        self._new_frame_event.clear()
        with self._lock:
            return self._latest_frame

    def close(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self.cam.close()


def benchmark_threaded(num_frames: int = 60):
    tc = ThreadedCamera(index=0, width=640, height=480)
    if not tc.initialize():
        print("Failed to initialize threaded camera.")
        return

    # Warmup
    time.sleep(0.5)

    read_times = []
    t_start = time.perf_counter()
    for _ in range(num_frames):
        t0 = time.perf_counter()
        f = tc.read_latest_frame()
        t1 = time.perf_counter()
        if f is not None:
            read_times.append((t1 - t0) * 1000.0)
        # Simulate ~10ms AI processing
        time.sleep(0.010)

    elapsed = time.perf_counter() - t_start
    fps = len(read_times) / elapsed
    tc.close()

    print(f"Threaded Camera FPS: {fps:.2f} FPS")
    print(f"Threaded Frame Read Time: avg {np.mean(read_times):.2f} ms (p95: {np.percentile(read_times, 95):.2f} ms)")


if __name__ == "__main__":
    benchmark_threaded(60)
