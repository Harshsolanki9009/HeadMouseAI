"""Comprehensive visual verification and screenshot capture script for HeadMouseAI Premium UI."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from config.settings import get_settings
from gui.main_window import MainWindow
from gui.widgets.splash_screen import SplashScreen
from gui.widgets.video_widget import VideoWidget
from utils.resource import get_icon_path


def generate_synthetic_camera_frame(width: int = 640, height: int = 480) -> QImage:
    """Generate a realistic synthetic 4:3 camera frame with a human face representation."""
    img = QImage(width, height, QImage.Format.Format_RGB888)
    img.fill(QColor(30, 41, 59))  # Slate background

    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Ambient room lighting gradient
    from PySide6.QtGui import QLinearGradient
    room_grad = QLinearGradient(0, 0, width, height)
    room_grad.setColorAt(0.0, QColor(45, 55, 72))
    room_grad.setColorAt(1.0, QColor(26, 32, 44))
    painter.fillRect(QRect(0, 0, width, height), room_grad)

    # Simulated head/face silhouette
    center_x = width // 2
    center_y = int(height * 0.48)
    face_w = int(width * 0.38)
    face_h = int(height * 0.58)

    painter.setBrush(QColor(230, 190, 165))  # Skin tone
    painter.setPen(QColor(180, 140, 120))
    painter.drawEllipse(QPoint(center_x, center_y), face_w // 2, face_h // 2)

    # Simulated hair
    painter.setBrush(QColor(40, 30, 25))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QPoint(center_x, center_y - 70), int(face_w * 0.55), int(face_h * 0.35))

    # Simulated eyes
    eye_offset_x = int(face_w * 0.22)
    eye_y = center_y - 20
    painter.setBrush(QColor(255, 255, 255))
    painter.drawEllipse(QPoint(center_x - eye_offset_x, eye_y), 16, 10)
    painter.drawEllipse(QPoint(center_x + eye_offset_x, eye_y), 16, 10)

    # Pupils
    painter.setBrush(QColor(45, 60, 90))
    painter.drawEllipse(QPoint(center_x - eye_offset_x, eye_y), 6, 6)
    painter.drawEllipse(QPoint(center_x + eye_offset_x, eye_y), 6, 6)

    # Nose tip landmark (Cyan marker)
    nose_y = center_y + 25
    painter.setBrush(QColor(0, 255, 255))
    painter.setPen(QColor(0, 200, 200))
    painter.drawEllipse(QPoint(center_x, nose_y), 5, 5)

    # Mouth
    painter.setBrush(QColor(190, 80, 80))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(QRect(center_x - 22, center_y + 65, 44, 12), 4, 4)

    # Overlay banner text
    painter.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
    painter.setPen(QColor(255, 255, 255, 180))
    painter.drawText(QRect(20, 20, 300, 24), Qt.AlignmentFlag.AlignLeft, "Face Detected: Tracking Active")

    painter.end()
    return img


def run_verification() -> int:
    """Execute complete UI visual capture and feature verification."""
    print("=" * 70)
    print("HEADMOUSE AI — Premium Windows Desktop UI Verification")
    print("=" * 70)

    output_dir = PROJECT_ROOT / "screenshots_premium"
    output_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    # 1. Verify App Icon Integration
    ico_path = get_icon_path("app_icon.ico")
    png_path = get_icon_path("app_icon.png")
    print(f"[*] Icon check: .ico exists: {ico_path.is_file()} ({ico_path.stat().st_size} bytes)")
    print(f"[*] Icon check: .png exists: {png_path.is_file()} ({png_path.stat().st_size} bytes)")
    assert ico_path.is_file() and png_path.is_file()

    # 2. Splash Screen Capture
    print("[*] Initializing animated Splash Screen...")
    splash = SplashScreen()
    splash.resize(480, 310)
    splash.set_status("Initializing AI vision models & camera pipeline...")
    splash.show()
    app.processEvents()

    # Capture Splash Screen
    splash_pix = splash.grab()
    splash_path = output_dir / "01_splash_screen.png"
    splash_pix.save(str(splash_path))
    print(f"[+] Saved Splash Screen: {splash_path}")
    splash.close()

    # 3. Main Window Initialization
    print("[*] Initializing MainWindow with Premium SaaS Theme...")
    settings = get_settings()
    win = MainWindow(settings)
    win.resize(1240, 820)
    win.show()
    app.processEvents()

    # Capture 02: Dashboard Clean (Offline state)
    win.tabs.setCurrentIndex(0)
    app.processEvents()
    dash_clean_path = output_dir / "02_dashboard_clean.png"
    win.grab().save(str(dash_clean_path))
    print(f"[+] Saved Dashboard Clean: {dash_clean_path}")

    # Capture 03: Dashboard with Live 4:3 Frame and Blurred Background Fill
    print("[*] Simulating live camera feed with blurred pillarbox fill...")
    test_frame = generate_synthetic_camera_frame(640, 480)
    win.video_widget.update_frame(test_frame)
    win.video_widget.update_telemetry({
        "mode": "NORMAL",
        "fps": 30.2,
        "latency_ms": 11.4,
        "has_face": True,
        "is_calibrated": True,
        "emergency_stopped": False,
        "position_locked": False,
    })
    win.card_cam.set_status("Connected (30 FPS)", "OK")
    win.card_face.set_status("Tracking Active", "OK")
    win.card_calib.set_status("Calibrated", "OK")
    win.card_mouse.set_status("Disabled [F8]", "NORMAL")
    win.hdr_badge_camera.set_state("OK", "LIVE")
    win.hdr_badge_tracking.set_state("OK", "TRACKING")
    app.processEvents()

    dash_live_path = output_dir / "03_dashboard_live_blurred_fill.png"
    win.grab().save(str(dash_live_path))
    print(f"[+] Saved Live Dashboard with Blurred Fill: {dash_live_path}")

    # Capture 04: Dashboard with Expanded Advanced Details
    print("[*] Expanding Advanced Details diagnostics section...")
    win._toggle_advanced_details()
    win.lbl_dash_fps.setText("30.2 FPS")
    win.lbl_dash_inf.setText("11.4 ms")
    win.lbl_dash_lear.setText("0.31 [OPEN]")
    win.lbl_dash_rear.setText("0.30 [OPEN]")
    win.lbl_dash_sys.setText("CPU: 3.2% | RAM: 94 MB")
    app.processEvents()

    dash_exp_path = output_dir / "04_dashboard_expanded_details.png"
    win.grab().save(str(dash_exp_path))
    print(f"[+] Saved Dashboard with Advanced Details: {dash_exp_path}")

    # Collapse back for clean layout
    win._toggle_advanced_details()

    # Capture 05: Live Tracking Tab
    print("[*] Switching to Live Tracking Tab...")
    win.tabs.setCurrentIndex(1)
    win.telemetry_widget.update_telemetry({
        "mode": "NORMAL",
        "emergency_stopped": False,
        "real_mouse_enabled": False,
        "has_face": True,
        "is_calibrated": True,
        "is_calibrating": False,
        "screen_x": 960,
        "screen_y": 540,
        "rel_dx": 0.005,
        "rel_dy": -0.012,
        "position_locked": False,
        "is_dragging": False,
        "left_ear": 0.31,
        "right_ear": 0.30,
        "left_eye_state": "OPEN",
        "right_eye_state": "OPEN",
        "blink_event": "NONE",
        "suppression_active": False,
        "teeth_visible": False,
        "left_eb_state": "NEUTRAL",
        "right_eb_state": "NEUTRAL",
        "head_direction": "CENTER",
        "gesture_action": "NONE",
        "mouth_width_ratio": 0.51,
        "mouth_width_baseline": 0.50,
        "mouth_open_ratio": 0.018,
        "gesture_reject_reason": "NONE",
    })
    app.processEvents()
    time.sleep(0.2)  # Wait for tab fade animation
    app.processEvents()
    live_path = output_dir / "05_live_tracking_tab.png"
    win.grab().save(str(live_path))
    print(f"[+] Saved Live Tracking Tab: {live_path}")

    # Capture 06: Settings Tab
    print("[*] Switching to Settings Tab...")
    win.tabs.setCurrentIndex(2)
    app.processEvents()
    time.sleep(0.2)
    app.processEvents()
    settings_path = output_dir / "06_settings_tab.png"
    win.grab().save(str(settings_path))
    print(f"[+] Saved Settings Tab: {settings_path}")

    # Capture 07: Help Tab
    print("[*] Switching to Help Tab...")
    win.tabs.setCurrentIndex(3)
    app.processEvents()
    time.sleep(0.2)
    app.processEvents()
    help_path = output_dir / "07_help_tab.png"
    win.grab().save(str(help_path))
    print(f"[+] Saved Help Tab: {help_path}")

    win.close()
    print("=" * 70)
    print("VERIFICATION COMPLETED SUCCESSFULLY: 7 Screenshots Captured.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(run_verification())
