"""Vision Worker Thread for HeadMouseAI PySide6 Application.

Decouples camera acquisition, MediaPipe vision processing, gesture state machines,
and PyAutoGUI OS actuation from the Qt UI event loop.
"""

from __future__ import annotations

import time
from typing import Any, Optional

import cv2
import numpy as np
import psutil
from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtGui import QImage

from config.settings import AppSettings, get_settings, validate_calibration_data
from core.blink_detector import BlinkDetector, DRAG_START, DRAG_STOP, LEFT_CLICK, NO_ACTION, RIGHT_CLICK
from core.camera import CameraCapture
from core.cursor_simulator import CursorSimulator
from core.eye_tracker import EyeTracker, calculate_eye_ear
from core.face_landmarker import FaceLandmarkerWrapper, LEFT_EYE_CENTER, NOSE_TIP, RIGHT_EYE_CENTER
from core.gesture_zoom import GestureZoomTracker
from core.mouse_controller import MouseController
from core.nose_tracker import NoseTracker
from utils.logger import logger


class VisionWorker(QThread):
    """Dedicated background worker thread running the real-time AI tracking pipeline."""

    # Outgoing Signals to Qt UI Main Thread
    sig_frame_ready = Signal(QImage)
    sig_telemetry = Signal(dict)
    sig_mouse_state_changed = Signal(bool, str)  # (is_enabled, state_label)
    sig_calibration_progress = Signal(float)      # 0.0 to 1.0
    sig_calibration_complete = Signal()
    sig_status_message = Signal(str, str)        # (level, text)
    sig_alert = Signal(str, str)                 # (title, body)

    def __init__(self, settings: Optional[AppSettings] = None, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.settings: AppSettings = settings if settings is not None else get_settings()

        # Thread lifecycle flags
        self._running: bool = False
        self._camera_switch_requested: Optional[int] = None
        self._show_mesh: bool = True
        self._show_cursor: bool = True

        # Pipeline Subsystems
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
        self.gesture_zoom = GestureZoomTracker(self.settings.zoom)
        self.mouse_controller = MouseController(settings=self.settings.mouse)

        # Baselines calibration samples
        self.calib_left_ear_samples: list[float] = []
        self.calib_right_ear_samples: list[float] = []
        self.calib_left_eyebrow_samples: list[float] = []
        self.calib_right_eyebrow_samples: list[float] = []
        self.calib_mouth_width_samples: list[float] = []

        # Action timers
        self.last_blink_event: Optional[str] = None
        self.blink_event_display_timer: float = 0.0
        self.last_scroll_action: Optional[str] = None
        self.scroll_event_display_timer: float = 0.0
        self.last_zoom_action: Optional[str] = None
        self.zoom_event_display_timer: float = 0.0

        # Performance metrics & resource monitoring
        self.pipeline_fps: float = 0.0
        self.frame_count: int = 0
        self.fps_timer: float = time.monotonic()
        self.last_inference_ms: float = 0.0
        self._last_resource_sample: float = 0.0
        self._current_cpu_percent: float = 0.0
        self._current_ram_mb: float = 0.0
        try:
            self._process: Optional[psutil.Process] = psutil.Process()
            self._process.cpu_percent(interval=None)
        except Exception:
            self._process = None

    def run(self) -> None:
        """Main camera acquisition and vision inference loop."""
        self._running = True
        logger.info("VisionWorker thread started.")

        try:
            self.camera.initialize(
                brightness=self.settings.camera.brightness,
                exposure=self.settings.camera.exposure,
                focus=self.settings.camera.focus,
            )
        except Exception as e:
            logger.error(f"VisionWorker camera initialization failed: {e}")
            self.sig_alert.emit("Camera Error", f"Could not initialize camera: {e}")
            self._running = False
            return

        # Start auto-calibration on startup
        self.start_calibration(self.settings.nose_tracking.calibration_frames)

        fps_frames = 0
        fps_start = time.monotonic()
        last_telemetry_emit = 0.0

        while self._running:
            # Handle dynamic camera switch request
            if self._camera_switch_requested is not None:
                new_idx = self._camera_switch_requested
                self._camera_switch_requested = None
                self._do_switch_camera(new_idx)

            loop_start = time.monotonic()

            frame = self.camera.read_frame()
            if frame is None:
                if not self.camera.is_camera_available():
                    logger.error("Camera disconnected in worker loop.")
                    self.sig_alert.emit("Camera Disconnected", "Video capture device was lost or unplugged.")
                    break
                time.sleep(0.01)
                continue

            # Mirror frame horizontally for natural intuitive interaction
            frame = cv2.flip(frame, 1)

            # Vision Processing Pipeline: Convert BGR to RGB once to eliminate redundant conversions
            now_mono = time.monotonic()
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            t_inf0 = time.perf_counter()
            landmarks_data = self.landmarker.detect_landmarks(rgb_frame, is_rgb=True)
            self.last_inference_ms = (time.perf_counter() - t_inf0) * 1000.0
            has_face = bool(landmarks_data.get("has_face", False))

            # 1. Calibration sample accumulation
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

                    l_eb, r_eb, m_w, m_o = self.gesture_zoom.extract_features(lm_c)
                    if l_eb is not None and r_eb is not None:
                        self.calib_left_eyebrow_samples.append(l_eb)
                        self.calib_right_eyebrow_samples.append(r_eb)
                    if m_w is not None:
                        self.calib_mouth_width_samples.append(m_w)

                    progress = self.nose_tracker.get_calibration_progress()
                    self.sig_calibration_progress.emit(progress)

                    if calib_done:
                        self._finish_all_calibrations()

            # 2. Eye & Blink Tracking
            eye_state = self.eye_tracker.update(landmarks_data)
            blink_state = self.blink_detector.update(landmarks_data, eye_state, timestamp=now_mono)
            blink_event = blink_state.get("event")

            is_actively_dragging = bool(blink_state.get("is_dragging", False) or self.mouse_controller.is_dragging)
            self.cursor.set_dragging(is_actively_dragging)

            # Click Position Stabilization Interlock
            if self.nose_tracker.is_calibrating or is_actively_dragging:
                self.cursor.unlock_position()
                self.mouse_controller.unlock_position()
            elif blink_state.get("gesture_started") and not is_actively_dragging:
                eye_name = blink_state.get("gesture_eye", "CLICK")
                self.cursor.lock_position(reason=f"CLICK_{eye_name.upper()}")
                self.mouse_controller.lock_position(reason=f"CLICK_{eye_name.upper()}")
            elif not blink_state.get("is_stabilizing"):
                self.cursor.unlock_position()
                self.mouse_controller.unlock_position()

            # 3. Nose Tracking & Virtual Cursor
            self.nose_tracker.update(landmarks_data)
            rel_dx, rel_dy = self.nose_tracker.get_relative_position(smoothed=True)
            cx, cy, cursor_moved = self.cursor.update(rel_dx, rel_dy)
            norm_cx, norm_cy = self.cursor.normalized_position

            # 4. Gesture Interaction (Scroll: Teeth Only, Zoom: Teeth + Eyebrows)
            gesture_status = self.gesture_zoom.update(landmarks_data, relative_dy=rel_dy, timestamp=now_mono)
            scroll_mode_active = gesture_status.get("scroll_mode_active", False)
            zoom_mode_active = gesture_status.get("zoom_mode_active", False)
            gesture_active = scroll_mode_active or zoom_mode_active
            scroll_amount = gesture_status.get("scroll_amount", 0)
            zoom_action = gesture_status.get("zoom_action")

            # Suppress wink clicks while gesture mode is actively engaged
            if gesture_active and blink_event in (LEFT_CLICK, RIGHT_CLICK):
                blink_event = None

            if blink_event in (LEFT_CLICK, RIGHT_CLICK, NO_ACTION, DRAG_START, DRAG_STOP):
                self.last_blink_event = blink_event
                self.blink_event_display_timer = now_mono + 1.2

            # 5. Real Windows Mouse Actuation (PyAutoGUI)
            is_calib_ready = self.nose_tracker.is_calibrated and not self.nose_tracker.is_calibrating
            self.mouse_controller.update_tracking_status(has_face=has_face, is_calibrated=is_calib_ready)

            if not gesture_active:
                self.mouse_controller.move_cursor(norm_cx, norm_cy)

            if scroll_amount != 0:
                self.mouse_controller.scroll(scroll_amount)
                self.last_scroll_action = "SCROLL_UP" if scroll_amount > 0 else "SCROLL_DOWN"
                self.scroll_event_display_timer = now_mono + 1.2

            if zoom_action:
                actual_zoom = self.mouse_controller.handle_zoom_action(
                    zoom_action,
                    steps=self.settings.zoom.zoom_step,
                    timestamp=now_mono,
                )
                self.last_zoom_action = actual_zoom or zoom_action
                self.zoom_event_display_timer = now_mono + 1.2

            actual_click = self.mouse_controller.handle_blink_event(blink_event, timestamp=now_mono)

            # 6. Performance Telemetry Computation
            fps_frames += 1
            elapsed_fps = time.monotonic() - fps_start
            if elapsed_fps >= 0.5:
                self.pipeline_fps = fps_frames / elapsed_fps
                fps_frames = 0
                fps_start = time.monotonic()

            latency_ms = (time.monotonic() - loop_start) * 1000.0

            # 7. Render UI Visualizations directly on rgb_frame (Zero redundant copies)
            perf_mode = getattr(self.settings.gui, "performance_mode", "balanced")
            if self._show_mesh and has_face and perf_mode != "performance":
                self._draw_landmarks(rgb_frame, landmarks_data.get("landmarks", []))

            if self._show_cursor:
                self._draw_virtual_cursor(rgb_frame, cx, cy, cursor_moved, norm_cx, norm_cy)

            # Direct QImage generation from active buffer
            h, w, ch = rgb_frame.shape
            bytes_per_line = ch * w
            q_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
            self.sig_frame_ready.emit(q_image)

            # 8. Sample System CPU & RAM every ~1.0 second
            if self._process is not None and (now_mono - self._last_resource_sample) >= 1.0:
                self._last_resource_sample = now_mono
                try:
                    self._current_cpu_percent = self._process.cpu_percent(interval=None)
                    self._current_ram_mb = self._process.memory_info().rss / (1024 * 1024)
                except Exception:
                    pass

            # 9. Package & Emit Comprehensive Telemetry (throttled by ui_refresh_hz)
            ui_hz = getattr(self.settings.gui, "ui_refresh_hz", 20)
            telemetry_dt = 1.0 / max(10, min(60, ui_hz))
            if (now_mono - last_telemetry_emit) >= telemetry_dt:
                last_telemetry_emit = now_mono
                m_status = self.mouse_controller.get_status()
                telemetry_payload = self._build_telemetry(
                    has_face=has_face,
                    is_calibrated=is_calib_ready,
                    blink_state=blink_state,
                    gesture_status=gesture_status,
                    mouse_status=m_status,
                    rel_dx=rel_dx,
                    rel_dy=rel_dy,
                    norm_cx=norm_cx,
                    norm_cy=norm_cy,
                    latency_ms=latency_ms,
                    now_mono=now_mono,
                    landmarks=landmarks_data.get("landmarks", []) if has_face else [],
                )
                self.sig_telemetry.emit(telemetry_payload)

            # Maintain natural camera pace
            time.sleep(0.001)

        # Cleanup on exit
        self._cleanup()
        logger.info("VisionWorker thread finished cleanly.")

    def _draw_landmarks(self, frame: np.ndarray, landmarks: list) -> None:
        """Draw non-intrusive face mesh points and tracking targets on RGB frame."""
        h, w = frame.shape[:2]
        total_lm = len(landmarks)
        for i in range(0, total_lm, 8):
            lm = landmarks[i]
            x, y = lm[0], lm[1]
            if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
                cv2.circle(frame, (int(x * w), int(y * h)), 1, (130, 130, 140), -1)

        # Prominent targets (in RGB format)
        if total_lm > NOSE_TIP:
            nx, ny = landmarks[NOSE_TIP][0], landmarks[NOSE_TIP][1]
            cv2.circle(frame, (int(nx * w), int(ny * h)), 4, (255, 215, 0), -1)

        if total_lm > LEFT_EYE_CENTER:
            lx, ly = landmarks[LEFT_EYE_CENTER][0], landmarks[LEFT_EYE_CENTER][1]
            cv2.circle(frame, (int(lx * w), int(ly * h)), 3, (0, 255, 120), -1)

        if total_lm > RIGHT_EYE_CENTER:
            rx, ry = landmarks[RIGHT_EYE_CENTER][0], landmarks[RIGHT_EYE_CENTER][1]
            cv2.circle(frame, (int(rx * w), int(ry * h)), 3, (0, 255, 120), -1)

    def _draw_virtual_cursor(
        self, frame: np.ndarray, cx: float, cy: float, moved: bool, norm_x: float, norm_y: float
    ) -> None:
        """Draw virtual target reticle on RGB frame indicating nose position and locking state."""
        ix, iy = int(round(cx)), int(round(cy))
        h, w = frame.shape[:2]
        ix = max(0, min(w - 1, ix))
        iy = max(0, min(h - 1, iy))

        locked = self.cursor.is_position_locked or self.mouse_controller.position_locked
        color = (255, 215, 0) if locked else ((0, 255, 0) if moved else (180, 180, 180))

        cv2.circle(frame, (ix, iy), 12, color, 2)
        cv2.circle(frame, (ix, iy), 3, color, -1)
        cv2.line(frame, (ix - 16, iy), (ix - 6, iy), color, 1)
        cv2.line(frame, (ix + 6, iy), (ix + 16, iy), color, 1)
        cv2.line(frame, (ix, iy - 16), (ix, iy - 6), color, 1)
        cv2.line(frame, (ix, iy + 6), (ix, iy + 16), color, 1)

    def _build_telemetry(
        self,
        has_face: bool,
        is_calibrated: bool,
        blink_state: dict,
        gesture_status: dict,
        mouse_status: dict,
        rel_dx: float,
        rel_dy: float,
        norm_cx: float,
        norm_cy: float,
        latency_ms: float,
        now_mono: float,
        landmarks: Optional[list] = None,
    ) -> dict[str, Any]:
        """Assemble comprehensive diagnostic telemetry dictionary for UI dashboard."""
        scroll_active = gesture_status.get("scroll_mode_active", False)
        zoom_active = gesture_status.get("zoom_mode_active", False)
        is_dragging = mouse_status.get("is_dragging", False) or blink_state.get("is_dragging", False)

        if is_dragging:
            mode = "DRAG"
        elif zoom_active:
            mode = "ZOOM"
        elif scroll_active:
            mode = "SCROLL"
        else:
            mode = "NORMAL"

        active_blink = (
            self.last_blink_event
            if (self.last_blink_event and now_mono < self.blink_event_display_timer)
            else "NONE"
        )
        last_scroll = (
            self.last_scroll_action
            if (self.last_scroll_action and now_mono < self.scroll_event_display_timer)
            else None
        )
        last_zoom = (
            self.last_zoom_action
            if (self.last_zoom_action and now_mono < self.zoom_event_display_timer)
            else None
        )

        # Genuine physiological nose landmark coordinates
        actual_nose_x = round(float(self.nose_tracker.nose_x), 4) if has_face else 0.5
        actual_nose_y = round(float(self.nose_tracker.nose_y), 4) if has_face else 0.5

        # Face distance & centering guidance
        distance_status = "OPTIMAL"
        if not has_face:
            distance_status = "NO_FACE"
        else:
            if landmarks and len(landmarks) > 263:
                p_l = landmarks[33]
                p_r = landmarks[263]
                lx = float(p_l[0]) if isinstance(p_l, (list, tuple)) else float(p_l.get("x", 0.0))
                ly = float(p_l[1]) if isinstance(p_l, (list, tuple)) else float(p_l.get("y", 0.0))
                rx = float(p_r[0]) if isinstance(p_r, (list, tuple)) else float(p_r.get("x", 0.0))
                ry = float(p_r[1]) if isinstance(p_r, (list, tuple)) else float(p_r.get("y", 0.0))
                iod = float(np.hypot(rx - lx, ry - ly))
                if iod < 0.10:
                    distance_status = "TOO_FAR"
                elif iod > 0.45:
                    distance_status = "TOO_CLOSE"
            if distance_status == "OPTIMAL" and (actual_nose_x < 0.20 or actual_nose_x > 0.80 or actual_nose_y < 0.20 or actual_nose_y > 0.80):
                distance_status = "OFF_CENTER"

        return {
            "fps": round(self.pipeline_fps, 1),
            "latency_ms": round(latency_ms, 1),
            "inference_ms": round(self.last_inference_ms, 1),
            "cpu_percent": round(self._current_cpu_percent, 1),
            "ram_mb": round(self._current_ram_mb, 1),
            "camera_resolution": self.camera.resolution,
            "tracking_status": "OPTIMAL" if (has_face and self.pipeline_fps >= 15) else ("TRACKING" if has_face else "SEARCHING"),
            "has_face": has_face,
            "is_calibrated": is_calibrated,
            "is_calibrating": self.nose_tracker.is_calibrating,
            "calib_progress": self.nose_tracker.get_calibration_progress(),
            "mode": mode,
            "real_mouse_enabled": mouse_status.get("enabled", False),
            "emergency_stopped": mouse_status.get("emergency_stopped", False),
            "mouse_down": mouse_status.get("is_mouse_down", False),
            "is_dragging": is_dragging,
            "position_locked": self.cursor.is_position_locked or mouse_status.get("position_locked", False),
            "screen_x": mouse_status.get("screen_x", 0),
            "screen_y": mouse_status.get("screen_y", 0),
            "norm_cx": norm_cx,
            "norm_cy": norm_cy,
            "nose_x": actual_nose_x,
            "nose_y": actual_nose_y,
            "face_distance_status": distance_status,
            "rel_dx": rel_dx,
            "rel_dy": rel_dy,
            # Eyes & Blink
            "left_ear": blink_state.get("left_ear", 0.0),
            "right_ear": blink_state.get("right_ear", 0.0),
            "left_eye_state": blink_state.get("left_state_detailed", "OPEN"),
            "right_eye_state": blink_state.get("right_state_detailed", "OPEN"),
            "left_eye_duration_ms": blink_state.get("left_duration_ms", 0.0),
            "right_eye_duration_ms": blink_state.get("right_duration_ms", 0.0),
            "blink_event": active_blink,
            "blink_reject_reason": blink_state.get("last_reject_reason", "NONE"),
            "suppression_active": blink_state.get("suppression_active", False),
            # Gesture Zoom & Scroll
            "teeth_visible": gesture_status.get("teeth_visible", False),
            "mouth_width_ratio": gesture_status.get("mouth_width_ratio", 0.0),
            "mouth_width_baseline": gesture_status.get("mouth_width_baseline", 0.0),
            "mouth_open_ratio": gesture_status.get("mouth_open_ratio", 0.0),
            "left_eb_ratio": gesture_status.get("left_eb_ratio", 0.0),
            "right_eb_ratio": gesture_status.get("right_eb_ratio", 0.0),
            "left_eb_state": "RAISED" if gesture_status.get("left_raised") else "NORMAL",
            "right_eb_state": "RAISED" if gesture_status.get("right_raised") else "NORMAL",
            "head_direction": gesture_status.get("head_direction", "NEUTRAL"),
            "gesture_action": gesture_status.get("action"),
            "gesture_step_ready": gesture_status.get("step_ready", True),
            "gesture_reject_reason": gesture_status.get("reject_reason", "NONE"),
            "last_scroll_action": last_scroll,
            "last_zoom_action": last_zoom,
        }

    def _finish_all_calibrations(self) -> None:
        """Apply all accumulated samples to trackers and persist valid baselines."""
        self.cursor.recalibrate()
        self.eye_tracker.calibrate_baseline(self.calib_left_ear_samples, self.calib_right_ear_samples)
        self.blink_detector.calibrate_baseline(self.calib_left_ear_samples, self.calib_right_ear_samples)
        self.gesture_zoom.calibrate_baseline(
            self.calib_left_eyebrow_samples,
            self.calib_right_eyebrow_samples,
            self.calib_mouth_width_samples,
        )
        # Update settings with calibrated values
        self.settings.nose_tracking.neutral_x = float(self.nose_tracker.neutral_x)
        self.settings.nose_tracking.neutral_y = float(self.nose_tracker.neutral_y)
        if len(self.calib_left_ear_samples) >= 5:
            self.settings.eye_blink.left_baseline_ear = float(np.median(self.calib_left_ear_samples))
        if len(self.calib_right_ear_samples) >= 5:
            self.settings.eye_blink.right_baseline_ear = float(np.median(self.calib_right_ear_samples))
        if len(self.calib_mouth_width_samples) >= 5:
            self.settings.zoom.mouth_width_baseline = float(np.median(self.calib_mouth_width_samples))
        if len(self.calib_left_eyebrow_samples) >= 5:
            self.settings.zoom.left_eyebrow_baseline = float(np.median(self.calib_left_eyebrow_samples))
        if len(self.calib_right_eyebrow_samples) >= 5:
            self.settings.zoom.right_eyebrow_baseline = float(np.median(self.calib_right_eyebrow_samples))
        self.settings.save()

        self.sig_calibration_complete.emit()
        self.sig_status_message.emit("INFO", "Neutral calibration completed and saved.")
        logger.info("VisionWorker: Neutral calibration completed and persisted.")

    def apply_calibration_profile(self, data: dict) -> tuple[bool, str]:
        """Validate and apply a full personalized calibration profile.

        Never overwrites valid configurations with incomplete or out-of-range data.
        """
        is_valid, err_msg = validate_calibration_data(data)
        if not is_valid:
            logger.warning(f"VisionWorker: Rejected invalid calibration data: {err_msg}")
            return False, err_msg

        # Apply nose
        if "neutral_x" in data and "neutral_y" in data:
            self.nose_tracker.set_neutral(float(data["neutral_x"]), float(data["neutral_y"]))
            self.nose_tracker.is_calibrating = False
            self.settings.nose_tracking.neutral_x = float(data["neutral_x"])
            self.settings.nose_tracking.neutral_y = float(data["neutral_y"])
            self.cursor.recalibrate()
            self.mouse_controller.is_calibrated = True

        # Apply eyes
        if "left_baseline_ear" in data and "right_baseline_ear" in data:
            l_ear = float(data["left_baseline_ear"])
            r_ear = float(data["right_baseline_ear"])
            self.blink_detector.calibrate_baseline([l_ear] * 5, [r_ear] * 5)
            self.eye_tracker.calibrate_baseline([l_ear] * 5, [r_ear] * 5)
            self.settings.eye_blink.left_baseline_ear = l_ear
            self.settings.eye_blink.right_baseline_ear = r_ear

        # Apply gestures (mouth and eyebrows)
        l_eb = data.get("left_eyebrow_baseline")
        r_eb = data.get("right_eyebrow_baseline")
        m_w = data.get("mouth_width_baseline")
        if l_eb is not None and r_eb is not None:
            eb_l = [float(l_eb)] * 5
            eb_r = [float(r_eb)] * 5
            mw_samples = [float(m_w)] * 5 if m_w is not None else None
            self.gesture_zoom.calibrate_baseline(eb_l, eb_r, mw_samples)
            self.settings.zoom.left_eyebrow_baseline = float(l_eb)
            self.settings.zoom.right_eyebrow_baseline = float(r_eb)
            if m_w is not None:
                self.settings.zoom.mouth_width_baseline = float(m_w)

        # Save to disk
        self.settings.save()
        self.sig_calibration_complete.emit()
        self.sig_status_message.emit("INFO", "Personalized calibration profile applied successfully.")
        logger.info("VisionWorker: Applied personalized calibration profile.")
        return True, "Calibration applied successfully."

    def _do_switch_camera(self, index: int) -> None:
        """Switch camera device cleanly."""
        try:
            self.camera.close()
            cam_w = getattr(self.settings.gui, "camera_view_width", 640)
            cam_h = getattr(self.settings.gui, "camera_view_height", 480)
            self.camera = CameraCapture(index=index, width=cam_w, height=cam_h)
            self.camera.initialize(
                brightness=self.settings.camera.brightness,
                exposure=self.settings.camera.exposure,
                focus=self.settings.camera.focus,
            )
            self.settings.camera.camera_index = index
            self.sig_status_message.emit("INFO", f"Switched to camera {index}")
            logger.info(f"VisionWorker switched to camera index {index}")
        except Exception as e:
            logger.error(f"Failed to switch camera: {e}")
            self.sig_alert.emit("Camera Error", f"Failed to switch to camera {index}: {e}")

    def _cleanup(self) -> None:
        """Safety release of OS resources and held mouse states."""
        self.mouse_controller.release_all_buttons()
        self.mouse_controller.disable()
        self.camera.close()

    # ---------------- Thread-Safe Control Slots ---------------- #
    @Slot()
    def stop_tracking(self) -> None:
        """Gracefully stop worker loop and join thread."""
        self._running = False
        self.wait(1500)

    @Slot()
    def stop(self) -> None:
        """Alias for stop_tracking."""
        self.stop_tracking()

    @Slot()
    def toggle_real_mouse(self) -> bool:
        """Safely toggle real mouse control state (F8 shortcut)."""
        if not self.nose_tracker.is_calibrated or self.nose_tracker.is_calibrating:
            self.sig_status_message.emit("WARNING", "Please calibrate [C] before enabling real mouse.")
            return False
        res = self.mouse_controller.toggle()
        m_stat = self.mouse_controller.get_status()
        self.sig_mouse_state_changed.emit(m_stat["enabled"], "ENABLED" if m_stat["enabled"] else "DISABLED")
        return res

    @Slot(bool)
    def set_real_mouse_enabled(self, enabled: bool) -> bool:
        """Explicitly enable or disable real mouse control."""
        if enabled:
            if not self.nose_tracker.is_calibrated or self.nose_tracker.is_calibrating:
                self.sig_status_message.emit("WARNING", "Cannot enable mouse: Neutral calibration is not complete.")
                return False
            ok = self.mouse_controller.enable()
        else:
            self.mouse_controller.disable()
            ok = True
        m_stat = self.mouse_controller.get_status()
        self.sig_mouse_state_changed.emit(m_stat["enabled"], "ENABLED" if m_stat["enabled"] else "DISABLED")
        return ok

    @Slot()
    def trigger_emergency_stop(self) -> None:
        """Immediately trigger emergency stop (F9 shortcut)."""
        self.mouse_controller.emergency_stop()
        self.sig_mouse_state_changed.emit(False, "EMERGENCY_STOP")
        self.sig_status_message.emit("ALERT", "EMERGENCY STOP ACTIVATED! Real mouse disengaged.")
        logger.warning("VisionWorker: Emergency Stop triggered.")

    @Slot(int)
    def start_calibration(self, frames: int = 30) -> None:
        """Start accumulating neutral camera calibration frames."""
        self.calib_left_ear_samples.clear()
        self.calib_right_ear_samples.clear()
        self.calib_left_eyebrow_samples.clear()
        self.calib_right_eyebrow_samples.clear()
        self.calib_mouth_width_samples.clear()
        self.mouse_controller.release_all_buttons()
        self.cursor.recalibrate()
        self.gesture_zoom.reset()
        self.nose_tracker.start_calibration(frames)
        self.sig_status_message.emit("INFO", "Started neutral calibration...")
        logger.info(f"VisionWorker: Calibration initiated ({frames} frames).")

    @Slot(int)
    def request_camera_switch(self, index: int) -> None:
        """Queue camera switch on the worker thread."""
        self._camera_switch_requested = int(index)

    @Slot(bool)
    def set_show_mesh(self, show: bool) -> None:
        """Toggle landmark mesh rendering."""
        self._show_mesh = bool(show)

    @Slot(bool)
    def set_show_cursor(self, show: bool) -> None:
        """Toggle virtual cursor reticle rendering."""
        self._show_cursor = bool(show)

    @Slot(dict)
    def update_dynamic_settings(self, settings_diff: dict) -> None:
        """Apply dynamic settings adjustments from settings tab."""
        if "sensitivity" in settings_diff:
            val = float(settings_diff["sensitivity"])
            self.settings.nose_tracking.sensitivity = val
            self.cursor.sensitivity = val
        if "dead_zone" in settings_diff:
            val = float(settings_diff["dead_zone"])
            self.settings.nose_tracking.dead_zone = val
            self.cursor.dead_zone = val
            self.nose_tracker.dead_zone = val
        if "smoothing_strength" in settings_diff:
            val = float(settings_diff["smoothing_strength"])
            self.settings.nose_tracking.smoothing_strength = val
            self.nose_tracker.smoothing_strength = val
        if "cursor_speed" in settings_diff:
            val = int(settings_diff["cursor_speed"])
            self.settings.mouse.cursor_speed = val
            self.mouse_controller.cursor_speed = val
        if "drag_hold_sec" in settings_diff:
            val = float(settings_diff["drag_hold_sec"])
            self.settings.eye_blink.drag_hold_sec = val
            self.blink_detector.drag_hold_sec = val
        if "left_sensitivity" in settings_diff or "right_sensitivity" in settings_diff:
            l_s = float(settings_diff.get("left_sensitivity", self.settings.eye_blink.left_sensitivity))
            r_s = float(settings_diff.get("right_sensitivity", self.settings.eye_blink.right_sensitivity))
            self.settings.eye_blink.left_sensitivity = l_s
            self.settings.eye_blink.right_sensitivity = r_s
            self.blink_detector.set_sensitivities(l_s, r_s)
        if "scroll_step" in settings_diff:
            s_step = int(settings_diff["scroll_step"])
            self.settings.zoom.scroll_step = s_step
            self.gesture_zoom.scroll_step = s_step
        if "scroll_sensitivity" in settings_diff:
            s_sens = float(settings_diff["scroll_sensitivity"])
            self.settings.zoom.scroll_sensitivity = s_sens
            self.gesture_zoom.scroll_sensitivity = s_sens
        if "zoom_step" in settings_diff:
            z_step = int(settings_diff["zoom_step"])
            self.settings.zoom.zoom_step = z_step
            self.gesture_zoom.zoom_step = z_step
        if "zoom_sensitivity" in settings_diff:
            z_sens = float(settings_diff["zoom_sensitivity"])
            self.settings.zoom.zoom_sensitivity = z_sens
            self.gesture_zoom.zoom_sensitivity = z_sens
        if "smile_sensitivity" in settings_diff:
            sm_sens = float(settings_diff["smile_sensitivity"])
            self.settings.zoom.smile_sensitivity = sm_sens
            self.gesture_zoom.smile_sensitivity = sm_sens
        if "camera_resolution" in settings_diff:
            res = settings_diff["camera_resolution"]
            if isinstance(res, (tuple, list)) and len(res) == 2:
                w, h = int(res[0]), int(res[1])
            elif isinstance(res, str) and "x" in res:
                parts = res.lower().split("x")
                w, h = int(parts[0]), int(parts[1])
            else:
                w, h = 640, 480
            self.camera.set_resolution(w, h)
            self.settings.camera.width = w
            self.settings.camera.height = h
        if "performance_mode" in settings_diff:
            pm = str(settings_diff["performance_mode"]).lower()
            self.settings.gui.performance_mode = pm
        if "ui_refresh_hz" in settings_diff:
            hz = int(settings_diff["ui_refresh_hz"])
            self.settings.gui.ui_refresh_hz = max(10, min(60, hz))
        logger.info(f"VisionWorker: Applied dynamic settings: {settings_diff}")
