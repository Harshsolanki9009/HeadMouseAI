"""Windows Registry Startup Integration for HeadMouseAI + Jadoo.

Manages automatic startup on Windows login via HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.
Requires explicit user opt-in; never installs silently.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from utils.logger import logger

STARTUP_KEY_NAME = "HeadMouseAI_Jadoo"
REGISTRY_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def get_startup_command() -> str:
    """Build the command line to launch HeadMouseAI minimized on startup."""
    python_exe = sys.executable
    app_root = Path(__file__).resolve().parent.parent
    app_script = app_root / "app.py"
    # Format with quotes to handle spaces in paths
    return f'"{python_exe}" "{app_script}" --minimized'


def is_windows_startup_enabled() -> bool:
    """Check if HeadMouseAI is currently registered in Windows Run key."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_SUBKEY, 0, winreg.KEY_READ) as key:
            try:
                val, _ = winreg.QueryValueEx(key, STARTUP_KEY_NAME)
                return bool(val)
            except FileNotFoundError:
                return False
    except Exception as e:
        logger.debug(f"Could not read Windows startup registry: {e}")
        return False


def set_windows_startup_enabled(enabled: bool) -> bool:
    """Enable or disable HeadMouseAI startup in Windows Registry.

    Args:
        enabled: True to register startup key, False to delete it.

    Returns:
        True if successfully set or removed, False on failure.
    """
    if sys.platform != "win32":
        logger.warning("Windows startup can only be configured on Windows OS.")
        return False

    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_SUBKEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                cmd = get_startup_command()
                winreg.SetValueEx(key, STARTUP_KEY_NAME, 0, winreg.REG_SZ, cmd)
                logger.info(f"Registered Windows startup command: {cmd}")
            else:
                try:
                    winreg.DeleteValue(key, STARTUP_KEY_NAME)
                    logger.info("Removed Windows startup registry entry.")
                except FileNotFoundError:
                    pass
        return True
    except Exception as e:
        logger.error(f"Failed to update Windows startup registry: {e}")
        return False
