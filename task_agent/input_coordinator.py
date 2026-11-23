"""Input Ownership Coordinator for HeadMouseAI and Jadoo Task Agent.

Guarantees mutually exclusive control of the Windows mouse and keyboard.
Prevents competing mouse loops between nose tracking and autonomous agent execution.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from utils.logger import logger


class InputOwnershipMode(str, Enum):
    """Mutually exclusive input control modes."""
    MANUAL_MODE = "MANUAL_MODE"          # Physical user mouse and keyboard
    HEADMOUSE_MODE = "HEADMOUSE_MODE"    # Nose-tip cursor tracking active
    AGENT_MODE = "AGENT_MODE"            # Autonomous AI Task Agent active
    PAUSED_MODE = "PAUSED_MODE"          # All automated input paused


class InputOwnershipCoordinator:
    """Coordinates seamless ownership transitions between HeadMouseAI and Task Agent."""

    def __init__(
        self,
        vision_worker: Optional[Any] = None,
        keyboard_controller: Optional[Any] = None,
    ) -> None:
        self.vision_worker = vision_worker
        self.keyboard_controller = keyboard_controller

        self._mode = InputOwnershipMode.MANUAL_MODE
        self._previous_mode = InputOwnershipMode.MANUAL_MODE
        self._was_headmouse_active: bool = False

    @property
    def mode(self) -> InputOwnershipMode:
        """Current input ownership mode."""
        return self._mode

    def acquire_agent_ownership(self) -> bool:
        """Transfer exclusive mouse and keyboard ownership to the Task Agent.

        Pauses HeadMouseAI cursor movement, releases any held mouse buttons,
        and preserves face/nose calibration.
        """
        logger.info("Acquiring AGENT_MODE input ownership...")
        self._previous_mode = self._mode

        # Check if HeadMouseAI was active
        if self.vision_worker:
            m_stat = getattr(self.vision_worker.mouse_controller, "get_status", lambda: {})()
            self._was_headmouse_active = bool(m_stat.get("enabled", False) and not m_stat.get("is_paused", False))

            # Pause HeadMouseAI safely
            if hasattr(self.vision_worker, "pause_cursor"):
                self.vision_worker.pause_cursor()
            if hasattr(self.vision_worker, "mouse_controller"):
                self.vision_worker.mouse_controller.release_all_buttons()

        self._mode = InputOwnershipMode.AGENT_MODE
        logger.info(f"AGENT_MODE acquired. (Previous headmouse active: {self._was_headmouse_active})")
        return True

    def release_agent_ownership(self, restore_headmouse: bool = False) -> None:
        """Release Task Agent ownership and restore previous input state.

        Releases all held buttons and keys before restoring.
        """
        logger.info(f"Releasing AGENT_MODE ownership (restore_headmouse={restore_headmouse})...")

        # 1. Hardware safety release
        self.safety_release_all_inputs()

        # 2. Decide next mode
        if restore_headmouse and self._was_headmouse_active and self.vision_worker:
            if hasattr(self.vision_worker, "resume_cursor"):
                ok = self.vision_worker.resume_cursor()
                if ok:
                    self._mode = InputOwnershipMode.HEADMOUSE_MODE
                    logger.info("HEADMOUSE_MODE safely restored.")
                    return

        # Default back to manual user mode
        self._mode = InputOwnershipMode.MANUAL_MODE
        logger.info("Input ownership transitioned to MANUAL_MODE.")

    def pause_all(self) -> None:
        """Freeze all automated input."""
        logger.info("Pausing all automated input...")
        self.safety_release_all_inputs()
        if self.vision_worker and hasattr(self.vision_worker, "pause_cursor"):
            self.vision_worker.pause_cursor()
        self._mode = InputOwnershipMode.PAUSED_MODE

    def resume_mode(self) -> None:
        """Resume previous ownership state."""
        if self._mode == InputOwnershipMode.PAUSED_MODE:
            self._mode = self._previous_mode
            logger.info(f"Resumed ownership to: {self._mode.value}")

    def safety_release_all_inputs(self) -> None:
        """Release any held mouse buttons or keyboard keys via PyAutoGUI."""
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
