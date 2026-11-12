"""Gesture-Based Interaction module for HeadMouse AI (Scroll & Zoom).

Provides unified, mutually-exclusive hands-free Scroll Mode and Zoom Mode
gated by scale-invariant MediaPipe Face Mesh landmarks.

Architecture & State Hierarchy:
1. TEETH SHOW ONLY (eyebrows normal):
   - Activate SCROLL MODE.
   - Head UP   = Scroll Up.
   - Head DOWN = Scroll Down.
   - Head neutral = Stop scrolling.

2. TEETH SHOW + BOTH EYEBROWS RAISED:
   - Switch from Scroll Mode to ZOOM MODE.
   - Head UP   = Zoom In (Ctrl + Plus).
   - Head DOWN = Zoom Out (Ctrl + Minus).
   - Head neutral = No action.

3. TEETH NOT VISIBLE:
   - Immediately disable BOTH Scroll Mode and Zoom Mode.

4. EYEBROWS RETURN TO NORMAL:
   - Disable Zoom Mode.
   - If teeth are still visible, return to SCROLL MODE automatically.

Safety & Anti-Runaway:
- Never run scrolling and zooming simultaneously.
- Scale-invariant MediaPipe Face Mesh landmark geometry normalized by Inter-Ocular Distance (IOD).
- Strictly NO pupil or iris coordinates used.
- Edge-triggered step latch: holding head tilted does NOT continuously trigger rapid runaway actions.
  Returning head to neutral deadzone re-arms for the next action.
"""

from __future__ import annotations

import time
from typing import Any, Tuple

import numpy as np

from config.settings import ZoomSettings, get_settings
from utils.logger import logger

# MediaPipe canonical face mesh landmark indices
LEFT_EYE_OUTER = 33
RIGHT_EYE_OUTER = 263
LEFT_EYEBROW_ARCH = 105
LEFT_EYE_TOP = 159
RIGHT_EYEBROW_ARCH = 334
RIGHT_EYE_TOP = 386

# Mouth / Lip landmarks for teeth detection
LEFT_MOUTH_CORNER = 61
RIGHT_MOUTH_CORNER = 291
UPPER_LIP_INNER = 13
LOWER_LIP_INNER = 14

# Feature states
STATE_NORMAL = "NORMAL"
STATE_RAISED = "RAISED"

# Mode Constants
MODE_NONE = "NONE"
MODE_SCROLL = "SCROLL"
MODE_ZOOM = "ZOOM"

# Action Constants
ZOOM_IN = "ZOOM_IN"
ZOOM_OUT = "ZOOM_OUT"
SCROLL_UP = "SCROLL_UP"
SCROLL_DOWN = "SCROLL_DOWN"
SCROLL_STOP = "STOP"


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


