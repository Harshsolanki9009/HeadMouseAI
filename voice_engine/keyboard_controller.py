"""Safe Keyboard Action Controller for Jadoo Accessibility System.

Translates accessibility commands into safe OS keyboard shortcuts and actions
using PyAutoGUI with debouncing, error handling, and guardrails against
accidental file or destructive system operations.
"""

from __future__ import annotations

import time
from typing import Any, Optional

import pyautogui

from utils.logger import logger
from voice_engine.command_registry import AccessibilityCommand


class KeyboardActionController:
    """Dispatches safe keyboard shortcuts and text editing operations."""

    def __init__(
        self,
        py_backend: Any = None,
        action_delay_sec: float = 0.05,
        min_interval_sec: float = 0.25,
    ) -> None:
        """Initialize KeyboardActionController.

        Args:
            py_backend: Optional backend (defaults to pyautogui, allows mocking in tests).
            action_delay_sec: Small settling pause between compound keystrokes.
            min_interval_sec: Debounce interval to suppress rapid duplicate keystrokes.
        """
        self.pyautogui = py_backend if py_backend is not None else pyautogui
        self.action_delay_sec = max(0.01, float(action_delay_sec))
        self.min_interval_sec = max(0.05, float(min_interval_sec))

        self._last_action: Optional[str] = None
        self._last_action_time: float = 0.0

    def _debounce(self, action_name: str) -> bool:
        """Return True if action should proceed; False if debounced/suppressed."""
        now = time.monotonic()
        if action_name == self._last_action and (now - self._last_action_time) < self.min_interval_sec:
            logger.debug(f"Keyboard action '{action_name}' debounced.")
            return False
        self._last_action = action_name
        self._last_action_time = now
        return True

    def backspace(self) -> bool:
        """Press Backspace key to delete character before cursor."""
        if not self._debounce("backspace"):
            return False
        try:
            self.pyautogui.press("backspace")
            logger.info("Keyboard action: BACKSPACE executed.")
            return True
        except Exception as e:
            logger.error(f"Error executing backspace: {e}")
            return False

    def delete_word(self) -> bool:
        """Delete previous word using Ctrl + Backspace."""
        if not self._debounce("delete_word"):
            return False
        try:
            self.pyautogui.hotkey("ctrl", "backspace")
            logger.info("Keyboard action: DELETE_WORD (Ctrl+Backspace) executed.")
            return True
        except Exception as e:
            logger.error(f"Error executing delete_word: {e}")
            return False

    def clear_current_field(self) -> bool:
        """Safely clear text within the currently active/focused editable text field.

        IMPORTANT SAFETY SPECIFICATION:
        Does NOT execute destructive delete commands on files or explorer directories.
        Selects all text within the active input field (Ctrl+A) and replaces/clears
        it with Backspace.
        """
        if not self._debounce("clear_field"):
            return False
        try:
            # Compound action: Select All -> Backspace
            self.pyautogui.hotkey("ctrl", "a")
            time.sleep(self.action_delay_sec)
            self.pyautogui.press("backspace")
            logger.info("Keyboard action: CLEAR_CURRENT_FIELD (Ctrl+A -> Backspace) executed.")
            return True
        except Exception as e:
            logger.error(f"Error executing clear_current_field: {e}")
            return False

    def select_all(self) -> bool:
        """Select all text in active document or field (Ctrl + A)."""
        if not self._debounce("select_all"):
            return False
        try:
            self.pyautogui.hotkey("ctrl", "a")
            logger.info("Keyboard action: SELECT_ALL (Ctrl+A) executed.")
            return True
        except Exception as e:
            logger.error(f"Error executing select_all: {e}")
            return False

    def copy(self) -> bool:
        """Copy selected text or item (Ctrl + C)."""
        if not self._debounce("copy"):
            return False
        try:
            self.pyautogui.hotkey("ctrl", "c")
            logger.info("Keyboard action: COPY (Ctrl+C) executed.")
            return True
        except Exception as e:
            logger.error(f"Error executing copy: {e}")
            return False

    def paste(self) -> bool:
        """Paste clipboard content at cursor location (Ctrl + V)."""
        if not self._debounce("paste"):
            return False
        try:
            self.pyautogui.hotkey("ctrl", "v")
            logger.info("Keyboard action: PASTE (Ctrl+V) executed.")
            return True
        except Exception as e:
            logger.error(f"Error executing paste: {e}")
            return False

    def enter(self) -> bool:
        """Press Enter key."""
        if not self._debounce("enter"):
            return False
        try:
            self.pyautogui.press("enter")
            logger.info("Keyboard action: ENTER executed.")
            return True
        except Exception as e:
            logger.error(f"Error executing enter: {e}")
            return False

    def new_line(self) -> bool:
        """Insert a new line using Shift + Enter (or Enter)."""
        if not self._debounce("new_line"):
            return False
        try:
            self.pyautogui.hotkey("shift", "enter")
            logger.info("Keyboard action: NEW_LINE (Shift+Enter) executed.")
            return True
        except Exception as e:
            logger.error(f"Error executing new_line: {e}")
            return False

    def tab(self) -> bool:
        """Press Tab key to advance focus to next field."""
        if not self._debounce("tab"):
            return False
        try:
            self.pyautogui.press("tab")
            logger.info("Keyboard action: TAB executed.")
            return True
        except Exception as e:
            logger.error(f"Error executing tab: {e}")
            return False

    def undo(self) -> bool:
        """Undo last action (Ctrl + Z)."""
        if not self._debounce("undo"):
            return False
        try:
            self.pyautogui.hotkey("ctrl", "z")
            logger.info("Keyboard action: UNDO (Ctrl+Z) executed.")
            return True
        except Exception as e:
            logger.error(f"Error executing undo: {e}")
            return False

    def redo(self) -> bool:
        """Redo last undone action (Ctrl + Y)."""
        if not self._debounce("redo"):
            return False
        try:
            self.pyautogui.hotkey("ctrl", "y")
            logger.info("Keyboard action: REDO (Ctrl+Y) executed.")
            return True
        except Exception as e:
            logger.error(f"Error executing redo: {e}")
            return False

    def execute_command(self, cmd: AccessibilityCommand) -> bool:
        """Dispatch a canonical AccessibilityCommand to its corresponding keyboard action.

        Returns True if action was executed, False if unsupported or debounced.
        """
        handlers = {
            AccessibilityCommand.BACKSPACE: self.backspace,
            AccessibilityCommand.DELETE_WORD: self.delete_word,
            AccessibilityCommand.CLEAR_FIELD: self.clear_current_field,
            AccessibilityCommand.SELECT_ALL: self.select_all,
            AccessibilityCommand.COPY: self.copy,
            AccessibilityCommand.PASTE: self.paste,
            AccessibilityCommand.ENTER: self.enter,
            AccessibilityCommand.NEW_LINE: self.new_line,
            AccessibilityCommand.TAB: self.tab,
            AccessibilityCommand.UNDO: self.undo,
            AccessibilityCommand.REDO: self.redo,
        }
        handler = handlers.get(cmd)
        if handler:
            return handler()
        return False
