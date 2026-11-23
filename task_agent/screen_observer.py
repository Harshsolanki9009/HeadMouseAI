"""Screen Observer for Jadoo Task Agent.

Provides on-demand desktop screen capture, active window identification,
geometry measurement, and structured UI Automation (UIA) tree snapshots via
Vercel Labs agent-desktop for AI visual and structural understanding.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from jadoo_assistant.screen_capture import ScreenCapture
from task_agent.agent_desktop_adapter import AgentDesktopAdapter
from utils.logger import logger


@dataclass
class WindowInfo:
    """Information regarding the currently active/focused desktop window."""
    hwnd: int
    title: str
    left: int
    top: int
    right: int
    bottom: int
    width: int
    height: int


class ScreenObserver:
    """Captures desktop state, inspects focused window metrics, and snapshots UIA trees."""

    def __init__(
        self,
        capture_max_dim: int = 1280,
        capture_quality: int = 75,
        agent_desktop: Optional[AgentDesktopAdapter] = None,
    ) -> None:
        self.capture_max_dim = capture_max_dim
        self.capture_quality = capture_quality
        self.agent_desktop = agent_desktop or AgentDesktopAdapter()

    def observe(self) -> Tuple[Optional[bytes], Optional[str], Optional[WindowInfo]]:
        """Capture current screen JPEG and active window information.

        Returns:
            Tuple of (jpeg_bytes, base64_jpeg, active_window_info)
        """
        jpeg_bytes, b64_str, err = ScreenCapture.capture_screen_jpeg(
            max_dimension=self.capture_max_dim,
            quality=self.capture_quality,
        )
        if err:
            logger.warning(f"ScreenObserver capture error: {err}")

        win_info = self.get_active_window_info()
        return jpeg_bytes, b64_str, win_info

    def snapshot_uia(
        self,
        app_name: Optional[str] = None,
        window_id: Optional[str] = None,
        root_ref: Optional[str] = None,
        interactive_only: bool = True,
        compact: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Capture Windows UI Automation tree via agent-desktop."""
        if not self.agent_desktop or not self.agent_desktop.is_available():
            return None

        try:
            res = self.agent_desktop.snapshot(
                app_name=app_name,
                window_id=window_id,
                root_ref=root_ref,
                interactive_only=interactive_only,
                compact=compact,
            )
            if res.get("ok", False):
                return res.get("data", {})
        except Exception as e:
            logger.debug(f"ScreenObserver snapshot_uia error: {e}")

        return None

    def observe_with_uia(
        self,
        app_name: Optional[str] = None,
        window_id: Optional[str] = None,
    ) -> Tuple[Optional[bytes], Optional[str], Optional[WindowInfo], Optional[Dict[str, Any]]]:
        """Capture visual JPEG screenshot, active window info, and native UIA tree snapshot."""
        jpeg_bytes, b64_str, win_info = self.observe()
        uia_data = self.snapshot_uia(app_name=app_name, window_id=window_id)
        return jpeg_bytes, b64_str, win_info, uia_data

    @staticmethod
    def get_active_window_info() -> Optional[WindowInfo]:
        """Query Windows user32 for foreground window title and bounding rect."""
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None

            # Get Title
            buf_len = 512
            buf = ctypes.create_unicode_buffer(buf_len)
            user32.GetWindowTextW(hwnd, buf, buf_len)
            title = buf.value.strip()

            # Get Rect
            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            rect = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = max(0, rect.right - rect.left)
            h = max(0, rect.bottom - rect.top)

            return WindowInfo(
                hwnd=hwnd,
                title=title,
                left=rect.left,
                top=rect.top,
                right=rect.right,
                bottom=rect.bottom,
                width=w,
                height=h,
            )
        except Exception as e:
            logger.debug(f"Could not read active window info: {e}")
            return None
