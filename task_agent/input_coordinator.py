"""Input Ownership Coordinator for HeadMouseAI and Jadoo Task Agent.

Guarantees mutually exclusive control of the Windows mouse and keyboard.
Prevents competing mouse loops between nose tracking and autonomous agent execution.
Implements the strict 4-mode state machine:
- MANUAL_MODE: Physical user mouse and keyboard; automation inactive
- HEADMOUSE_MODE: HeadMouseAI nose-tip cursor owns movement and wink clicks
- AGENT_MODE: Autonomous AI computer-use agent owns mouse and keyboard
- PAUSED_MODE: All automated input paused, hardware keys/buttons safely released
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from PySide6.QtCore import QObject, Signal

from utils.logger import logger


class InputOwnershipMode(str, Enum):
    """Mutually exclusive input control modes."""
    MANUAL = "MANUAL"                   # Physical user mouse and keyboard
    HEAD_MOUSE = "HEAD_MOUSE"           # Nose-tip cursor tracking active
    AUTONOMOUS_AI = "AUTONOMOUS_AI"     # Autonomous AI Task Agent active
    PAUSED = "PAUSED"                   # All automated input paused

    # Aliases for backwards compatibility
    MANUAL_MODE = "MANUAL"
    HEADMOUSE_MODE = "HEAD_MOUSE"
    AGENT_MODE = "AUTONOMOUS_AI"
    PAUSED_MODE = "PAUSED"


class InputOwnershipCoordinator(QObject):
    """Authoritative input ownership coordinator with strict mutual exclusion."""

    sig_mode_changed = Signal(str)       # Emits current mode string

    def __init__(
        self,
        vision_worker: Optional[Any] = None,
        keyboard_controller: Optional[Any] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.vision_worker = vision_worker
        self.keyboard_controller = keyboard_controller

        self._mode = InputOwnershipMode.MANUAL_MODE
        self._previous_mode = InputOwnershipMode.MANUAL_MODE
        self._was_headmouse_active: bool = False

    @property
    def mode(self) -> InputOwnershipMode:
        """Current input ownership mode."""
        return self._mode

    def set_mode(self, new_mode: InputOwnershipMode | str) -> bool:
        """Explicitly switch the active input ownership mode with strict mutual exclusion."""
        if isinstance(new_mode, str):
            try:
                new_mode = InputOwnershipMode(new_mode)
            except ValueError:
                # Handle common aliases
                mode_str = new_mode.upper().strip()
                if "MANUAL" in mode_str:
                    new_mode = InputOwnershipMode.MANUAL
                elif "HEAD" in mode_str or "NOSE" in mode_str:
                    new_mode = InputOwnershipMode.HEAD_MOUSE
                elif "AGENT" in mode_str or "AUTO" in mode_str:
                    new_mode = InputOwnershipMode.AUTONOMOUS_AI
                elif "PAUSE" in mode_str:
                    new_mode = InputOwnershipMode.PAUSED
                else:
                    logger.warning(f"Unknown input ownership mode requested: {new_mode}")
                    return False

        if self._mode == new_mode:
            return True

        logger.info(f"InputOwnershipCoordinator: Transitioning from {self._mode.value} -> {new_mode.value}")

        # 1. Always safely release hardware buttons and keys before any transition
        self.safety_release_all_inputs()

        self._previous_mode = self._mode

        if new_mode == InputOwnershipMode.MANUAL_MODE:
            # Pause / disable automated cursor
            if self.vision_worker and hasattr(self.vision_worker, "pause_cursor"):
                self.vision_worker.pause_cursor()
            self._mode = InputOwnershipMode.MANUAL_MODE

        elif new_mode == InputOwnershipMode.HEADMOUSE_MODE:
            # Enable and resume HeadMouse cursor
            if self.vision_worker:
                if hasattr(self.vision_worker, "set_real_mouse_enabled"):
                    self.vision_worker.set_real_mouse_enabled(True)
                if hasattr(self.vision_worker, "resume_cursor"):
                    self.vision_worker.resume_cursor()
            self._mode = InputOwnershipMode.HEADMOUSE_MODE

        elif new_mode == InputOwnershipMode.AGENT_MODE:
            # Check if headmouse was active so we can restore it later
            if self.vision_worker:
                m_stat = getattr(self.vision_worker.mouse_controller, "get_status", lambda: {})()
                self._was_headmouse_active = bool(m_stat.get("enabled", False) and not m_stat.get("is_paused", False))
                # Pause headmouse cursor while allowing facial tracking to continue for telemetry
                if hasattr(self.vision_worker, "pause_cursor"):
                    self.vision_worker.pause_cursor()
            self._mode = InputOwnershipMode.AGENT_MODE

        elif new_mode == InputOwnershipMode.PAUSED_MODE:
            if self.vision_worker and hasattr(self.vision_worker, "pause_cursor"):
                self.vision_worker.pause_cursor()
            self._mode = InputOwnershipMode.PAUSED_MODE

        self.sig_mode_changed.emit(self._mode.value)
        return True

    def acquire_agent_ownership(self) -> bool:
        """Transfer exclusive mouse and keyboard ownership to the Task Agent.

        Pauses HeadMouseAI cursor movement, releases any held mouse buttons,
        and preserves face/nose calibration.
        """
        return self.set_mode(InputOwnershipMode.AGENT_MODE)

    def release_agent_ownership(self, restore_headmouse: bool = False) -> None:
        """Release Task Agent ownership and restore previous input state.

        Releases all held buttons and keys before restoring.
        """
        logger.info(f"Releasing AGENT_MODE ownership (restore_headmouse={restore_headmouse})...")
        self.safety_release_all_inputs()

        if restore_headmouse and self._was_headmouse_active and self.vision_worker:
            ok = False
            if hasattr(self.vision_worker, "resume_cursor"):
                ok = self.vision_worker.resume_cursor()
            if ok:
                self._mode = InputOwnershipMode.HEADMOUSE_MODE
                self.sig_mode_changed.emit(self._mode.value)
                logger.info("HEADMOUSE_MODE safely restored.")
                return

        self._mode = InputOwnershipMode.MANUAL_MODE
        self.sig_mode_changed.emit(self._mode.value)
        logger.info("Input ownership transitioned to MANUAL_MODE.")

    def pause_all(self) -> None:
        """Freeze all automated input immediately."""
        self.set_mode(InputOwnershipMode.PAUSED_MODE)

    def resume_mode(self) -> None:
        """Resume previous ownership state."""
        if self._mode == InputOwnershipMode.PAUSED_MODE:
            target = self._previous_mode if self._previous_mode != InputOwnershipMode.PAUSED_MODE else InputOwnershipMode.MANUAL_MODE
            self.set_mode(target)
            logger.info(f"Resumed ownership to: {self._mode.value}")

    def safety_release_all_inputs(self) -> None:
        """Release any held mouse buttons or keyboard keys via PyAutoGUI and MouseController."""
        try:
            import pyautogui
            pyautogui.mouseUp(button="left")
            pyautogui.mouseUp(button="right")
            for key in ("ctrl", "shift", "alt", "win"):
                try:
                    pyautogui.keyUp(key)
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Exception during safety input release: {e}")

        if self.vision_worker and hasattr(self.vision_worker, "mouse_controller"):
            self.vision_worker.mouse_controller.release_all_buttons()