class GestureZoomTracker:
    """Tracks mouth and eyebrow gestures to control mutually-exclusive scroll and zoom modes."""

    def __init__(self, settings: ZoomSettings | None = None) -> None:
        if settings is None:
            settings = get_settings().zoom

        self.settings = settings
        self.enabled: bool = bool(settings.enabled)
        self.mouth_width_threshold: float = float(settings.mouth_width_threshold)
        self.mouth_open_min: float = float(settings.mouth_open_min)
        self.mouth_open_max: float = float(settings.mouth_open_max)
        self.raise_threshold: float = float(settings.eyebrow_raise_threshold)
        self.hysteresis: float = float(settings.eyebrow_hysteresis)
        self.zoom_deadzone: float = float(settings.zoom_deadzone)
        self.scroll_deadzone: float = float(getattr(settings, "scroll_deadzone", 0.020))
        self.neutral_deadzone: float = float(settings.neutral_deadzone)
        self.zoom_step: int = int(settings.zoom_step)
        self.scroll_step: int = int(getattr(settings, "scroll_step", 2))
        self.scroll_sensitivity: float = float(getattr(settings, "scroll_sensitivity", 1.0))
        self.zoom_sensitivity: float = float(getattr(settings, "zoom_sensitivity", 1.0))
        self.smile_sensitivity: float = float(getattr(settings, "smile_sensitivity", 1.0))
        self.zoom_cooldown_sec: float = float(settings.zoom_cooldown_sec)
        self.scroll_cooldown_sec: float = float(getattr(settings, "scroll_cooldown_sec", 0.20))
        self.continuous_scroll: bool = bool(getattr(settings, "continuous_scroll", True))
        self.activation_grace_frames: int = int(getattr(settings, "activation_grace_frames", 1))
        self.deactivation_grace_sec: float = float(getattr(settings, "deactivation_grace_sec", 0.08))
        self.face_loss_grace_sec: float = float(getattr(settings, "face_loss_grace_sec", 0.08))

        # Baseline resting ratios normalized by IOD
        self.left_eyebrow_baseline: float = float(settings.left_eyebrow_baseline)
        self.right_eyebrow_baseline: float = float(settings.right_eyebrow_baseline)
        self.mouth_width_baseline: float = float(settings.mouth_width_baseline)
        self.is_calibrated: bool = False

        # Live interaction modes
        self.mode: str = MODE_NONE
        self.scroll_mode_active: bool = False
        self.zoom_mode_active: bool = False
        self.teeth_visible: bool = False

        # Temporal stability & debounce tracking
        self._candidate_smile_frames: int = 0
        self._last_face_time: float | None = None
        self._last_teeth_time: float | None = None
        self._eyebrow_raise_start_time: float | None = None
        self._last_valid_metrics: tuple[float, float, float, float] | None = None

        # Live eyebrow states
        self.left_eb_state: str = STATE_NORMAL
        self.right_eb_state: str = STATE_NORMAL

        # Live ratios
        self.left_eb_ratio: float = self.left_eyebrow_baseline
        self.right_eb_ratio: float = self.right_eyebrow_baseline
        self.mouth_width_ratio: float = self.mouth_width_baseline
        self.mouth_open_ratio: float = 0.0

        # Edge-triggered step latching (anti-runaway)
        self.step_ready: bool = True
        self.last_zoom_time: float = 0.0
        self.last_scroll_time: float = 0.0
        self.last_action: str | None = None
        self.last_reject_reason: str = "NONE"

    def extract_features(
        self, landmarks: list
    ) -> Tuple[float | None, float | None, float | None, float | None]:
        """Compute scale-invariant normalized facial metrics using IOD.

        Args:
            landmarks: List of MediaPipe landmarks.

        Returns:
            Tuple of (left_eb_ratio, right_eb_ratio, mouth_width_ratio, mouth_open_ratio)
            or (None, None, None, None) if points cannot be extracted.
        """
        if not landmarks or len(landmarks) < 300:
            return None, None, None, None

        p_l_corner = _extract_pt(landmarks, LEFT_EYE_OUTER)
        p_r_corner = _extract_pt(landmarks, RIGHT_EYE_OUTER)
        p_l_brow = _extract_pt(landmarks, LEFT_EYEBROW_ARCH)
        p_l_eye = _extract_pt(landmarks, LEFT_EYE_TOP)
        p_r_brow = _extract_pt(landmarks, RIGHT_EYEBROW_ARCH)
        p_r_eye = _extract_pt(landmarks, RIGHT_EYE_TOP)
        p_m_left = _extract_pt(landmarks, LEFT_MOUTH_CORNER)
        p_m_right = _extract_pt(landmarks, RIGHT_MOUTH_CORNER)
        p_lip_up = _extract_pt(landmarks, UPPER_LIP_INNER)
        p_lip_lo = _extract_pt(landmarks, LOWER_LIP_INNER)

        if not (
            p_l_corner
            and p_r_corner
            and p_l_brow
            and p_l_eye
            and p_r_brow
            and p_r_eye
            and p_m_left
            and p_m_right
            and p_lip_up
            and p_lip_lo
        ):
            return None, None, None, None

        # Inter-Ocular Distance (IOD) as universal scale reference
        iod = float(np.hypot(p_r_corner[0] - p_l_corner[0], p_r_corner[1] - p_l_corner[1]))
        if iod < 0.05:
            iod = 0.35

        # Vertical eyebrow-to-eye distance (eye.y - brow.y, positive when brow is above eye)
        d_left_eb = p_l_eye[1] - p_l_brow[1]
        d_right_eb = p_r_eye[1] - p_r_brow[1]
        left_eb_ratio = float(d_left_eb / iod)
        right_eb_ratio = float(d_right_eb / iod)

        # Mouth metrics
        d_mouth_w = float(np.hypot(p_m_right[0] - p_m_left[0], p_m_right[1] - p_m_left[1]))
        d_mouth_o = float(np.hypot(p_lip_lo[0] - p_lip_up[0], p_lip_lo[1] - p_lip_up[1]))
        mouth_width_ratio = float(d_mouth_w / iod)
        mouth_open_ratio = float(d_mouth_o / iod)

        return left_eb_ratio, right_eb_ratio, mouth_width_ratio, mouth_open_ratio

    def calibrate_baseline(
        self,
        left_eb_samples: list[float],
        right_eb_samples: list[float],
        mouth_width_samples: list[float] | None = None,
    ) -> None:
        """Calibrate resting natural baselines from neutral camera frames."""
        valid_l = [s for s in left_eb_samples if 0.05 <= s <= 0.45]
        valid_r = [s for s in right_eb_samples if 0.05 <= s <= 0.45]

        if len(valid_l) >= 5:
            self.left_eyebrow_baseline = float(np.median(valid_l))
        if len(valid_r) >= 5:
            self.right_eyebrow_baseline = float(np.median(valid_r))

        if mouth_width_samples:
            valid_m = [s for s in mouth_width_samples if 0.35 <= s <= 0.95]
            if len(valid_m) >= 5:
                self.mouth_width_baseline = float(np.median(valid_m))

        self.is_calibrated = True
        logger.info(
            f"Gesture interaction baselines calibrated: LeftEB={self.left_eyebrow_baseline:.3f}, "
            f"RightEB={self.right_eyebrow_baseline:.3f}, MouthW={self.mouth_width_baseline:.3f}"
        )

    def set_sensitivities(
        self,
        scroll_sensitivity: float | None = None,
        zoom_sensitivity: float | None = None,
        smile_sensitivity: float | None = None,
        scroll_step: int | None = None,
        zoom_step: int | None = None,
    ) -> None:
        """Update gesture sensitivities and step sizes dynamically."""
        if scroll_sensitivity is not None:
            self.scroll_sensitivity = float(np.clip(scroll_sensitivity, 0.1, 10.0))
        if zoom_sensitivity is not None:
            self.zoom_sensitivity = float(np.clip(zoom_sensitivity, 0.1, 10.0))
        if smile_sensitivity is not None:
            self.smile_sensitivity = float(np.clip(smile_sensitivity, 0.5, 2.0))
        if scroll_step is not None:
            self.scroll_step = max(1, int(scroll_step))
        if zoom_step is not None:
            self.zoom_step = max(1, int(zoom_step))

    def reset(self) -> None:
        """Reset state tracking."""
        self.left_eb_state = STATE_NORMAL
        self.right_eb_state = STATE_NORMAL
        self.teeth_visible = False
        self.mode = MODE_NONE
        self.scroll_mode_active = False
        self.zoom_mode_active = False
        self.step_ready = True
        self.last_action = None
        self.last_reject_reason = "NONE"
        self._candidate_smile_frames = 0
        self._last_face_time = None
        self._last_teeth_time = None
        self._eyebrow_raise_start_time = None
        self._last_valid_metrics = None

    def update(
        self,
        landmarks_data: dict | None,
        relative_dy: float = 0.0,
        timestamp: float | None = None,
    ) -> dict[str, Any]:
        """Process frame landmarks and relative vertical head displacement.

        Args:
            landmarks_data: Dictionary containing 'has_face' and 'landmarks'.
            relative_dy: Vertical displacement from neutral nose position (positive = UP, negative = DOWN).
            timestamp: Monotonic timestamp in seconds.

        Returns:
            Dictionary with interaction mode, actions (scroll/zoom), telemetry, and safety flags.
        """
        if timestamp is None:
            timestamp = time.monotonic()

        has_face = False
        lm_list: list = []
        if landmarks_data:
            has_face = bool(landmarks_data.get("has_face", False))
            lm_list = landmarks_data.get("landmarks", [])

        # Face loss safety with brief landmark-drop grace period
        if not has_face or len(lm_list) == 0:
            elapsed_lost = (timestamp - self._last_face_time) if self._last_face_time is not None else 999.0
            # If face loss persists beyond grace period, or if no gesture was active: safe reset
            if elapsed_lost >= self.face_loss_grace_sec or not (self.scroll_mode_active or self.zoom_mode_active):
                self.reset()
                return self._build_status(None, 0, None, relative_dy, reject_reason="FACE_LOST")
            else:
                # Brief momentary dropout (e.g. single camera frame dip): suppress action but hold mode
                return self._build_status(None, 0, None, relative_dy, reject_reason="FACE_LOST_GRACE")

        self._last_face_time = timestamp

        if not self.enabled:
            self.reset()
            return self._build_status(None, 0, None, relative_dy, reject_reason="DISABLED")

        # 1. Extract scale-invariant metrics
        l_eb, r_eb, m_w, m_o = self.extract_features(lm_list)
        if l_eb is not None and r_eb is not None and m_w is not None and m_o is not None:
            self.left_eb_ratio = l_eb
            self.right_eb_ratio = r_eb
            self.mouth_width_ratio = m_w
            self.mouth_open_ratio = m_o
            self._last_valid_metrics = (l_eb, r_eb, m_w, m_o)
        elif self._last_valid_metrics is not None and (self.scroll_mode_active or self.zoom_mode_active):
            l_eb, r_eb, m_w, m_o = self._last_valid_metrics

        # Relative stretch of mouth width relative to baseline
        base_w = max(0.35, self.mouth_width_baseline)
        stretch_ratio = self.mouth_width_ratio / base_w
        eff_smile_sens = max(0.1, self.smile_sensitivity)

        # 2. Teeth-Show Gesture Detection with Schmitt Trigger Hysteresis & Debounce:
        # Requires lateral corner expansion (smile) AND vertical inner lip parting (showing teeth).
        # Speech has mouth_open_ratio in [0.02, 0.12] but stretch_ratio < 1.06, so speech is strictly rejected.
        reject_reason = "NONE"

        if not self.teeth_visible:
            req_stretch = 1.10 / eff_smile_sens
            req_width = self.mouth_width_threshold / eff_smile_sens
            is_wide_smile = (stretch_ratio >= req_stretch) or (self.mouth_width_ratio >= req_width)
            has_lip_separation = self.mouth_open_min <= self.mouth_open_ratio <= self.mouth_open_max
            if is_wide_smile and has_lip_separation:
                self._candidate_smile_frames += 1
                if self._candidate_smile_frames >= self.activation_grace_frames:
                    self.teeth_visible = True
                    self._last_teeth_time = timestamp
                else:
                    reject_reason = "HOLDING_SMILE"
            else:
                self._candidate_smile_frames = 0
                if not is_wide_smile:
                    reject_reason = "MOUTH_NARROW"
                elif self.mouth_open_ratio < self.mouth_open_min:
                    reject_reason = "LIPS_CLOSED"
                elif self.mouth_open_ratio > self.mouth_open_max:
                    reject_reason = "MOUTH_TOO_OPEN"
        else:
            # Deactivation condition with Schmitt trigger hysteresis & temporal debounce:
            # Closing the mouth (lips meeting) or relaxing lateral smile deactivates gesture.
            # Perspective foreshortening during head tilt compresses vertical lip separation in 2D.
            # A temporal grace period (deactivation_grace_sec = 0.08s = 80ms) protects against
            # momentary single-frame or multi-frame landmark flickers during head tilt.
            deact_closed = self.mouth_open_ratio < max(0.009, self.mouth_open_min - 0.008)
            deact_width = (stretch_ratio < 1.05) and (self.mouth_width_ratio < (self.mouth_width_threshold - 0.04))
            deact_yawn = self.mouth_open_ratio > (self.mouth_open_max + 0.05)

            if deact_closed or deact_width or deact_yawn:
                elapsed_deact = (timestamp - self._last_teeth_time) if self._last_teeth_time is not None else 999.0
                if elapsed_deact >= self.deactivation_grace_sec:
                    self.teeth_visible = False
                    self._candidate_smile_frames = 0
                    self._last_teeth_time = None
                    reject_reason = "MOUTH_CLOSED" if deact_closed else ("MOUTH_RELAXED" if deact_width else "MOUTH_TOO_OPEN")
                else:
                    reject_reason = "DEACT_GRACE"
            else:
                self._last_teeth_time = timestamp

        # 3. Bilateral Eyebrow Raise Detection with Schmitt Trigger Hysteresis
        high_l = self.left_eyebrow_baseline * (1.0 + self.raise_threshold)
        low_l = self.left_eyebrow_baseline * (1.0 + max(0.02, self.raise_threshold - self.hysteresis))
        if self.left_eb_state == STATE_NORMAL:
            if self.left_eb_ratio >= high_l:
                self.left_eb_state = STATE_RAISED
        else:
            if self.left_eb_ratio < low_l:
                self.left_eb_state = STATE_NORMAL

        high_r = self.right_eyebrow_baseline * (1.0 + self.raise_threshold)
        low_r = self.right_eyebrow_baseline * (1.0 + max(0.02, self.raise_threshold - self.hysteresis))
        if self.right_eb_state == STATE_NORMAL:
            if self.right_eb_ratio >= high_r:
                self.right_eb_state = STATE_RAISED
        else:
            if self.right_eb_ratio < low_r:
                self.right_eb_state = STATE_NORMAL

        both_eyebrows_raised = (self.left_eb_state == STATE_RAISED) and (self.right_eb_state == STATE_RAISED)

        # 4. Mode Selection State Machine:
        # Rule 3: Teeth not visible -> Immediately disable BOTH Scroll Mode and Zoom Mode!
        # Rule 1: Teeth visible ONLY (eyebrows normal) -> Activate Scroll Mode.
        # Rule 2: Teeth visible + BOTH eyebrows raised -> Switch from Scroll Mode to Zoom Mode.
        # Rule 4: Eyebrows return to normal -> Disable Zoom Mode; if teeth still visible, return to Scroll Mode.
        prev_mode = self.mode

        if not self.teeth_visible:
            self.mode = MODE_NONE
            self.scroll_mode_active = False
            self.zoom_mode_active = False
        else:
            if both_eyebrows_raised:
                self.mode = MODE_ZOOM
                self.zoom_mode_active = True
                self.scroll_mode_active = False
            else:
                self.mode = MODE_SCROLL
                self.scroll_mode_active = True
                self.zoom_mode_active = False

        if self.mode != prev_mode:
            if self.mode == MODE_ZOOM:
                logger.info("GESTURE MODE: Switched to ZOOM MODE (Teeth + Both Eyebrows Raised).")
            elif self.mode == MODE_SCROLL:
                logger.info("GESTURE MODE: Switched to SCROLL MODE (Teeth Visible Only).")
            else:
                logger.info(f"GESTURE MODE: Deactivated ({reject_reason}).")
            # Whenever mode switches, re-arm step latch
            self.step_ready = True

        # 5. Mutually Exclusive Action Evaluation & Anti-Runaway
        # Never run scrolling and zooming simultaneously!
        action: str | None = None
        scroll_amount: int = 0
        zoom_action: str | None = None

        if self.mode == MODE_ZOOM:
            # ZOOM MODE: Head UP = Zoom In, Head DOWN = Zoom Out, Head Neutral = Stop/No action
            if self.step_ready:
                if (timestamp - self.last_zoom_time) >= self.zoom_cooldown_sec:
                    if relative_dy >= self.zoom_deadzone:
                        zoom_action = ZOOM_IN
                        action = ZOOM_IN
                        self.last_zoom_time = timestamp
                        self.step_ready = False
                        logger.info(f"ZOOM_IN step triggered (rel_dy={relative_dy:+.3f}).")
                    elif relative_dy <= -self.zoom_deadzone:
                        zoom_action = ZOOM_OUT
                        action = ZOOM_OUT
                        self.last_zoom_time = timestamp
                        self.step_ready = False
                        logger.info(f"ZOOM_OUT step triggered (rel_dy={relative_dy:+.3f}).")
                    else:
                        if reject_reason == "NONE":
                            reject_reason = "HEAD_NEUTRAL"
                else:
                    if reject_reason == "NONE":
                        reject_reason = "COOLDOWN"
            else:
                # Anti-runaway for zoom: return to neutral deadzone re-arms for the next zoom action
                if abs(relative_dy) <= self.neutral_deadzone:
                    self.step_ready = True
                    if reject_reason == "NONE":
                        reject_reason = "RE_ARMED"
                else:
                    if reject_reason == "NONE":
                        reject_reason = "AWAIT_NEUTRAL"

        elif self.mode == MODE_SCROLL:
            # SCROLL MODE: Head UP = Scroll Up, Head DOWN = Scroll Down, Head Neutral = Stop scrolling
            eff_scroll = max(1, int(round(self.scroll_step * self.scroll_sensitivity)))

            if relative_dy >= self.scroll_deadzone:
                can_scroll = (timestamp - self.last_scroll_time) >= self.scroll_cooldown_sec
                if self.continuous_scroll:
                    if can_scroll:
                        scroll_amount = eff_scroll
                        action = SCROLL_UP
                        self.last_scroll_time = timestamp
                        self.step_ready = True
                        logger.info(f"SCROLL_UP pulse (rel_dy={relative_dy:+.3f}, amount={scroll_amount}).")
                    else:
                        if reject_reason == "NONE":
                            reject_reason = "COOLDOWN"
                else:
                    if self.step_ready:
                        if can_scroll:
                            scroll_amount = eff_scroll
                            action = SCROLL_UP
                            self.last_scroll_time = timestamp
                            self.step_ready = False
                            logger.info(f"SCROLL_UP step triggered (rel_dy={relative_dy:+.3f}, amount={scroll_amount}).")
                        else:
                            if reject_reason == "NONE":
                                reject_reason = "COOLDOWN"
                    else:
                        if reject_reason == "NONE":
                            reject_reason = "AWAIT_NEUTRAL"

            elif relative_dy <= -self.scroll_deadzone:
                can_scroll = (timestamp - self.last_scroll_time) >= self.scroll_cooldown_sec
                if self.continuous_scroll:
                    if can_scroll:
                        scroll_amount = -eff_scroll
                        action = SCROLL_DOWN
                        self.last_scroll_time = timestamp
                        self.step_ready = True
                        logger.info(f"SCROLL_DOWN pulse (rel_dy={relative_dy:+.3f}, amount={scroll_amount}).")
                    else:
                        if reject_reason == "NONE":
                            reject_reason = "COOLDOWN"
                else:
                    if self.step_ready:
                        if can_scroll:
                            scroll_amount = -eff_scroll
                            action = SCROLL_DOWN
                            self.last_scroll_time = timestamp
                            self.step_ready = False
                            logger.info(f"SCROLL_DOWN step triggered (rel_dy={relative_dy:+.3f}, amount={scroll_amount}).")
                        else:
                            if reject_reason == "NONE":
                                reject_reason = "COOLDOWN"
                    else:
                        if reject_reason == "NONE":
                            reject_reason = "AWAIT_NEUTRAL"

            else:
                # Return to neutral deadzone: re-arm step latch and pause scroll pulses
                self.step_ready = True
                if reject_reason == "NONE":
                    reject_reason = "HEAD_NEUTRAL"

        else:  # MODE_NONE
            self.step_ready = True

        self.last_action = action
        self.last_reject_reason = reject_reason
        return self._build_status(action, scroll_amount, zoom_action, relative_dy, reject_reason)

    def _build_status(
        self,
        action: str | None,
        scroll_amount: int,
        zoom_action: str | None,
        relative_dy: float,
        reject_reason: str = "NONE",
    ) -> dict[str, Any]:
        """Construct comprehensive diagnostic status dictionary."""
        both_raised = (self.left_eb_state == STATE_RAISED) and (self.right_eb_state == STATE_RAISED)
        base_w = max(0.35, self.mouth_width_baseline)
        stretch = self.mouth_width_ratio / base_w
        left_elev = (self.left_eb_ratio / max(0.05, self.left_eyebrow_baseline)) - 1.0
        right_elev = (self.right_eb_ratio / max(0.05, self.right_eyebrow_baseline)) - 1.0

        head_dir = "NEUTRAL"
        if relative_dy >= self.scroll_deadzone:
            head_dir = "UP"
        elif relative_dy <= -self.scroll_deadzone:
            head_dir = "DOWN"

        return {
            "mode": self.mode,
            "scroll_mode_active": self.scroll_mode_active,
            "zoom_mode_active": self.zoom_mode_active,
            "gesture_active": (self.mode in (MODE_SCROLL, MODE_ZOOM)),
            "action": action,
            "scroll_amount": scroll_amount,
            "zoom_action": zoom_action,
            "teeth_visible": self.teeth_visible,
            "left_raised": (self.left_eb_state == STATE_RAISED),
            "right_raised": (self.right_eb_state == STATE_RAISED),
            "both_eyebrows_raised": both_raised,
            "mouth_width_ratio": self.mouth_width_ratio,
            "mouth_open_ratio": self.mouth_open_ratio,
            "mouth_width_baseline": self.mouth_width_baseline,
            "mouth_stretch_ratio": stretch,
            "left_eb_ratio": self.left_eb_ratio,
            "right_eb_ratio": self.right_eb_ratio,
            "left_eb_baseline": self.left_eyebrow_baseline,
            "right_eb_baseline": self.right_eyebrow_baseline,
            "left_eb_elevation": left_elev,
            "right_eb_elevation": right_elev,
            "step_ready": self.step_ready,
            "relative_dy": relative_dy,
            "head_direction": head_dir,
            "reject_reason": reject_reason,
            "zoom_step": self.zoom_step,
            "scroll_step": self.scroll_step,
        }
