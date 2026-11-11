"""Eyebrow Gesture Tracking & Scroll Mode module for HeadMouse AI.

Uses MediaPipe facial landmarks to track left and right eyebrow heights
independently. Normalized scale-invariant distance measurements detect
intentional bilateral eyebrow raises to engage Hands-Free Scroll Mode.

Gestures:
- Both eyebrows raised for >= 300ms -> SCROLL MODE: ACTIVE
- Either/both eyebrows return to normal -> SCROLL MODE: INACTIVE
- While active:
    - Head vertical displacement UP   -> Scroll UP
    - Head vertical displacement DOWN -> Scroll DOWN
    - Head within neutral deadzone    -> STOP (no scroll)

IMPORTANT:
Does NOT use pupil or iris coordinates. Operates strictly on eyebrow arch
and eyelid landmarks, normalized by inter-ocular scale.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from config.settings import ScrollSettings, get_settings
from utils.logger import logger

# MediaPipe canonical face mesh indices
# Left eye / eyebrow (Screen-left / Canonical)
LEFT_EYEBROW_ARCH = 105
LEFT_EYEBROW_INNER = 70
LEFT_EYEBROW_OUTER = 107
LEFT_EYE_TOP = 159
LEFT_EYE_OUTER_CORNER = 33
LEFT_EYE_INNER_CORNER = 133

# Right eye / eyebrow (Screen-right / Canonical)
RIGHT_EYEBROW_ARCH = 334
RIGHT_EYEBROW_INNER = 336
RIGHT_EYEBROW_OUTER = 300
RIGHT_EYE_TOP = 386
RIGHT_EYE_OUTER_CORNER = 263
RIGHT_EYE_INNER_CORNER = 362

# States
STATE_NORMAL = "NORMAL"
STATE_RAISED = "RAISED"

# Direction states
SCROLL_DIR_STOP = "STOP"
SCROLL_DIR_UP = "UP"
SCROLL_DIR_DOWN = "DOWN"


def _extract_pt(lm_list: list, index: int) -> Tuple[float, float] | None:
    """Extract normalized (x, y) coordinates for a landmark index safely."""
    if not lm_list or index >= len(lm_list):
        return None
    pt = lm_list[index]
    if isinstance(pt, dict):
        return float(pt.get("x", 0.0)), float(pt.get("y", 0.0))
    elif isinstance(pt, (list, tuple)):
        return float(pt[0]), float(pt[1])
    elif hasattr(pt, "x") and hasattr(pt, "y"):
        return float(pt.x), float(pt.y)
    return None


class EyebrowTracker:
    """Detects bilateral eyebrow raising gestures and controls head-driven scrolling."""

    def __init__(self, settings: ScrollSettings | None = None) -> None:
        if settings is None:
            settings = get_settings().scroll

        self.settings = settings
        self.enabled = bool(settings.enabled)
        self.raise_threshold = float(settings.eyebrow_raise_threshold)
        self.hysteresis = float(settings.eyebrow_hysteresis)
        self.activation_delay_sec = float(settings.activation_delay_sec)
        self.scroll_deadzone = float(settings.scroll_deadzone)
        self.min_scroll_speed = int(settings.min_scroll_speed)
        self.max_scroll_speed = int(settings.max_scroll_speed)
        self.scroll_gain = float(settings.scroll_gain)
        self.scroll_interval_sec = float(settings.scroll_interval_sec)

        # Baseline resting ratios (eyebrow height / inter-ocular scale)
        self.left_baseline: float = float(settings.left_eyebrow_baseline)
        self.right_baseline: float = float(settings.right_eyebrow_baseline)
        self.is_calibrated: bool = False

        # Live eyebrow states
        self.left_state: str = STATE_NORMAL
        self.right_state: str = STATE_NORMAL
        self.left_ratio: float = self.left_baseline
        self.right_ratio: float = self.right_baseline

        # Activation timer
        self.raise_start_time: float | None = None
        self.scroll_mode_active: bool = False
        self.last_scroll_time: float = 0.0

        # Current scroll telemetry
        self.scroll_direction: str = SCROLL_DIR_STOP
        self.scroll_speed: int = 0
        self.last_action: str = "INACTIVE"

    def calculate_ratios(self, landmarks: list) -> Tuple[float | None, float | None]:
        """Compute normalized eyebrow-to-eye distances.

        Args:
            landmarks: MediaPipe landmark list.

        Returns:
            Tuple of (left_ratio, right_ratio) or (None, None).
        """
        if not landmarks or len(landmarks) < 400:
            return None, None

        p_left_brow = _extract_pt(landmarks, LEFT_EYEBROW_ARCH)
        p_left_eye = _extract_pt(landmarks, LEFT_EYE_TOP)
        p_right_brow = _extract_pt(landmarks, RIGHT_EYEBROW_ARCH)
        p_right_eye = _extract_pt(landmarks, RIGHT_EYE_TOP)
        p_l_corner = _extract_pt(landmarks, LEFT_EYE_OUTER_CORNER)
        p_r_corner = _extract_pt(landmarks, RIGHT_EYE_OUTER_CORNER)

        if not (p_left_brow and p_left_eye and p_right_brow and p_right_eye and p_l_corner and p_r_corner):
            return None, None

        # Inter-ocular distance as scale reference (in normalized 2D coordinates)
        dx = p_r_corner[0] - p_l_corner[0]
        dy = p_r_corner[1] - p_l_corner[1]
        scale = float(np.hypot(dx, dy))
        if scale < 0.05:
            scale = 0.35  # Fallback default scale

        # Vertical eyebrow-to-eye distance (eye.y - brow.y; higher brow = smaller brow.y = larger distance)
        d_left = p_left_eye[1] - p_left_brow[1]
        d_right = p_right_eye[1] - p_right_brow[1]

        left_ratio = float(d_left / scale)
        right_ratio = float(d_right / scale)

        return left_ratio, right_ratio

    def extract_ratios(self, landmarks: list) -> Tuple[float | None, float | None]:
        """Alias for calculate_ratios."""
        return self.calculate_ratios(landmarks)

    def calibrate_baseline(self, left_samples: list[float], right_samples: list[float]) -> None:
        """Calibrate resting natural eyebrow baselines from camera samples."""
        valid_l = [s for s in left_samples if 0.05 <= s <= 0.45]
        valid_r = [s for s in right_samples if 0.05 <= s <= 0.45]

        if len(valid_l) >= 5:
            self.left_baseline = float(np.median(valid_l))
        if len(valid_r) >= 5:
            self.right_baseline = float(np.median(valid_r))

        self.is_calibrated = True
        logger.info(
            f"Eyebrow baseline calibrated: Left={self.left_baseline:.3f}, "
            f"Right={self.right_baseline:.3f} (Samples: L={len(valid_l)}, R={len(valid_r)})"
        )

    def update(
        self,
        landmarks_data: dict | None,
        relative_dy: float = 0.0,
        timestamp: float | None = None,
    ) -> dict[str, Any]:
        """Update eyebrow tracking and scroll state machine.

        Args:
            landmarks_data: Landmarker dict containing 'has_face' and 'landmarks'.
            relative_dy: Relative vertical head displacement from neutral baseline.
            timestamp: Monotonic timestamp in seconds.

        Returns:
            Dictionary of live eyebrow and scroll telemetry.
        """
        if timestamp is None:
            timestamp = time.monotonic()

        has_face = False
        lm_list: list = []
        if landmarks_data:
            has_face = bool(landmarks_data.get("has_face", False))
            lm_list = landmarks_data.get("landmarks", [])

        if not has_face or len(lm_list) == 0:
            # Face loss safety: immediately cut scroll mode
            self.scroll_mode_active = False
            self.raise_start_time = None
            self.left_state = STATE_NORMAL
            self.right_state = STATE_NORMAL
            self.scroll_direction = SCROLL_DIR_STOP
            self.scroll_speed = 0
            return self._build_status(0.0)

        # 1. Calculate live normalized ratios
        l_ratio, r_ratio = self.calculate_ratios(lm_list)
        if l_ratio is not None and r_ratio is not None:
            self.left_ratio = l_ratio
            self.right_ratio = r_ratio

        # 2. Schmitt Trigger Hysteresis for Left Eyebrow
        high_thresh_l = self.left_baseline * (1.0 + self.raise_threshold)
        low_thresh_l = self.left_baseline * (1.0 + max(0.02, self.raise_threshold - self.hysteresis))

        if self.left_state == STATE_NORMAL:
            if self.left_ratio >= high_thresh_l:
                self.left_state = STATE_RAISED
        else:
            if self.left_ratio < low_thresh_l:
                self.left_state = STATE_NORMAL

        # 3. Schmitt Trigger Hysteresis for Right Eyebrow
        high_thresh_r = self.right_baseline * (1.0 + self.raise_threshold)
        low_thresh_r = self.right_baseline * (1.0 + max(0.02, self.raise_threshold - self.hysteresis))

        if self.right_state == STATE_NORMAL:
            if self.right_ratio >= high_thresh_r:
                self.right_state = STATE_RAISED
        else:
            if self.right_ratio < low_thresh_r:
                self.right_state = STATE_NORMAL

        # 4. Bilateral Activation State Machine
        hold_duration_sec = 0.0
        both_raised = (self.left_state == STATE_RAISED) and (self.right_state == STATE_RAISED)

        if both_raised:
            if self.raise_start_time is None:
                self.raise_start_time = timestamp
            hold_duration_sec = timestamp - self.raise_start_time

            if hold_duration_sec >= self.activation_delay_sec:
                if not self.scroll_mode_active:
                    logger.info("SCROLL MODE: ACTIVATED by bilateral eyebrow raise.")
                self.scroll_mode_active = True
        else:
            if self.scroll_mode_active:
                logger.info("SCROLL MODE: DEACTIVATED (eyebrows returned to normal).")
            self.raise_start_time = None
            self.scroll_mode_active = False

        # 5. Calculate Scroll Direction & Speed from Head Movement
        scroll_amount = 0
        if self.scroll_mode_active:
            # Check vertical head displacement from neutral
            if abs(relative_dy) < self.scroll_deadzone:
                self.scroll_direction = SCROLL_DIR_STOP
                self.scroll_speed = 0
            elif relative_dy > self.scroll_deadzone:
                # Head moved UP -> Scroll UP
                self.scroll_direction = SCROLL_DIR_UP
                excess = relative_dy - self.scroll_deadzone
                speed = int(round(self.min_scroll_speed + excess * self.scroll_gain))
                self.scroll_speed = max(self.min_scroll_speed, min(self.max_scroll_speed, speed))
                scroll_amount = self.scroll_speed
            else:
                # Head moved DOWN -> Scroll DOWN
                self.scroll_direction = SCROLL_DIR_DOWN
                excess = abs(relative_dy) - self.scroll_deadzone
                speed = int(round(self.min_scroll_speed + excess * self.scroll_gain))
                self.scroll_speed = max(self.min_scroll_speed, min(self.max_scroll_speed, speed))
                scroll_amount = -self.scroll_speed
        else:
            self.scroll_direction = SCROLL_DIR_STOP
            self.scroll_speed = 0

        return self._build_status(scroll_amount, hold_duration_sec)

    def compute_scroll(self, relative_dy: float, timestamp: float | None = None) -> dict[str, Any]:
        """Compute scroll direction, speed, and amount directly from relative head movement."""
        if not self.scroll_mode_active:
            return {"direction": SCROLL_DIR_STOP, "speed": 0, "amount": 0}

        if abs(relative_dy) < self.scroll_deadzone:
            self.scroll_direction = SCROLL_DIR_STOP
            self.scroll_speed = 0
            return {"direction": SCROLL_DIR_STOP, "speed": 0, "amount": 0}
        elif relative_dy > self.scroll_deadzone:
            self.scroll_direction = SCROLL_DIR_UP
            excess = relative_dy - self.scroll_deadzone
            speed = int(round(self.min_scroll_speed + excess * self.scroll_gain))
            self.scroll_speed = max(self.min_scroll_speed, min(self.max_scroll_speed, speed))
            return {"direction": SCROLL_DIR_UP, "speed": self.scroll_speed, "amount": self.scroll_speed}
        else:
            self.scroll_direction = SCROLL_DIR_DOWN
            excess = abs(relative_dy) - self.scroll_deadzone
            speed = int(round(self.min_scroll_speed + excess * self.scroll_gain))
            self.scroll_speed = max(self.min_scroll_speed, min(self.max_scroll_speed, speed))
            return {"direction": SCROLL_DIR_DOWN, "speed": self.scroll_speed, "amount": -self.scroll_speed}

    def _build_status(self, scroll_amount: float, hold_duration_sec: float = 0.0) -> dict[str, Any]:
        """Construct status dictionary."""
        return {
            "scroll_mode_active": self.scroll_mode_active,
            "left_state": self.left_state,
            "right_state": self.right_state,
            "left_raised": (self.left_state == STATE_RAISED),
            "right_raised": (self.right_state == STATE_RAISED),
            "left_ratio": self.left_ratio,
            "right_ratio": self.right_ratio,
            "left_baseline": self.left_baseline,
            "right_baseline": self.right_baseline,
            "scroll_direction": self.scroll_direction,
            "scroll_speed": self.scroll_speed,
            "scroll_amount": int(round(scroll_amount)),
            "hold_duration_ms": hold_duration_sec * 1000.0,
            "is_calibrated": self.is_calibrated,
            "any_raised": (self.left_state == STATE_RAISED or self.right_state == STATE_RAISED),
        }
