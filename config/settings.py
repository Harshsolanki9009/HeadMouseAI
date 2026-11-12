"""Project-wide settings for HeadMouse AI.

Contains values that can be adjusted by the user via the GUI and that
are used by multiple modules.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields
from typing import Any, List, Tuple
from pathlib import Path

import toml

SETTINGS_FILE = Path(__file__).resolve().parent.parent / "config.toml"


def _instantiate_dataclass(cls_type: Any, d: dict) -> Any:
    """Instantiate a dataclass filtering out any unsupported or unexpected keys."""
    if not isinstance(d, dict):
        return cls_type()
    valid_names = {f.name for f in fields(cls_type)}
    filtered = {k: v for k, v in d.items() if k in valid_names}
    return cls_type(**filtered)


def _is_valid_num(val: Any) -> bool:
    """Check that value is a finite number."""
    if not isinstance(val, (int, float)):
        return False
    return not (math.isnan(val) or math.isinf(val))


@dataclass
class CameraSettings:
    """Settings related to camera capture."""

    camera_index: int = 0
    resolution_width: int = 1280
    resolution_height: int = 720
    fps: int = 30
    auto_exposure: bool = True
    brightness: int = 100
    exposure: int = -1  # Auto exposure when -1
    focus: int = -1    # Auto focus when -1
    api_preference: str = "opencv"  # "opencv", "mediapipe"


@dataclass
class TrackingSettings:
    """Settings for face and nose tracking."""

    face_detection_confidence: float = 0.5
    max_num_faces: int = 1
    smooth_landmarks: bool = True
    landmark_visualization: bool = True
    show_nose_tip_only: bool = False
    # MediaPipe Face Landmark model options
    # Use the preloaded default model: https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float32/1/face_landmarker.task


@dataclass
class NoseTrackingSettings:
    """Settings for converting nose movement to cursor control."""

    # Calibration
    calibration_frames: int = 30
    nose_neutral_threshold: float = 0.02  # Relative movement threshold
    neutral_x: float = 0.5  # Calibrated neutral center (0.0 to 1.0)
    neutral_y: float = 0.5  # Calibrated neutral center (0.0 to 1.0)
    # Sensitivity mapping
    sensitivity: float = 1.0  # Controlled, predictable multiplier for nose-to-cursor mapping
    dead_zone: float = 4.0  # Minimum nose movement before cursor moves (pixels)
    # Smoothing
    smoothing_strength: float = 0.35  # Simple Exponential Moving Average gain
    max_velocity: float = 30.0  # Maximum cursor movement per frame (pixels)
    # Display
    show_nose_coordinates: bool = True
    show_nose_prediction: bool = False


@dataclass
class EyeBlinkSettings:
    """Settings for detecting blinks with eyes."""

    # EAR (Eye Aspect Ratio) calculation
    # Formula: (|p1-p4| + |p2-p5|) / (2 * |p3-p6|)
    # Open eye ≈ 0.2-0.3, Closed eye ≈ 0.0-0.1
    left_eye_ear_threshold: float = 0.21
    right_eye_ear_threshold: float = 0.21
    # Adaptive threshold configuration
    adaptive_threshold: bool = True
    sensitivity: float = 0.75  # Default/global sensitivity factor (0.50 to 0.85)
    left_sensitivity: float | None = None   # Independent left wink sensitivity (defaults to sensitivity)
    right_sensitivity: float | None = None  # Independent right wink sensitivity (defaults to sensitivity)
    baseline_window: int = 40  # Frames to compute/adapt baseline
    left_baseline_ear: float = 0.28
    right_baseline_ear: float = 0.28
    hysteresis_ratio: float = 0.08  # Difference between close and open thresholds
    # Blink duration limits (timestamp and frame based)
    min_blink_duration_sec: float = 0.04  # Supports short natural blinks (40-100ms)
    max_blink_duration_sec: float = 0.65  # Prolonged closure limit (600-700ms configurable)
    blink_cooldown_sec: float = 0.25      # Cooldown duration after click
    min_blink_frames: int = 1             # Short natural blinks (1-2 frames at 15-30 FPS)
    max_blink_duration_frames: int = 25   # Maximum frames before considered prolonged closure
    blink_cooldown_frames: int = 6        # Cooldown frames after click before next blink
    # Debouncing
    debounce_frames: int = 2
    # Detection mode
    independent_blink_detection: bool = True
    simultaneous_blink_suppression: bool = True
    debug_logging: bool = False
    # Hands-Free Drag settings
    drag_hold_sec: float = 0.38  # Closure duration to activate drag (380ms)
    drag_enabled: bool = False
    # Click Position Stabilization
    click_stabilization: bool = True  # Pause cursor movement during intentional click gestures
    stabilization_cooldown_sec: float = 0.08  # Brief post-click settling window (80ms)

    def __post_init__(self) -> None:
        if self.left_sensitivity is None:
            self.left_sensitivity = self.sensitivity
        if self.right_sensitivity is None:
            self.right_sensitivity = self.sensitivity


@dataclass
class ScrollSettings:
    """Settings for eyebrow-gesture activated head scrolling."""

    enabled: bool = True
    eyebrow_raise_threshold: float = 0.18  # 18% above resting baseline
    eyebrow_hysteresis: float = 0.08      # Falls below 10% to deactivate
    activation_delay_sec: float = 0.30     # Require eyebrows held raised for 300ms
    scroll_deadzone: float = 0.015         # Vertical head displacement deadzone
    min_scroll_speed: int = 1              # Minimum scroll clicks per pulse
    max_scroll_speed: int = 8              # Maximum scroll clicks per pulse
    scroll_gain: float = 50.0              # Speed scaling factor
    scroll_interval_sec: float = 0.05      # Interval between scroll pulses
    scroll_sensitivity: float = 1.0        # Multiplier / sensitivity for scroll response
    left_eyebrow_baseline: float = 0.16
    right_eyebrow_baseline: float = 0.16


@dataclass
class ZoomSettings:
    """Settings for gesture-activated head zoom and scroll mode (teeth visible, eyebrows for zoom)."""

    enabled: bool = True
    mouth_width_threshold: float = 0.60   # Absolute fallback ratio of mouth width to IOD (dist 61->291)
    mouth_open_min: float = 0.018         # Minimum vertical inner lip separation (dist 13->14) to IOD
    mouth_open_max: float = 0.22          # Maximum vertical inner lip separation (dist 13->14) to IOD
    eyebrow_raise_threshold: float = 0.14 # Eyebrow elevation (14% above resting baseline)
    eyebrow_hysteresis: float = 0.07      # Deactivation drop (baseline * 1.07)
    zoom_deadzone: float = 0.022          # Vertical head displacement threshold to trigger zoom step
    scroll_deadzone: float = 0.020        # Vertical head displacement threshold to trigger scroll step
    neutral_deadzone: float = 0.012       # Return-to-neutral deadzone to re-arm zoom/scroll step
    zoom_step: int = 1                    # Zoom hotkey step multiplier
    scroll_step: int = 2                  # Number of scroll clicks per step
    zoom_cooldown_sec: float = 0.25       # Minimum cooldown between zoom steps
    scroll_cooldown_sec: float = 0.25     # Minimum cooldown between scroll steps
    scroll_sensitivity: float = 1.0       # Adjustable scroll sensitivity
    zoom_sensitivity: float = 1.0         # Adjustable zoom sensitivity
    smile_sensitivity: float = 1.0        # Smile / teeth gesture activation sensitivity factor
    continuous_scroll: bool = True        # Continuous scrolling while head is held tilted
    activation_grace_frames: int = 1      # Consecutive frames candidate smile must hold to activate
    deactivation_grace_sec: float = 0.08  # Baseline grace period before deactivating on mouth closure
    face_loss_grace_sec: float = 0.08     # Grace period before resetting on face loss
    left_eyebrow_baseline: float = 0.16
    right_eyebrow_baseline: float = 0.16
    mouth_width_baseline: float = 0.52


@dataclass
class MouseControlSettings:
    """Settings for actual mouse control via PyAutoGUI."""

    # Control
    cursor_speed: int = 3  # PyAutoGUI speed (1-10)
    # Left click (from left eye)
    left_click_delay: float = 0.05  # Delay after click
    left_click_button: str = "left"
    # Right click (from right eye)
    right_click_delay: float = 0.05
    right_click_button: str = "right"
    # Phase 4 Safety Settings
    enabled_by_default: bool = False
    failsafe: bool = True
    click_cooldown_sec: float = 0.25


@dataclass
class GuiSettings:
    """GUI related settings."""

    window_width: int = 1280
    window_height: int = 720
    camera_view_width: int = 640
    camera_view_height: int = 480
    fps_display: bool = True
    performance_metrics: bool = True
    auto_start: bool = False
    always_on_top: bool = False
    performance_mode: str = "balanced"  # "performance", "quality", "balanced"
    ui_refresh_hz: int = 20             # 20 or 30 Hz
    first_launch_done: bool = False     # First-launch onboarding flag


@dataclass
class AppSettings:
    """Top-level settings container."""

    camera: CameraSettings = field(default_factory=CameraSettings)
    tracking: TrackingSettings = field(default_factory=TrackingSettings)
    nose_tracking: NoseTrackingSettings = field(default_factory=NoseTrackingSettings)
    eye_blink: EyeBlinkSettings = field(default_factory=lambda: EyeBlinkSettings(drag_enabled=True))
    mouse: MouseControlSettings = field(default_factory=MouseControlSettings)
    gui: GuiSettings = field(default_factory=GuiSettings)
    scroll: ScrollSettings = field(default_factory=ScrollSettings)
    zoom: ZoomSettings = field(default_factory=ZoomSettings)

    @classmethod
    def load(cls, config_path: Path | str | None = None) -> AppSettings:
        """Load settings from config.toml (or specified path) if it exists, otherwise return defaults."""
        target_file = Path(config_path) if config_path else SETTINGS_FILE
        if target_file.exists():
            try:
                data = toml.load(str(target_file))
                eb_data = data.get("eye_blink", {})
                if "drag_enabled" not in eb_data:
                    eb_data["drag_enabled"] = True
                # Map keys to create nested objects safely filtering unexpected fields
                inst = AppSettings(
                    camera=_instantiate_dataclass(CameraSettings, data.get("camera", {})),
                    tracking=_instantiate_dataclass(TrackingSettings, data.get("tracking", {})),
                    nose_tracking=_instantiate_dataclass(NoseTrackingSettings, data.get("nose_tracking", {})),
                    eye_blink=_instantiate_dataclass(EyeBlinkSettings, eb_data),
                    mouse=_instantiate_dataclass(MouseControlSettings, data.get("mouse", {})),
                    gui=_instantiate_dataclass(GuiSettings, data.get("gui", {})),
                    scroll=_instantiate_dataclass(ScrollSettings, data.get("scroll", {})),
                    zoom=_instantiate_dataclass(ZoomSettings, data.get("zoom", {})),
                )
                val_errors = inst.validate()
                if not val_errors:
                    return inst
                # If there are validation errors in the loaded file, log them and fallback to defaults
            except Exception:
                # If anything goes wrong loading, fall back to defaults
                pass
        instance = cls()
        instance.save()
        return instance

    def save(self, config_path: Path | str | None = None) -> None:
        """Save settings to config.toml (or target path) as TOML."""
        target_file = Path(config_path) if config_path else SETTINGS_FILE
        data = {
            "camera": self.camera.__dict__,
            "tracking": self.tracking.__dict__,
            "nose_tracking": self.nose_tracking.__dict__,
            "eye_blink": self.eye_blink.__dict__,
            "mouse": self.mouse.__dict__,
            "gui": self.gui.__dict__,
            "scroll": self.scroll.__dict__,
            "zoom": self.zoom.__dict__,
        }
        with open(target_file, "w", encoding="utf-8") as f:
            toml.dump(data, f)

    def validate(self) -> list[str]:
        """Validate all settings and return a list of error descriptions (empty if fully valid)."""
        errors: list[str] = []

        # Camera
        if not _is_valid_num(self.camera.camera_index) or self.camera.camera_index < 0:
            errors.append(f"Invalid camera_index: {self.camera.camera_index}")

        # Nose tracking
        nt = self.nose_tracking
        if not _is_valid_num(nt.sensitivity) or not (0.1 <= nt.sensitivity <= 20.0):
            errors.append(f"Nose sensitivity out of range [0.1, 20.0]: {nt.sensitivity}")
        if not _is_valid_num(nt.dead_zone) or not (0.0 <= nt.dead_zone <= 100.0):
            errors.append(f"Dead zone out of range [0.0, 100.0]: {nt.dead_zone}")
        if not _is_valid_num(nt.smoothing_strength) or not (0.01 <= nt.smoothing_strength <= 1.0):
            errors.append(f"Smoothing strength out of range [0.01, 1.0]: {nt.smoothing_strength}")
        if not _is_valid_num(nt.neutral_x) or not (0.0 <= nt.neutral_x <= 1.0):
            errors.append(f"Nose neutral_x out of range [0.0, 1.0]: {nt.neutral_x}")
        if not _is_valid_num(nt.neutral_y) or not (0.0 <= nt.neutral_y <= 1.0):
            errors.append(f"Nose neutral_y out of range [0.0, 1.0]: {nt.neutral_y}")

        # Eye blink
        eb = self.eye_blink
        if not _is_valid_num(eb.left_eye_ear_threshold) or not (0.05 <= eb.left_eye_ear_threshold <= 0.45):
            errors.append(f"Left eye EAR threshold out of range [0.05, 0.45]: {eb.left_eye_ear_threshold}")
        if not _is_valid_num(eb.right_eye_ear_threshold) or not (0.05 <= eb.right_eye_ear_threshold <= 0.45):
            errors.append(f"Right eye EAR threshold out of range [0.05, 0.45]: {eb.right_eye_ear_threshold}")
        if not _is_valid_num(eb.sensitivity) or not (0.30 <= eb.sensitivity <= 1.0):
            errors.append(f"Blink sensitivity out of range [0.30, 1.0]: {eb.sensitivity}")
        if not _is_valid_num(eb.left_sensitivity) or not (0.30 <= eb.left_sensitivity <= 1.0):
            errors.append(f"Left wink sensitivity out of range [0.30, 1.0]: {eb.left_sensitivity}")
        if not _is_valid_num(eb.right_sensitivity) or not (0.30 <= eb.right_sensitivity <= 1.0):
            errors.append(f"Right wink sensitivity out of range [0.30, 1.0]: {eb.right_sensitivity}")
        if not _is_valid_num(eb.left_baseline_ear) or not (0.15 <= eb.left_baseline_ear <= 0.50):
            errors.append(f"Left baseline EAR out of range [0.15, 0.50]: {eb.left_baseline_ear}")
        if not _is_valid_num(eb.right_baseline_ear) or not (0.15 <= eb.right_baseline_ear <= 0.50):
            errors.append(f"Right baseline EAR out of range [0.15, 0.50]: {eb.right_baseline_ear}")
        if not _is_valid_num(eb.drag_hold_sec) or not (0.15 <= eb.drag_hold_sec <= 2.0):
            errors.append(f"Drag hold duration out of range [0.15, 2.0]: {eb.drag_hold_sec}")

        # Mouse
        m = self.mouse
        if not _is_valid_num(m.cursor_speed) or not (1 <= m.cursor_speed <= 10):
            errors.append(f"Cursor speed out of range [1, 10]: {m.cursor_speed}")

        # Zoom & Scroll
        z = self.zoom
        if not _is_valid_num(z.mouth_width_baseline) or not (0.25 <= z.mouth_width_baseline <= 0.90):
            errors.append(f"Mouth width baseline out of range [0.25, 0.90]: {z.mouth_width_baseline}")
        if not _is_valid_num(z.left_eyebrow_baseline) or not (0.05 <= z.left_eyebrow_baseline <= 0.40):
            errors.append(f"Left eyebrow baseline out of range [0.05, 0.40]: {z.left_eyebrow_baseline}")
        if not _is_valid_num(z.right_eyebrow_baseline) or not (0.05 <= z.right_eyebrow_baseline <= 0.40):
            errors.append(f"Right eyebrow baseline out of range [0.05, 0.40]: {z.right_eyebrow_baseline}")
        if not _is_valid_num(z.scroll_step) or not (1 <= z.scroll_step <= 20):
            errors.append(f"Scroll step out of range [1, 20]: {z.scroll_step}")
        if not _is_valid_num(z.zoom_step) or not (1 <= z.zoom_step <= 10):
            errors.append(f"Zoom step out of range [1, 10]: {z.zoom_step}")

        return errors

    def reset_to_defaults(self) -> None:
        """Reset all configuration settings to standard default factory values."""
        self.camera = CameraSettings()
        self.tracking = TrackingSettings()
        self.nose_tracking = NoseTrackingSettings()
        self.eye_blink = EyeBlinkSettings(drag_enabled=True)
        self.mouse = MouseControlSettings()
        self.gui = GuiSettings()
        self.scroll = ScrollSettings()
        self.zoom = ZoomSettings()
        self.save()

    def save_profile(self, target_path: Path | str) -> bool:
        """Save current configuration to a custom user profile TOML file."""
        try:
            self.save(config_path=Path(target_path))
            return True
        except Exception:
            return False

    @classmethod
    def load_profile(cls, source_path: Path | str) -> AppSettings:
        """Load configuration from a custom user profile TOML file."""
        return cls.load(config_path=Path(source_path))

    def __post_init__(self) -> None:
        """Initialize default settings when the object is created."""
        # If no settings file, initialize with defaults
        if not SETTINGS_FILE.exists():
            self.save()


def validate_calibration_data(data: dict) -> tuple[bool, str]:
    """Validate collected calibration baselines before allowing them to be applied or persisted.

    Returns:
        (is_valid: bool, error_message: str)
    """
    if not isinstance(data, dict):
        return False, "Calibration payload must be a dictionary."

    # Check nose
    nx = data.get("neutral_x")
    ny = data.get("neutral_y")
    if nx is not None and ny is not None:
        if not (_is_valid_num(nx) and 0.15 <= nx <= 0.85):
            return False, f"Calibrated neutral_x ({nx}) is outside valid physiological boundary [0.15, 0.85]."
        if not (_is_valid_num(ny) and 0.15 <= ny <= 0.85):
            return False, f"Calibrated neutral_y ({ny}) is outside valid physiological boundary [0.15, 0.85]."

    # Check eyes
    l_ear = data.get("left_baseline_ear")
    r_ear = data.get("right_baseline_ear")
    if l_ear is not None:
        if not (_is_valid_num(l_ear) and 0.18 <= l_ear <= 0.42):
            return False, f"Calibrated left eye baseline EAR ({l_ear}) is outside normal range [0.18, 0.42]."
    if r_ear is not None:
        if not (_is_valid_num(r_ear) and 0.18 <= r_ear <= 0.42):
            return False, f"Calibrated right eye baseline EAR ({r_ear}) is outside normal range [0.18, 0.42]."

    # Check mouth
    mw = data.get("mouth_width_baseline")
    if mw is not None:
        if not (_is_valid_num(mw) and 0.35 <= mw <= 0.85):
            return False, f"Calibrated mouth width baseline ({mw}) is outside normal range [0.35, 0.85]."

    # Check eyebrows
    leb = data.get("left_eyebrow_baseline")
    reb = data.get("right_eyebrow_baseline")
    if leb is not None:
        if not (_is_valid_num(leb) and 0.08 <= leb <= 0.35):
            return False, f"Calibrated left eyebrow baseline ({leb}) is outside normal range [0.08, 0.35]."
    if reb is not None:
        if not (_is_valid_num(reb) and 0.08 <= reb <= 0.35):
            return False, f"Calibrated right eyebrow baseline ({reb}) is outside normal range [0.08, 0.35]."

    return True, ""


# Default settings instance
_settings: AppSettings | None = None


def get_settings() -> AppSettings:
    """Return the global settings instance."""
    global _settings
    if _settings is None:
        _settings = AppSettings.load()
    return _settings


def update_settings(**kwargs: Any) -> None:
    """Update settings from keyword arguments."""
    global _settings
    if _settings is None:
        _settings = AppSettings.load()
    # This is a simple implementation - a more sophisticated one would handle nested updates
    for key, value in kwargs.items():
        if hasattr(_settings, key):
            setattr(_settings, key, value)
    _settings.save()