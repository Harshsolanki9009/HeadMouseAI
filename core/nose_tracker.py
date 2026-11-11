"""Nose tip tracking module for HeadMouse AI.

Extracts nose tip coordinates from facial landmarks and provides relative
movement calculations for cursor control. Uses neutral position calibration.

IMPORTANT: This project does NOT use pupil or iris coordinates. Only nose tip (index 1).
"""

from __future__ import annotations

import time
from typing import Tuple, List, Optional, Any

import numpy as np

from utils.logger import logger

# Face landmark indices - MediaPipe Face Mesh
NOSE_TIP = 1
LEFT_EYE_CENTER = 33
RIGHT_EYE_CENTER = 160


class NoseTracker:
    """Detects nose movement and calculates relative displacement from neutral position."""

    def __init__(self, smoothing_strength: float = 0.5, dead_zone: float = 0.01) -> None:
        # Current raw coordinates (normalized 0.0 to 1.0)
        self.nose_x: float = 0.5
        self.nose_y: float = 0.5

        # Smoothed coordinates (EMA filtered)
        self.smoothed_x: float = 0.5
        self.smoothed_y: float = 0.5
        self.smoothing_strength: float = float(smoothing_strength)
        self.dead_zone: float = float(dead_zone)
        self._has_first_frame: bool = False

        # Velocities
        self.nose_vx: float = 0.0
        self.nose_vy: float = 0.0

        # Calibrated neutral baseline position
        self.neutral_x: float = 0.5
        self.neutral_y: float = 0.5
        self.is_calibrated: bool = False

        # Real camera-frame calibration state
        self.is_calibrating: bool = False
        self.calibration_frames: int = 30
        self.calibration_buffer: list[Tuple[float, float]] = []

        self.last_move_time: float = time.monotonic()
        self.curvature: float = 0.0
        self.total_displacement_squared: float = 0.0

    # ------------------------------------------------------------------ #
    # Live frame updates
    # ------------------------------------------------------------------ #
    def update(self, landmarks: dict | None) -> Tuple[bool, float]:
        """Update tracking state from facial landmarks.

        Args:
            landmarks: Dictionary containing 'has_face' and 'landmarks' list.

        Returns:
            Tuple of (detected: bool, movement: float).
        """
        if landmarks is None:
            return False, 0.0

        has_face = landmarks.get("has_face", False)
        lms = landmarks.get("landmarks", [])

        # If has_face is not explicitly set, infer from non-empty landmarks
        if not has_face and len(lms) > 0:
            has_face = True

        if not has_face or len(lms) == 0:
            return False, 0.0

        try:
            # Extract nose tip (index 1), fallback to first element if only 1 point
            if len(lms) > NOSE_TIP:
                nose_data = lms[NOSE_TIP]
            elif len(lms) > 0:
                nose_data = lms[0]
            else:
                return False, 0.0

            if nose_data is None:
                return False, 0.0

            # Handle various data formats (dict, tuple/list, landmark object)
            if isinstance(nose_data, dict):
                nx = float(nose_data.get("x", 0.5))
                ny = float(nose_data.get("y", 0.5))
            elif isinstance(nose_data, (list, tuple)):
                if len(nose_data) > 0 and isinstance(nose_data[0], dict):
                    nx = float(nose_data[0].get("x", 0.5))
                    ny = float(nose_data[0].get("y", 0.5))
                else:
                    nx = float(nose_data[0])
                    ny = float(nose_data[1])
            elif hasattr(nose_data, "x") and hasattr(nose_data, "y"):
                nx = float(nose_data.x)
                ny = float(nose_data.y)
            else:
                return False, 0.0

            # Normalized coordinate convention:
            # nx in [0, 1] (left to right)
            # ny_adjusted in [0, 1] where up is positive
            ny_adjusted = 1.0 - ny

            self.nose_x = nx
            self.nose_y = ny_adjusted

            # Proper Exponential Moving Average (EMA) smoothing
            alpha = max(0.01, min(1.0, self.smoothing_strength))
            if not self._has_first_frame:
                self.smoothed_x = self.nose_x
                self.smoothed_y = self.nose_y
                self._has_first_frame = True
            else:
                self.smoothed_x = alpha * self.nose_x + (1.0 - alpha) * self.smoothed_x
                self.smoothed_y = alpha * self.nose_y + (1.0 - alpha) * self.smoothed_y

            # Relative displacement from neutral baseline
            relative_dx = self.smoothed_x - self.neutral_x
            relative_dy = self.smoothed_y - self.neutral_y

            # Velocity calculation
            now = time.time()
            dt = max(now - self.last_move_time, 1e-6)
            self.last_move_time = now

            self.nose_vx = relative_dx / dt
            self.nose_vy = relative_dy / dt

            dist_sq = relative_dx * relative_dx + relative_dy * relative_dy
            self.total_displacement_squared = (
                self.total_displacement_squared * 0.9 + dist_sq * 0.1
            )

            movement = float(np.sqrt(relative_dx ** 2 + relative_dy ** 2))
            return True, movement

        except Exception as e:
            logger.debug(f"NoseTracker update error: {e}")
            return False, 0.0

    # ------------------------------------------------------------------ #
    # Real camera-frame-based calibration
    # ------------------------------------------------------------------ #
    def start_calibration(self, frames: int = 30) -> None:
        """Begin accumulating real camera frames for neutral calibration."""
        self.calibration_frames = max(5, int(frames))
        self.calibration_buffer.clear()
        self.is_calibrating = True
        self.is_calibrated = False
        logger.info(f"Started real camera calibration ({self.calibration_frames} frames)...")

    def add_calibration_sample(self, sample_data: Any) -> bool:
        """Add a real camera frame's nose measurement to the calibration buffer.

        Args:
            sample_data: Either a landmark dict from detect_landmarks, or an (x, y) tuple.

        Returns:
            True if calibration is complete, False if still collecting.
        """
        if not self.is_calibrating:
            self.start_calibration(self.calibration_frames)

        nx: Optional[float] = None
        ny: Optional[float] = None

        if isinstance(sample_data, dict):
            has_face = sample_data.get("has_face", False)
            lms = sample_data.get("landmarks", [])
            if not has_face and len(lms) > 0:
                has_face = True
            if has_face and len(lms) > NOSE_TIP:
                nose = lms[NOSE_TIP]
                nx = float(nose[0])
                ny = 1.0 - float(nose[1])
            elif has_face and len(lms) > 0:
                nose = lms[0]
                nx = float(nose[0]) if isinstance(nose, (list, tuple)) else float(nose.get("x", 0.5))
                ny = 1.0 - (float(nose[1]) if isinstance(nose, (list, tuple)) else float(nose.get("y", 0.5)))
        elif isinstance(sample_data, (tuple, list)) and len(sample_data) >= 2:
            nx = float(sample_data[0])
            ny = float(sample_data[1])

        if nx is None or ny is None:
            return False

        self.calibration_buffer.append((nx, ny))

        if len(self.calibration_buffer) >= self.calibration_frames:
            return self.finish_calibration()
        return False

    def finish_calibration(self) -> bool:
        """Compute the neutral baseline from genuine accumulated camera samples."""
        if len(self.calibration_buffer) > 0:
            self.neutral_x = float(np.mean([p[0] for p in self.calibration_buffer]))
            self.neutral_y = float(np.mean([p[1] for p in self.calibration_buffer]))
        else:
            self.neutral_x = self.nose_x
            self.neutral_y = self.nose_y

        self.nose_x = self.neutral_x
        self.nose_y = self.neutral_y
        self.smoothed_x = self.neutral_x
        self.smoothed_y = self.neutral_y
        self.nose_vx = 0.0
        self.nose_vy = 0.0
        self.total_displacement_squared = 0.0
        self.curvature = 0.0
        self.last_move_time = time.time()
        self.is_calibrated = True
        self.is_calibrating = False

        logger.info(
            f"Nose calibrated at ({self.neutral_x:.4f}, {1.0 - self.neutral_y:.4f}) "
            f"over {len(self.calibration_buffer)} real frames."
        )
        return True

    def set_neutral(self, x: float, y: float) -> None:
        """Set neutral baseline coordinates directly from calibration profile."""
        if 0.1 <= x <= 0.9 and 0.1 <= y <= 0.9:
            self.neutral_x = float(x)
            self.neutral_y = float(y)
            self.smoothed_x = float(x)
            self.smoothed_y = float(y)
            self.is_calibrated = True
            self.is_calibrating = False
            logger.info(f"NoseTracker neutral set to ({self.neutral_x:.4f}, {self.neutral_y:.4f})")

    def get_calibration_progress(self) -> float:
        """Return calibration progress ratio (0.0 to 1.0)."""
        if not self.is_calibrating or self.calibration_frames <= 0:
            return 1.0 if self.is_calibrated else 0.0
        return min(1.0, len(self.calibration_buffer) / float(self.calibration_frames))

    def calibrate(
        self,
        calibration_frames: int = 30,
        *,
        calibration_points: int | None = None,
        samples: Optional[List[Tuple[float, float]]] = None,
    ) -> bool:
        """Calibrate the neutral nose position.

        Supports real sample lists, buffer finalization, or current tracked position.
        Zero random/synthetic numbers are generated.
        """
        count = calibration_points if calibration_points is not None else calibration_frames
        self.calibration_frames = max(5, int(count))

        if samples and len(samples) > 0:
            self.calibration_buffer = list(samples)
            return self.finish_calibration()

        if len(self.calibration_buffer) >= self.calibration_frames:
            return self.finish_calibration()

        # Deterministic calibration to current tracked nose coordinates
        self.calibration_buffer = [(self.nose_x, self.nose_y)]
        return self.finish_calibration()

    def reset(self) -> None:
        """Reset all tracking state to defaults."""
        self.nose_x = 0.5
        self.nose_y = 0.5
        self.smoothed_x = 0.5
        self.smoothed_y = 0.5
        self._has_first_frame = False

        self.nose_vx = 0.0
        self.nose_vy = 0.0

        self.neutral_x = 0.5
        self.neutral_y = 0.5
        self.is_calibrated = False
        self.is_calibrating = False
        self.calibration_buffer.clear()

        self.last_move_time = time.time()
        self.curvature = 0.0
        self.total_displacement_squared = 0.0
        logger.info("NoseTracker reset.")

    def get_relative_position(self, smoothed: bool = False) -> Tuple[float, float]:
        """Get relative nose displacement from neutral position.

        Args:
            smoothed: If True, uses the smoothed coordinates. Otherwise raw.
        """
        if smoothed:
            dx = self.smoothed_x - self.neutral_x
            dy = self.smoothed_y - self.neutral_y
        else:
            dx = self.nose_x - self.neutral_x
            dy = self.nose_y - self.neutral_y
        return (float(dx), float(dy))

    @staticmethod
    def get_landmark_indices() -> dict[str, int]:
        """Return landmark index constants."""
        return {"NOSE_TIP": NOSE_TIP}
