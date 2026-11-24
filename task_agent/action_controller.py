"""Visible Action Controller for Jadoo Task Agent.

Dispatches visible Windows mouse movements, clicks, keyboard typing,
application launches, and hotkeys via Vercel Labs agent-desktop as the
primary engine, with PyAutoGUI retained as a coordinate-based fallback.
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import Any, List, Optional, Tuple, Union

import pyautogui
import pyperclip

from task_agent.action_overlay import ActionOverlay
from task_agent.agent_desktop_adapter import AgentDesktopAdapter
from utils.logger import logger

# Common Windows application executable mappings
APP_LAUNCH_MAP = {
    "notepad": "notepad.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "edge": "msedge.exe",
    "msedge": "msedge.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "terminal": "cmd.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "paint": "mspaint.exe",
}


class ActionController:
    """Executes visible mouse, keyboard, and application automation."""

    def __init__(
        self,
        py_backend: Any = None,
        overlay: Optional[ActionOverlay] = None,
        default_move_duration: float = 0.45,
        agent_desktop: Optional[AgentDesktopAdapter] = None,
    ) -> None:
        self._has_custom_py_backend = py_backend is not None
        self.pyautogui = py_backend if py_backend is not None else pyautogui
        self.overlay = overlay
        self.default_move_duration = max(0.1, float(default_move_duration))
        self.agent_desktop = agent_desktop or AgentDesktopAdapter()

        # Disable PyAutoGUI corner failsafe (we use global F9 Emergency Stop instead)
        try:
            self.pyautogui.FAILSAFE = False
        except Exception:
            pass

    def launch_application(self, app_name: str) -> Tuple[bool, str]:
        """Launch a Windows desktop application or open a URL / folder."""
        clean_name = app_name.strip()
        lower_name = clean_name.lower()

        # Handle direct URLs
        if lower_name.startswith("http://") or lower_name.startswith("https://"):
            try:
                if self.overlay:
                    self.overlay.show_action(f"Opening {clean_name[:35]}...")
                os.startfile(clean_name)
                time.sleep(1.0)
                return True, f"Opened URL {clean_name}"
            except Exception as e:
                return False, f"Failed opening URL {clean_name}: {e}"

        cmd = APP_LAUNCH_MAP.get(lower_name, clean_name)

        # Resolve explicit paths for common browsers on Windows
        if lower_name in ("chrome", "google chrome"):
            for p in (
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            ):
                if os.path.exists(p):
                    cmd = f'"{p}"'
                    break

        elif lower_name in ("edge", "msedge"):
            for p in (
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            ):
                if os.path.exists(p):
                    cmd = f'"{p}"'
                    break

        if self.overlay:
            self.overlay.show_action(f"Launching {app_name}...")

        logger.info(f"TaskAgent launching application: '{cmd}'")
        try:
            # If agent-desktop is available and no custom mock backend is used, try agent-desktop launch
            if self.agent_desktop and self.agent_desktop.is_available() and not self._has_custom_py_backend:
                # agent-desktop expects bare executable or app name
                clean_target = "chrome.exe" if "chrome" in lower_name else ("msedge.exe" if "edge" in lower_name else cmd)
                res = self.agent_desktop.launch_app(clean_target, activate=True, timeout_ms=8000)
                if res.get("ok", False):
                    time.sleep(0.5)
                    return True, f"Launched {app_name} via agent-desktop"

            # Fallback to subprocess execution
            subprocess.Popen(cmd, shell=True)
            time.sleep(1.2)  # Allow window to appear and initialize
            return True, f"Launched {app_name}"
        except Exception as e:
            msg = f"Failed to launch application '{app_name}': {e}"
            logger.error(msg)
            return False, msg

    def move_mouse_visible(self, x: int, y: int, duration: Optional[float] = None) -> bool:
        """Move cursor visibly across the desktop with smooth easing."""
        dur = self.default_move_duration if duration is None else duration
        try:
            sz = self.pyautogui.size()
            max_w, max_h = sz[0], sz[1]
            safe_x = max(1, min(max_w - 2, int(x)))
            safe_y = max(1, min(max_h - 2, int(y)))

            if self._has_custom_py_backend or not (self.agent_desktop and self.agent_desktop.is_available()):
                self.pyautogui.moveTo(safe_x, safe_y, duration=dur, tween=self.pyautogui.easeInOutQuad)
            else:
                # Dispatch visible headed movement via agent-desktop, supplemented by smooth visual easing
                try:
                    self.pyautogui.moveTo(safe_x, safe_y, duration=dur, tween=self.pyautogui.easeInOutQuad)
                except Exception:
                    pass
                self.agent_desktop.mouse_move(safe_x, safe_y, headed=True)

            return True
        except Exception as e:
            logger.error(f"Error moving mouse to ({x}, {y}): {e}")
            return False

    def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
        ref_id: Optional[str] = None,
    ) -> bool:
        """Move cursor visibly to target and perform click with visual halo indicator."""
        try:
            # 1. Target is an agent-desktop UIA element ref
            if ref_id and self.agent_desktop and self.agent_desktop.is_available():
                bounds = self.agent_desktop.get_bounds(ref_id)
                if bounds:
                    cx = int(bounds["x"] + bounds["width"] / 2.0)
                    cy = int(bounds["y"] + bounds["height"] / 2.0)
                    self.move_mouse_visible(cx, cy)
                    if self.overlay:
                        self.overlay.trigger_click_halo(cx, cy)
                res = self.agent_desktop.click(ref_id, button=button, headed=True)
                if res.get("ok", False):
                    logger.info(f"TaskAgent clicked ref {ref_id} via agent-desktop [{button}]")
                    return True
                # If ref action failed, fall through to coordinate click if bounds were available
                if not bounds:
                    return False
                x, y = cx, cy

            # 2. Coordinate-based click
            if x is not None and y is not None:
                self.move_mouse_visible(x, y)
                cur_x, cur_y = x, y
            else:
                pos = self.pyautogui.position()
                cur_x, cur_y = pos[0], pos[1]

            # Trigger visual halo indicator on overlay
            if self.overlay:
                self.overlay.trigger_click_halo(int(cur_x), int(cur_y))

            time.sleep(0.08)
            if self._has_custom_py_backend or not (self.agent_desktop and self.agent_desktop.is_available()):
                self.pyautogui.click(cur_x, cur_y, button=button)
            else:
                res = self.agent_desktop.mouse_click(int(cur_x), int(cur_y), button=button, headed=True)
                if not res.get("ok", False):
                    self.pyautogui.click(cur_x, cur_y, button=button)

            logger.info(f"TaskAgent visible click at ({cur_x}, {cur_y}) [{button}]")
            return True
        except Exception as e:
            logger.error(f"Error executing click: {e}")
            return False

    def double_click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        ref_id: Optional[str] = None,
    ) -> bool:
        """Perform visible double click."""
        try:
            if ref_id and self.agent_desktop and self.agent_desktop.is_available():
                bounds = self.agent_desktop.get_bounds(ref_id)
                if bounds:
                    cx = int(bounds["x"] + bounds["width"] / 2.0)
                    cy = int(bounds["y"] + bounds["height"] / 2.0)
                    self.move_mouse_visible(cx, cy)
                    if self.overlay:
                        self.overlay.trigger_click_halo(cx, cy)
                res = self.agent_desktop.double_click(ref_id, headed=True)
                if res.get("ok", False):
                    logger.info(f"TaskAgent double-clicked ref {ref_id} via agent-desktop")
                    return True

            if x is not None and y is not None:
                self.move_mouse_visible(x, y)
                cur_x, cur_y = x, y
            else:
                pos = self.pyautogui.position()
                cur_x, cur_y = pos[0], pos[1]

            if self.overlay:
                self.overlay.trigger_click_halo(int(cur_x), int(cur_y))

            self.pyautogui.doubleClick(cur_x, cur_y)
            logger.info(f"TaskAgent double-click at ({cur_x}, {cur_y})")
            return True
        except Exception as e:
            logger.error(f"Error executing double click: {e}")
            return False

    def type_text(
        self,
        text: str,
        ref_id: Optional[str] = None,
        use_clipboard_for_long: bool = True,
    ) -> bool:
        """Type text into focused application or specific UIA target ref.

        For specific @ref targets, sets value directly or uses headed keystrokes.
        For short ascii strings, types with realistic typing interval.
        For multiline or Unicode (Hindi, accents), pastes safely via clipboard.
        """
        if not text:
            return False

        if self.overlay:
            preview = text[:25] + "..." if len(text) > 25 else text
            self.overlay.show_action(f"Typing: '{preview}'")

        try:
            # 1. Target element ref via agent-desktop
            if ref_id and self.agent_desktop and self.agent_desktop.is_available():
                # Try set_value first (instant & exact)
                res_set = self.agent_desktop.set_value(ref_id, text)
                if res_set.get("ok", False):
                    logger.info(f"TaskAgent set text value on ref {ref_id} via agent-desktop")
                    return True

                # Fallback to headed typing on ref
                res_type = self.agent_desktop.type_text(ref_id, text, headed=True)
                if res_type.get("ok", False):
                    logger.info(f"TaskAgent typed into ref {ref_id} via agent-desktop")
                    return True

            # 2. General keyboard typing fallback
            has_unicode = any(ord(c) > 127 for c in text)
            if has_unicode or (use_clipboard_for_long and len(text) > 40):
                prev_cb = pyperclip.paste()
                pyperclip.copy(text)
                time.sleep(0.05)
                self.pyautogui.hotkey("ctrl", "v")
                time.sleep(0.08)
                pyperclip.copy(prev_cb)
            else:
                self.pyautogui.write(text, interval=0.03)

            logger.info(f"TaskAgent typed text ({len(text)} chars)")
            return True
        except Exception as e:
            logger.error(f"Error typing text: {e}")
            return False

    def set_element_value(self, ref_id: str, value: str) -> bool:
        """Set UIA element value directly via agent-desktop."""
        if not self.agent_desktop or not self.agent_desktop.is_available():
            return False
        res = self.agent_desktop.set_value(ref_id, value)
        return bool(res.get("ok", False))

    def press_hotkey(self, *keys: str, app_name: Optional[str] = None) -> bool:
        """Press compound hotkey (e.g. ('ctrl', 's'))."""
        if not keys:
            return False
        if self.overlay:
            self.overlay.show_action(f"Hotkey: {' + '.join(keys).upper()}")
        try:
            if not self._has_custom_py_backend and self.agent_desktop and self.agent_desktop.is_available():
                combo = "+".join(k.lower() for k in keys)
                res = self.agent_desktop.press_key(combo, app_name=app_name, headed=True)
                if res.get("ok", False):
                    logger.info(f"TaskAgent pressed hotkey via agent-desktop: {combo}")
                    return True

            self.pyautogui.hotkey(*keys)
            logger.info(f"TaskAgent hotkey: {'+'.join(keys)}")
            return True
        except Exception as e:
            logger.error(f"Error executing hotkey {keys}: {e}")
            return False

    def scroll(self, clicks: int) -> bool:
        """Scroll vertical wheel."""
        if clicks == 0:
            return False
        try:
            self.pyautogui.scroll(clicks)
            logger.info(f"TaskAgent scrolled {clicks} clicks")
            return True
        except Exception as e:
            logger.error(f"Error scrolling: {e}")
            return False

    def wait(self, seconds: float) -> bool:
        """Wait pause."""
        time.sleep(max(0.05, float(seconds)))
        return True
