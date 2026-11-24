"""Always-On-Top Floating Accessibility Control Panel for Jadoo.

Provides a compact/expandable draggable overlay with 17 high-contrast accessible buttons,
live mode indicators, and direct hands-free control via head mouse or physical click.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from config.settings import AppSettings, get_settings
from gui.styles import (
    INK_CANVAS,
    INK_COOL_GRAY,
    INK_ELEVATED,
    INK_GRAPHITE,
    INK_MUTED_AMBER,
    INK_MUTED_CRIMSON,
    INK_PURE_WHITE,
    INK_SAGE_GRAY,
    INK_SILVER_GRAY,
    INK_SOFT_IVORY,
)
from utils.logger import logger
from voice_engine.command_registry import AccessibilityCommand
from voice_engine.mode_manager import JadooOperatingMode


class AccessibleButton(QPushButton):
    """High-contrast, large-target button optimized for head-mouse clicking."""

    def __init__(
        self,
        text: str,
        tooltip: str = "",
        accent_color: str = INK_SOFT_IVORY,
        is_danger: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(text, parent)
        self.setToolTip(tooltip)
        self.setAccessibleName(text)
        self.setAccessibleDescription(tooltip)
        self.accent_color = accent_color
        self.is_danger = is_danger
        self._is_active_state: bool = False

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_style()

    def set_active_state(self, active: bool) -> None:
        """Update visual highlight state when the feature is actively enabled."""
        if self._is_active_state != active:
            self._is_active_state = active
            self._apply_style()

    def _apply_style(self) -> None:
        if self.is_danger:
            bg = "#5A2324" if self._is_active_state else "#3B1819"
            border = INK_MUTED_CRIMSON
            text_color = INK_PURE_WHITE
            hover_bg = "#6E2D2E"
        elif self._is_active_state:
            bg = INK_COOL_GRAY
            border = INK_SOFT_IVORY
            text_color = INK_SOFT_IVORY
            hover_bg = INK_ELEVATED
        else:
            bg = INK_GRAPHITE
            border = INK_COOL_GRAY
            text_color = INK_SOFT_IVORY
            hover_bg = INK_ELEVATED

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {text_color};
                border: 2px solid {border};
                border-radius: 8px;
                padding: 6px 6px;
                font-size: 12px;
                font-weight: 700;
                text-align: center;
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
                border-color: {self.accent_color};
            }}
            QPushButton:pressed {{
                background-color: {INK_CANVAS};
                border-color: {INK_SILVER_GRAY};
            }}
            QPushButton:focus {{
                border: 2px solid {INK_SOFT_IVORY};
                outline: none;
            }}
        """)


