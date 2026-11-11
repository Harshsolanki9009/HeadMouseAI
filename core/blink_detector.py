"""Independent Eye Blink Detector module for HeadMouse AI.

Detects independent left and right eye blinks from Eye Aspect Ratio (EAR) signals:
- Left eye blink alone  -> LEFT_CLICK signal
- Right eye blink alone -> RIGHT_CLICK signal
- Both eyes blinking    -> Simultaneous suppression (NO_ACTION)
- Face lost             -> Safety suppression (NO_ACTION)

Key Architecture:
- True Schmitt trigger hysteresis:
    - OPEN -> CLOSING/CLOSED only occurs when EAR < threshold_close.
    - CLOSED -> REOPENING/OPEN only occurs when EAR >= threshold_open.
    - Between [threshold_close, threshold_open], the state is latched and never flips.
- Wall-clock timestamp duration tracking (independent of camera FPS).
- Configurable blink duration: 100-400 ms supported, prolonged limit ~650 ms.
- Complete state and timestamp cleanup upon reopening (no stale prolonged state).
- Genuine dual-blink suppression that immediately clears when eyes reopen or when one eye is open.
- Clear event reporting for UI: LEFT_CLICK, RIGHT_CLICK, NO_ACTION.

STRICT SAFETY:
Does not invoke OS-level mouse clicks (no pyautogui, no Win32 APIs).
Operates purely in software signal mode.
"""

from __future__ import annotations

import logging
import time
from typing import Optional, Dict, Any, List

import numpy as np

from config.settings import EyeBlinkSettings, get_settings
from core.eye_tracker import calculate_eye_ear
from utils.logger import logger

# Signal action constants
LEFT_CLICK = "LEFT_CLICK"
RIGHT_CLICK = "RIGHT_CLICK"
NO_ACTION = "NO_ACTION"
DRAG_START = "DRAG_START"
DRAG_STOP = "DRAG_STOP"

# State constants per eye
STATE_OPEN = "OPEN"
STATE_CLOSING = "CLOSING"
STATE_CLOSED = "CLOSED"
STATE_REOPENING = "REOPENING"


