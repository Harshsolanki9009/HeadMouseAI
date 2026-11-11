"""HeadMouse AI - Main Application.

Phase 4 implementation: Actual Windows Mouse Control & Safety Interlocks.
Provides camera-based neutral calibration, relative movement mapping,
dead-zone filtering, Kalman smoothing, normalized simulated cursor preview,
independent left/right eye blink detection via EAR (with simultaneous suppression),
and optional actual Windows OS mouse cursor control and clicks via PyAutoGUI.

IMPORTANT SAFETY SYSTEM:
- Real mouse control is DISABLED by default upon startup.
- Virtual cursor and simulated signals continue operating at all times.
- F8: Enable / Disable real mouse control.
- F9: Emergency Stop (instantly disables mouse actions; require F8 to re-enable).
- Face-loss & Recalibration interlocks automatically disable real mouse actions.

Controls:
  [F8]  - Toggle Real Mouse Control (Enable / Disable)
  [F9]  - EMERGENCY STOP Real Mouse Control
  [C]   - Start / Restart camera-based neutral calibration
  [R]   - Recalibrate / Recenter virtual cursor
  [D]   - Toggle debug telemetry logging
  [ESC] - Quit application
"""

from __future__ import annotations

import sys
import time
import signal
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from config.settings import get_settings
from core.camera import CameraCapture, CameraError
from core.face_landmarker import FaceLandmarkerWrapper, NOSE_TIP, LEFT_EYE_CENTER, RIGHT_EYE_CENTER
from core.nose_tracker import NoseTracker
from core.cursor_simulator import CursorSimulator
from core.eye_tracker import EyeTracker, calculate_eye_ear
from core.blink_detector import BlinkDetector, LEFT_CLICK, RIGHT_CLICK, NO_ACTION, DRAG_START, DRAG_STOP
from core.eyebrow_tracker import EyebrowTracker
from core.gesture_zoom import GestureZoomTracker, ZOOM_IN, ZOOM_OUT
from core.mouse_controller import MouseController
from utils.logger import logger

# Windows Virtual Key Codes for Global Hotkey Monitoring
VK_F8 = 0x77
VK_F9 = 0x78


def check_windows_key(vk_code: int) -> bool:
    """Check physical key state via user32 GetAsyncKeyState on Windows."""
    try:
        import ctypes
        if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32"):
            u32 = ctypes.windll.user32
            u32.GetAsyncKeyState.restype = ctypes.c_short
            state = u32.GetAsyncKeyState(vk_code)
            # Bit 15 indicates key is currently held down
            return bool(state & 0x8000)
    except Exception:
        pass
    return False

# Colors for visualization (BGR)
COLOR_NOSE = (0, 255, 255)         # Cyan
COLOR_LEFT_EYE = (255, 0, 0)       # Blue
COLOR_RIGHT_EYE = (0, 100, 255)    # Orange
COLOR_FACE = (0, 200, 0)           # Green
COLOR_TEXT = (255, 255, 255)       # White
COLOR_BG = (25, 25, 25)            # Dark gray
COLOR_CURSOR_MOVING = (0, 255, 100) # Bright Green
COLOR_CURSOR_IDLE = (0, 200, 255)  # Amber / Yellow
COLOR_NEUTRAL = (200, 200, 200)    # Light gray
COLOR_DEADZONE = (100, 100, 100)   # Dim gray


def draw_landmarks(frame: np.ndarray, landmarks: list, landmark_indices: dict | None = None) -> np.ndarray:
    """Draw facial landmarks on a frame efficiently.

    Args:
        frame: BGR frame (HxWx3, uint8)
        landmarks: List of [x, y, z, visibility, presence] per point (0-1 normalized)
        landmark_indices: Dict mapping friendly names to indices in the landmarks list.
    """
    if not landmarks or len(landmarks) == 0:
        return frame

    h, w = frame.shape[:2]
    total_lm = len(landmarks)

    # 1. Draw subtle background mesh points (sampled every 6th point for low CPU latency)
    for i in range(0, total_lm, 6):
        lm = landmarks[i]
        x, y = lm[0], lm[1]
        if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 and lm[3] >= 25:
            cv2.circle(frame, (int(x * w), int(y * h)), 1, (160, 160, 160), -1)

    # 2. Draw prominent key landmarks (Nose tip, Left eye, Right eye)
    if total_lm > NOSE_TIP:
        nx, ny = landmarks[NOSE_TIP][0], landmarks[NOSE_TIP][1]
        cv2.circle(frame, (int(nx * w), int(ny * h)), 4, COLOR_NOSE, -1)

    if total_lm > LEFT_EYE_CENTER:
        lx, ly = landmarks[LEFT_EYE_CENTER][0], landmarks[LEFT_EYE_CENTER][1]
        cv2.circle(frame, (int(lx * w), int(ly * h)), 3, COLOR_LEFT_EYE, -1)

    if total_lm > RIGHT_EYE_CENTER:
        rx, ry = landmarks[RIGHT_EYE_CENTER][0], landmarks[RIGHT_EYE_CENTER][1]
        cv2.circle(frame, (int(rx * w), int(ry * h)), 3, COLOR_RIGHT_EYE, -1)

    return frame