class FloatingControlPanel(QWidget):
    """Always-on-top, draggable floating panel for hands-free computer control."""

    # Outgoing signals to application coordinator
    sig_command_requested = Signal(str)           # Canonical AccessibilityCommand value
    sig_toggle_dictation = Signal(bool)          # True to start, False to stop
    sig_toggle_listening = Signal(bool)          # True to listen, False to pause
    sig_toggle_mouse = Signal()                  # Toggle head mouse
    sig_scroll = Signal(int)                     # Scroll amount (+120 or -120)
    sig_stop_all = Signal()                      # Stop all / Emergency stop
    sig_open_assistant = Signal()                # Focus or trigger Gemini assistant

    # Phase 4 AI Cursor signals
    sig_cursor_on = Signal()
    sig_cursor_off = Signal()
    sig_cursor_pause = Signal()
    sig_cursor_resume = Signal()
    sig_calibrate_cursor = Signal()
    sig_recenter_cursor = Signal()

    # Phase 5 Task Agent signals
    sig_submit_task = Signal(str)
    sig_stop_task = Signal()

    def __init__(
        self,
        settings: Optional[AppSettings] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.settings: AppSettings = settings if settings is not None else get_settings()

        # Window flags: Always on top, frameless tool window
        flags = (
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setWindowTitle("Jadoo Floating Control Panel")

        # Internal state
        self._is_compact: bool = self.settings.accessibility.compact_mode
        self._drag_pos: Optional[QPoint] = None
        self._is_listening: bool = True
        self._is_dictating: bool = False
        self._mouse_enabled: bool = False
        self._cursor_paused: bool = False
        self._current_mode: JadooOperatingMode = JadooOperatingMode.WAKE_LISTENING

        self._init_ui()
        self._restore_geometry()

    def _init_ui(self) -> None:
        """Build the high-contrast accessible layout."""
        self.setObjectName("FloatingPanel")
        self.setStyleSheet(f"""
            QWidget#FloatingPanel {{
                background-color: {INK_CANVAS};
                border: 2px solid {INK_COOL_GRAY};
                border-radius: 12px;
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # ---------------- Title & Drag Header ---------------- #
        self.header_frame = QFrame()
        self.header_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {INK_GRAPHITE};
                border: 1px solid {INK_COOL_GRAY};
                border-radius: 8px;
                padding: 2px 6px;
            }}
        """)
        h_layout = QHBoxLayout(self.header_frame)
        h_layout.setContentsMargins(6, 4, 6, 4)
        h_layout.setSpacing(6)

        # Drag handle icon / Title
        self.lbl_title = QLabel("✦ HEADMOUSE AI")
        self.lbl_title.setStyleSheet(f"color: {INK_SOFT_IVORY}; font-size: 11px; font-weight: 800; letter-spacing: 0.5px;")
        h_layout.addWidget(self.lbl_title)

        # Live Operating Mode Badge
        self.lbl_mode_badge = QLabel("LISTENING")
        self.lbl_mode_badge.setStyleSheet(f"""
            background-color: #1A211D;
            color: {INK_SAGE_GRAY};
            border: 1px solid {INK_SAGE_GRAY};
            border-radius: 4px;
            padding: 2px 6px;
            font-size: 10px;
            font-weight: 800;
        """)
        h_layout.addWidget(self.lbl_mode_badge)

        h_layout.addStretch(1)

        # Compact / Expand button
        self.btn_toggle_compact = QPushButton("▲" if not self._is_compact else "▼")
        self.btn_toggle_compact.setToolTip("Toggle Compact Mode")
        self.btn_toggle_compact.setFixedSize(24, 24)
        self.btn_toggle_compact.setStyleSheet("""
            QPushButton {
                background-color: #1E222D;
                color: #E2E8F0;
                border: 1px solid #333A4A;
                border-radius: 4px;
                font-weight: 900;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #3B4252; }
        """)
        self.btn_toggle_compact.clicked.connect(self.toggle_compact_mode)
        h_layout.addWidget(self.btn_toggle_compact)

        # Close / Hide button
        self.btn_close = QPushButton("✕")
        self.btn_close.setToolTip("Hide Floating Panel")
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: #1E222D;
                color: #EF4444;
                border: 1px solid #333A4A;
                border-radius: 4px;
                font-weight: 900;
            }
            QPushButton:hover { background-color: #991B1B; color: #FFFFFF; }
        """)
        self.btn_close.clicked.connect(self.hide)
        h_layout.addWidget(self.btn_close)

        main_layout.addWidget(self.header_frame)

        # ---------------- Quick Compact Row ---------------- #
        self.compact_row = QFrame()
        self.compact_row.setStyleSheet("background: transparent; border: none;")
        cr_layout = QHBoxLayout(self.compact_row)
        cr_layout.setContentsMargins(0, 0, 0, 0)
        cr_layout.setSpacing(6)

        self.btn_quick_typing = AccessibleButton("Typing ON", "Toggle Voice Typing Mode")
        self.btn_quick_typing.clicked.connect(self._on_quick_typing_clicked)
        cr_layout.addWidget(self.btn_quick_typing)

        self.btn_quick_stop = AccessibleButton("Stop All", "Emergency Stop", is_danger=True)
        self.btn_quick_stop.clicked.connect(self._on_stop_all_clicked)
        cr_layout.addWidget(self.btn_quick_stop)

        main_layout.addWidget(self.compact_row)

        # ---------------- Expanded Scrollable Button Grid ---------------- #
        self.expanded_container = QWidget()
        grid = QGridLayout(self.expanded_container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)

        # Button 1 & 2: Listening Controls
        self.btn_start_listen = AccessibleButton("Start Listening", "Turn microphone on")
        self.btn_start_listen.clicked.connect(lambda: self.sig_toggle_listening.emit(True))
        grid.addWidget(self.btn_start_listen, 0, 0)

        self.btn_stop_listen = AccessibleButton("Stop Listening", "Pause microphone")
        self.btn_stop_listen.clicked.connect(lambda: self.sig_toggle_listening.emit(False))
        grid.addWidget(self.btn_stop_listen, 0, 1)

        # Button 3 & 4: Typing Controls
        self.btn_typing_on = AccessibleButton("Typing ON", "Start dictation (verbatim text)")
        self.btn_typing_on.clicked.connect(lambda: self.sig_toggle_dictation.emit(True))
        grid.addWidget(self.btn_typing_on, 1, 0)

        self.btn_typing_off = AccessibleButton("Typing OFF", "Stop dictation mode")
        self.btn_typing_off.clicked.connect(lambda: self.sig_toggle_dictation.emit(False))
        grid.addWidget(self.btn_typing_off, 1, 1)

        # Button 5 & 6: Backspace & Delete Word
        self.btn_backspace = AccessibleButton("Backspace", "Delete single character")
        self.btn_backspace.clicked.connect(lambda: self.sig_command_requested.emit(AccessibilityCommand.BACKSPACE.value))
        grid.addWidget(self.btn_backspace, 2, 0)

        self.btn_delete_word = AccessibleButton("Delete Word", "Delete previous word")
        self.btn_delete_word.clicked.connect(lambda: self.sig_command_requested.emit(AccessibilityCommand.DELETE_WORD.value))
        grid.addWidget(self.btn_delete_word, 2, 1)

        # Button 7: Clear Current Field (Full Width)
        self.btn_clear_field = AccessibleButton("Clear Current Field", "Safely clear text in focused field")
        self.btn_clear_field.clicked.connect(lambda: self.sig_command_requested.emit(AccessibilityCommand.CLEAR_FIELD.value))
        grid.addWidget(self.btn_clear_field, 3, 0, 1, 2)

        # Button 8 & 9: Select All & Copy
        self.btn_select_all = AccessibleButton("Select All", "Select all text (Ctrl+A)")
        self.btn_select_all.clicked.connect(lambda: self.sig_command_requested.emit(AccessibilityCommand.SELECT_ALL.value))
        grid.addWidget(self.btn_select_all, 4, 0)

        self.btn_copy = AccessibleButton("Copy", "Copy selected text (Ctrl+C)")
        self.btn_copy.clicked.connect(lambda: self.sig_command_requested.emit(AccessibilityCommand.COPY.value))
        grid.addWidget(self.btn_copy, 4, 1)

        # Button 10 & 11: Paste & Enter
        self.btn_paste = AccessibleButton("Paste", "Paste clipboard text (Ctrl+V)")
        self.btn_paste.clicked.connect(lambda: self.sig_command_requested.emit(AccessibilityCommand.PASTE.value))
        grid.addWidget(self.btn_paste, 5, 0)

        self.btn_enter = AccessibleButton("Enter", "Press Enter key")
        self.btn_enter.clicked.connect(lambda: self.sig_command_requested.emit(AccessibilityCommand.ENTER.value))
        grid.addWidget(self.btn_enter, 5, 1)

        # Button 12 & 13: New Line & Mouse ON/OFF
        self.btn_new_line = AccessibleButton("New Line", "Insert new line")
        self.btn_new_line.clicked.connect(lambda: self.sig_command_requested.emit(AccessibilityCommand.NEW_LINE.value))
        grid.addWidget(self.btn_new_line, 6, 0)

        self.btn_mouse_toggle = AccessibleButton("Mouse ON/OFF", "Toggle head mouse control")
        self.btn_mouse_toggle.clicked.connect(lambda: self.sig_toggle_mouse.emit())
        grid.addWidget(self.btn_mouse_toggle, 6, 1)

        # Button 14 & 15: Scroll Up & Scroll Down
        self.btn_scroll_up = AccessibleButton("Scroll Up ▲", "Scroll active window up")
        self.btn_scroll_up.clicked.connect(lambda: self.sig_scroll.emit(120))
        grid.addWidget(self.btn_scroll_up, 7, 0)

        self.btn_scroll_down = AccessibleButton("Scroll Down ▼", "Scroll active window down")
        self.btn_scroll_down.clicked.connect(lambda: self.sig_scroll.emit(-120))
        grid.addWidget(self.btn_scroll_down, 7, 1)

        # Button 16: Stop All (Emergency Halt)
        self.btn_stop_all = AccessibleButton("Stop All (F9)", "Emergency Stop All Control", is_danger=True)
        self.btn_stop_all.clicked.connect(self._on_stop_all_clicked)
        grid.addWidget(self.btn_stop_all, 8, 0, 1, 2)

        # Button 17: Open Jadoo Assistant
        self.btn_assistant = AccessibleButton("Open Jadoo Assistant ✦", "Open AI assistant panel")
        self.btn_assistant.clicked.connect(lambda: self.sig_open_assistant.emit())
        grid.addWidget(self.btn_assistant, 9, 0, 1, 2)

        # ---- AI Cursor (HeadMouseAI) Section ----
        hdr_cursor = QLabel("— AI CURSOR (HEADMOUSEAI) —")
        hdr_cursor.setStyleSheet("color: #C4B5FD; font-size: 10px; font-weight: 800; padding-top: 6px;")
        grid.addWidget(hdr_cursor, 10, 0)

        self.lbl_cursor_badge = QLabel("OFF")
        self.lbl_cursor_badge.setStyleSheet("""
            background-color: #1E2330; color: #94A3B8; border: 1px solid #334155;
            border-radius: 4px; padding: 1px 6px; font-size: 9px; font-weight: 800;
        """)
        grid.addWidget(self.lbl_cursor_badge, 10, 1)

        self.btn_ai_cursor_on = AccessibleButton("Cursor ON", "Start HeadMouseAI cursor")
        self.btn_ai_cursor_on.clicked.connect(self.sig_cursor_on.emit)
        grid.addWidget(self.btn_ai_cursor_on, 11, 0)

        self.btn_ai_cursor_off = AccessibleButton("Cursor OFF", "Stop HeadMouseAI cursor")
        self.btn_ai_cursor_off.clicked.connect(self.sig_cursor_off.emit)
        grid.addWidget(self.btn_ai_cursor_off, 11, 1)

        self.btn_ai_cursor_pause = AccessibleButton("Pause Cursor", "Temporarily pause cursor movement")
        self.btn_ai_cursor_pause.clicked.connect(self._on_cursor_pause_clicked)
        grid.addWidget(self.btn_ai_cursor_pause, 12, 0)

        self.btn_ai_cursor_recenter = AccessibleButton("Recenter [R]", "Recenter tracking center")
        self.btn_ai_cursor_recenter.clicked.connect(self.sig_recenter_cursor.emit)
        grid.addWidget(self.btn_ai_cursor_recenter, 12, 1)

        self.btn_ai_cursor_calib = AccessibleButton("Calibrate Neutral Center [C]", "Run neutral calibration")
        self.btn_ai_cursor_calib.clicked.connect(self.sig_calibrate_cursor.emit)
        grid.addWidget(self.btn_ai_cursor_calib, 13, 0, 1, 2)

        # ---- Autonomous Task Agent Section ----
        hdr_task = QLabel("— AUTONOMOUS TASK AGENT —")
        hdr_task.setStyleSheet("color: #6EE7B7; font-size: 10px; font-weight: 800; padding-top: 6px;")
        grid.addWidget(hdr_task, 14, 0)

        self.lbl_task_badge = QLabel("IDLE")
        self.lbl_task_badge.setStyleSheet("""
            background-color: #1E2330; color: #94A3B8; border: 1px solid #334155;
            border-radius: 4px; padding: 1px 6px; font-size: 9px; font-weight: 800;
        """)
        grid.addWidget(self.lbl_task_badge, 14, 1)

        self.inp_panel_task = QLineEdit()
        self.inp_panel_task.setPlaceholderText("Task: e.g. Open Notepad and type...")
        self.inp_panel_task.setFixedHeight(34)
        self.inp_panel_task.setStyleSheet("""
            QLineEdit {
                background-color: #0E1017; color: #FFF; border: 1px solid #333A4A;
                border-radius: 6px; padding: 0 8px; font-size: 11px;
            }
        """)
        self.inp_panel_task.returnPressed.connect(self._on_submit_task_clicked)
        grid.addWidget(self.inp_panel_task, 15, 0, 1, 2)

        self.btn_panel_run_task = AccessibleButton("Run Task", "Execute automated task")
        self.btn_panel_run_task.clicked.connect(self._on_submit_task_clicked)
        grid.addWidget(self.btn_panel_run_task, 16, 0)

        self.btn_panel_stop_task = AccessibleButton("Stop Task (F9)", "Emergency Stop Task", is_danger=True)
        self.btn_panel_stop_task.clicked.connect(self.sig_stop_task.emit)
        grid.addWidget(self.btn_panel_stop_task, 16, 1)

        # Scroll area wrapping expanded container
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.expanded_container)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 6px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {INK_COOL_GRAY};
                min-height: 20px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {INK_SILVER_GRAY};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)

        main_layout.addWidget(self.scroll_area)

        # Apply initial compact state visibility
        self._update_compact_view()

    def _restore_geometry(self) -> None:
        """Restore position and size from saved configuration."""
        acc = self.settings.accessibility
        width = max(360, acc.panel_width)
        height = 110 if self._is_compact else max(460, acc.panel_height)
        self.resize(width, height)

        if acc.panel_x >= 0 and acc.panel_y >= 0:
            self.move(acc.panel_x, acc.panel_y)
        else:
            # Default to top right corner of the primary screen
            screen = self.screen()
            if screen:
                geom = screen.availableGeometry()
                self.move(geom.right() - width - 24, geom.top() + 48)

    def _save_geometry(self) -> None:
        """Persist current geometry to configuration."""
        pos = self.pos()
        self.settings.accessibility.panel_x = pos.x()
        self.settings.accessibility.panel_y = pos.y()
        if not self._is_compact:
            self.settings.accessibility.panel_width = self.width()
            self.settings.accessibility.panel_height = self.height()
        self.settings.accessibility.compact_mode = self._is_compact
        self.settings.save()

    @Slot()
    def toggle_compact_mode(self) -> None:
        """Switch between compact overlay and expanded control panel."""
        self._is_compact = not self._is_compact
        self._update_compact_view()
        self._save_geometry()

    def _update_compact_view(self) -> None:
        """Adjust UI elements based on compact mode."""
        if self._is_compact:
            self.scroll_area.setVisible(False)
            self.compact_row.setVisible(True)
            self.btn_toggle_compact.setText("▼")
            self.resize(self.width(), 105)
        else:
            self.compact_row.setVisible(False)
            self.scroll_area.setVisible(True)
            self.btn_toggle_compact.setText("▲")
            saved_h = max(460, self.settings.accessibility.panel_height)
            self.resize(self.width(), saved_h)

    # ---------------- Dragging Implementation ---------------- #
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Record initial mouse position for window dragging."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Move floating window smoothly as user drags."""
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Save position upon drag release."""
        self._drag_pos = None
        self._save_geometry()

    # ---------------- State Updates from Application ---------------- #
    @Slot(bool)
    def update_dictation_state(self, is_dictating: bool) -> None:
        """Update dictation buttons active highlight."""
        self._is_dictating = is_dictating
        self.btn_typing_on.set_active_state(is_dictating)
        self.btn_quick_typing.setText("Typing OFF" if is_dictating else "Typing ON")
        self.btn_quick_typing.set_active_state(is_dictating)

    @Slot(bool)
    def update_listening_state(self, is_listening: bool) -> None:
        """Update microphone listening button states."""
        self._is_listening = is_listening
        self.btn_start_listen.set_active_state(is_listening)
        self.btn_stop_listen.set_active_state(not is_listening)

    @Slot(bool, str)
    def update_mouse_state(self, enabled: bool, state_label: str) -> None:
        """Update real mouse button highlight."""
        self._mouse_enabled = enabled
        self.btn_mouse_toggle.set_active_state(enabled)
        if state_label == "EMERGENCY_STOP":
            self.btn_mouse_toggle.setText("STOPPED (F8)")
        elif enabled:
            self.btn_mouse_toggle.setText("Mouse ON [F8]")
        else:
            self.btn_mouse_toggle.setText("Mouse OFF [F8]")

    @Slot(str)
    def update_mode_badge(self, mode_str: str) -> None:
        """Update mode badge text and styling."""
        mode_u = mode_str.upper().replace("_MODE", "")
        self.lbl_mode_badge.setText(mode_u[:11])

        if "HEAD" in mode_u or "NOSE" in mode_u:
            self.lbl_mode_badge.setStyleSheet(f"""
                background-color: #1A2520; color: {INK_SAGE_GRAY};
                border: 1px solid {INK_SAGE_GRAY}; border-radius: 4px; padding: 2px 6px; font-weight: 800; font-size: 10px;
            """)
        elif "AGENT" in mode_u or "AUTO" in mode_u:
            self.lbl_mode_badge.setStyleSheet("""
                background-color: #1F1F2B; color: #C4B5FD;
                border: 1px solid #7C3AED; border-radius: 4px; padding: 2px 6px; font-weight: 800; font-size: 10px;
            """)
        elif "PAUSE" in mode_u or "STOP" in mode_u:
            self.lbl_mode_badge.setStyleSheet(f"""
                background-color: #291516; color: {INK_MUTED_CRIMSON};
                border: 1px solid {INK_MUTED_CRIMSON}; border-radius: 4px; padding: 2px 6px; font-weight: 800; font-size: 10px;
            """)
        elif "DICTAT" in mode_u:
            self.lbl_mode_badge.setStyleSheet(f"""
                background-color: #24201A; color: {INK_MUTED_AMBER};
                border: 1px solid {INK_MUTED_AMBER}; border-radius: 4px; padding: 2px 6px; font-weight: 800; font-size: 10px;
            """)
        else:
            self.lbl_mode_badge.setStyleSheet(f"""
                background-color: {INK_GRAPHITE}; color: {INK_SILVER_GRAY};
                border: 1px solid {INK_COOL_GRAY}; border-radius: 4px; padding: 2px 6px; font-weight: 800; font-size: 10px;
            """)

    @Slot()
    def _on_quick_typing_clicked(self) -> None:
        """Toggle dictation from compact view button."""
        self.sig_toggle_dictation.emit(not self._is_dictating)

    @Slot()
    def _on_stop_all_clicked(self) -> None:
        """Trigger emergency stop / stop all."""
        self.sig_stop_all.emit()

    @Slot()
    def _on_cursor_pause_clicked(self) -> None:
        """Toggle pause/resume for AI Cursor."""
        self._cursor_paused = not self._cursor_paused
        if self._cursor_paused:
            self.btn_ai_cursor_pause.setText("Resume Cursor")
            self.btn_ai_cursor_pause.set_active_state(True)
            self.sig_cursor_pause.emit()
        else:
            self.btn_ai_cursor_pause.setText("Pause Cursor")
            self.btn_ai_cursor_pause.set_active_state(False)
            self.sig_cursor_resume.emit()

    @Slot()
    def _on_submit_task_clicked(self) -> None:
        """Submit text from panel task input to Task Agent."""
        task_text = self.inp_panel_task.text().strip()
        if task_text:
            self.sig_submit_task.emit(task_text)
            self.inp_panel_task.clear()

    @Slot(str)
    def update_ai_cursor_status(self, status_str: str) -> None:
        """Update AI Cursor status badge in panel."""
        st = status_str.upper()
        self.lbl_cursor_badge.setText(st)
        if "ACTIVE" in st or "ON" in st:
            self.lbl_cursor_badge.setStyleSheet("""
                background-color: #064E3B; color: #6EE7B7; border: 1px solid #059669;
                border-radius: 4px; padding: 1px 6px; font-size: 9px; font-weight: 800;
            """)
        elif "PAUSED" in st:
            self.lbl_cursor_badge.setStyleSheet("""
                background-color: #78350F; color: #FCD34D; border: 1px solid #D97706;
                border-radius: 4px; padding: 1px 6px; font-size: 9px; font-weight: 800;
            """)
        elif "ERR" in st or "NOT DETECTED" in st:
            self.lbl_cursor_badge.setStyleSheet("""
                background-color: #7F1D1D; color: #FCA5A5; border: 1px solid #DC2626;
                border-radius: 4px; padding: 1px 6px; font-size: 9px; font-weight: 800;
            """)
        else:
            self.lbl_cursor_badge.setStyleSheet("""
                background-color: #1E2330; color: #94A3B8; border: 1px solid #334155;
                border-radius: 4px; padding: 1px 6px; font-size: 9px; font-weight: 800;
            """)

    @Slot(str)
    def update_task_status(self, status_str: str) -> None:
        """Update Task Agent status badge in panel."""
        st = status_str.upper()
        self.lbl_task_badge.setText(st)
        if "RUNNING" in st or "ACTIVE" in st or "EXECUTING" in st:
            self.lbl_task_badge.setStyleSheet("""
                background-color: #064E3B; color: #6EE7B7; border: 1px solid #059669;
                border-radius: 4px; padding: 1px 6px; font-size: 9px; font-weight: 800;
            """)
        elif "PAUSED" in st or "WAITING" in st or "CONFIRM" in st:
            self.lbl_task_badge.setStyleSheet("""
                background-color: #78350F; color: #FCD34D; border: 1px solid #D97706;
                border-radius: 4px; padding: 1px 6px; font-size: 9px; font-weight: 800;
            """)
        elif "FAILED" in st or "ERROR" in st or "STOPPED" in st:
            self.lbl_task_badge.setStyleSheet("""
                background-color: #7F1D1D; color: #FCA5A5; border: 1px solid #DC2626;
                border-radius: 4px; padding: 1px 6px; font-size: 9px; font-weight: 800;
            """)
        else:
            self.lbl_task_badge.setStyleSheet("""
                background-color: #1E2330; color: #94A3B8; border: 1px solid #334155;
                border-radius: 4px; padding: 1px 6px; font-size: 9px; font-weight: 800;
            """)