class SingleEyeTracker:
    """State tracker and adaptive threshold manager for a single eye."""

    def __init__(
        self,
        name: str,
        initial_baseline: float = 0.28,
        fallback_threshold: float = 0.21,
        sensitivity: float = 0.75,
        hysteresis_ratio: float = 0.10,
        min_blink_duration_sec: float = 0.06,
        max_blink_duration_sec: float = 0.65,
        min_blink_frames: int = 1,
        max_blink_duration_frames: int = 25,
        drag_hold_sec: float = 0.35,
        drag_enabled: bool = True,
    ) -> None:
        self.name = name
        self.state: str = STATE_OPEN
        self.current_ear: float | None = None

        # Baseline and adaptive thresholds
        self.baseline_ear: float = initial_baseline
        self.fallback_threshold: float = fallback_threshold
        self.sensitivity: float = sensitivity
        self.hysteresis_ratio: float = hysteresis_ratio

        # Timestamp and duration tracking
        self.closure_start_time: float | None = None
        self.closure_duration_sec: float = 0.0
        self.min_duration_sec: float = min_blink_duration_sec
        self.max_duration_sec: float = max_blink_duration_sec
        self.drag_hold_sec: float = float(drag_hold_sec)
        self.drag_enabled: bool = bool(drag_enabled)
        self.is_dragging: bool = False

        # State transition counters
        self.closed_frames: int = 0
        self.open_frames: int = 0
        self.is_prolonged: bool = False
        self.is_dual_suppressed: bool = False

        # Thresholds (computed from baseline and sensitivity)
        self.threshold_close: float = fallback_threshold
        self.threshold_open: float = fallback_threshold + 0.03
        self._update_thresholds()

        # Frame-based limits for fallback/tests
        self.min_blink_frames: int = min_blink_frames
        self.max_blink_duration_frames: int = max_blink_duration_frames

        # Diagnostic telemetry
        self.last_reject_reason: str | None = None
        self.last_accept_reason: str | None = None

    def _update_thresholds(self) -> None:
        """Calculate closing and opening thresholds using baseline and sensitivity.

        Higher sensitivity scales close_factor smoothly between 0.69 (firm closure)
        and 0.81 (light, effortless natural closure).
        """
        close_factor = max(0.60, min(0.82, 0.54 + 0.30 * self.sensitivity))
        self.threshold_close = float(np.clip(self.baseline_ear * close_factor, 0.11, 0.26))

        open_factor = min(0.92, close_factor + self.hysteresis_ratio)
        self.threshold_open = float(np.clip(self.baseline_ear * open_factor, self.threshold_close + 0.020, 0.31))

    def update_baseline(self, ear: float) -> None:
        """Gently update open-eye baseline when the eye is stable and fully open."""
        if self.state == STATE_OPEN and ear >= self.threshold_open and 0.20 <= ear <= 0.45:
            self.baseline_ear = float(0.992 * self.baseline_ear + 0.008 * ear)
            self._update_thresholds()

    def set_baseline(self, baseline: float) -> None:
        """Directly set the baseline EAR (e.g. from camera calibration)."""
        if 0.15 <= baseline <= 0.45:
            self.baseline_ear = float(baseline)
            self._update_thresholds()

    def set_sensitivity(self, sensitivity: float) -> None:
        """Set eye wink sensitivity and recalculate Schmitt trigger thresholds."""
        self.sensitivity = float(np.clip(sensitivity, 0.30, 0.98))
        self._update_thresholds()

    def step(self, ear: float | None, timestamp: float | None = None) -> None:
        """Advance the state machine using true Schmitt trigger hysteresis."""
        self.current_ear = ear
        if timestamp is None:
            timestamp = time.monotonic()

        if ear is None:
            return

        # ---------------- True Schmitt Trigger State Machine ---------------- #
        if self.state == STATE_OPEN:
            # In OPEN state: transition to CLOSING/CLOSED ONLY when ear drops below threshold_close
            if ear < self.threshold_close:
                self.state = STATE_CLOSED
                self.closure_start_time = timestamp
                self.closure_duration_sec = 0.0
                self.closed_frames = 1
                self.open_frames = 0
                self.is_prolonged = False
                self.is_dual_suppressed = False
                self.last_reject_reason = None
            else:
                # Remains open: clear any stale closure timestamps
                self.open_frames += 1
                self.closure_start_time = None
                self.closure_duration_sec = 0.0
                self.closed_frames = 0
                self.is_prolonged = False
                self.is_dual_suppressed = False
                self.update_baseline(ear)

        elif self.state in (STATE_CLOSING, STATE_CLOSED):
            if self.closure_start_time is None:
                self.closure_start_time = timestamp
            self.closure_duration_sec = timestamp - self.closure_start_time
            self.closed_frames += 1

            if ear >= self.threshold_open:
                # Eye has risen above the open threshold -> REOPENING!
                self.state = STATE_REOPENING
            else:
                # Eye remains closed: check for prolonged closure
                self.state = STATE_CLOSED
                if not self.is_dragging:
                    if (self.closure_duration_sec > self.max_duration_sec) or (self.closed_frames > self.max_blink_duration_frames):
                        self.is_prolonged = True
                        self.last_reject_reason = "PROLONGED"

        elif self.state == STATE_REOPENING:
            # Reopening is processed by detector, then transitions immediately to OPEN
            self.state = STATE_OPEN
            self.open_frames = 1
            self.closure_start_time = None
            self.closure_duration_sec = 0.0
            self.closed_frames = 0
            self.is_prolonged = False
            self.is_dual_suppressed = False

    def reset(self) -> None:
        """Reset state tracking while preserving baseline."""
        self.state = STATE_OPEN
        self.closed_frames = 0
        self.open_frames = 0
        self.closure_start_time = None
        self.closure_duration_sec = 0.0
        self.is_prolonged = False
        self.is_dragging = False
        self.is_dual_suppressed = False
        self.last_reject_reason = None
        self.last_accept_reason = None


