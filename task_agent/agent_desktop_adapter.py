"""Vercel Labs Agent-Desktop Adapter for Jadoo Task Agent.

Provides native Windows UI Automation (UIA) tree inspection, qualified @ref ID
interactions, visible headed cursor movements, typing, and state verification
via the official `agent-desktop` CLI binary.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from utils.logger import logger


class AgentDesktopAdapter:
    """Python bridge to the official Vercel Labs agent-desktop binary."""

    def __init__(self, executable_path: Optional[str] = None) -> None:
        self.executable_path = executable_path or self._locate_binary()
        self._is_available: Optional[bool] = None

    @staticmethod
    def _locate_binary() -> Optional[str]:
        """Locate the agent-desktop binary across common installation paths."""
        # 0. Bundled inside application assets (self-contained release)
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        bundled = os.path.join(base_dir, "assets", "bin", "agent-desktop", "agent-desktop.exe")
        if os.path.exists(bundled):
            return bundled

        # 1. Direct native win32-x64 binary in global npm cache (fastest, no cmd wrapper)
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            direct_bin = os.path.join(
                appdata,
                "npm",
                "node_modules",
                "agent-desktop",
                "bin",
                "agent-desktop-win32-x64.exe",
            )
            if os.path.exists(direct_bin):
                return direct_bin

        # 2. PATH resolution for agent-desktop or agent-desktop-win32-x64.exe
        for candidate in ["agent-desktop", "agent-desktop.cmd", "agent-desktop-win32-x64.exe"]:
            found = shutil.which(candidate)
            if found:
                return found

        return None

    @staticmethod
    def get_desktop_directory() -> str:
        """Resolve actual Windows Desktop path, handling OneDrive redirection if present."""
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            )
            raw_path, _ = winreg.QueryValueEx(key, "Desktop")
            expanded = os.path.expandvars(raw_path)
            if os.path.exists(expanded):
                return expanded
        except Exception:
            pass

        # Fallbacks
        userprofile = os.environ.get("USERPROFILE", "")
        onedrive_desktop = os.path.join(userprofile, "OneDrive", "Desktop")
        if os.path.exists(onedrive_desktop):
            return onedrive_desktop

        std_desktop = os.path.join(userprofile, "Desktop")
        if os.path.exists(std_desktop):
            return std_desktop

        return os.path.expanduser("~/Desktop")

    def is_available(self) -> bool:
        """Check whether the agent-desktop CLI binary is installed and executable."""
        if self._is_available is not None:
            return self._is_available

        if not self.executable_path or not os.path.exists(self.executable_path):
            self._is_available = False
            return False

        try:
            res = self.execute(["status"], timeout=5.0)
            self._is_available = bool(res.get("ok", False))
        except Exception as e:
            logger.debug(f"agent-desktop availability check failed: {e}")
            self._is_available = False

        return self._is_available

    def execute(self, args: List[str], timeout: float = 30.0) -> Dict[str, Any]:
        """Execute an agent-desktop CLI command and return the parsed JSON envelope."""
        if not self.executable_path or not os.path.exists(self.executable_path):
            return {
                "ok": False,
                "error": {
                    "code": "BINARY_NOT_FOUND",
                    "message": "agent-desktop executable not found on system.",
                    "disposition": {"delivery": "not_delivered", "retry": "unsafe"},
                },
            }

        cmd = [self.executable_path] + [str(a) for a in args]
        logger.debug(f"Executing agent-desktop: {' '.join(cmd)}")

        try:
            start_t = time.time()
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            duration = time.time() - start_t
            raw_out = (proc.stdout or "").strip()
            raw_err = (proc.stderr or "").strip()

            if not raw_out:
                if proc.returncode == 0:
                    return {"ok": True, "data": {}}
                return {
                    "ok": False,
                    "error": {
                        "code": "EMPTY_OUTPUT",
                        "message": raw_err or f"Process exited with code {proc.returncode}",
                        "disposition": {"delivery": "not_delivered", "retry": "safe"},
                    },
                }

            # Find valid JSON envelope in output
            try:
                data = json.loads(raw_out)
                return data
            except json.JSONDecodeError:
                # If stderr was attached or multiline debug output exists
                for line in raw_out.splitlines():
                    trimmed = line.strip()
                    if trimmed.startswith("{") and trimmed.endswith("}"):
                        try:
                            return json.loads(trimmed)
                        except json.JSONDecodeError:
                            continue

                logger.warning(f"Unparseable agent-desktop output: {raw_out[:300]}")
                return {
                    "ok": False,
                    "error": {
                        "code": "INVALID_JSON",
                        "message": raw_out[:300],
                        "disposition": {"delivery": "not_delivered", "retry": "safe"},
                    },
                }

        except subprocess.TimeoutExpired:
            logger.error(f"agent-desktop command timed out after {timeout}s: {' '.join(args[:4])}")
            return {
                "ok": False,
                "error": {
                    "code": "TIMEOUT",
                    "message": f"Command timed out after {timeout} seconds",
                    "disposition": {"delivery": "not_delivered", "retry": "safe"},
                },
            }
        except Exception as e:
            logger.error(f"agent-desktop execution exception: {e}")
            return {
                "ok": False,
                "error": {
                    "code": "EXECUTION_EXCEPTION",
                    "message": str(e),
                    "disposition": {"delivery": "not_delivered", "retry": "safe"},
                },
            }

    # =========================================================================
    # High-Level Operations
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Query agent-desktop adapter health, platform info, and permission states."""
        return self.execute(["status"])

    def launch_app(self, app_name: str, activate: bool = True, timeout_ms: int = 30000) -> Dict[str, Any]:
        """Launch an application and wait until its window is active."""
        args = ["launch", app_name, "--timeout", str(timeout_ms)]
        if activate:
            args.append("--activate")
        return self.execute(args, timeout=float(timeout_ms) / 1000.0 + 5.0)

    def close_app(self, app_name: str, force: bool = False) -> Dict[str, Any]:
        """Quit an application gracefully or forcefully."""
        args = ["close-app", app_name]
        if force:
            args.append("--force")
        return self.execute(args)

    def screenshot(
        self,
        output_path: Optional[str] = None,
        screen_index: int = 0,
        app_name: Optional[str] = None,
        window_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Take a PNG screenshot of a screen or application window."""
        args = ["screenshot", "--screen", str(screen_index)]
        if app_name:
            args.extend(["--app", app_name])
        if window_id:
            args.extend(["--window-id", window_id])
        if output_path:
            args.append(output_path)
        return self.execute(args)

    def list_windows(self, app_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all visible windows, optionally filtered by application name."""
        args = ["list-windows"]
        if app_name:
            args.extend(["--app", app_name])
        res = self.execute(args)
        if res.get("ok", False):
            return res.get("data", [])
        return []

    def restore_window(self, app_name: str) -> Dict[str, Any]:
        """Restore a minimized or maximized window."""
        return self.execute(["restore", "--app", app_name])

    def focus_window(self, window_id: str) -> Dict[str, Any]:
        """Bring target window to front and confirm OS focus."""
        return self.execute(["focus-window", window_id])

    def snapshot(
        self,
        app_name: Optional[str] = None,
        window_id: Optional[str] = None,
        root_ref: Optional[str] = None,
        interactive_only: bool = True,
        compact: bool = True,
        skeleton: bool = False,
        include_bounds: bool = False,
        timeout_ms: int = 15000,
    ) -> Dict[str, Any]:
        """Capture accessibility tree as structured JSON with qualified @ref IDs.

        Args:
            app_name: Target application name (e.g. "notepad.exe", "chrome.exe")
            window_id: Target specific window ID from list-windows
            root_ref: Root ref ID to drill down into a specific subtree
            interactive_only: Filter out static labels/inert containers (-i)
            compact: Return concise tree format
            skeleton: High-level overview tree
            include_bounds: Include bounds in nodes
            timeout_ms: Settle wait timeout in milliseconds
        """
        args = ["snapshot"]
        if app_name:
            args.extend(["--app", app_name])
        if window_id:
            args.extend(["--window-id", window_id])
        if root_ref:
            args.extend(["--root", root_ref])
        if interactive_only:
            args.append("-i")
        if compact:
            args.append("--compact")
        if skeleton:
            args.append("--skeleton")
        if include_bounds:
            args.append("--include-bounds")
        if timeout_ms:
            args.extend(["--timeout-ms", str(timeout_ms)])

        return self.execute(args, timeout=float(timeout_ms) / 1000.0 + 5.0)

    def find(
        self,
        app_name: Optional[str] = None,
        role: Optional[str] = None,
        name: Optional[str] = None,
        window_id: Optional[str] = None,
        timeout_ms: int = 15000,
        exact: bool = False,
    ) -> List[Dict[str, Any]]:
        """Search accessibility elements by role, name, or window ID."""
        args = ["find"]
        if app_name:
            args.extend(["--app", app_name])
        if role:
            args.extend(["--role", role])
        if name:
            args.extend(["--name", name])
        if window_id:
            args.extend(["--window-id", window_id])
        if exact:
            args.append("--exact")
        if timeout_ms:
            args.extend(["--timeout-ms", str(timeout_ms)])

        res = self.execute(args, timeout=float(timeout_ms) / 1000.0 + 5.0)
        if res.get("ok", False):
            data = res.get("data", {})
            return data.get("matches", [])
        return []

    def get_property(self, property_name: str, ref_id: str) -> Any:
        """Read an element property (text, value, title, bounds, role, states)."""
        res = self.execute(["get", property_name, ref_id])
        if res.get("ok", False):
            return res.get("data", {}).get("value")
        return None

    def get_bounds(self, ref_id: str) -> Optional[Dict[str, float]]:
        """Read physical screen bounding rectangle {x, y, width, height} of an element."""
        res = self.execute(["get", "bounds", ref_id])
        if res.get("ok", False):
            bounds = res.get("data", {}).get("bounds")
            if isinstance(bounds, dict):
                return {
                    "x": float(bounds.get("x", 0)),
                    "y": float(bounds.get("y", 0)),
                    "width": float(bounds.get("width", 0)),
                    "height": float(bounds.get("height", 0)),
                }
        return None

    def is_state(self, state_name: str, ref_id: str) -> bool:
        """Check element state (visible, enabled, checked, focused, expanded, selected)."""
        res = self.execute(["is", state_name, ref_id])
        if res.get("ok", False):
            return bool(res.get("data", {}).get("is", False))
        return False

    def hover(self, target: Union[str, Tuple[int, int]], headed: bool = True) -> Dict[str, Any]:
        """Move cursor visibly to element center or absolute coordinates."""
        args = []
        if headed:
            args.append("--headed")
        args.append("hover")

        if isinstance(target, (tuple, list)) and len(target) >= 2:
            args.extend(["--xy", f"{int(target[0])},{int(target[1])}"])
        else:
            args.append(str(target))

        return self.execute(args)

    def mouse_move(self, x: int, y: int, headed: bool = True) -> Dict[str, Any]:
        """Move cursor visibly to absolute screen coordinates."""
        args = []
        if headed:
            args.append("--headed")
        args.extend(["mouse-move", "--xy", f"{int(x)},{int(y)}"])
        return self.execute(args)

    def mouse_click(
        self,
        x: int,
        y: int,
        button: str = "left",
        count: int = 1,
        headed: bool = True,
    ) -> Dict[str, Any]:
        """Click at absolute screen coordinates."""
        args = []
        if headed:
            args.append("--headed")
        args.extend(["mouse-click", "--xy", f"{int(x)},{int(y)}", "--button", button, "--count", str(count)])
        return self.execute(args)

    def click(
        self,
        ref_id: str,
        button: str = "left",
        headed: bool = True,
        timeout_ms: int = 25000,
    ) -> Dict[str, Any]:
        """Click element via accessibility press action or physical headed click."""
        args = []
        if headed:
            args.append("--headed")

        if button == "right":
            args.extend(["right-click", ref_id])
        else:
            args.extend(["click", ref_id])

        if timeout_ms:
            args.extend(["--timeout-ms", str(timeout_ms)])

        res = self.execute(args, timeout=float(timeout_ms) / 1000.0 + 5.0)

        # If headed click fails because window is not foreground in headless/background mode, retry semantically
        if not res.get("ok", False) and headed and button != "right":
            err_msg = res.get("error", {}).get("message", "")
            if "foreground" in err_msg.lower():
                semantic_args = ["click", ref_id]
                if timeout_ms:
                    semantic_args.extend(["--timeout-ms", str(timeout_ms)])
                res = self.execute(semantic_args, timeout=float(timeout_ms) / 1000.0 + 5.0)

        return res

    def double_click(self, ref_id: str, headed: bool = True) -> Dict[str, Any]:
        """Physically double-click element (requires --headed)."""
        args = []
        if headed:
            args.append("--headed")
        args.extend(["double-click", ref_id])
        return self.execute(args)

    def type_text(
        self,
        ref_id: str,
        text: str,
        headed: bool = True,
        interval_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Insert text into a text target via keystroke synthesis."""
        args = []
        if headed:
            args.append("--headed")
        args.extend(["type", ref_id, text])
        if interval_ms and interval_ms > 0:
            args.extend(["--interval-ms", str(interval_ms)])
        return self.execute(args)

    def set_value(self, ref_id: str, value: str, timeout_ms: int = 25000) -> Dict[str, Any]:
        """Set element value directly via accessibility attribute (instant & reliable)."""
        args = ["set-value", ref_id, value]
        if timeout_ms:
            args.extend(["--timeout-ms", str(timeout_ms)])
        return self.execute(args, timeout=float(timeout_ms) / 1000.0 + 5.0)

    def press_key(
        self,
        combo: str,
        app_name: Optional[str] = None,
        headed: bool = True,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Send key combination (e.g. 'return', 'escape', 'ctrl+s', 'ctrl+l')."""
        args = []
        if headed:
            args.append("--headed")
        args.extend(["press", combo])
        if app_name:
            args.extend(["--app", app_name])
        if force:
            args.append("--force")
        return self.execute(args)

    def expand(self, ref_id: str) -> Dict[str, Any]:
        """Expand a menu or tree item."""
        return self.execute(["expand", ref_id])

    def collapse(self, ref_id: str) -> Dict[str, Any]:
        """Collapse a menu or tree item."""
        return self.execute(["collapse", ref_id])

    def wait(
        self,
        ms: Optional[int] = None,
        window_title: Optional[str] = None,
        app_name: Optional[str] = None,
        timeout_ms: int = 30000,
    ) -> Dict[str, Any]:
        """Wait for time (ms) or window appearance."""
        args = ["wait"]
        if ms is not None and ms > 0:
            args.append(str(int(ms)))
        if window_title:
            args.extend(["--window", window_title])
        if app_name:
            args.extend(["--app", app_name])
        if timeout_ms:
            args.extend(["--timeout", str(timeout_ms)])
        return self.execute(args, timeout=float(timeout_ms) / 1000.0 + 5.0)
