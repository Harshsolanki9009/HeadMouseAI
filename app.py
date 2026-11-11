"""HeadMouseAI - Professional Hands-Free Windows Mouse Desktop Application.

PySide6 Desktop Application Entry Point with Native Taskbar Integration,
Custom Animated Startup Splash Screen, and SaaS Styling.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure application root directory is in sys.path
APP_ROOT = Path(__file__).resolve().parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

# Windows explicit AppUserModelID for proper taskbar grouping and icon binding
try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("HeadMouseAI.DesktopApp.1.0")
except Exception:
    pass

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from config.settings import get_settings
from gui.main_window import MainWindow
from utils.logger import logger
from utils.resource import get_icon_path


def main() -> int:
    """Initialize and run the PySide6 desktop application."""
    logger.info("=" * 65)
    logger.info("HEADMOUSE AI - Professional Hands-Free Desktop Controller Launch")
    logger.info("=" * 65)

    # Windows DPI awareness
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    app = QApplication(sys.argv)
    app.setApplicationName("HeadMouseAI")
    app.setOrganizationName("HeadMouseAI")
    app.setApplicationDisplayName("HeadMouseAI - Hands-Free Windows Mouse")

    # Set Multi-Resolution Global Application & Taskbar Icon
    app_icon = QIcon()
    ico_path = get_icon_path("app_icon.ico")
    png_path = get_icon_path("app_icon.png")
    if ico_path.is_file():
        app_icon.addFile(str(ico_path))
    if png_path.is_file():
        app_icon.addFile(str(png_path))
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    use_splash = "--no-splash" not in sys.argv

    if use_splash:
        try:
            from gui.widgets.splash_screen import SplashScreen

            splash = SplashScreen()
            splash.show_animated()
            app.processEvents()

            splash.set_status("Loading configuration & user preferences...")
            settings = get_settings()

            splash.set_status("Initializing AI tracking subsystem & camera...")
            window = MainWindow(settings)

            splash.set_status("Ready. Launching workspace...")

            # Transition to main window with ~1.6s smooth splash experience
            QTimer.singleShot(1600, lambda: splash.finish_and_show(window))

        except Exception as e:
            logger.error(f"Startup error: {e}", exc_info=True)
            if "splash" in locals() and splash is not None:
                splash.close()
            QMessageBox.critical(
                None,
                "HeadMouseAI - Startup Error",
                f"Application initialization failed:\n\n{e}",
            )
            return 1
    else:
        settings = get_settings()
        window = MainWindow(settings)
        window.show()

    logger.info("HeadMouseAI desktop application presented.")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
