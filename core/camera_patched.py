"""Patched CameraCapture — fixes MSMF ReadSample failure via CAP_DSHOW backend."""
from __future__ import annotations

import time
import logging
from typing import Optional, Callable

import cv2
import numpy as np

from utils.logger import logger


class CameraError(Exception):
    """Raised when camera initialization or capture fails."""
    pass


class CameraCapture:
    """Wrapper around an OpenCV camera that provides live frame access."""

    def __init__(self, index: int = 0, width: int = 640, height: int = 480) -> None:
        self.index = index
        self.width = width
        self.height = height
        self._cap: Optional[cv2.VideoCapture] = None
        self.is_running = False
        self.error: Optional[str] = None
        self.frames = []
        self.frame_count = 0
        self.fps = 0.0
        self.start_time = 0.0

    def initialize(self, brightness: int = 100, exposure: int = -1, focus: int = -1) -> bool:
        """Initialize the camera device. Returns True on success."""
        # DirectShow (CAP_DSHOW) avoids MSMF's ReadSample failures on Windows
        backend = cv2.CAP_DSHOW
        for attempt in range(5):
            time.sleep(0.4 * attempt)
            for idx in [self.index, self.index + 1, self.index - 1]:
                try:
                    cap = cv2.VideoCapture(idx, backend)
                    if cap is None or not cap.isOpened():
                        cap.release()
                        continue
                    # Set resolution if possible
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
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

        self.frames.append(frame.copy())
        if len(self.frames) > 5:
            self.frames = self.frames[-5:]
        self.frame_count += 1

        elapsed = time.time() - self.start_time
        if elapsed > 0:
            self.fps = (self.frame_count / elapsed) * 1000

        return frame

    def is_camera_available(self) -> bool:
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
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self.is_running = False
        logger.info("Camera released.")