def draw_simulated_cursor(
    frame: np.ndarray,
    cx: float,
    cy: float,
    moved: bool,
    norm_x: float,
    norm_y: float,
    locked: bool = False,
) -> None:
    """Draw a virtual cursor reticle with state indicator and coordinates."""
    ix, iy = int(round(cx)), int(round(cy))
    h, w = frame.shape[:2]
    ix = max(0, min(w - 1, ix))
    iy = max(0, min(h - 1, iy))

    if locked:
        color = (0, 215, 255)  # Bright amber/yellow when click position is locked
    else:
        color = COLOR_CURSOR_MOVING if moved else COLOR_CURSOR_IDLE

    # Outer target ring
    cv2.circle(frame, (ix, iy), 14, color, 2)
    # Inner solid dot
    cv2.circle(frame, (ix, iy), 3, color, -1)
    # Crosshairs
    cv2.line(frame, (ix - 20, iy), (ix - 7, iy), color, 1)
    cv2.line(frame, (ix + 7, iy), (ix + 20, iy), color, 1)
    cv2.line(frame, (ix, iy - 20), (ix, iy - 7), color, 1)
    cv2.line(frame, (ix, iy + 7), (ix, iy + 20), color, 1)

    # Label with virtual coordinates
    label = f"CURSOR ({norm_x:.2f}, {norm_y:.2f}) [LOCKED]" if locked else f"CURSOR ({norm_x:.2f}, {norm_y:.2f})"
    cv2.putText(
        frame,
        label,
        (ix + 16, iy - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.4,
        color,
        1,
        cv2.LINE_AA,
    )


def draw_neutral_reference(
    frame: np.ndarray,
    neutral_x: float,
    neutral_y: float,
    dead_zone_radius: float,
) -> None:
    """Draw neutral baseline anchor and deadzone circle on the camera preview."""
    h, w = frame.shape[:2]
    # Invert neutral_y back to image coordinate convention for display
    nx_pix = int(round(neutral_x * w))
    ny_pix = int(round((1.0 - neutral_y) * h))

    # Neutral center cross
    cv2.drawMarker(
        frame,
        (nx_pix, ny_pix),
        COLOR_NEUTRAL,
        markerType=cv2.MARKER_CROSS,
        markerSize=14,
        thickness=1,
    )

    # Deadzone circle
    dz_r = max(4, int(round(dead_zone_radius)))
    cv2.circle(frame, (nx_pix, ny_pix), dz_r, COLOR_DEADZONE, 1, cv2.LINE_AA)
    cv2.putText(
        frame,
        "DEADZONE",
        (nx_pix - 24, ny_pix + dz_r + 12),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.32,
        COLOR_DEADZONE,
        1,
        cv2.LINE_AA,
    )


def draw_calibration_overlay(
    frame: np.ndarray,
    progress: float,
    sample_count: int,
    target_frames: int,
) -> None:
    """Draw calibration instructions and progress indicator."""
    h, w = frame.shape[:2]

    # Semi-transparent dark banner in top-center
    banner_w, banner_h = 440, 100
    bx1 = (w - banner_w) // 2
    by1 = 40
    overlay = frame.copy()
    cv2.rectangle(overlay, (bx1, by1), (bx1 + banner_w, by1 + banner_h), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
    cv2.rectangle(frame, (bx1, by1), (bx1 + banner_w, by1 + banner_h), (0, 200, 255), 1)

    cv2.putText(
        frame,
        "CALIBRATING NEUTRAL POSITION",
        (bx1 + 25, by1 + 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 255, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        "Keep head steady and look straight ahead",
        (bx1 + 35, by1 + 55),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (220, 220, 220),
        1,
        cv2.LINE_AA,
    )

    # Progress bar
    bar_x = bx1 + 30
    bar_y = by1 + 72
    bar_w = banner_w - 60
    bar_h = 12
    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (60, 60, 60), -1)
    fill_w = int(round(bar_w * progress))
    if fill_w > 0:
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + fill_w, bar_y + bar_h), (0, 255, 100), -1)
    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (180, 180, 180), 1)

    cv2.putText(
        frame,
        f"{sample_count}/{target_frames}",
        (bar_x + bar_w + 8, bar_y + 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.35,
        (220, 220, 220),
        1,
    )


class HeadMouseApp:
    """HeadMouse AI Phase 2: Real Nose Tracking, Camera Calibration, & Cursor Simulation."""

    def __init__(self) -> None:
        self.app_running = False
        self.camera_ok = True
        self.error_message: Optional[str] = None

        self.settings = get_settings()

        # Core subsystems
        cam_w = getattr(self.settings.gui, "camera_view_width", 640)
        cam_h = getattr(self.settings.gui, "camera_view_height", 480)
        self.camera = CameraCapture(
            index=self.settings.camera.camera_index,
            width=cam_w,
            height=cam_h,
        )
        self.landmarker = FaceLandmarkerWrapper()
        self.nose_tracker = NoseTracker(
            smoothing_strength=self.settings.nose_tracking.smoothing_strength,
            dead_zone=self.settings.nose_tracking.dead_zone,
        )
        self.cursor = CursorSimulator(
            sensitivity=self.settings.nose_tracking.sensitivity,
            dead_zone=self.settings.nose_tracking.dead_zone,
            max_velocity=self.settings.nose_tracking.max_velocity,
            window_width=cam_w,
            window_height=cam_h,
        )
        self.eye_tracker = EyeTracker(
            open_threshold=self.settings.eye_blink.left_eye_ear_threshold,
            independent_blink_detection=self.settings.eye_blink.independent_blink_detection,
            simultaneous_blink_suppression=self.settings.eye_blink.simultaneous_blink_suppression,
            blink_cooldown_frames=self.settings.eye_blink.blink_cooldown_frames,
            left_threshold=self.settings.eye_blink.left_eye_ear_threshold,
            right_threshold=self.settings.eye_blink.right_eye_ear_threshold,
        )
        self.blink_detector = BlinkDetector(self.settings.eye_blink)
        self.last_blink_event: str | None = None
        self.blink_event_display_timer: float = 0.0

        # Phase 4 Subsystem: Real Windows Mouse Controller (DISABLED by default)
        self.mouse_controller = MouseController(settings=self.settings.mouse)
        self.last_actual_click: str | None = None
        self._prev_f8_down: bool = False
        self._prev_f9_down: bool = False
        self._last_f8_trigger_time: float = 0.0
        self._last_f9_trigger_time: float = 0.0

        # Clickable Dashboard UI Button rects: (x, y, w, h)
        self._btn_toggle_rect: tuple[int, int, int, int] = (0, 0, 0, 0)
        self._btn_stop_rect: tuple[int, int, int, int] = (0, 0, 0, 0)
        self._ui_button_toggle_clicked: bool = False
        self._ui_button_stop_clicked: bool = False
        self.window_name: str = "HeadMouse AI - Hands-Free Interaction (Drag & Gesture Zoom)"

        # Eyebrow and Gesture Zoom Subsystems
        self.eyebrow_tracker = EyebrowTracker(settings=self.settings.scroll)
        self.gesture_zoom = GestureZoomTracker(settings=self.settings.zoom)
        self.calib_left_eyebrow_samples: list[float] = []
        self.calib_right_eyebrow_samples: list[float] = []
        self.calib_mouth_width_samples: list[float] = []
        self.last_zoom_action: str | None = None
        self.zoom_event_display_timer: float = 0.0
        self.last_scroll_action: str | None = None
        self.scroll_event_display_timer: float = 0.0

        # Calibration buffers for open-eye EAR baselines
        self.calib_left_ear_samples: list[float] = []
        self.calib_right_ear_samples: list[float] = []

        # Calibration and timing state
        self.auto_calibrate_on_start = True
        self.pipeline_fps: float = 0.0
        self._last_persist_time: float = 0.0

    def _on_mouse_click(self, event: int, x: int, y: int, flags: int, param: object) -> None:
        """Handle mouse clicks on OpenCV GUI overlay buttons."""
        if event == cv2.EVENT_LBUTTONDOWN:
            tx, ty, tw, th = self._btn_toggle_rect
            if tx <= x <= tx + tw and ty <= y <= ty + th:
                self._ui_button_toggle_clicked = True
                return

            sx, sy, sw, sh = self._btn_stop_rect
            if sx <= x <= sx + sw and sy <= y <= sy + sh:
                self._ui_button_stop_clicked = True
                return

    def toggle_real_mouse(self, source: str = "F8") -> bool:
        """Safely toggle real mouse control with safety checks and clear logging."""
        logger.info(f"{source} DETECTED")
        if not self.nose_tracker.is_calibrated or self.nose_tracker.is_calibrating:
            logger.warning("Cannot enable real mouse: Neutral calibration is not complete. Please press [C] to calibrate first.")
            return False
        return self.mouse_controller.toggle()

    def emergency_stop_real_mouse(self, source: str = "F9") -> None:
        """Instantly trigger emergency stop."""
        logger.warning(f"{source} EMERGENCY STOP")
        self.mouse_controller.emergency_stop()

    def _draw_dashboard_buttons(self, frame: np.ndarray, m_status: dict) -> None:
        """Draw interactive clickable buttons for real mouse toggle and emergency stop."""
        h, w = frame.shape[:2]

        btn_stop_w, btn_stop_h = 205, 36
        btn_toggle_w, btn_toggle_h = 245, 36
        gap = 10

        tx = w - btn_toggle_w - 12
        ty = 10
        self._btn_toggle_rect = (tx, ty, btn_toggle_w, btn_toggle_h)

        sx = tx - btn_stop_w - gap
        sy = 10
        self._btn_stop_rect = (sx, sy, btn_stop_w, btn_stop_h)

        # 1. Emergency Stop Button
        if m_status["emergency_stopped"]:
            s_bg = (0, 0, 220)  # Bright Red
            s_border = (255, 255, 255)
            s_text = "EMERGENCY STOPPED"
        else:
            s_bg = (0, 0, 140)  # Dark Red
            s_border = (0, 0, 255)
            s_text = "EMERGENCY STOP (F9/E)"

        cv2.rectangle(frame, (sx, sy), (sx + btn_stop_w, sy + btn_stop_h), s_bg, -1)
        cv2.rectangle(frame, (sx, sy), (sx + btn_stop_w, sy + btn_stop_h), s_border, 2)
        cv2.putText(frame, s_text, (sx + 10, sy + 23), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (255, 255, 255), 1, cv2.LINE_AA)

        # 2. Real Mouse Toggle Button
        if m_status["emergency_stopped"]:
            t_bg = (40, 40, 40)
            t_border = (0, 255, 100)
            t_text = "[ CLICK TO RESET & ENABLE ]"
            t_txt_col = (0, 255, 100)
        elif m_status["enabled"]:
            t_bg = (0, 120, 0)  # Green
            t_border = (0, 255, 100)
            t_text = f"REAL MOUSE: ON ({m_status['screen_x']},{m_status['screen_y']})"
            t_txt_col = (255, 255, 255)
        else:
            t_bg = (30, 30, 30)  # Dark Gray
            t_border = (0, 200, 255)  # Cyan border
            t_text = "[ ENABLE REAL MOUSE (F8/M) ]"
            t_txt_col = (0, 255, 255)

        cv2.rectangle(frame, (tx, ty), (tx + btn_toggle_w, ty + btn_toggle_h), t_bg, -1)
        cv2.rectangle(frame, (tx, ty), (tx + btn_toggle_w, ty + btn_toggle_h), t_border, 2)
        cv2.putText(frame, t_text, (tx + 10, ty + 23), cv2.FONT_HERSHEY_SIMPLEX, 0.40, t_txt_col, 1, cv2.LINE_AA)

    def _start_calibration(self) -> None:
        """Start neutral nose, eye baseline, eyebrow baseline, and mouth calibration."""
        self.calib_left_ear_samples.clear()
        self.calib_right_ear_samples.clear()
        self.calib_left_eyebrow_samples.clear()
        self.calib_right_eyebrow_samples.clear()
        self.calib_mouth_width_samples.clear()
        # Recalibration safety: automatically release held buttons and disable real mouse control during calibration
        self.mouse_controller.release_all_buttons()
        self.mouse_controller.update_tracking_status(has_face=False, is_calibrated=False)
        self.nose_tracker.start_calibration(self.settings.nose_tracking.calibration_frames)
        self.cursor.recalibrate()
        self.gesture_zoom.reset()
        logger.info("Started camera-based neutral nose, eye, eyebrow, and mouth baseline calibration.")

    def run(self) -> None:
        """Main application loop."""
        logger.info("=" * 60)
        logger.info("HEADMOUSE AI - Phase 2: Real Nose Tracking & Simulated Cursor")
        logger.info("=" * 60)

        try:
            logger.info(
                f"Initializing camera (index={self.camera.index}, "
                f"resolution={self.camera.width}x{self.camera.height})..."
            )
            self.camera.initialize(
                brightness=self.settings.camera.brightness,
                exposure=self.settings.camera.exposure,
                focus=self.settings.camera.focus,
            )
            logger.info("Camera initialized successfully!")

            # Verify initial frame
            test_frame = self.camera.read_frame()
            if test_frame is None:
                raise CameraError("Could not read initial frame from camera.")
            logger.info(f"First frame captured: {test_frame.shape}")

            # Start camera-frame-based calibration
            if self.auto_calibrate_on_start:
                self._start_calibration()

            # Create named window and attach mouse callback for clickable dashboard buttons
            cv2.namedWindow(self.window_name, cv2.WINDOW_AUTOSIZE)
            cv2.setMouseCallback(self.window_name, self._on_mouse_click)

            self.app_running = True
            loop_prev_time = time.perf_counter()

            while self.app_running:
                now = time.perf_counter()
                loop_dt = now - loop_prev_time
                loop_prev_time = now
                if loop_dt > 0:
                    inst_fps = 1.0 / loop_dt
                    self.pipeline_fps = 0.9 * self.pipeline_fps + 0.1 * inst_fps if self.pipeline_fps > 0 else inst_fps

                # Capture frame
                frame = self.camera.read_frame()
                if frame is None:
                    logger.error("Failed to capture frame. Checking camera health...")
                    if not self.camera.is_camera_available():
                        logger.error("All cameras appear disconnected. Stopping.")
                        self.camera.close()
                        break
                    continue

                # Mirror frame horizontally so head movements feel natural (mirror mode)
                frame = cv2.flip(frame, 1)

                # MediaPipe landmark detection (nose tip index 1 only for cursor)
                landmarks_data = self.landmarker.detect_landmarks(frame)
                has_face = landmarks_data.get("has_face", False)

                # Real camera calibration handling (Nose neutral & Eye baselines)
                if self.nose_tracker.is_calibrating:
                    if has_face:
                        calib_done = self.nose_tracker.add_calibration_sample(landmarks_data)
                        lm_c = landmarks_data.get("landmarks", [])
                        l_ear_c = calculate_eye_ear(lm_c, eye="left")
                        r_ear_c = calculate_eye_ear(lm_c, eye="right")
                        if l_ear_c is not None and l_ear_c > 0.15:
                            self.calib_left_ear_samples.append(l_ear_c)
                        if r_ear_c is not None and r_ear_c > 0.15:
                            self.calib_right_ear_samples.append(r_ear_c)

                        # Collect eyebrow and mouth samples during neutral calibration
                        l_eb, r_eb, m_w, m_o = self.gesture_zoom.extract_features(lm_c)
                        if l_eb is not None and r_eb is not None:
                            self.calib_left_eyebrow_samples.append(l_eb)
                            self.calib_right_eyebrow_samples.append(r_eb)
                        if m_w is not None:
                            self.calib_mouth_width_samples.append(m_w)

                        if calib_done:
                            self.cursor.recalibrate()
                            self.eye_tracker.calibrate_baseline(self.calib_left_ear_samples, self.calib_right_ear_samples)
                            self.blink_detector.calibrate_baseline(self.calib_left_ear_samples, self.calib_right_ear_samples)
                            self.eyebrow_tracker.calibrate_baseline(self.calib_left_eyebrow_samples, self.calib_right_eyebrow_samples)
                            self.gesture_zoom.calibrate_baseline(
                                self.calib_left_eyebrow_samples,
                                self.calib_right_eyebrow_samples,
                                self.calib_mouth_width_samples,
                            )
                            logger.info("Camera calibration complete! Nose neutral, Eye, Eyebrow & Mouth baselines active.")

                # Update eye tracking and blink detection FIRST so gesture onset is detected
                now_mono = time.monotonic()
                eye_state = self.eye_tracker.update(landmarks_data)
                blink_state = self.blink_detector.update(landmarks_data, eye_state, timestamp=now_mono)
                blink_event = blink_state.get("event")

                is_actively_dragging = bool(blink_state.get("is_dragging", False) or self.mouse_controller.is_dragging)
                self.cursor.set_dragging(is_actively_dragging)

                # Click Position Stabilization Interlock:
                # 1. During neutral calibration or active drag, position MUST be unlocked
                if self.nose_tracker.is_calibrating or is_actively_dragging:
                    self.cursor.unlock_position()
                    self.mouse_controller.unlock_position()
                # 2. Lock position immediately when deliberate single-eye click gesture begins
                elif blink_state.get("gesture_started") and not is_actively_dragging:
                    eye_name = blink_state.get("gesture_eye", "CLICK")
                    self.cursor.lock_position(reason=f"CLICK_{eye_name.upper()}")
                    self.mouse_controller.lock_position(reason=f"CLICK_{eye_name.upper()}")
                # 3. Unlock position as soon as gesture finishes, drag starts, or stabilization expires
                elif not blink_state.get("is_stabilizing"):
                    self.cursor.unlock_position()
                    self.mouse_controller.unlock_position()

                # Update nose tracking
                nose_detected, nose_movement = self.nose_tracker.update(landmarks_data)

                # Update virtual cursor simulation (strictly simulated, no OS mouse moves)
                rel_dx, rel_dy = self.nose_tracker.get_relative_position(smoothed=True)
                cx, cy, cursor_moved = self.cursor.update(rel_dx, rel_dy)
                norm_cx, norm_cy = self.cursor.normalized_position

                # Update gesture-activated interaction (Scroll: teeth only, Zoom: teeth + eyebrows)
                gesture_status = self.gesture_zoom.update(landmarks_data, relative_dy=rel_dy, timestamp=now_mono)
                scroll_mode_active = gesture_status.get("scroll_mode_active", False)
                zoom_mode_active = gesture_status.get("zoom_mode_active", False)
                gesture_active = scroll_mode_active or zoom_mode_active
                scroll_amount = gesture_status.get("scroll_amount", 0)
                zoom_action = gesture_status.get("zoom_action")

                # Suppress blink clicks while gesture mode (scroll or zoom) is actively engaged
                if gesture_active:
                    if blink_event in (LEFT_CLICK, RIGHT_CLICK):
                        blink_event = None

                if blink_event in (LEFT_CLICK, RIGHT_CLICK, NO_ACTION, DRAG_START, DRAG_STOP):
                    self.last_blink_event = blink_event
                    self.blink_event_display_timer = now_mono + 1.2

                # ---------------- Phase 4 & 5: Real Windows Mouse Control ---------------- #
                # Update mouse controller tracking state & safety interlocks
                is_calib_ready = self.nose_tracker.is_calibrated and not self.nose_tracker.is_calibrating
                self.mouse_controller.update_tracking_status(has_face=has_face, is_calibrated=is_calib_ready)

                # Move real cursor (only active when enabled; paused during scroll or zoom mode)
                real_cursor_pos = None
                if not gesture_active:
                    real_cursor_pos = self.mouse_controller.move_cursor(norm_cx, norm_cy)

                # Execute scroll if scroll_amount != 0
                if scroll_amount != 0:
                    self.mouse_controller.scroll(scroll_amount)
                    self.last_scroll_action = "SCROLL_UP" if scroll_amount > 0 else "SCROLL_DOWN"
                    self.scroll_event_display_timer = now_mono + 1.2

                # Execute zoom action if triggered (Ctrl + Plus / Ctrl + Minus)
                if zoom_action:
                    actual_zoom = self.mouse_controller.handle_zoom_action(
                        zoom_action,
                        steps=self.settings.zoom.zoom_step,
                        timestamp=now_mono,
                    )
                    self.last_zoom_action = actual_zoom or zoom_action
                    self.zoom_event_display_timer = now_mono + 1.2

                # Handle actual clicks and drag start/stop via PyAutoGUI (only active when enabled)
                actual_action = self.mouse_controller.handle_blink_event(blink_event, timestamp=now_mono)
                if actual_action:
                    self.last_actual_click = actual_action

                # ---------------- Visual Overlays ---------------- #
                lm_list = landmarks_data.get("landmarks", [])
                indices_dict = landmarks_data.get("landmark_indices", {})
                if has_face and len(lm_list) > 0:
                    frame = draw_landmarks(frame, lm_list, indices_dict)

                # Neutral baseline & deadzone visualization
                if self.nose_tracker.is_calibrated:
                    draw_neutral_reference(
                        frame,
                        self.nose_tracker.neutral_x,
                        self.nose_tracker.neutral_y,
                        self.settings.nose_tracking.dead_zone,
                    )

                # Calibration overlay when in calibrating state
                if self.nose_tracker.is_calibrating:
                    draw_calibration_overlay(
                        frame,
                        self.nose_tracker.get_calibration_progress(),
                        len(self.nose_tracker.calibration_buffer),
                        self.nose_tracker.calibration_frames,
                    )
                else:
                    # Draw simulated virtual cursor
                    draw_simulated_cursor(
                        frame,
                        cx,
                        cy,
                        cursor_moved,
                        norm_cx,
                        norm_cy,
                        locked=self.cursor.is_position_locked,
                    )

                # Prominent interactive dashboard buttons for Real Mouse Toggle & Emergency Stop
                m_status = self.mouse_controller.get_status()
                self._draw_dashboard_buttons(frame, m_status)

                # On-screen prominent visual notification for blink & drag events
                if self.last_blink_event and now_mono < self.blink_event_display_timer:
                    bw, bh = 500, 48
                    bx = (frame.shape[1] - bw) // 2
                    by = 22
                    overlay = frame.copy()
                    cv2.rectangle(overlay, (bx, by), (bx + bw, by + bh), (20, 20, 20), -1)
                    cv2.addWeighted(overlay, 0.70, frame, 0.30, 0, frame)

                    if self.last_blink_event == DRAG_START:
                        banner_color = (0, 165, 255)  # Orange
                        banner_text = "DRAG STARTED (MOUSE DOWN)"
                    elif self.last_blink_event == DRAG_STOP:
                        banner_color = (0, 255, 100)  # Green
                        banner_text = "DRAG STOPPED (MOUSE RELEASED)"
                    elif self.last_blink_event == LEFT_CLICK:
                        banner_color = (0, 255, 100) if m_status["enabled"] else (0, 255, 255)
                        banner_text = "ACTUAL LEFT_CLICK (REAL MOUSE)" if (m_status["enabled"] and self.last_actual_click == "LEFT_CLICK") else "SIMULATED LEFT_CLICK"
                    elif self.last_blink_event == RIGHT_CLICK:
                        banner_color = (0, 140, 255)
                        banner_text = "ACTUAL RIGHT_CLICK (REAL MOUSE)" if (m_status["enabled"] and self.last_actual_click == "RIGHT_CLICK") else "SIMULATED RIGHT_CLICK"
                    else:  # NO_ACTION
                        banner_color = (200, 200, 200)  # White/gray
                        banner_text = "SIMULTANEOUS BLINK (NO ACTION)"

                    cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), banner_color, 2)
                    cv2.putText(
                        frame,
                        banner_text,
                        (bx + 16, by + 32),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.54,
                        banner_color,
                        2,
                        cv2.LINE_AA,
                    )

                # Prominent Drag Active Badge (persistent while dragging)
                if m_status["is_dragging"]:
                    cv2.putText(
                        frame,
                        "DRAG: ACTIVE (LEFT BUTTON DOWN)",
                        (frame.shape[1] // 2 - 180, 80),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (0, 165, 255),
                        2,
                        cv2.LINE_AA,
                    )

                # Prominent Scroll or Zoom Mode Active Badge
                if zoom_mode_active:
                    zm_act_text = zoom_action or ("READY" if gesture_status.get("step_ready") else "RETURN TO NEUTRAL")
                    cv2.putText(
                        frame,
                        f"ZOOM MODE: ACTIVE (Teeth+Brows) | Step: {zm_act_text}",
                        (frame.shape[1] // 2 - 210, 105),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (0, 255, 255),
                        2,
                        cv2.LINE_AA,
                    )
                elif scroll_mode_active:
                    scr_act_text = gesture_status.get("action") or ("READY" if gesture_status.get("step_ready") else "STOPPED (NEUTRAL)")
                    cv2.putText(
                        frame,
                        f"SCROLL MODE: ACTIVE (Teeth Only) | Action: {scr_act_text}",
                        (frame.shape[1] // 2 - 210, 105),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (0, 255, 200),
                        2,
                        cv2.LINE_AA,
                    )
                elif self.last_zoom_action and now_mono < self.zoom_event_display_timer:
                    cv2.putText(
                        frame,
                        f"ZOOM: {self.last_zoom_action} (Ctrl + {'+' if self.last_zoom_action == 'ZOOM_IN' else '-'})",
                        (frame.shape[1] // 2 - 180, 105),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (0, 255, 100),
                        2,
                        cv2.LINE_AA,
                    )
                elif self.last_scroll_action and now_mono < self.scroll_event_display_timer:
                    cv2.putText(
                        frame,
                        f"SCROLL: {self.last_scroll_action}",
                        (frame.shape[1] // 2 - 140, 105),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (0, 200, 255),
                        2,
                        cv2.LINE_AA,
                    )

                if blink_state.get("suppression_active"):
                    cv2.putText(
                        frame,
                        "DUAL BLINK SUPPRESSED",
                        (frame.shape[1] // 2 - 130, 130),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.48,
                        (0, 0, 255),
                        2,
                        cv2.LINE_AA,
                    )

                # Prominent Position Lock Active Badge
                if self.cursor.is_position_locked:
                    cv2.putText(
                        frame,
                        f"CLICK POSITION LOCKED ({self.cursor.lock_reason})",
                        (frame.shape[1] // 2 - 160, 155),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.52,
                        (0, 215, 255),
                        2,
                        cv2.LINE_AA,
                    )

                # Status HUD overlay at bottom (Phase 5: Real Mouse, Drag, Gesture Interaction Telemetry)
                calib_label = (
                    f"CALIB {self.nose_tracker.get_calibration_progress()*100:.0f}%"
                    if self.nose_tracker.is_calibrating
                    else ("CALIBRATED" if self.nose_tracker.is_calibrated else "UNCALIBRATED")
                )
                l_ear = blink_state.get("left_ear")
                r_ear = blink_state.get("right_ear")
                l_ear_str = f"{l_ear:.2f}" if l_ear is not None else "--"
                r_ear_str = f"{r_ear:.2f}" if r_ear is not None else "--"
                l_th_c = blink_state.get("left_threshold_close", 0.21)
                l_th_o = blink_state.get("left_threshold_open", 0.24)
                r_th_c = blink_state.get("right_threshold_close", 0.21)
                r_th_o = blink_state.get("right_threshold_open", 0.24)
                l_state = blink_state.get("left_state_detailed", "OPEN")
                r_state = blink_state.get("right_state_detailed", "OPEN")
                l_dur_ms = blink_state.get("left_duration_ms", 0.0)
                r_dur_ms = blink_state.get("right_duration_ms", 0.0)
                supp_active = blink_state.get("suppression_active", False)
                active_blink_label = (
                    self.last_blink_event
                    if (self.last_blink_event and now_mono < self.blink_event_display_timer)
                    else "NONE"
                )
                active_status = blink_state.get("active_status")
                rej_reason = blink_state.get("last_reject_reason")
                acc_reason = blink_state.get("last_accept_reason")

                m_state_label = "EMERGENCY_STOP" if m_status["emergency_stopped"] else ("ENABLED" if m_status["enabled"] else "DISABLED")
                if m_status.get("is_dragging") or blink_state.get("is_dragging"):
                    current_mode = "DRAG"
                elif zoom_mode_active:
                    current_mode = "ZOOM"
                elif scroll_mode_active:
                    current_mode = "SCROLL"
                else:
                    current_mode = "NORMAL"

                if rel_dy >= self.settings.zoom.scroll_deadzone:
                    head_dir = "UP"
                elif rel_dy <= -self.settings.zoom.scroll_deadzone:
                    head_dir = "DOWN"
                else:
                    head_dir = "NEUTRAL"

                teeth_str = "SHOWN" if gesture_status.get("teeth_visible") else "NO"
                l_eb_state = "RAISED" if gesture_status.get("left_raised") else "NORMAL"
                r_eb_state = "RAISED" if gesture_status.get("right_raised") else "NORMAL"
                act_str = gesture_status.get("action") or ("READY" if gesture_status.get("step_ready") else "AWAIT_NEUTRAL")
                drag_state_str = "ACTIVE" if (m_status.get("is_dragging") or blink_state.get("is_dragging")) else "INACTIVE"
                btn_state_str = "DOWN" if m_status.get("is_mouse_down") else "UP"
                lock_state_str = "ACTIVE" if (self.cursor.is_position_locked or m_status.get("position_locked")) else "OFF"
                em_stop_str = "ACTIVE" if m_status.get("emergency_stopped") else "OFF"
                face_status_str = "OK" if has_face else "MISS"

                # Last completed scroll/zoom action string
                last_sz_str = "NONE"
                if self.last_zoom_action and now_mono < self.zoom_event_display_timer:
                    last_sz_str = f"ZOOM:{self.last_zoom_action}"
                elif self.last_scroll_action and now_mono < self.scroll_event_display_timer:
                    last_sz_str = f"SCROLL:{self.last_scroll_action}"
                elif gesture_status.get("action"):
                    last_sz_str = str(gesture_status.get("action"))

                g_rej = gesture_status.get("reject_reason", "NONE")

                hud_line1 = (
                    f"Eye L: [{l_state}] EAR:{l_ear_str} (Cl:{l_th_c:.2f}, Op:{l_th_o:.2f}) {l_dur_ms:.0f}ms | "
                    f"Eye R: [{r_state}] EAR:{r_ear_str} (Cl:{r_th_c:.2f}, Op:{r_th_o:.2f}) {r_dur_ms:.0f}ms | "
                    f"Blink: {active_blink_label} | Suppress: {'ACTIVE' if supp_active else 'OFF'}"
                )
                hud_line2 = (
                    f"MODE: [{current_mode}] | HEAD: [{head_dir}] (dy:{rel_dy:+.3f}) | "
                    f"MOUTH: W:{gesture_status.get('mouth_width_ratio', 0):.2f}(base:{gesture_status.get('mouth_width_baseline', 0):.2f}) "
                    f"O:{gesture_status.get('mouth_open_ratio', 0):.3f} [{teeth_str}] | "
                    f"BROWS: L:{gesture_status.get('left_eb_ratio', 0):.2f} R:{gesture_status.get('right_eb_ratio', 0):.2f} [{l_eb_state}/{r_eb_state}] | "
                    f"ACT: [{act_str}] | LAST: [{last_sz_str}] | G-REJ: [{g_rej}]"
                )
                hud_line3 = (
                    f"REAL MOUSE: [{m_state_label}] | BUTTON: [{btn_state_str}] | DRAG: [{drag_state_str}] | "
                    f"LOCK: [{lock_state_str}] | ACTION: [{m_status['last_action']}] | REJ: [{rej_reason or 'NONE'}]"
                )
                hud_line4 = (
                    f"FACE TRACKING STATUS: [{face_status_str}] | EMERGENCY STOP STATUS: [{em_stop_str}] | "
                    f"State: {calib_label} | Screen: ({m_status['screen_x']}, {m_status['screen_y']})"
                )
                hud_line5 = (
                    f"Controls: [F8/M or Click] Mouse ON/OFF | [F9/E] Emergency Stop | [C] Calib | [R] Reset | [ESC] Quit"
                )

                hud_h = 105
                cv2.rectangle(
                    frame,
                    (0, frame.shape[0] - hud_h),
                    (frame.shape[1], frame.shape[0]),
                    COLOR_BG,
                    -1,
                )
                cv2.putText(frame, hud_line1, (10, frame.shape[0] - 85), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (120, 240, 255), 1, cv2.LINE_AA)
                cv2.putText(frame, hud_line2, (10, frame.shape[0] - 65), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 200) if gesture_active else (200, 200, 200), 1, cv2.LINE_AA)
                cv2.putText(frame, hud_line3, (10, frame.shape[0] - 46), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 165, 255) if m_status.get("is_dragging") else COLOR_TEXT, 1, cv2.LINE_AA)
                m_color = (0, 0, 255) if m_status["emergency_stopped"] else ((0, 255, 100) if m_status["enabled"] else (180, 180, 180))
                cv2.putText(frame, hud_line4, (10, frame.shape[0] - 26), cv2.FONT_HERSHEY_SIMPLEX, 0.35, m_color, 1, cv2.LINE_AA)
                cv2.putText(frame, hud_line5, (10, frame.shape[0] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 220, 255), 1, cv2.LINE_AA)

                # Render window
                cv2.imshow(self.window_name, frame)
                self._persist_frame(frame)

                # ---------------- Unified Input & Trigger Pipeline ---------------- #
                f8_triggered = False
                f8_source = "F8"
                f9_triggered = False
                f9_source = "F9"

                # 1. Global hardware hotkey polling (user32 GetAsyncKeyState)
                f8_hotkey_down = check_windows_key(VK_F8)
                if f8_hotkey_down and not self._prev_f8_down:
                    f8_triggered = True
                    f8_source = "F8_HOTKEY"
                self._prev_f8_down = f8_hotkey_down

                f9_hotkey_down = check_windows_key(VK_F9)
                if f9_hotkey_down and not self._prev_f9_down:
                    f9_triggered = True
                    f9_source = "F9_HOTKEY"
                self._prev_f9_down = f9_hotkey_down

                # 2. Clickable UI Dashboard buttons
                if self._ui_button_toggle_clicked:
                    f8_triggered = True
                    f8_source = "UI_BUTTON"
                    self._ui_button_toggle_clicked = False

                if self._ui_button_stop_clicked:
                    f9_triggered = True
                    f9_source = "UI_BUTTON"
                    self._ui_button_stop_clicked = False

                # 3. Active window OpenCV key events (handles F8, F9, ESC, C, R, D, and fallback M/E keys)
                key = cv2.waitKeyEx(1)
                if key != -1:
                    if key == 27:  # ESC -> Quit
                        break
                    # F8 Key: matches raw virtual key, scancode bitmask, or 'M' key (for laptops with media keys)
                    elif (
                        ((key & 0xFF) == 119)
                        or ((key & 0xFFFF) == 119)
                        or (key in (0x770000, 119, 4325495, 65477))
                        or (key in (ord("m"), ord("M")))
                    ):
                        f8_triggered = True
                        f8_source = "M_KEY" if key in (ord("m"), ord("M")) else "F8_KEY"
                    # F9 Key: matches raw virtual key, scancode bitmask, or 'E' key (emergency stop)
                    elif (
                        ((key & 0xFF) == 120)
                        or ((key & 0xFFFF) == 120)
                        or (key in (0x780000, 120, 4391032, 65478))
                        or (key in (ord("e"), ord("E")))
                    ):
                        f9_triggered = True
                        f9_source = "E_KEY" if key in (ord("e"), ord("E")) else "F9_KEY"
                    elif key in (ord("c"), ord("C")):
                        logger.info("Recalibration requested by user.")
                        self._start_calibration()
                    elif key in (ord("r"), ord("R")):
                        logger.info("Cursor reset to center requested.")
                        self.cursor.recalibrate()
                    elif key in (ord("d"), ord("D")):
                        self.blink_detector.debug_logging = not self.blink_detector.debug_logging
                        logger.info(f"Blink debug logging toggled to: {self.blink_detector.debug_logging}")

                # 4. Debounced Trigger Execution (prevents double-toggle in same frame)
                now_mono = time.monotonic()
                if f8_triggered and (now_mono - self._last_f8_trigger_time > 0.30):
                    self._last_f8_trigger_time = now_mono
                    self.toggle_real_mouse(source=f8_source)

                if f9_triggered and (now_mono - self._last_f9_trigger_time > 0.30):
                    self._last_f9_trigger_time = now_mono
                    self.emergency_stop_real_mouse(source=f9_source)

        except CameraError as e:
            logger.error(f"Camera error: {e}")
            self.error_message = str(e)
            self.camera_ok = False
            self.app_running = True
            self._show_fallback_window()
        except KeyboardInterrupt:
            pass
        finally:
            self.cleanup()

    def _persist_frame(self, frame: np.ndarray, force: bool = False) -> None:
        """Save the current displayed frame to PNG periodically without blocking the loop."""
        now = time.monotonic()
        if not force and (now - self._last_persist_time < 5.0):
            return
        self._last_persist_time = now
        try:
            out_p4 = Path(r"C:\Users\Admin\HeadMouseAI\assets") / "screenshot_phase4.png"
            out_p4.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(out_p4), frame)
            out_p3 = Path(r"C:\Users\Admin\HeadMouseAI\assets") / "screenshot_phase3.png"
            cv2.imwrite(str(out_p3), frame)
            out_p2 = Path(r"C:\Users\Admin\HeadMouseAI\assets") / "screenshot_phase2.png"
            cv2.imwrite(str(out_p2), frame)
        except Exception as e:
            logger.debug(f"Persist frame failed: {e}")

    def cleanup(self) -> None:
        """Clean up resources."""
        logger.info("Cleaning up...")
        if hasattr(self, "mouse_controller") and self.mouse_controller is not None:
            try:
                self.mouse_controller.release_all_buttons()
            except Exception as e:
                logger.debug(f"Cleanup release_all_buttons exception: {e}")
        self.camera.close()
        cv2.destroyAllWindows()
        logger.info("Cleanup complete. Bye!")

    def _show_fallback_window(self) -> None:
        """Show a static error overlay window when the camera is unavailable."""
        h, w = 480, 640
        frame = np.zeros((h, w, 3), dtype=np.uint8)

        margin = 40
        cv2.putText(
            frame,
            "HEADMOUSE AI - Camera Unavailable",
            (margin, margin + 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (90, 180, 255),
            2,
        )

        err_text = self.error_message or "No camera detected."
        cv2.putText(
            frame,
            f"Details: {err_text}",
            (margin, margin + 120),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (100, 100, 255),
            1,
        )
        cv2.putText(
            frame,
            "Press ESC or any key to quit.",
            (margin, margin + 200),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (200, 200, 200),
            1,
        )

        cv2.imshow("HeadMouse AI - Phase 3: Nose Tracking & Eye Blink Detection", frame)
        self._persist_frame(frame)
        self.app_running = True
        while self.app_running:
            if cv2.waitKey(1) & 0xFF != 255:
                break
            self.app_running = False
        cv2.destroyAllWindows()

    def _run_with_camera_and_fallback(self) -> None:
        """Run the main loop; fall back to window on camera failure."""
        try:
            self.run()
        except Exception as e:
            logger.error(f"Unexpected error during run: {type(e).__name__}: {e}")
            self._show_fallback_window()


# Backward compatibility alias for previous tests/scripts
Phase1App = HeadMouseApp


def _on_sigint(signum: int, frame: object) -> None:
    """Signal handler."""
    global app
    if "app" in globals() and app is not None:
        app.app_running = False


def _fix_console_encoding() -> None:
    """Reconfigure stdout/stderr to UTF-8 on Windows."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def main() -> None:
    """Entry point."""
    _fix_console_encoding()
    global app
    app = HeadMouseApp()
    signal.signal(signal.SIGINT, _on_sigint)
    app._run_with_camera_and_fallback()


if __name__ == "__main__":
    main()
