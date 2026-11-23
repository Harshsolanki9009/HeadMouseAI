"""Operating Mode Finite State Machine for Jadoo Accessibility System.

Enforces strict isolation between Dictation Mode and Command Mode.
When Dictation Mode is active, speech is NEVER executed as commands, and is
strictly routed as literal text, except for the dedicated 'typing off' exit phrase.
"""

from __future__ import annotations

from enum import Enum
import time
from typing import Optional, Tuple

from utils.logger import logger
from voice_engine.command_engine import CommandEngine
from voice_engine.command_registry import AccessibilityCommand


class JadooOperatingMode(str, Enum):
    """Explicit operating states of the Jadoo accessibility subsystem."""
    IDLE = "IDLE"                         # Voice engine not listening
    WAKE_LISTENING = "WAKE_LISTENING"     # Listening for wake phrase or commands
    COMMAND_MODE = "COMMAND_MODE"         # Active command recognition mode
    DICTATION_MODE = "DICTATION_MODE"     # Typing is ON; verbatim text output
    PROCESSING = "PROCESSING"             # Query or complex action being handled
    STOPPED = "STOPPED"                   # Emergency stop triggered


class ModeRouter:
    """Routes transcribed speech according to the active operating mode.

    CRITICAL ARCHITECTURAL ISOLATION RULE:
    - In DICTATION_MODE:
        Checks ONLY for the exact dedicated exit command (TYPING_OFF).
        If exit command: switches mode to COMMAND_MODE.
        If NOT exit command: routes text strictly to dictation (literal injection).
        Normal commands (backspace, clear all, mouse off, etc.) are TYPED VERBATIM.
    - In COMMAND_MODE / WAKE_LISTENING:
        Routes speech to CommandEngine.
        'typing on' switches mode to DICTATION_MODE.
    """

    def __init__(
        self,
        initial_mode: JadooOperatingMode = JadooOperatingMode.WAKE_LISTENING,
        command_engine: Optional[CommandEngine] = None,
    ) -> None:
        self._mode = initial_mode
        self.command_engine = command_engine or CommandEngine()

    @property
    def mode(self) -> JadooOperatingMode:
        """Current operating mode."""
        return self._mode

    def set_mode(self, new_mode: JadooOperatingMode) -> None:
        """Set active operating mode."""
        if self._mode != new_mode:
            prev = self._mode
            self._mode = new_mode
            logger.info(f"Jadoo mode transitioned: {prev.value} -> {new_mode.value}")

    def route_speech(
        self,
        text: str,
    ) -> Tuple[str, Optional[AccessibilityCommand], str]:
        """Route transcribed speech according to strict mode isolation rules.

        Args:
            text: Transcribed speech from Whisper STT.

        Returns:
            Tuple of:
            - route_action: 'DICTATE_TEXT' | 'EXECUTE_COMMAND' | 'WAKE_QUERY' | 'IGNORE'
            - command: Optional[AccessibilityCommand] if matched
            - payload: Transcribed text for dictation, or query text for wake/command
        """
        clean_text = text.strip()
        if not clean_text:
            return "IGNORE", None, ""

        # If system is in STOPPED or IDLE mode
        if self._mode == JadooOperatingMode.STOPPED:
            logger.debug(f"Speech ignored in STOPPED mode: '{clean_text}'")
            return "IGNORE", None, ""

        # ------------------------------------------------------------- #
        # 1. STRICT DICTATION MODE ROUTE                                #
        # ------------------------------------------------------------- #
        if self._mode == JadooOperatingMode.DICTATION_MODE:
            # Check ONLY for dedicated dictation exit phrases without updating command history
            matched_cmd, conf, _ = self.command_engine.match(clean_text, enforce_cooldown=False, update_history=False)
            if matched_cmd == AccessibilityCommand.TYPING_OFF:
                logger.info(f"Dictation exit phrase detected: '{clean_text}'. Exiting DICTATION_MODE.")
                self.command_engine._last_command = matched_cmd
                self.command_engine._last_command_time = time.monotonic()
                self.set_mode(JadooOperatingMode.COMMAND_MODE)
                return "EXECUTE_COMMAND", AccessibilityCommand.TYPING_OFF, ""

            # Check emergency stop command even during dictation for safety
            if matched_cmd in (AccessibilityCommand.EMERGENCY_STOP, AccessibilityCommand.STOP_ALL):
                logger.warning(f"Safety stop detected during dictation: '{clean_text}'")
                self.command_engine._last_command = matched_cmd
                self.command_engine._last_command_time = time.monotonic()
                self.set_mode(JadooOperatingMode.STOPPED)
                return "EXECUTE_COMMAND", matched_cmd, ""

            # MANDATORY: ALL OTHER SPEECH IS STRICTLY LITERAL DICTATION TEXT
            # Words like "backspace", "clear all", "mouse off", "scroll up" are typed as plain text!
            logger.info(f"Dictation mode active: treating '{clean_text}' strictly as literal text.")
            return "DICTATE_TEXT", None, clean_text

        # ------------------------------------------------------------- #
        # 2. COMMAND MODE / WAKE LISTENING ROUTE                       #
        # ------------------------------------------------------------- #
        matched_cmd, conf, remainder = self.command_engine.match(clean_text)

        if matched_cmd is not None:
            if matched_cmd == AccessibilityCommand.TYPING_ON:
                logger.info("Command 'typing on' recognized. Switching to DICTATION_MODE.")
                self.set_mode(JadooOperatingMode.DICTATION_MODE)
                return "EXECUTE_COMMAND", AccessibilityCommand.TYPING_ON, ""

            elif matched_cmd == AccessibilityCommand.WAKE_UP:
                logger.info(f"Wake phrase recognized. Query: '{remainder}'")
                self.set_mode(JadooOperatingMode.COMMAND_MODE)
                return "WAKE_QUERY", AccessibilityCommand.WAKE_UP, remainder

            elif matched_cmd in (AccessibilityCommand.EMERGENCY_STOP, AccessibilityCommand.STOP_ALL):
                self.set_mode(JadooOperatingMode.STOPPED)
                return "EXECUTE_COMMAND", matched_cmd, ""

            else:
                return "EXECUTE_COMMAND", matched_cmd, remainder

        # In command mode, non-command speech is ignored or passed to assistant if wake query
        logger.debug(f"Unmatched speech in {self._mode.value} ignored: '{clean_text}'")
        return "IGNORE", None, clean_text
