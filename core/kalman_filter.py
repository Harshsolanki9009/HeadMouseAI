"""1-D Kalman filter for cursor smoothing.

Reduces per-frame cursor jitter while preserving responsiveness. Each cursor
axis gets its own filter instance so the two axes can be tuned independently.

The state vector is ``[position]`` only (no velocity), which keeps the model
lightweight and easy to understand while still performing temporal smoothing.

Process/measurement noise values are deliberately conservative relative to a
typical webcam face-tracking jitter budget, giving strong smoothing with minimal
lag for the start/stop/recalibrate use cases of HeadMouse AI.
"""

from __future__ import annotations

import numpy as np


class KalmanFilter1D:
    """A simple scalar Kalman filter.

    State: ``x = position estimate``.
    Transition model is the identity matrix (no motion model).
    Process noise ``Q`` models unknown tracking variance.
    Measurement noise ``R`` models sensor noise.
    """

    def __init__(
        self,
        process_noise: float = 0.02,
        measurement_noise: float = 0.6,
        initial_uncertainty: float = 1.0,
    ) -> None:
        self.process_noise = float(process_noise)
        self.measurement_noise = float(measurement_noise)
        self.initial_uncertainty = float(initial_uncertainty)
        self.state = 0.0
        self.error_covariance = self.initial_uncertainty

    def predict(self) -> float:
        """Propagate prior estimate forward; returns predicted state."""
        self.error_covariance += self.process_noise
        return self.state

    def update(self, measurement: float) -> float:
        """Incorporate a measurement; returns filtered estimate."""
        k = self.error_covariance / (self.error_covariance + self.measurement_noise)
        self.state += k * (measurement - self.state)
        self.error_covariance *= (1.0 - k)
        return self.state

    @property
    def estimate(self) -> float:
        return float(self.state)

    @property
    def x(self) -> float:
        """Alias for state in standard Kalman notation."""
        return float(self.state)

    @x.setter
    def x(self, value: float) -> None:
        self.state = float(value)

    def reset(self) -> None:
        self.state = 0.0
        self.error_covariance = self.initial_uncertainty


def estimate_jitter(measurements: list[float], window: int = 20) -> float:
    """Heuristic helper: standard deviation of recent measurements."""
    if len(measurements) < 2:
        return 0.0
    recent = list(measurements[-window:])
    arr = np.asarray(recent, dtype=np.float64)
    if arr.size == 0:
        return 0.0
    return float(np.std(arr))
