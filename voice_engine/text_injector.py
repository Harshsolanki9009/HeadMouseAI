"""Safe Unicode text injector for Jadoo Voice Engine.

Injects speech-to-text output into active desktop controls via the Windows
clipboard and synthetic paste (Ctrl+V), with automatic clipboard preservation
and restoration to prevent user data loss. Supports full UTF-8 Unicode
including Hindi (Devanagari), English, and mixed Hinglish scripts.
"""

from __future__ import annotations

import time
from typing import Optional

import pyautogui
import pyperclip

from utils.logger import logger


class TextInjector:
    """Safe clipboard-based text injector for multilingual Unicode dictation."""

    def __init__(self, restore_clipboard: bool = True, paste_delay_s: float = 0.08) -> None:
        self.restore_clipboard = restore_clipboard
        self.paste_delay_s = max(0.02, float(paste_delay_s))

    @staticmethod
    def is_app_foreground() -> bool:
        """Return True if HeadMouseAI application window currently has foreground focus."""
        try:
            from PySide6.QtWidgets import QApplication
            return QApplication.activeWindow() is not None
        except Exception:
            return False

    def inject_text(
        self,
        text: str,
        restore: Optional[bool] = None,
        only_external: bool = False,
    ) -> bool:
        """Inject Unicode text into active desktop window at current cursor location.

        Args:
            text: Unicode string to insert (Devanagari, Latin, digits, symbols).
            restore: Override default restore_clipboard setting if specified.
            only_external: If True, avoid simulating Ctrl+V when HeadMouseAI itself has foreground focus.

        Returns:
            True if text was successfully copied and paste command was dispatched.
        """
        if not text:
            return False

        if only_external and self.is_app_foreground():
            logger.debug("Skipping synthetic paste: HeadMouseAI application has foreground focus.")
            return False

        should_restore = self.restore_clipboard if restore is None else restore
        prev_clipboard: Optional[str] = None

        if should_restore:
            try:
                prev_clipboard = pyperclip.paste()
            except Exception as e:
                logger.debug(f"Could not read previous clipboard content: {e}")
                prev_clipboard = None

        try:
            # 1. Set clipboard with new UTF-8 text
            pyperclip.copy(text)
            time.sleep(0.02)  # Short settling time for Windows clipboard

            # 2. Simulate Ctrl+V to paste into active window
            pyautogui.hotkey("ctrl", "v")

            # 3. Allow target application to process paste event
            time.sleep(self.paste_delay_s)

            logger.info(f"Injected dictation text ({len(text)} chars): '{text[:30]}...'")
            return True

        except Exception as e:
            logger.error(f"Failed to inject dictation text: {e}")
            return False

        finally:
            # 4. Restore original clipboard content if configured
            if should_restore and prev_clipboard is not None:
                try:
                    time.sleep(0.05)
                    pyperclip.copy(prev_clipboard)
                except Exception as e:
                    logger.debug(f"Failed to restore original clipboard: {e}")
