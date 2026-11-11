"""Virtual cursor simulator for HeadMouse AI Phase 2.

Maps nose-relative displacement to a simulated 2D cursor position. Handles:
  * Dead-zone rejection (no cursor movement below a threshold)
  * Sensitivity scaling (multiplies raw displacement)
  * Per-axis Kalman smoothing (reduces jitter)
  * Boundary clamping (cursor stays inside preview window)

The virtual cursor is drawn on the live preview — it NEVER moves the real
Windows mouse and NEVER invokes OS click APIs.
"""

from __future__ import annotations

import time
from typing import Optional, Tuple

import numpy as np

from core.kalman_filter import KalmanFilter1D


class CursorSimulator:
    """Smoothed, dead-zone-filtered virtual cursor state machine."""

    def __init__(
        self,
        sensitivity: float = 1.0,
        dead_zone: float = 4.0,
        max_velocity: float = 30.0,
        window_width: int = 640,
        window_height: int = 480,
    ) -> None:
        self.sensitivity = float(sensitivity)
        self.dead_zone = float(dead_zone)
        self.max_velocity = float(max_velocity)
        self.window_width = int(window_width)
        self.window_height = int(window_height)

        # Simulation state
        self._active: bool = True

        # Cursor position in window pixel coordinates (origin (0,0) at top-left)
        self.cx: float = self.window_width / 2.0
        self.cy: float = self.window_height / 2.0

        # Simple gentle linear Kalman smoothing (slow, controlled, predictable)
        self._kf_x = KalmanFilter1D(process_noise=0.05, measurement_noise=0.20)
        self._kf_y = KalmanFilter1D(process_noise=0.05, measurement_noise=0.20)

        # Velocity tracking
        self.vx: float = 0.0
        self.vy: float = 0.0
        self.prev_time: float = time.monotonic()

        # Position lock / Click stabilization state
        self._position_locked: bool = False
        self._is_dragging: bool = False
        self._locked_cx: float = self.cx
        self._locked_cy: float = self.cy
        self._locked_norm_x: float = 0.5
        self._locked_norm_y: float = 0.5
        self._lock_reason: str = "NONE"
        self._lock_time: float = 0.0
        self._pre_lock_kf_x: float = 0.0
        self._pre_lock_kf_y: float = 0.0

    # ------------------------------------------------------------------ #
    # Configuration accessors / mutators
    # ------------------------------------------------------------------ #
    @property
    def is_active(self) -> bool:
        """True while the simulation is running."""
        return self._active

    @is_active.setter
    def is_active(self, value: bool) -> None:
        self._active = bool(value)
        if not value:
            # Snap to centre immediately when paused/stopped
            self.cx = self.window_width / 2.0
            self.cy = self.window_height / 2.0
            self.vx = 0.0
            self.vy = 0.0

    @property
    def is_position_locked(self) -> bool:
        """True while cursor position is locked for click stabilization."""
        return self._position_locked and not self._is_dragging

    @property
    def is_dragging(self) -> bool:
        """True while drag mode is active."""
        return self._is_dragging

    def set_dragging(self, is_dragging: bool) -> None:
        """Update active dragging state and ensure position lock is released."""
        self._is_dragging = bool(is_dragging)
        if self._is_dragging and self._position_locked:
            self.unlock_position()

    @property
    def lock_reason(self) -> str:
        """Return the reason cursor position is currently locked."""
        return self._lock_reason

    @property
    def locked_position(self) -> Tuple[float, float]:
        """Return (locked_cx, locked_cy)."""
        return (self._locked_cx, self._locked_cy)

    def lock_position(self, reason: str = "CLICK") -> None:
        """Lock virtual cursor at its current position, pausing nose-based movement."""
        if self._is_dragging:
            return  # Never lock position while dragging
        if not self._position_locked:
            self._position_locked = True
            self._locked_cx = self.cx
            self._locked_cy = self.cy
            self._locked_norm_x = self.normalized_position[0]
            self._locked_norm_y = self.normalized_position[1]
            self._lock_reason = reason
            self._lock_time = time.monotonic()
            self._pre_lock_kf_x = float(self._kf_x.state)
            self._pre_lock_kf_y = float(self._kf_y.state)

    def unlock_position(self) -> None:
        """Unlock virtual cursor and restore smooth tracking without sudden jumps."""
        if self._position_locked:
            self._position_locked = False
            self._lock_reason = "NONE"
            self._kf_x.state = self._pre_lock_kf_x
            self._kf_y.state = self._pre_lock_kf_y
            self.prev_time = time.monotonic()

    @property
    def x_pixels(self) -> float:
        """Current cursor X position in pixels."""
        return self.cx

    @property
    def y_pixels(self) -> float:
        """Current cursor Y position in pixels."""
        return self.cy

    @property
    def screen_position(self) -> Tuple[float, float]:
        """Return (x, y) in window pixel coordinates."""
        return (self.cx, self.cy)

    @property
    def normalized_position(self) -> Tuple[float, float]:
        """Return normalized (x, y) in [0.0, 1.0] range."""
        nx = max(0.0, min(1.0, self.cx / max(1, self.window_width)))
        ny = max(0.0, min(1.0, self.cy / max(1, self.window_height)))
        return (nx, ny)

    # ------------------------------------------------------------------ #
    # Core update — called every frame with nose movement
    # ------------------------------------------------------------------ #
    def update(
        self,
        relative_dx: float,
        relative_dy: float,
    ) -> Tuple[float, float, bool]:
        """Advance the virtual cursor given nose displacement from neutral.

        Args:
            relative_dx: Raw X displacement from neutral baseline.
                         Positive = nose moved right => cursor moves right.
            relative_dy: Raw Y displacement from neutral baseline.
                         Positive = nose moved up => cursor moves up.

        Returns:
            Tuple of (new_cx, new_cy, moved).
        """
        if not self._active:
            return (self.cx, self.cy, False)

        if self._position_locked and not self._is_dragging:
            # Auto-safety unlock timeout: never lock for more than 0.35s
            if (time.monotonic() - self._lock_time) > 0.35:
                self.unlock_position()
            else:
                self.cx = self._locked_cx
                self.cy = self._locked_cy
                self.prev_time = time.monotonic()
                return (self.cx, self.cy, False)

        now = time.monotonic()
        dt = max(now - self.prev_time, 1e-6)
        self.prev_time = now

        # Convert normalized displacement to pixel coordinates if needed
        if abs(relative_dx) <= 1.0 and abs(relative_dy) <= 1.0 and self.window_width > 1:
            raw_px = relative_dx * self.window_width
            raw_py = relative_dy * self.window_height
        else:
            raw_px = relative_dx
            raw_py = relative_dy

        # Dead zone filtering (radial distance)
        dist = float(np.hypot(raw_px, raw_py))
        if dist < self.dead_zone:
            # Inside dead zone: update Kalman filter towards 0 and smoothly return to center
            self._kf_x.predict()
            self._kf_x.update(0.0)
            self._kf_y.predict()
            self._kf_y.update(0.0)
            target_x = self.window_width / 2.0
            target_y = self.window_height / 2.0
            moved = False
        else:
            # Scale by sensitivity
            scaled_dx = raw_px * self.sensitivity
            scaled_dy = raw_py * self.sensitivity

            # Smooth via Kalman filter with measured displacement
            self._kf_x.predict()
            filtered_dx = self._kf_x.update(scaled_dx)
            self._kf_y.predict()
            filtered_dy = self._kf_y.update(scaled_dy)

            # Map from window center
            # X: right is positive
            # Y: up is positive in relative_dy, which maps to decreasing Y in OpenCV pixel space
            target_x = (self.window_width / 2.0) + filtered_dx
            target_y = (self.window_height / 2.0) - filtered_dy
            moved = True

        # Clamp to window boundaries
        target_x = max(0.0, min(float(self.window_width), target_x))
        target_y = max(0.0, min(float(self.window_height), target_y))

        # Max velocity limiting (supports pixels-per-frame <= 100, or pixels-per-sec > 100)
        if self.max_velocity <= 0:
            max_step = float("inf")
        elif self.max_velocity <= 100.0:
            max_step = float(self.max_velocity)
        else:
            max_step = max(30.0, self.max_velocity * dt)
        step_x = target_x - self.cx
        step_y = target_y - self.cy
        step_mag = float(np.hypot(step_x, step_y))

        if step_mag > max_step and step_mag > 0:
            ratio = max_step / step_mag
            self.cx += step_x * ratio
            self.cy += step_y * ratio
        else:
            self.cx = target_x
            self.cy = target_y

        self.vx = step_x / dt
        self.vy = step_y / dt

        return (float(self.cx), float(self.cy), moved)

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def start(self) -> None:
        """Start or resume cursor simulation."""
        self.is_active = True

    def pause(self) -> None:
        """Pause cursor simulation."""
        self.is_active = False

    def stop(self) -> None:
        """Stop cursor simulation and reset to center."""
        self.is_active = False
        self.recalibrate()

    def recalibrate(self) -> None:
        """Reset cursor to window centre and clear Kalman memory and lock state."""
        self.unlock_position()
        self.cx = self.window_width / 2.0
        self.cy = self.window_height / 2.0
        self._kf_x.reset()
        self._kf_y.reset()
        self.vx = 0.0
        self.vy = 0.0

    @staticmethod
    def normalize_direction(dx: float, dy: float) -> Tuple[float, float]:
        """Confirm sign convention for raw relative displacement."""
        return (float(dx), float(dy))
