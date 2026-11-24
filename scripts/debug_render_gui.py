"""Render MainWindow and FloatingPanel offscreen and save screenshots to examine visual polish."""

import os
import sys
sys.path.insert(0, os.path.abspath("."))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSize
from gui.main_window import MainWindow
from gui.floating_panel import FloatingControlPanel
from config.settings import get_settings

def capture_widget(widget, filename):
    widget.show()
    widget.repaint()
    QApplication.processEvents()
    pixmap = widget.grab()
    os.makedirs("scratch_ui", exist_ok=True)
    out_path = os.path.join("scratch_ui", filename)
    pixmap.save(out_path)
    print(f"Saved: {out_path} ({pixmap.width()}x{pixmap.height()})")

def main():
    app = QApplication.instance() or QApplication(sys.argv)
    settings = get_settings()
    
    # 1. Main window with Dashboard
    win = MainWindow(settings)
    win.resize(1280, 840)
    capture_widget(win, "main_window_dashboard.png")
    if hasattr(win, "task_agent_widget") and win.task_agent_widget:
        capture_widget(win.task_agent_widget, "task_agent_widget.png")
    
    # 2. Main window Tab 1: Live Tracking
    win.tabs.setCurrentIndex(1)
    capture_widget(win, "main_window_live_tracking.png")
    
    # 3. Main window Tab 2: Settings
    win.tabs.setCurrentIndex(2)
    capture_widget(win, "main_window_settings.png")
    
    # 4. Main window Tab 3: Help
    win.tabs.setCurrentIndex(3)
    capture_widget(win, "main_window_help.png")
    
    # 5. Floating Panel (Compact)
    panel = FloatingControlPanel(settings)
    capture_widget(panel, "floating_panel_compact.png")
    
    # 6. Floating Panel (Expanded)
    panel.toggle_compact_mode()
    capture_widget(panel, "floating_panel_expanded.png")

    win.close()
    panel.close()
    app.quit()
    sys.exit(0)

if __name__ == "__main__":
    main()
