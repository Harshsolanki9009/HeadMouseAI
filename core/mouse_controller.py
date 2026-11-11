"""Actual Windows Mouse Controller for HeadMouse AI Phase 4.

Translates virtual cursor positions and simulated blink signals into actual
Windows OS cursor movements and clicks via PyAutoGUI with hardware failsafes,
emergency stop (F9), enable/disable toggle (F8), face-loss safety interlocks,
and calibration gating.

IMPORTANT SAFETY NOTICE:
Real mouse control is strictly DISABLED by default upon startup.
Virtual cursor preview and simulated click events continue operating at all times.
"""

from __future__ import annotations

import time
from typing import Tuple, Optional, Any
import pyautogui

from utils.logger import logger
from core.blink_detector import LEFT_CLICK, RIGHT_CLICK, NO_ACTION, DRAG_START, DRAG_STOP
from config.settings import MouseControlSettings, get_settings


class MouseController:
    """Hardware OS mouse controller with safety interlocks and failsafe mechanisms."""

    def __init__(
        self,
        screen_width: int | None = None,
        screen_height: int | None = None,
        settings: MouseControlSettings | None = None,
        py_backend: Any = None,
    ) -> None:
        """Initialize the mouse controller.

        Args:
            screen_width: Optional override for screen width (pixels).
            screen_height: Optional override for screen height (pixels).
            settings: Mouse control settings dataclass.
            py_backend: Optional backend (defaults to pyautogui, allows mocking for tests).
        """
        if settings is None:
            settings = get_settings().mouse

        self.settings = settings
        self.pyautogui = py_backend if py_backend is not None else pyautogui

        # Ensure failsafe is always strictly enabled
        try:
            self.pyautogui.FAILSAFE = True
            # Zero pause prevents artificial thread sleeps and latency in the video loop
            self.pyautogui.PAUSE = 0.0
        except Exception as e:
            logger.debug(f"PyAutoGUI initialization attribute configuration: {e}")

        # Obtain screen resolution safely
        if screen_width is not None and screen_height is not None:
            self.screen_width = int(screen_width)
            self.screen_height = int(screen_height)
        else:
            try:
                sz = self.pyautogui.size()
                self.screen_width = int(sz[0]) if isinstance(sz, (tuple, list)) else int(sz.width)
                self.screen_height = int(sz[1]) if isinstance(sz, (tuple, list)) else int(sz.height)
            except Exception as e:
                logger.warning(f"Failed to read screen size from PyAutoGUI: {e}. Defaulting to 1920x1080.")
                self.screen_width = 1920
                self.screen_height = 1080

        # Safety State Machine: STRICTLY DISABLED BY DEFAULT
        self.enabled: bool = False
        self.emergency_stopped: bool = False
        self.has_face: bool = False
        self.is_calibrated: bool = False

        # Live Cursor State in screen pixels
        self.screen_x: int = self.screen_width // 2
        self.screen_y: int = self.screen_height // 2

        # Click debouncing & cooldown
        self.last_click_time: float = 0.0
        self.click_cooldown_sec: float = float(getattr(settings, "click_cooldown_sec", 0.35))
        self.last_blink_signal: str | None = None

        # Telemetry & Diagnostics
        self.last_action: str = "DISABLED"
        self.last_action_time: float = time.monotonic()
        self._last_move_log_time: float = 0.0
        self.total_moves: int = 0
        self.total_left_clicks: int = 0
        self.total_right_clicks: int = 0
        self.total_drags: int = 0
        self.total_scrolls: int = 0
        self.total_zooms: int = 0
        self.failsafe_triggered: bool = False

        # Live button and mode states
        self.is_mouse_down: bool = False
        self.is_dragging: bool = False
        self.is_scrolling: bool = False

        # Position lock / Click stabilization state
        self.position_locked: bool = False
        self.locked_screen_x: int = self.screen_x
        self.locked_screen_y: int = self.screen_y
        self.lock_reason: str = "NONE"
        self.lock_time: float = 0.0

    @property
    def is_position_locked(self) -> bool:
        """True while OS mouse position is locked for click stabilization."""
        return self.position_locked and not self.is_dragging

    def lock_position(self, reason: str = "CLICK") -> None:
        """Lock mouse controller at current screen coordinates."""
        if self.is_dragging:
            return  # Never lock position while dragging
        if not self.position_locked:
            self.position_locked = True
            self.locked_screen_x = self.screen_x
            self.locked_screen_y = self.screen_y
            self.lock_reason = reason
            self.lock_time = time.monotonic()
            logger.debug(f"Mouse position locked at ({self.locked_screen_x}, {self.locked_screen_y}) [{reason}]")

    def unlock_position(self) -> None:
        """Unlock mouse controller position."""
        if self.position_locked:
            self.position_locked = False
            self.lock_reason = "NONE"
            logger.debug("Mouse position unlocked.")

    def can_operate(self) -> Tuple[bool, str]:
        """Check if real mouse actions are currently permitted.

        Returns:
            Tuple of (allowed: bool, status_reason: str).
        """
        if self.emergency_stopped:
            return False, "EMERGENCY_STOP"
        if not self.enabled:
            return False, "DISABLED"
        if not self.is_calibrated:
            return False, "UNCALIBRATED"
        if not self.has_face:
            return False, "FACE_LOST"
        return True, "OPERATIONAL"

    def enable(self) -> bool:
        """Enable real mouse control if safety conditions are satisfied.

        Returns:
            True if successfully enabled, False if blocked by safety checks.
        """
        if not self.is_calibrated:
            logger.warning("Cannot enable real mouse: nose calibration is not complete.")
            self.last_action = "CANNOT_ENABLE_UNCALIBRATED"
            return False

        # Clear emergency stop upon explicit manual user enable request (F8)
        self.emergency_stopped = False
        self.enabled = True
        self.last_action = "ENABLED"
        self.last_action_time = time.monotonic()
        logger.info("REAL MOUSE ENABLED")
        return True

    def disable(self) -> None:
        """Disable real mouse control."""
        self.unlock_position()
        self.release_all_buttons()
        self.enabled = False
        self.last_action = "DISABLED"
        self.last_action_time = time.monotonic()
        logger.info("REAL MOUSE DISABLED")

    def toggle(self) -> bool:
        """Toggle real mouse control state (F8 shortcut).

        Returns:
            True if now enabled, False if disabled or blocked.
        """
        if self.enabled:
            self.disable()
            return False
        else:
            return self.enable()

    def emergency_stop(self) -> None:
        """Instantly disable all mouse actions and lock into emergency stop (F9 shortcut)."""
        self.unlock_position()
        self.release_all_buttons()
        self.enabled = False
        self.emergency_stopped = True
        self.last_action = "EMERGENCY_STOP"
        self.last_action_time = time.monotonic()
        self.last_blink_signal = None
        logger.warning("F9 EMERGENCY STOP")

    def reset_emergency_stop(self) -> None:
        """Clear emergency stop flag so F8 can re-enable."""
        self.emergency_stopped = False
        if self.last_action == "EMERGENCY_STOP":
            self.last_action = "DISABLED"

    def mouse_down(self, button: str = "left") -> bool:
        """Press and hold mouse button for drag / area selection."""
        can_run, reason = self.can_operate()
        if not can_run:
            return False
        if self.is_mouse_down:
            return True  # Already held, avoid duplicate calls
        try:
            self.pyautogui.mouseDown(button=button)
            self.is_mouse_down = True
            self.is_dragging = True
            self.total_drags += 1
            self.last_action = "MOUSE_DOWN"
            self.last_action_time = time.monotonic()
            logger.info(f"MOUSE BUTTON DOWN ({button}): Drag / selection started.")
            return True
        except getattr(self.pyautogui, "FailSafeException", Exception) as e:
            logger.critical(f"PyAutoGUI FailSafeException during mouseDown: {e}")
            self.failsafe_triggered = True
            self.emergency_stop()
            return False
        except Exception as e:
            logger.error(f"Error executing mouseDown: {e}")
            return False

    def mouse_up(self, button: str = "left") -> bool:
        """Release held mouse button for drag / area selection."""
        if not self.is_mouse_down:
            return False  # Already released
        try:
            self.pyautogui.mouseUp(button=button)
            self.is_mouse_down = False
            self.is_dragging = False
            self.last_action = "MOUSE_UP"
            self.last_action_time = time.monotonic()
            logger.info(f"MOUSE BUTTON UP ({button}): Drag / selection released.")
            return True
        except getattr(self.pyautogui, "FailSafeException", Exception) as e:
            logger.critical(f"PyAutoGUI FailSafeException during mouseUp: {e}")
            self.failsafe_triggered = True
            self.emergency_stop()
            return False
        except Exception as e:
            logger.error(f"Error executing mouseUp: {e}")
            self.is_mouse_down = False
            self.is_dragging = False
            return False

    def scroll(self, amount: int) -> bool:
        """Execute vertical mouse scroll via PyAutoGUI."""
        can_run, reason = self.can_operate()
        if not can_run or amount == 0:
            return False
        try:
            self.pyautogui.scroll(amount)
            self.is_scrolling = True
            self.total_scrolls += 1
            self.last_action = "SCROLL_UP" if amount > 0 else "SCROLL_DOWN"
            self.last_action_time = time.monotonic()
            return True
        except getattr(self.pyautogui, "FailSafeException", Exception) as e:
            logger.critical(f"PyAutoGUI FailSafeException during scroll: {e}")
            self.failsafe_triggered = True
            self.emergency_stop()
            return False
        except Exception as e:
            logger.error(f"Error executing scroll: {e}")
            return False

    def zoom_in(self, steps: int = 1) -> bool:
        """Trigger discrete zoom-in step(s) using Ctrl + Plus."""
        can_run, reason = self.can_operate()
        if not can_run or steps <= 0:
            return False
        try:
            for _ in range(steps):
                self.pyautogui.hotkey("ctrl", "+")
            self.total_zooms += steps
            self.last_action = "ZOOM_IN"
            self.last_action_time = time.monotonic()
            logger.info(f"ZOOM_IN executed ({steps} step(s)).")
            return True
        except getattr(self.pyautogui, "FailSafeException", Exception) as e:
            logger.critical(f"PyAutoGUI FailSafeException during zoom_in: {e}")
            self.failsafe_triggered = True
            self.emergency_stop()
            return False
        except Exception as e:
            logger.error(f"Error executing zoom_in: {e}")
            return False

    def zoom_out(self, steps: int = 1) -> bool:
        """Trigger discrete zoom-out step(s) using Ctrl + Minus."""
        can_run, reason = self.can_operate()
        if not can_run or steps <= 0:
            return False
        try:
            for _ in range(steps):
                self.pyautogui.hotkey("ctrl", "-")
            self.total_zooms += steps
            self.last_action = "ZOOM_OUT"
            self.last_action_time = time.monotonic()
            logger.info(f"ZOOM_OUT executed ({steps} step(s)).")
            return True
        except getattr(self.pyautogui, "FailSafeException", Exception) as e:
            logger.critical(f"PyAutoGUI FailSafeException during zoom_out: {e}")
            self.failsafe_triggered = True
            self.emergency_stop()
            return False
        except Exception as e:
            logger.error(f"Error executing zoom_out: {e}")
            return False

    def handle_zoom_action(self, action: str | None, steps: int = 1, timestamp: float | None = None) -> str | None:
        """Translate gesture zoom actions into keyboard zoom shortcuts.

        Args:
            action: Zoom action ('ZOOM_IN', 'ZOOM_OUT', or None).
            steps: Number of zoom steps to apply.
            timestamp: Monotonic timestamp in seconds.

        Returns:
            Action executed ('ZOOM_IN', 'ZOOM_OUT', or None).
        """
        if action is None:
            return None
        can_run, reason = self.can_operate()
        if not can_run:
            return None

        if action == "ZOOM_IN":
            if self.zoom_in(steps=steps):
                return "ZOOM_IN"
        elif action == "ZOOM_OUT":
            if self.zoom_out(steps=steps):
                return "ZOOM_OUT"
        return None

    def release_all_buttons(self) -> None:
        """Safety release of any held mouse buttons."""
        self.unlock_position()
        if self.is_mouse_down:
            logger.info("Safety release: releasing held mouse button.")
            try:
                btn = getattr(self.settings, "left_click_button", "left")
                self.pyautogui.mouseUp(button=btn)
            except Exception as e:
                logger.debug(f"Exception during safety mouseUp: {e}")
            self.is_mouse_down = False
            self.is_dragging = False
            self.last_action = "SAFETY_RELEASE"
        self.is_scrolling = False

    def update_tracking_status(self, has_face: bool, is_calibrated: bool) -> None:
        """Update live face detection and calibration state.

        Args:
            has_face: Whether a face is actively detected in the current frame.
            is_calibrated: Whether neutral nose calibration has been completed.
        """
        prev_calibrated = self.is_calibrated
        self.has_face = bool(has_face)
        self.is_calibrated = bool(is_calibrated)

        # Recalibration protection: if calibration is reset, release buttons and disable real mouse control
        if prev_calibrated and not self.is_calibrated:
            if self.is_mouse_down:
                self.release_all_buttons()
            if self.enabled:
                logger.info("Recalibration started: automatically disabling real mouse control.")
                self.disable()
                self.last_action = "DISABLED_FOR_RECALIBRATION"

        # Face-loss safety interlock: release held buttons immediately and unlock position
        if not self.has_face:
            self.unlock_position()
            if self.is_mouse_down:
                self.release_all_buttons()
            if self.enabled:
                self.last_action = "FACE_LOST"

    def move_cursor(self, norm_x: float, norm_y: float) -> Tuple[int, int] | None:
        """Map normalized virtual cursor [0, 1] to screen pixels and move the Windows cursor.

        Args:
            norm_x: Normalized horizontal position (0.0=left, 1.0=right).
            norm_y: Normalized vertical position (0.0=top, 1.0=bottom).

        Returns:
            Tuple of (screen_x, screen_y) if moved, None if blocked or disabled.
        """
        # If position is locked for click stabilization, hold locked screen coordinates
        if self.position_locked and not self.is_dragging:
            # Auto-safety unlock timeout: never lock for more than 0.35s
            if (time.monotonic() - self.lock_time) > 0.35:
                self.unlock_position()
            else:
                safe_x = max(1, min(self.screen_width - 2, self.locked_screen_x))
                safe_y = max(1, min(self.screen_height - 2, self.locked_screen_y))
                self.screen_x = safe_x
                self.screen_y = safe_y
                can_run, reason = self.can_operate()
                if not can_run:
                    return None
                try:
                    self.pyautogui.moveTo(safe_x, safe_y)
                    return (safe_x, safe_y)
                except getattr(self.pyautogui, "FailSafeException", Exception) as e:
                    logger.critical(f"PyAutoGUI FailSafeException encountered: {e}. Executing Emergency Stop.")
                    self.failsafe_triggered = True
                    self.emergency_stop()
                    return None
                except Exception as e:
                    logger.error(f"Unexpected error maintaining locked cursor: {e}")
                    return None

        # Always update internal coordinate telemetry for display
        clamped_nx = max(0.0, min(1.0, float(norm_x)))
        clamped_ny = max(0.0, min(1.0, float(norm_y)))

        target_x = int(round(clamped_nx * (self.screen_width - 1)))
        target_y = int(round(clamped_ny * (self.screen_height - 1)))

        # Safety boundary clamp: stays strictly inside screen bounds
        target_x = max(0, min(self.screen_width - 1, target_x))
        target_y = max(0, min(self.screen_height - 1, target_y))

        self.screen_x = target_x
        self.screen_y = target_y

        can_run, reason = self.can_operate()
        if not can_run:
            return None

        # Keep 1px away from screen corners (0,0) to prevent accidental PyAutoGUI failsafe trips during tracking
        safe_x = max(1, min(self.screen_width - 2, target_x))
        safe_y = max(1, min(self.screen_height - 2, target_y))

        try:
            self.pyautogui.moveTo(safe_x, safe_y)
            self.screen_x = safe_x
            self.screen_y = safe_y
            self.total_moves += 1
            self.last_action = "MOVE"
            self.last_action_time = time.monotonic()
            now = time.monotonic()
            if (now - self._last_move_log_time >= 0.25) or (self.total_moves <= 5):
                logger.info(f"MOUSE MOVE: ({safe_x}, {safe_y})")
                self._last_move_log_time = now
            return (safe_x, safe_y)
        except getattr(self.pyautogui, "FailSafeException", Exception) as e:
            logger.critical(f"PyAutoGUI FailSafeException encountered: {e}. Executing Emergency Stop.")
            self.failsafe_triggered = True
            self.emergency_stop()
            return None
        except Exception as e:
            logger.error(f"Unexpected error moving Windows cursor: {e}")
            return None

    def handle_blink_event(self, event: str | None, timestamp: float | None = None) -> str | None:
        """Translate simulated blink events into actual OS mouse clicks.

        Args:
            event: Blink event string ('LEFT_CLICK', 'RIGHT_CLICK', 'NO_ACTION', or None).
            timestamp: Monotonic timestamp in seconds (defaults to time.monotonic()).

        Returns:
            Action executed ('LEFT_CLICK', 'RIGHT_CLICK', or None).
        """
        if timestamp is None:
            timestamp = time.monotonic()

        can_run, reason = self.can_operate()
        if not can_run:
            # When disabled, uncalibrated, face-lost, or emergency-stopped: NEVER click
            return None

        if event is None or event == NO_ACTION:
            return None

        if event == DRAG_START:
            self.unlock_position()
            btn = getattr(self.settings, "left_click_button", "left")
            if self.mouse_down(button=btn):
                return "DRAG_START"
            return None

        elif event == DRAG_STOP:
            self.unlock_position()
            btn = getattr(self.settings, "left_click_button", "left")
            if self.mouse_up(button=btn):
                return "DRAG_STOP"
            return None

        elif event in (LEFT_CLICK, RIGHT_CLICK):
            # Check cooldown to prevent duplicate clicks
            if (timestamp - self.last_click_time) < self.click_cooldown_sec:
                logger.debug(f"Click suppressed by mouse controller cooldown ({event}).")
                return None

            if event == LEFT_CLICK:
                try:
                    if self.position_locked:
                        self.pyautogui.moveTo(self.locked_screen_x, self.locked_screen_y)
                    self.pyautogui.click(button=self.settings.left_click_button)
                    self.last_click_time = timestamp
                    self.total_left_clicks += 1
                    self.last_action = "LEFT_CLICK"
                    self.last_action_time = timestamp
                    logger.info("ACTUAL LEFT CLICK executed.")
                    return "LEFT_CLICK"
                except getattr(self.pyautogui, "FailSafeException", Exception) as e:
                    logger.critical(f"PyAutoGUI FailSafeException during left click: {e}")
                    self.failsafe_triggered = True
                    self.emergency_stop()
                    return None
                except Exception as e:
                    logger.error(f"Error executing actual left click: {e}")
                    return None

            elif event == RIGHT_CLICK:
                try:
                    if self.position_locked:
                        self.pyautogui.moveTo(self.locked_screen_x, self.locked_screen_y)
                    self.pyautogui.click(button=self.settings.right_click_button)
                    self.last_click_time = timestamp
                    self.total_right_clicks += 1
                    self.last_action = "RIGHT_CLICK"
                    self.last_action_time = timestamp
                    logger.info("ACTUAL RIGHT CLICK executed.")
                    return "RIGHT_CLICK"
                except getattr(self.pyautogui, "FailSafeException", Exception) as e:
                    logger.critical(f"PyAutoGUI FailSafeException during right click: {e}")
                    self.failsafe_triggered = True
                    self.emergency_stop()
                    return None
                except Exception as e:
                    logger.error(f"Error executing actual right click: {e}")
                    return None

        return None

    def get_status(self) -> dict[str, Any]:
        """Return rich telemetry dictionary for dashboard overlay."""
        can_run, reason = self.can_operate()
        return {
            "enabled": self.enabled,
            "emergency_stopped": self.emergency_stopped,
            "can_operate": can_run,
            "status_reason": reason,
            "screen_x": self.screen_x,
            "screen_y": self.screen_y,
            "screen_width": self.screen_width,
            "screen_height": self.screen_height,
            "has_face": self.has_face,
            "is_calibrated": self.is_calibrated,
            "last_action": self.last_action,
            "total_moves": self.total_moves,
            "total_left_clicks": self.total_left_clicks,
            "total_right_clicks": self.total_right_clicks,
            "total_drags": self.total_drags,
            "total_scrolls": self.total_scrolls,
            "total_zooms": self.total_zooms,
            "is_mouse_down": self.is_mouse_down,
            "is_dragging": self.is_dragging,
            "is_scrolling": self.is_scrolling,
            "position_locked": self.position_locked,
            "failsafe_triggered": self.failsafe_triggered,
        }