class BlinkDetector:
    """State machine for detecting independent eye blinks and suppressing simultaneous blinks."""

    def __init__(self, settings: EyeBlinkSettings | None = None) -> None:
        if settings is None:
            settings = get_settings().eye_blink

        self.settings = settings
        self.adaptive_threshold = bool(getattr(settings, "adaptive_threshold", True))
        self.sensitivity = float(getattr(settings, "sensitivity", 0.75))
        self.blink_cooldown_frames = int(settings.blink_cooldown_frames)
        self.blink_cooldown_sec = float(getattr(settings, "blink_cooldown_sec", 0.25))
        self.debounce_frames = int(settings.debounce_frames)
        self.independent_blink_detection = bool(settings.independent_blink_detection)
        self.simultaneous_blink_suppression = bool(settings.simultaneous_blink_suppression)
        self.debug_logging = bool(getattr(settings, "debug_logging", False))

        # Per-eye trackers
        left_baseline = float(getattr(settings, "left_baseline_ear", 0.28))
        right_baseline = float(getattr(settings, "right_baseline_ear", 0.28))
        left_sens = getattr(settings, "left_sensitivity", None)
        self.left_sensitivity = float(left_sens if left_sens is not None else self.sensitivity)
        right_sens = getattr(settings, "right_sensitivity", None)
        self.right_sensitivity = float(right_sens if right_sens is not None else self.sensitivity)
        left_thresh = float(settings.left_eye_ear_threshold)
        right_thresh = float(settings.right_eye_ear_threshold)
        min_sec = float(getattr(settings, "min_blink_duration_sec", 0.06))
        max_sec = float(getattr(settings, "max_blink_duration_sec", 0.65))
        min_frames = int(settings.min_blink_frames)
        max_frames = int(settings.max_blink_duration_frames)
        hysteresis = float(getattr(settings, "hysteresis_ratio", 0.10))
        drag_hold = float(getattr(settings, "drag_hold_sec", 0.45))
        drag_en = bool(getattr(settings, "drag_enabled", True))

        self.left_eye = SingleEyeTracker(
            name="left",
            initial_baseline=left_baseline,
            fallback_threshold=left_thresh,
            sensitivity=self.left_sensitivity,
            hysteresis_ratio=hysteresis,
            min_blink_duration_sec=min_sec,
            max_blink_duration_sec=max_sec,
            min_blink_frames=min_frames,
            max_blink_duration_frames=max_frames,
            drag_hold_sec=drag_hold,
            drag_enabled=drag_en,
        )
        self.right_eye = SingleEyeTracker(
            name="right",
            initial_baseline=right_baseline,
            fallback_threshold=right_thresh,
            sensitivity=self.right_sensitivity,
            hysteresis_ratio=hysteresis,
            min_blink_duration_sec=min_sec,
            max_blink_duration_sec=max_sec,
            min_blink_frames=min_frames,
            max_blink_duration_frames=max_frames,
        )

        # Simultaneous suppression tracking
        self.simultaneous_suppression_active: bool = False
        self.suppression_reason: str = "NONE"

        # Cooldown timer (timestamp & frame counter)
        self.cooldown_remaining: int = 0
        self.cooldown_until: float = 0.0

        # Telemetry & Diagnostics
        self.last_event: str | None = None
        self.last_accept_reason: str | None = None
        self.last_reject_reason: str | None = None
        self.total_left_clicks: int = 0
        self.total_right_clicks: int = 0
        self.total_suppressions: int = 0

        # Position Lock / Click Stabilization State
        self.click_stabilization_enabled: bool = bool(getattr(settings, "click_stabilization", True))
        self.stabilization_cooldown_sec: float = float(getattr(settings, "stabilization_cooldown_sec", 0.08))
        self.gesture_active: bool = False
        self.gesture_started: bool = False
        self.gesture_eye: str | None = None
        self.gesture_start_time: float | None = None
        self.stabilization_until: float = 0.0
        self._current_time: float = 0.0

    @property
    def is_stabilizing(self) -> bool:
        """True while click stabilization is active (gesture closure or post-click cooldown)."""
        if not self.click_stabilization_enabled:
            return False
        if self.left_eye.is_dragging:
            return False
        cur_time = self._current_time if self._current_time > 0 else time.monotonic()
        if self.gesture_active and self.gesture_start_time is not None:
            if (cur_time - self.gesture_start_time) > 0.35:
                return False
        return self.gesture_active or (cur_time < self.stabilization_until)

    def set_sensitivity(self, sensitivity: float) -> None:
        """Update sensitivity dynamically (0.30 to 0.98)."""
        self.set_sensitivities(sensitivity, sensitivity)

    def set_sensitivities(self, left_sensitivity: float, right_sensitivity: float | None = None) -> None:
        """Update independent eye sensitivities dynamically."""
        if right_sensitivity is None:
            right_sensitivity = left_sensitivity
        self.left_sensitivity = float(np.clip(left_sensitivity, 0.30, 0.98))
        self.right_sensitivity = float(np.clip(right_sensitivity, 0.30, 0.98))
        self.sensitivity = (self.left_sensitivity + self.right_sensitivity) / 2.0
        self.left_eye.set_sensitivity(self.left_sensitivity)
        self.right_eye.set_sensitivity(self.right_sensitivity)

    def calibrate_baseline(self, left_samples: list[float], right_samples: list[float]) -> None:
        """Calibrate baselines from collected open-eye frames."""
        if len(left_samples) >= 5:
            l_base = float(np.median(left_samples))
            self.left_eye.set_baseline(l_base)
            logger.info(f"Left eye baseline calibrated to {l_base:.3f} (close: {self.left_eye.threshold_close:.3f}, open: {self.left_eye.threshold_open:.3f})")

        if len(right_samples) >= 5:
            r_base = float(np.median(right_samples))
            self.right_eye.set_baseline(r_base)
            logger.info(f"Right eye baseline calibrated to {r_base:.3f} (close: {self.right_eye.threshold_close:.3f}, open: {self.right_eye.threshold_open:.3f})")

    def reset(self) -> None:
        """Reset all tracking counters, cooldowns, and suppression state."""
        self.left_eye.reset()
        self.right_eye.reset()
        self.simultaneous_suppression_active = False
        self.suppression_reason = "NONE"
        self.gesture_active = False
        self.gesture_started = False
        self.gesture_eye = None
        self.gesture_start_time = None
        self.stabilization_until = 0.0
        self.cooldown_remaining = 0
        self.cooldown_until = 0.0
        self.last_event = None
        self.last_accept_reason = None
        self.last_reject_reason = None

    def update(
        self,
        landmarks_data: dict[str, Any] | None,
        eye_state: dict[str, Any] | None = None,
        timestamp: float | None = None,
    ) -> dict[str, Any]:
        """Process a frame's landmarks or eye tracker output and evaluate blink signals.

        Args:
            landmarks_data: Landmarks dictionary from FaceLandmarkerWrapper, or None.
            eye_state: Optional dictionary from EyeTracker.update().
            timestamp: Optional monotonic timestamp (seconds); defaults to time.monotonic().

        Returns:
            Dictionary with tracking details, eye states, durations in ms, and detected click event.
        """
        if timestamp is None:
            timestamp = time.monotonic()
        self._current_time = timestamp
        self.gesture_started = False

        if self.cooldown_remaining > 0:
            self.cooldown_remaining -= 1

        # ---------------- 1. Face Loss Safety Interlock ---------------- #
        if landmarks_data is None:
            self._handle_face_loss()
            return self._build_result(None, None)

        has_face = landmarks_data.get("has_face", False)
        lm_list = landmarks_data.get("landmarks", [])
        if not has_face and len(lm_list) > 0:
            has_face = True

        if not has_face or len(lm_list) == 0:
            self._handle_face_loss()
            return self._build_result(None, None)

        # ---------------- 2. Extract or Compute EAR ---------------- #
        left_ear: float | None = None
        right_ear: float | None = None

        if eye_state is not None:
            left_ear = eye_state.get("left_ear")
            right_ear = eye_state.get("right_ear")
        else:
            left_ear = calculate_eye_ear(lm_list, eye="left")
            right_ear = calculate_eye_ear(lm_list, eye="right")

        if left_ear is None or right_ear is None:
            return self._build_result(left_ear, right_ear)

        # ---------------- 3. Step Single Eye Trackers ---------------- #
        prev_left_state = self.left_eye.state
        prev_right_state = self.right_eye.state

        self.left_eye.step(left_ear, timestamp=timestamp)
        self.right_eye.step(right_ear, timestamp=timestamp)

        if self.debug_logging:
            if self.left_eye.state != prev_left_state:
                logger.debug(f"[LeftEye] {prev_left_state} -> {self.left_eye.state} (EAR={left_ear:.3f}, ThClose={self.left_eye.threshold_close:.3f}, ThOpen={self.left_eye.threshold_open:.3f})")
            if self.right_eye.state != prev_right_state:
                logger.debug(f"[RightEye] {prev_right_state} -> {self.right_eye.state} (EAR={right_ear:.3f}, ThClose={self.right_eye.threshold_close:.3f}, ThOpen={self.right_eye.threshold_open:.3f})")

        # ---------------- 4. Simultaneous Blink Detection & Suppression ---------------- #
        left_is_closed = self.left_eye.state in (STATE_CLOSING, STATE_CLOSED)
        right_is_closed = self.right_eye.state in (STATE_CLOSING, STATE_CLOSED)

        # Check bilateral symmetry vs unilateral wink asymmetry:
        # A true bilateral blink closes both eyes symmetrically and deeply (EAR diff < 0.04).
        # If one eye is deeply closed while the other eye only squints (EAR diff >= 0.04 and other eye >= 0.15),
        # it is an intentional single-eye wink and must NOT be dual suppressed.
        is_bilateral_blink = True
        if left_ear is not None and right_ear is not None:
            ear_diff = abs(left_ear - right_ear)
            if ear_diff >= 0.04 and (left_ear >= 0.15 or right_ear >= 0.15):
                is_bilateral_blink = False

        # ---------------- 3b. Click Gesture Stabilization Tracking ---------------- #
        if self.click_stabilization_enabled:
            # Auto-expire gesture if duration exceeds natural wink window (0.35s)
            if self.gesture_active and self.gesture_start_time is not None:
                if (timestamp - self.gesture_start_time) > 0.35:
                    self.gesture_active = False
                    self.gesture_started = False
                    self.gesture_eye = None
                    self.gesture_start_time = None

            if left_is_closed and right_is_closed and is_bilateral_blink:
                # Dual closure cancels single-eye click gesture
                self.gesture_active = False
                self.gesture_started = False
                self.gesture_eye = None
                self.gesture_start_time = None
            elif self.left_eye.is_prolonged or self.right_eye.is_prolonged:
                # Prolonged closure cancels click gesture
                self.gesture_active = False
                self.gesture_started = False
                self.gesture_eye = None
                self.gesture_start_time = None
            elif not self.gesture_active and not self.left_eye.is_dragging:
                # Detect single-eye closure onset (transition from open to closed, accounting for squint)
                left_winking = (prev_left_state == STATE_OPEN) and left_is_closed and (self.right_eye.state == STATE_OPEN or (not is_bilateral_blink and left_ear is not None and right_ear is not None and left_ear < right_ear))
                right_winking = (prev_right_state == STATE_OPEN) and right_is_closed and (self.left_eye.state == STATE_OPEN or (not is_bilateral_blink and left_ear is not None and right_ear is not None and right_ear < left_ear))
                if left_winking:
                    self.gesture_active = True
                    self.gesture_started = True
                    self.gesture_eye = "left"
                    self.gesture_start_time = timestamp
                    logger.debug(f"Click gesture started: LEFT eye closed at t={timestamp:.3f}")
                elif right_winking:
                    self.gesture_active = True
                    self.gesture_started = True
                    self.gesture_eye = "right"
                    self.gesture_start_time = timestamp
                    logger.debug(f"Click gesture started: RIGHT eye closed at t={timestamp:.3f}")

        # Active suppression ONLY when BOTH eyes are genuinely closed simultaneously with synchronous onset and symmetry
        is_synchronous_onset = True
        if self.left_eye.closure_start_time is not None and self.right_eye.closure_start_time is not None:
            time_diff = abs(self.left_eye.closure_start_time - self.right_eye.closure_start_time)
            if time_diff > 0.12:
                is_synchronous_onset = False

        if (
            self.simultaneous_blink_suppression
            and left_is_closed
            and right_is_closed
            and not self.left_eye.is_dragging
            and is_synchronous_onset
            and is_bilateral_blink
        ):
            self.simultaneous_suppression_active = True
            self.suppression_reason = "BOTH_EYES_CLOSED"
            self.left_eye.is_dual_suppressed = True
            self.right_eye.is_dual_suppressed = True
            self.last_reject_reason = "DUAL_SUPPRESSED"
            self.total_suppressions += 1
            if self.debug_logging:
                logger.debug("Dual blink detected: clicks suppressed.")

        # Once both eyes are open, immediately clear suppression and dual suppression flags
        if self.left_eye.state == STATE_OPEN and self.right_eye.state == STATE_OPEN:
            self.simultaneous_suppression_active = False
            self.suppression_reason = "NONE"
            self.left_eye.is_dual_suppressed = False
            self.right_eye.is_dual_suppressed = False
            if timestamp >= self.stabilization_until:
                self.gesture_active = False
                self.gesture_started = False
                self.gesture_eye = None
                self.gesture_start_time = None

        # One eye closed and the other open: CANNOT be a dual blink! Clear suppression immediately on both
        if left_is_closed != right_is_closed:
            self.simultaneous_suppression_active = False
            self.suppression_reason = "NONE"
            self.left_eye.is_dual_suppressed = False
            self.right_eye.is_dual_suppressed = False

        # ---------------- 4b. Evaluate Left Eye Drag Hold ---------------- #
        detected_event: str | None = None
        is_simultaneous_reopen: bool = False

        if (
            self.left_eye.drag_enabled
            and not self.left_eye.is_dragging
            and self.left_eye.state in (STATE_CLOSING, STATE_CLOSED)
            and not self.left_eye.is_dual_suppressed
            and not self.simultaneous_suppression_active
            and (self.right_eye.state == STATE_OPEN or (right_ear is not None and right_ear >= 0.15))
        ):
            if self.left_eye.closure_duration_sec >= (self.left_eye.drag_hold_sec - 1e-4):
                self.left_eye.is_dragging = True
                self.gesture_active = False
                self.gesture_started = False
                self.gesture_eye = None
                self.gesture_start_time = None
                detected_event = DRAG_START
                dur_ms = self.left_eye.closure_duration_sec * 1000.0
                self.left_eye.last_accept_reason = f"DRAG_START ({dur_ms:.0f}ms)"
                self.last_accept_reason = f"DRAG_START ({dur_ms:.0f}ms)"
                self.last_reject_reason = None
                logger.info(f"DRAG_START signal emitted ({dur_ms:.0f}ms).")

        # ---------------- 5. Evaluate Left Eye Click or Drag Stop on Reopening ---------------- #
        if prev_left_state in (STATE_CLOSED, STATE_CLOSING) and self.left_eye.state == STATE_REOPENING:
            was_dragging = self.left_eye.is_dragging
            self.left_eye.is_dragging = False

            if was_dragging:
                detected_event = DRAG_STOP
                self.left_eye.last_accept_reason = "DRAG_STOP"
                self.last_accept_reason = "DRAG_STOP"
                self.last_reject_reason = None
                logger.info("DRAG_STOP signal emitted.")
            else:
                duration_sec = self.left_eye.closure_duration_sec
                frames = self.left_eye.closed_frames

                # Duration evaluation
                if duration_sec > 0:
                    is_too_long = (duration_sec > self.left_eye.max_duration_sec) or self.left_eye.is_prolonged
                    is_too_short = (duration_sec < self.left_eye.min_duration_sec) and (frames < self.left_eye.min_blink_frames)
                else:
                    is_too_long = (frames > self.left_eye.max_blink_duration_frames) or self.left_eye.is_prolonged
                    is_too_short = (frames < self.left_eye.min_blink_frames)

                not_dual_suppressed = not self.left_eye.is_dual_suppressed
                opposite_eye_open = (
                    (self.right_eye.state == STATE_OPEN)
                    or (right_ear is not None and right_ear >= (self.right_eye.threshold_close - 0.035))
                    or (right_ear is not None and right_ear >= 0.15)
                )
                no_cooldown = (timestamp >= self.cooldown_until) and (self.cooldown_remaining == 0)

                if is_too_long:
                    self.left_eye.last_reject_reason = "PROLONGED"
                    self.last_reject_reason = "LEFT_PROLONGED"
                elif is_too_short:
                    self.left_eye.last_reject_reason = "TOO_SHORT"
                    self.last_reject_reason = "LEFT_TOO_SHORT"
                elif not not_dual_suppressed or not opposite_eye_open:
                    self.left_eye.last_reject_reason = "DUAL_SUPPRESSION"
                    self.last_reject_reason = "DUAL_SUPPRESSED"
                    is_simultaneous_reopen = True
                elif not no_cooldown:
                    self.left_eye.last_reject_reason = "COOLDOWN"
                    self.last_reject_reason = "COOLDOWN_ACTIVE"
                else:
                    # Valid intentional left click!
                    detected_event = LEFT_CLICK
                    self.total_left_clicks += 1
                    self.cooldown_until = timestamp + self.blink_cooldown_sec
                    self.cooldown_remaining = self.blink_cooldown_frames
                    if self.click_stabilization_enabled:
                        self.stabilization_until = timestamp + self.stabilization_cooldown_sec
                    dur_ms = duration_sec * 1000.0 if duration_sec > 0 else (frames * 35.0)
                    self.left_eye.last_accept_reason = f"ACCEPTED ({dur_ms:.0f}ms, {frames}f)"
                    self.last_accept_reason = f"LEFT_CLICK ({dur_ms:.0f}ms)"
                    self.last_reject_reason = None
                    logger.info(f"LEFT_CLICK signal emitted ({dur_ms:.0f}ms, {frames} frames).")

            # Always clean up left closure state immediately upon reopening
            self.gesture_active = False
            self.gesture_started = False
            self.gesture_eye = None
            self.gesture_start_time = None
            self.left_eye.closed_frames = 0
            self.left_eye.closure_start_time = None
            self.left_eye.closure_duration_sec = 0.0
            self.left_eye.is_prolonged = False
            self.left_eye.is_dual_suppressed = False
            self.left_eye.state = STATE_OPEN
            self.left_eye.open_frames = 1

        # ---------------- 6. Evaluate Right Eye Click on Reopening ---------------- #
        if prev_right_state in (STATE_CLOSED, STATE_CLOSING) and self.right_eye.state == STATE_REOPENING:
            if self.left_eye.is_dragging:
                # Right eye blink during active drag must NOT emit right click and NOT interrupt drag
                self.right_eye.reset()
            else:
                duration_sec = self.right_eye.closure_duration_sec
                frames = self.right_eye.closed_frames

                if duration_sec > 0:
                    is_too_long = (duration_sec > self.right_eye.max_duration_sec) or self.right_eye.is_prolonged
                    is_too_short = (duration_sec < self.right_eye.min_duration_sec) and (frames < self.right_eye.min_blink_frames)
                else:
                    is_too_long = (frames > self.right_eye.max_blink_duration_frames) or self.right_eye.is_prolonged
                    is_too_short = (frames < self.right_eye.min_blink_frames)

                not_dual_suppressed = not self.right_eye.is_dual_suppressed
                opposite_eye_open = (
                    (self.left_eye.state == STATE_OPEN)
                    or (left_ear is not None and left_ear >= (self.left_eye.threshold_close - 0.035))
                    or (left_ear is not None and left_ear >= 0.15)
                )
                no_cooldown = (timestamp >= self.cooldown_until) and (self.cooldown_remaining == 0)

                if is_too_long:
                    self.right_eye.last_reject_reason = "PROLONGED"
                    self.last_reject_reason = "RIGHT_PROLONGED"
                elif is_too_short:
                    self.right_eye.last_reject_reason = "TOO_SHORT"
                    self.last_reject_reason = "RIGHT_TOO_SHORT"
                elif not not_dual_suppressed or not opposite_eye_open:
                    self.right_eye.last_reject_reason = "DUAL_SUPPRESSION"
                    self.last_reject_reason = "DUAL_SUPPRESSED"
                    is_simultaneous_reopen = True
                elif not no_cooldown:
                    self.right_eye.last_reject_reason = "COOLDOWN"
                    self.last_reject_reason = "COOLDOWN_ACTIVE"
                else:
                    if detected_event == DRAG_STOP:
                        pass
                    elif detected_event is not None:
                        # Both emitted on same frame -> cancel both and trigger dual suppression
                        detected_event = None
                        is_simultaneous_reopen = True
                        self.last_reject_reason = "DUAL_SUPPRESSED"
                    else:
                        detected_event = RIGHT_CLICK
                        self.total_right_clicks += 1
                        self.cooldown_until = timestamp + self.blink_cooldown_sec
                        self.cooldown_remaining = self.blink_cooldown_frames
                        if self.click_stabilization_enabled:
                            self.stabilization_until = timestamp + self.stabilization_cooldown_sec
                        dur_ms = duration_sec * 1000.0 if duration_sec > 0 else (frames * 35.0)
                        self.right_eye.last_accept_reason = f"ACCEPTED ({dur_ms:.0f}ms, {frames}f)"
                        self.last_accept_reason = f"RIGHT_CLICK ({dur_ms:.0f}ms)"
                        self.last_reject_reason = None
                        logger.info(f"RIGHT_CLICK signal emitted ({dur_ms:.0f}ms, {frames} frames).")

            # Always clean up right closure state immediately upon reopening
            self.gesture_active = False
            self.gesture_started = False
            self.gesture_eye = None
            self.gesture_start_time = None
            self.right_eye.closed_frames = 0
            self.right_eye.closure_start_time = None
            self.right_eye.closure_duration_sec = 0.0
            self.right_eye.is_prolonged = False
            self.right_eye.is_dual_suppressed = False
            self.right_eye.state = STATE_OPEN
            self.right_eye.open_frames = 1

        if is_simultaneous_reopen:
            if detected_event is None:
                detected_event = NO_ACTION
            self.simultaneous_suppression_active = False
            self.suppression_reason = "NONE"
            self.left_eye.is_dual_suppressed = False
            self.right_eye.is_dual_suppressed = False

        self.last_event = detected_event
        return self._build_result(left_ear, right_ear, event=detected_event)

    def _handle_face_loss(self) -> None:
        """Safety action when face detection is lost."""
        self.left_eye.reset()
        self.right_eye.reset()
        self.left_eye.is_dragging = False
        self.simultaneous_suppression_active = False
        self.suppression_reason = "NONE"
        self.gesture_active = False
        self.gesture_started = False
        self.gesture_eye = None
        self.gesture_start_time = None
        self.stabilization_until = 0.0
        self.last_event = None
        self.last_reject_reason = "FACE_LOST"

    def _build_result(
        self,
        left_ear: float | None,
        right_ear: float | None,
        event: str | None = None,
    ) -> dict[str, Any]:
        """Construct the rich diagnostic output dictionary."""
        left_simple = "CLOSED" if self.left_eye.state in (STATE_CLOSING, STATE_CLOSED) else "OPEN"
        right_simple = "CLOSED" if self.right_eye.state in (STATE_CLOSING, STATE_CLOSED) else "OPEN"

        # Determine live status string for HUD
        active_status = None
        if self.left_eye.is_dragging:
            l_ms = self.left_eye.closure_duration_sec * 1000.0
            active_status = f"DRAG_ACTIVE ({l_ms:.0f}ms)"
        elif self.left_eye.state in (STATE_CLOSING, STATE_CLOSED):
            l_ms = self.left_eye.closure_duration_sec * 1000.0
            active_status = f"L_PROLONGED ({l_ms:.0f}ms)" if self.left_eye.is_prolonged else f"L_BLINKING ({l_ms:.0f}ms)"
        elif self.right_eye.state in (STATE_CLOSING, STATE_CLOSED):
            r_ms = self.right_eye.closure_duration_sec * 1000.0
            active_status = f"R_PROLONGED ({r_ms:.0f}ms)" if self.right_eye.is_prolonged else f"R_BLINKING ({r_ms:.0f}ms)"

        return {
            "event": event,
            "is_dragging": self.left_eye.is_dragging,
            "gesture_active": self.gesture_active,
            "gesture_started": self.gesture_started,
            "gesture_eye": self.gesture_eye,
            "is_stabilizing": self.is_stabilizing,
            "stabilization_active": self.is_stabilizing,
            "left_state": left_simple,
            "right_state": right_simple,
            "left_state_detailed": self.left_eye.state,
            "right_state_detailed": self.right_eye.state,
            "left_ear": left_ear,
            "right_ear": right_ear,
            "left_baseline": self.left_eye.baseline_ear,
            "right_baseline": self.right_eye.baseline_ear,
            "left_threshold_close": self.left_eye.threshold_close,
            "right_threshold_close": self.right_eye.threshold_close,
            "left_threshold_open": self.left_eye.threshold_open,
            "right_threshold_open": self.right_eye.threshold_open,
            "suppression_active": self.simultaneous_suppression_active,
            "suppression_reason": self.suppression_reason,
            "cooldown_remaining": self.cooldown_remaining,
            "left_duration": self.left_eye.closed_frames,
            "right_duration": self.right_eye.closed_frames,
            "left_duration_ms": self.left_eye.closure_duration_sec * 1000.0 if self.left_eye.state in (STATE_CLOSING, STATE_CLOSED) else 0.0,
            "right_duration_ms": self.right_eye.closure_duration_sec * 1000.0 if self.right_eye.state in (STATE_CLOSING, STATE_CLOSED) else 0.0,
            "active_status": active_status,
            "last_accept_reason": self.last_accept_reason,
            "last_reject_reason": self.last_reject_reason,
            "sensitivity": self.sensitivity,
        }
