"""Eye tracking module for HeadMouse AI.

Uses Eye Aspect Ratio (EAR) to determine if an eye is open or closed.
Left and right eyes are tracked independently using MediaPipe eyelid and corner landmarks.
No pupil or iris tracking is used.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import numpy as np
from utils.logger import logger

# Key landmark indices for eye geometry in canonical MediaPipe 468/478 Face Mesh:
# Left eye (MediaPipe indices):
LEFT_EYE_OUTER_CORNER_CANONICAL = 33   # Lateral corner
LEFT_EYE_INNER_CORNER_CANONICAL = 133  # Medial corner
LEFT_EYE_TOP_1 = 160
LEFT_EYE_BOTTOM_1 = 144
LEFT_EYE_TOP_2 = 158
LEFT_EYE_BOTTOM_2 = 153
LEFT_EYE_CANONICAL_INDICES = [33, 133, 160, 144, 158, 153]

# Right eye (MediaPipe indices):
RIGHT_EYE_OUTER_CORNER_CANONICAL = 263  # Lateral corner
RIGHT_EYE_INNER_CORNER_CANONICAL = 362  # Medial corner
RIGHT_EYE_TOP_1 = 385
RIGHT_EYE_BOTTOM_1 = 380
RIGHT_EYE_TOP_2 = 387
RIGHT_EYE_BOTTOM_2 = 373
RIGHT_EYE_CANONICAL_INDICES = [263, 362, 385, 380, 387, 373]

# Legacy key landmark indices preserved for backward compatibility:
LEFT_EYE_OUTER_CORNER = 36       # Outer corner of left eye (lateral side)
LEFT_EYE_INNER_CORNER = 133     # Inner corner of left eye
LEFT_EYE_LEFT_CORNER = 240   # Top-left corner of left eye
RIGHT_EYE_RIGHT_CORNER = 51  # Outer right corner
RIGHT_EYE_LEFT_CORNER = 370 # Top-left corner of right eye
LEFT_EYE_CENTER = 33
RIGHT_EYE_CENTER = 160

# Required landmark indices for legacy EAR calculation
REQUIRED_EAR_INDICES = [36, 240, 33, 133, 51, 370]

# EAR thresholds - EAR higher means more open
# Typical values: open eye ≈ 0.2-0.3, closed eye ≈ 0.0-0.1
DEFAULT_OPEN_THRESHOLD = 0.22  # EAR below this = likely closed
DEFAULT_CLOSED_THRESHOLD = 0.18  # (lower than open = clearly closed)

# Blink detection configuration options
DEFAULT_INDEPENDENT_BLINK = True
DEFAULT_SIMULTANEOUS_BLINK_SUPPRESSION = True
DEFAULT_BLINK_COOLDOWN = 30


def _norm_2d(p1: np.ndarray, p2: np.ndarray) -> float:
    """Euclidean distance between two 2D points."""
    return float(np.linalg.norm(p1 - p2))


def calculate_ear(points: list[list]) -> float | None:
    """Calculate Eye Aspect Ratio (EAR) for backward compatibility and test vectors.

    Formula: EAR = (|p1-p4| + |p2-p5|) / (2 * |p3-p6|)
    Where:
      p1 = left_eye_outer_corner (idx 36)
      p2 = left_eye_top_corner (idx 240)
      p3 = left_eye_center (idx 33)
      p4 = left_eye_inner_corner (idx 133)
      p5 = right_eye_inner_corner (idx 51)
      p6 = right_eye_outer_corner (idx 370)

    Args:
        points: Flat list of [x, y, z, visibility, presence] per face point index,
                or a list of 4-6 eye landmark coordinates directly.

    Returns:
        EAR value between 0 and 1, or None if insufficient data.
    """
    if points is None or len(points) < 4:
        return None

    try:
        if len(points) >= max(REQUIRED_EAR_INDICES) + 1:
            pt_1 = np.array([float(points[36][0]), float(points[36][1])], dtype=np.float64)
            pt_2 = np.array([float(points[240][0]), float(points[240][1])], dtype=np.float64)
            pt_3 = np.array([float(points[33][0]), float(points[33][1])], dtype=np.float64)
            pt_4 = np.array([float(points[133][0]), float(points[133][1])], dtype=np.float64)
            pt_5 = np.array([float(points[51][0]), float(points[51][1])], dtype=np.float64)
            pt_6 = np.array([float(points[370][0]), float(points[370][1])], dtype=np.float64)
        elif len(points) >= 6:
            pt_1 = np.array([float(points[0][0]), float(points[0][1])], dtype=np.float64)
            pt_2 = np.array([float(points[1][0]), float(points[1][1])], dtype=np.float64)
            pt_3 = np.array([float(points[2][0]), float(points[2][1])], dtype=np.float64)
            pt_4 = np.array([float(points[3][0]), float(points[3][1])], dtype=np.float64)
            pt_5 = np.array([float(points[4][0]), float(points[4][1])], dtype=np.float64)
            pt_6 = np.array([float(points[5][0]), float(points[5][1])], dtype=np.float64)
        else:  # 4 or 5 points
            pt_1 = np.array([float(points[0][0]), float(points[0][1])], dtype=np.float64)
            pt_2 = np.array([float(points[1][0]), float(points[1][1])], dtype=np.float64)
            pt_3 = np.array([float(points[2][0]), float(points[2][1])], dtype=np.float64)
            pt_4 = np.array([float(points[3][0]), float(points[3][1])], dtype=np.float64)
            pt_5 = pt_2
            pt_6 = pt_3

        num = _norm_2d(pt_1, pt_4) + _norm_2d(pt_2, pt_5)
        denom = 2.0 * _norm_2d(pt_3, pt_6)
        ear = num / denom if denom > 1e-6 else 0.0
        ear = max(0.0, min(1.0, ear))
        return float(ear)
    except Exception:
        return None


def calculate_eye_ear(landmarks: list, eye: str = "left") -> float | None:
    """Calculate Eye Aspect Ratio (EAR) for a specific eye independently.

    Uses canonical MediaPipe eyelid and corner landmarks without iris/pupil tracking.
    Formula: EAR = (||p_top1 - p_bottom1|| + ||p_top2 - p_bottom2||) / (2 * ||p_corner1 - p_corner2||)

    Left Eye canonical indices:
      Corner 1: 33, Corner 2: 133
      Top 1: 160, Bottom 1: 144
      Top 2: 158, Bottom 2: 153

    Right Eye canonical indices:
      Corner 1: 263, Corner 2: 362
      Top 1: 385, Bottom 1: 380
      Top 2: 387, Bottom 2: 373

    If the requested eye points are not populated or are degenerate (e.g. in legacy tests),
    falls back cleanly to calculate_ear(landmarks).

    Args:
        landmarks: List of landmarks (each [x, y, z, ...])
        eye: "left" or "right"

    Returns:
        EAR float between 0.0 and 1.0, or None if invalid.
    """
    if landmarks is None or len(landmarks) == 0:
        return None

    eye_lower = eye.lower()
    indices = LEFT_EYE_CANONICAL_INDICES if eye_lower == "left" else RIGHT_EYE_CANONICAL_INDICES

    try:
        # Check if full mesh landmarks are available
        if len(landmarks) > max(indices):
            c1 = np.array([float(landmarks[indices[0]][0]), float(landmarks[indices[0]][1])], dtype=np.float64)
            c2 = np.array([float(landmarks[indices[1]][0]), float(landmarks[indices[1]][1])], dtype=np.float64)
            t1 = np.array([float(landmarks[indices[2]][0]), float(landmarks[indices[2]][1])], dtype=np.float64)
            b1 = np.array([float(landmarks[indices[3]][0]), float(landmarks[indices[3]][1])], dtype=np.float64)
            t2 = np.array([float(landmarks[indices[4]][0]), float(landmarks[indices[4]][1])], dtype=np.float64)
            b2 = np.array([float(landmarks[indices[5]][0]), float(landmarks[indices[5]][1])], dtype=np.float64)

            width = _norm_2d(c1, c2)
            has_vertical = not (np.all(t1[:2] == 0) and np.all(b1[:2] == 0) and np.all(t2[:2] == 0) and np.all(b2[:2] == 0))
            # If the canonical coordinates have valid width and populated vertical points, calculate independent EAR
            if width > 1e-4 and has_vertical:
                v1 = _norm_2d(t1, b1)
                v2 = _norm_2d(t2, b2)
                ear = (v1 + v2) / (2.0 * width)
                return float(max(0.0, min(1.0, ear)))

        # Fallback to legacy EAR for synthetic test vectors
        return calculate_ear(landmarks)
    except Exception:
        return None


class EyeTracker:
    """Tracks eye open/closed state using EAR calculations."""

    def __init__(
        self,
        open_threshold: float = DEFAULT_OPEN_THRESHOLD,
        independent_blink_detection: bool = DEFAULT_INDEPENDENT_BLINK,
        simultaneous_blink_suppression: bool = DEFAULT_SIMULTANEOUS_BLINK_SUPPRESSION,
        blink_cooldown_frames: int = DEFAULT_BLINK_COOLDOWN,
        left_threshold: float | None = None,
        right_threshold: float | None = None,
    ) -> None:
        self.left_ear: float | None = None  # Current left eye EAR
        self.right_ear: float | None = None  # Current right eye EAR
        self.left_is_open: bool = True  # Normalized state
        self.right_is_open: bool = True  # Normalized state
        self.left_ear_history: list[float] = []  # Track history for adaptation
        self.right_ear_history: list[float] = []
        self.open_threshold = open_threshold
        self.left_threshold = left_threshold if left_threshold is not None else open_threshold
        self.right_threshold = right_threshold if right_threshold is not None else open_threshold
        self.adapted_thresholds: dict[str, float] = {
            "left": self.left_threshold,
            "right": self.right_threshold,
        }
        self.last_blink_time: float = 0.0
        self.blink_count: int = 0
        self.baseline_window: int = 30  # Frames of history to consider for baseline
        self.left_baseline: float = 0.28
        self.right_baseline: float = 0.28
        self.independent_blink_detection = independent_blink_detection
        self.simultaneous_blink_suppression = simultaneous_blink_suppression
        self.blink_cooldown_frames = blink_cooldown_frames

    def calibrate_baseline(self, left_samples: list[float], right_samples: list[float]) -> None:
        """Calibrate open-eye baselines from collected frame EAR values."""
        if len(left_samples) >= 5:
            self.left_baseline = float(np.median(left_samples))
            self.adapted_thresholds["left"] = max(0.10, self.left_baseline * 0.76)
        if len(right_samples) >= 5:
            self.right_baseline = float(np.median(right_samples))
            self.adapted_thresholds["right"] = max(0.10, self.right_baseline * 0.76)
        logger.info(f"EyeTracker baseline calibrated: Left={self.left_baseline:.3f}, Right={self.right_baseline:.3f}")

    @staticmethod
    def calculate_ear(points: list[list]) -> float | None:
        """Calculate Eye Aspect Ratio (EAR) - backward compatible."""
        return calculate_ear(points)

    @staticmethod
    def calculate_eye_ear(landmarks: list, eye: str = "left") -> float | None:
        """Calculate independent EAR for specified eye."""
        return calculate_eye_ear(landmarks, eye=eye)

    def update(self, landmarks: dict | None) -> dict[str, object]:
        """Update eye tracking state from landmark data.

        Calculates left and right EAR independently using canonical eyelid/corner
        landmarks without pupil or iris tracking.

        Args:
            landmarks: Output from FaceLandmarkerWrapper.detect_landmarks()

        Returns:
            Dictionary with updated states:
            {
                "left_is_open": bool,
                "right_is_open": bool,
                "left_ear": float|None,
                "right_ear": float|None,
                "left_blink_detected": bool,
                "right_blink_detected": bool,
            }
        """
        result = {
            "left_is_open": self.left_is_open,
            "right_is_open": self.right_is_open,
            "left_ear": self.left_ear,
            "right_ear": self.right_ear,
            "left_blink_detected": False,
            "right_blink_detected": False,
        }

        if landmarks is None:
            return result

        has_face = landmarks.get("has_face", False)
        lm_list = landmarks.get("landmarks", [])
        if not has_face and len(lm_list) > 0:
            has_face = True

        if not has_face or len(lm_list) == 0:
            return result

        try:
            # Independent EAR computation
            left_ear = calculate_eye_ear(lm_list, eye="left")
            right_ear = calculate_eye_ear(lm_list, eye="right")

            # Fallback if both returned None
            if left_ear is None and right_ear is None:
                fallback_ear = calculate_ear(lm_list)
                left_ear = fallback_ear
                right_ear = fallback_ear

            if left_ear is not None:
                self._update_ear_history("left", left_ear)
                self.left_ear = left_ear
                result["left_ear"] = left_ear
                self.left_is_open = left_ear > self.adapted_thresholds["left"]
                result["left_is_open"] = self.left_is_open

            if right_ear is not None:
                self._update_ear_history("right", right_ear)
                self.right_ear = right_ear
                result["right_ear"] = right_ear
                self.right_is_open = right_ear > self.adapted_thresholds["right"]
                result["right_is_open"] = self.right_is_open

            # Blink pattern detection
            left_blink = self._check_blink_pattern("left")
            right_blink = self._check_blink_pattern("right")
            result["left_blink_detected"] = left_blink
            result["right_blink_detected"] = right_blink

            return result

        except Exception as e:
            logger.debug(f"EyeTracker update error: {e}")
            return result

    def _update_ear_history(self, eye: str, ear: float) -> None:
        """Update the EAR history for adaptive thresholding."""
        hist = getattr(self, f"{eye}_ear_history")
        hist.append(ear)
        if len(hist) > self.baseline_window * 3:
            del hist[0]

    def _check_blink_pattern(self, eye: str) -> bool:
        """Simple blink detection based on EAR history drop pattern."""
        hist = getattr(self, f"{eye}_ear_history")
        if len(hist) < 5:
            return False

        recent = hist[-min(5, len(hist)):]
        current_ear = getattr(self, f"{eye}_ear")
        if current_ear is None:
            return False

        was_closed = all(e < self.adapted_thresholds[eye] for e in recent[:-1])
        currently_closed = current_ear < self.adapted_thresholds[eye]
        rising = len(recent) > 0 and recent[-1] >= recent[0]

        if was_closed and currently_closed and rising:
            self.blink_count += 1
            return True
        return False

    def adapt_thresholds(self) -> None:
        """Adaptive threshold calculation based on historical EAR values."""
        for eye in ["left", "right"]:
            hist = getattr(self, f"{eye}_ear_history")
            if len(hist) < 10:
                continue

            recent = hist[-max(10, len(hist) // 2):]
            avg_ear = float(np.mean(recent))
            std_ear = float(np.std(recent))

            new_threshold = max(avg_ear - std_ear * 0.5, 0.05)
            self.adapted_thresholds[eye] = new_threshold

        logger.info("EyeTracker adaptive thresholds updated.")

    def reset(self) -> None:
        """Reset all tracking state."""
        self.left_ear = None
        self.right_ear = None
        self.left_is_open = True
        self.right_is_open = True
        self.left_ear_history = []
        self.right_ear_history = []
        self.last_blink_time = 0.0
        self.blink_count = 0
        self.baseline_window = 30
