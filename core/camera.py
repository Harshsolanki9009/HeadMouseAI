"""Camera capture module for HeadMouse AI.

Handles initialization, opening, and live frame capture from
connected cameras (Iriun Webcam / built-in webcam). Provides both
OpenCV and MediaPipe-based capture paths.

This module is focused on Phase 1 requirements: simply establishing a
working camera connection and producing live frames.
"""

from __future__ import annotations

import time
import logging
from collections import deque
from typing import Optional, Callable

import cv2
import numpy as np

from utils.logger import logger


class CameraError(Exception):
    """Raised when camera initialization or capture fails."""
    pass


class CameraCapture:
    """Wrapper around an OpenCV camera that provides live frame access with low-latency buffering."""

    def __init__(self, index: int = 0, width: int = 640, height: int = 480) -> None:
        self.index = index
        self.width = width
        self.height = height
        self._cap: Optional[cv2.VideoCapture] = None
        self.is_running = False
        self.error: Optional[str] = None
        # Bounded frame buffer: keeps at most 2 references to prevent memory accumulation
        self.frames: deque = deque(maxlen=2)
        self.frame_count = 0
        self.fps = 0.0
        self.start_time = time.perf_counter()
        self._last_frame_time = 0.0

    def initialize(self, brightness: int = 100, exposure: int = -1, focus: int = -1) -> bool:
        """Initialize the camera device. Returns True on success."""
        # DirectShow (CAP_DSHOW) tends to avoid MSMF ReadSample failures on Windows
        backend = cv2.CAP_DSHOW
        # Retry with small delays — some backends open then fail later
        for attempt in range(5):
            time.sleep(0.4 * attempt)
            opened = False
            for idx in [self.index, self.index + 1, self.index - 1]:
                try:
                    cap = cv2.VideoCapture(idx, backend)
                    if cap is None or not cap.isOpened():
                        cap.release()
                        continue

                    # Set resolution if possible
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                    # Low latency: limit internal driver frame buffer to 1 to avoid stale queued frames
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    cap.set(cv2.CAP_PROP_BRIGHTNESS, brightness)
                    cap.set(cv2.CAP_PROP_EXPOSURE, exposure)
                    cap.set(cv2.CAP_PROP_FOCUS, focus)
                    if hasattr(cv2, "CAP_PROP_AUTO_FOCUS"):
                        cap.set(cv2.CAP_PROP_AUTO_FOCUS, 1 if focus == -1 else 0)
                    if hasattr(cv2, "CAP_PROP_AUTO_EXPOSURE"):
                        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1 if exposure == -1 else 0)

                    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    logger.info(f"Camera {idx} opened successfully. Resolution: {actual_w}x{actual_h}")

                    if actual_w > 0 and actual_h > 0:
                        self._cap = cap
                        self.is_running = True
                        self.start_time = time.perf_counter()
                        self._last_frame_time = time.perf_counter()
                        return True

                    cap.release()
                except Exception as e:
                    logger.debug(f"Tried camera index {idx}, failed: {e}")
                    if cap:
                        cap.release()

        raise CameraError("Could not open any available camera.")

    def read_frame(self) -> np.ndarray | None:
        """Read a single frame from the camera. Returns None if unavailable."""
        if self._cap is None:
            raise CameraError("Camera not initialized.")

        ret, frame = self._cap.read()
        if not ret or frame is None:
            self.error = "Failed to read frame."
            self.fps = 0.0
            return None

        now = time.perf_counter()
        if self._last_frame_time > 0:
            dt = now - self._last_frame_time
            if dt > 0:
                instant_fps = 1.0 / dt
                self.fps = 0.85 * self.fps + 0.15 * instant_fps if self.fps > 0 else instant_fps
        self._last_frame_time = now

        # Bounded frame storage for tests/debugging
        self.frames.append(frame)
        self.frame_count += 1

        return frame

    @property
    def resolution(self) -> str:
        """Current camera resolution formatted as 'WIDTHxHEIGHT'."""
        if self._cap is not None and self._cap.isOpened():
            w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if w > 0 and h > 0:
                return f"{w}x{h}"
        return f"{self.width}x{self.height}"

    @property
    def actual_width(self) -> int:
        if self._cap is not None and self._cap.isOpened():
            w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            if w > 0:
                return w
        return self.width

    @property
    def actual_height(self) -> int:
        if self._cap is not None and self._cap.isOpened():
            h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if h > 0:
                return h
        return self.height

    def set_resolution(self, width: int, height: int) -> bool:
        """Dynamically update camera capture resolution."""
        self.width = int(width)
        self.height = int(height)
        if self._cap is not None and self._cap.isOpened():
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            actual_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            logger.info(f"Camera resolution switched to: {actual_w}x{actual_h}")
            return actual_w == self.width and actual_h == self.height
        return False

    def set_fps(self, fps: int) -> bool:
        """Set camera hardware target capture frame rate."""
        if self._cap is not None and self._cap.isOpened():
            self._cap.set(cv2.CAP_PROP_FPS, float(fps))
            return True
        return False

    def is_camera_available(self) -> bool:
        """Check if any camera is currently connected."""
        for idx in [self.index, self.index + 1, self.index - 1]:
            try:
                cap = cv2.VideoCapture(idx)
                if cap is not None and cap.isOpened():
                    cap.release()
                    return True
            except Exception:
                pass
        return False

    def list_available_cams(self) -> list[int]:
        """List all camera indices that can be opened."""
        available = []
        for idx in range(0, 5):
            try:
                cap = cv2.VideoCapture(idx)
                if cap is not None and cap.isOpened():
                    available.append(idx)
                    cap.release()
            except Exception:
                pass
        return available

    def close(self) -> None:
        """Release camera hardware and internal frame buffers cleanly."""
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        self.is_running = False
        self.frames.clear()
        logger.info("Camera released.")
