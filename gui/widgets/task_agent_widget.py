"""Task Agent Control and Monitoring Widget for HeadMouseAI + Jadoo.

Provides interactive natural language task input, step-by-step progress tracking,
authorization prompts for sensitive actions, and completion reporting.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui.styles import (
    INK_CANVAS,
    INK_COOL_GRAY,
    INK_ELEVATED,
    INK_GRAPHITE,
    INK_MUTED_AMBER,
    INK_MUTED_CRIMSON,
    INK_MUTED_SLATE,
    INK_PURE_WHITE,
    INK_SAGE_GRAY,
    INK_SILVER_GRAY,
    INK_SOFT_IVORY,
)
from task_agent.task_manager import TaskManager
from task_agent.task_state import StepStatus, TaskStatus
from utils.logger import logger


class TaskAgentWidget(QFrame):
    """Interactive control card for Autonomous AI Desktop Task Agent."""

    sig_instruction_submitted = Signal(str)
    sig_start_requested = Signal()
    sig_pause_requested = Signal()
    sig_resume_requested = Signal()
    sig_stop_requested = Signal()
    sig_approval_given = Signal(bool)

    def __init__(self, task_manager: Optional[TaskManager] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.task_manager = task_manager
        self._is_paused: bool = False

        self.setObjectName("TaskAgentCard")
        self.setStyleSheet(f"""
            QFrame#TaskAgentCard {{
                background-color: {INK_GRAPHITE};
                border: 1px solid {INK_COOL_GRAY};
                border-radius: 10px;
                padding: 12px;
            }}
        """)

        self._init_ui()
        if self.task_manager:
            self._connect_manager()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        # ---------------- Header ---------------- #
        hdr = QHBoxLayout()
        lbl_title = QLabel("✦ Autonomous AI Computer Task Agent")
        lbl_title.setStyleSheet(f"font-size: 14px; font-weight: 800; color: {INK_SOFT_IVORY}; letter-spacing: 0.3px;")
        hdr.addWidget(lbl_title)

        self.lbl_task_status = QLabel("IDLE")
        self.lbl_task_status.setStyleSheet(f"""
            background-color: {INK_CANVAS};
            color: {INK_SILVER_GRAY};
            border: 1px solid {INK_COOL_GRAY};
            border-radius: 4px;
            padding: 3px 8px;
            font-size: 11px;
            font-weight: 800;
        """)
        hdr.addWidget(self.lbl_task_status)
        hdr.addStretch(1)
        layout.addLayout(hdr)

        # ---------------- Natural Language Input ---------------- #
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.inp_instruction = QLineEdit()
        self.inp_instruction.setPlaceholderText("E.g., Open Notepad and write a project summary...")
        self.inp_instruction.setFixedHeight(36)
        self.inp_instruction.setStyleSheet("""
            QLineEdit {
                background-color: #0E1017;
                color: #FFFFFF;
                border: 1px solid #3B4254;
                border-radius: 6px;
                padding: 0 10px;
                font-size: 13px;
            }
            QLineEdit:focus { border: 1px solid #8B5CF6; }
        """)
        self.inp_instruction.returnPressed.connect(self._on_plan_clicked)
        input_row.addWidget(self.inp_instruction, 1)

        self.btn_plan = QPushButton("Plan Task")
        self.btn_plan.setFixedHeight(36)
        self.btn_plan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_plan.setStyleSheet("""
            QPushButton {
                background-color: #4C1D95;
                color: #FFFFFF;
                border: 1px solid #7C3AED;
                border-radius: 6px;
                font-weight: 700;
                font-size: 12px;
                padding: 0 16px;
            }
            QPushButton:hover { background-color: #6D28D9; }
        """)
        self.btn_plan.clicked.connect(self._on_plan_clicked)
        input_row.addWidget(self.btn_plan)

        layout.addLayout(input_row)

        # ---------------- Controls Row ---------------- #
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)

        self.btn_start = QPushButton("▶ Start Task")
        self.btn_start.setFixedHeight(32)
        self.btn_start.setEnabled(False)
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.setStyleSheet("""
            QPushButton {
                background-color: #065F46; color: #FFFFFF;
                border: 1px solid #059669; border-radius: 6px;
                font-weight: 700; padding: 0 14px;
            }
            QPushButton:hover { background-color: #047857; }
            QPushButton:disabled { background-color: #1E293B; color: #64748B; border-color: #334155; }
        """)
        self.btn_start.clicked.connect(self.sig_start_requested.emit)
        ctrl_row.addWidget(self.btn_start)

        self.btn_pause = QPushButton("⏸ Pause")
        self.btn_pause.setFixedHeight(32)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pause.setStyleSheet("""
            QPushButton {
                background-color: #1E2330; color: #E2E8F0;
                border: 1px solid #334155; border-radius: 6px;
                font-weight: 700; padding: 0 14px;
            }
            QPushButton:hover { background-color: #334155; }
            QPushButton:disabled { background-color: #1E293B; color: #64748B; border-color: #334155; }
        """)
        self.btn_pause.clicked.connect(self._on_pause_toggled)
        ctrl_row.addWidget(self.btn_pause)

        self.btn_stop = QPushButton("⏹ Stop Task (F9)")
        self.btn_stop.setFixedHeight(32)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background-color: #991B1B; color: #FFFFFF;
                border: 1px solid #DC2626; border-radius: 6px;
                font-weight: 700; padding: 0 14px;
            }
            QPushButton:hover { background-color: #B91C1C; }
            QPushButton:disabled { background-color: #1E293B; color: #64748B; border-color: #334155; }
        """)
        self.btn_stop.clicked.connect(self.sig_stop_requested.emit)
        ctrl_row.addWidget(self.btn_stop)

        ctrl_row.addStretch(1)
        layout.addLayout(ctrl_row)

        # ---------------- Confirmation Box (hidden by default) ---------------- #
        self.frame_approval = QFrame()
        self.frame_approval.setStyleSheet("""
            QFrame {
                background-color: #2D1A1A;
                border: 1px solid #DC2626;
                border-radius: 8px;
                padding: 8px;
            }
        """)
        appr_layout = QHBoxLayout(self.frame_approval)
        appr_layout.setContentsMargins(8, 4, 8, 4)

        self.lbl_approval_prompt = QLabel("⚠️ Risky action requires authorization:")
        self.lbl_approval_prompt.setStyleSheet("color: #FCA5A5; font-weight: 700; font-size: 12px;")
        appr_layout.addWidget(self.lbl_approval_prompt, 1)

        self.btn_approve = QPushButton("Authorize Step")
        self.btn_approve.setStyleSheet("background-color: #059669; color: #FFF; font-weight: 700; border-radius: 4px; padding: 4px 10px;")
        self.btn_approve.clicked.connect(lambda: self._on_approval_response(True))
        appr_layout.addWidget(self.btn_approve)

        self.btn_decline = QPushButton("Decline")
        self.btn_decline.setStyleSheet("background-color: #7F1D1D; color: #FFF; font-weight: 700; border-radius: 4px; padding: 4px 10px;")
        self.btn_decline.clicked.connect(lambda: self._on_approval_response(False))
        appr_layout.addWidget(self.btn_decline)

        self.frame_approval.setVisible(False)
        layout.addWidget(self.frame_approval)

        # ---------------- Middle: Steps List & Activity Log ---------------- #
        mid_row = QHBoxLayout()
        mid_row.setSpacing(10)

        # Left: Steps checklist
        left_box = QVBoxLayout()
        lbl_steps = QLabel("Plan Execution Steps:")
        lbl_steps.setStyleSheet("font-size: 11px; font-weight: 700; color: #94A3B8;")
        left_box.addWidget(lbl_steps)

        self.list_steps = QListWidget()
        self.list_steps.setFixedHeight(120)
        self.list_steps.setStyleSheet("""
            QListWidget {
                background-color: #0E1017;
                border: 1px solid #282D3C;
                border-radius: 6px;
                color: #F1F5F9;
                font-size: 12px;
                padding: 4px;
            }
            QListWidget::item { padding: 4px; }
        """)
        left_box.addWidget(self.list_steps)
        mid_row.addLayout(left_box, 1)

        # Right: Activity Log
        right_box = QVBoxLayout()
        lbl_log = QLabel("Live Activity Log:")
        lbl_log.setStyleSheet("font-size: 11px; font-weight: 700; color: #94A3B8;")
        right_box.addWidget(lbl_log)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setFixedHeight(120)
        self.txt_log.setStyleSheet("""
            QTextEdit {
                background-color: #0B0D13;
                border: 1px solid #282D3C;
                border-radius: 6px;
                color: #CBD5E1;
                font-family: 'Consolas', monospace;
                font-size: 11px;
                padding: 4px;
            }
        """)
        right_box.addWidget(self.txt_log)
        mid_row.addLayout(right_box, 1)

        # Rightmost: Desktop Screen Preview & Live Verification
        preview_box = QVBoxLayout()
        preview_box.setSpacing(4)
        lbl_preview_hdr = QLabel("Desktop Preview:")
        lbl_preview_hdr.setStyleSheet("font-size: 11px; font-weight: 700; color: #94A3B8;")
        preview_box.addWidget(lbl_preview_hdr)

        self.lbl_screenshot_preview = QLabel("No desktop\ncapture yet")
        self.lbl_screenshot_preview.setFixedSize(140, 90)
        self.lbl_screenshot_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_screenshot_preview.setStyleSheet(f"""
            QLabel {{
                background-color: {INK_CANVAS};
                color: {INK_MUTED_SLATE};
                border: 1px solid {INK_COOL_GRAY};
                border-radius: 6px;
                font-size: 10px;
                font-weight: 500;
            }}
        """)
        preview_box.addWidget(self.lbl_screenshot_preview)

        self.lbl_verification_status = QLabel("VERIFIED: IDLE")
        self.lbl_verification_status.setStyleSheet(f"""
            background-color: {INK_CANVAS};
            color: {INK_SILVER_GRAY};
            border: 1px solid {INK_COOL_GRAY};
            border-radius: 4px;
            padding: 2px 4px;
            font-size: 9px;
            font-weight: 700;
        """)
        self.lbl_verification_status.setFixedWidth(140)
        self.lbl_verification_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_box.addWidget(self.lbl_verification_status)
        preview_box.addStretch(1)

        mid_row.addLayout(preview_box)

        layout.addLayout(mid_row)

    def _connect_manager(self) -> None:
        """Connect task manager signals to UI controls."""
        assert self.task_manager is not None
        self.sig_instruction_submitted.connect(self.task_manager.submit_instruction)
        self.sig_start_requested.connect(self.task_manager.start_task)
        self.sig_pause_requested.connect(self.task_manager.pause_task)
        self.sig_resume_requested.connect(self.task_manager.resume_task)
        self.sig_stop_requested.connect(self.task_manager.stop_task)
        self.sig_approval_given.connect(self.task_manager.authorize_step)

        self.task_manager.sig_plan_ready.connect(self.display_plan)
        self.task_manager.sig_status_changed.connect(self.update_status)
        self.task_manager.sig_step_started.connect(self._on_step_started)
        self.task_manager.sig_step_completed.connect(self._on_step_completed)
        self.task_manager.sig_step_failed.connect(self._on_step_failed)
        self.task_manager.sig_confirmation_required.connect(self._on_confirmation_required)
        self.task_manager.sig_task_completed.connect(self._on_task_completed)
        self.task_manager.sig_log_message.connect(self.append_log)
        self.task_manager.sig_screenshot_captured.connect(self.on_screenshot_captured)
        self.task_manager.sig_verification_status.connect(self.on_verification_status)

    @Slot()
    def _on_plan_clicked(self) -> None:
        """Handle submit/plan button click."""
        text = self.inp_instruction.text().strip()
        if text:
            self.sig_instruction_submitted.emit(text)

    @Slot()
    def _on_pause_toggled(self) -> None:
        """Toggle pause / resume."""
        if not self._is_paused:
            self._is_paused = True
            self.btn_pause.setText("▶ Resume")
            self.sig_pause_requested.emit()
        else:
            self._is_paused = False
            self.btn_pause.setText("⏸ Pause")
            self.sig_resume_requested.emit()

    def _on_approval_response(self, approved: bool) -> None:
        """User authorized or declined risky step."""
        self.frame_approval.setVisible(False)
        self.sig_approval_given.emit(approved)

    @Slot(dict)
    def display_plan(self, plan_dict: dict) -> None:
        """Render plan steps into checklist."""
        self.list_steps.clear()
        steps = plan_dict.get("steps", [])
        for s in steps:
            idx = s.get("step_index", 0) + 1
            desc = s.get("description", "")
            item = QListWidgetItem(f"⏳ Step {idx}: {desc}")
            self.list_steps.addItem(item)

        self.btn_start.setEnabled(len(steps) > 0)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.update_status("READY")

    @Slot(str)
    def update_status(self, status: str) -> None:
        """Update top status pill and button states."""
        st_u = status.upper()
        self.lbl_task_status.setText(st_u)

        if "RUN" in st_u or "OBSERV" in st_u:
            self.lbl_task_status.setStyleSheet("""
                background-color: #064E3B; color: #6EE7B7; border: 1px solid #059669;
                border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight: 800;
            """)
            self.btn_start.setEnabled(False)
            self.btn_pause.setEnabled(True)
            self.btn_stop.setEnabled(True)
        elif "WAIT" in st_u:
            self.lbl_task_status.setStyleSheet("""
                background-color: #78350F; color: #FDE68A; border: 1px solid #D97706;
                border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight: 800;
            """)
        elif "COMPLET" in st_u:
            self.lbl_task_status.setStyleSheet("""
                background-color: #1E1B4B; color: #C4B5FD; border: 1px solid #7C3AED;
                border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight: 800;
            """)
            self.btn_start.setEnabled(False)
            self.btn_pause.setEnabled(False)
            self.btn_stop.setEnabled(False)
        elif "STOP" in st_u or "FAIL" in st_u:
            self.lbl_task_status.setStyleSheet("""
                background-color: #7F1D1D; color: #FCA5A5; border: 1px solid #DC2626;
                border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight: 800;
            """)
            self.btn_start.setEnabled(False)
            self.btn_pause.setEnabled(False)
            self.btn_stop.setEnabled(False)
        else:
            self.lbl_task_status.setStyleSheet("""
                background-color: #1E2330; color: #94A3B8; border: 1px solid #334155;
                border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight: 800;
            """)

    @Slot(int, str)
    def _on_step_started(self, idx: int, desc: str) -> None:
        if idx < self.list_steps.count():
            item = self.list_steps.item(idx)
            item.setText(f"🔄 Step {idx + 1}: {desc}")
            item.setForeground(Qt.GlobalColor.cyan)

    @Slot(int)
    def _on_step_completed(self, idx: int) -> None:
        if idx < self.list_steps.count():
            item = self.list_steps.item(idx)
            clean_text = item.text().replace("🔄 ", "").replace("⏳ ", "")
            item.setText(f"✅ {clean_text}")
            item.setForeground(Qt.GlobalColor.green)

    @Slot(int, str)
    def _on_step_failed(self, idx: int, err: str) -> None:
        if idx < self.list_steps.count():
            item = self.list_steps.item(idx)
            clean_text = item.text().replace("🔄 ", "").replace("⏳ ", "")
            item.setText(f"❌ {clean_text} ({err})")
            item.setForeground(Qt.GlobalColor.red)

    @Slot(int, str)
    def _on_confirmation_required(self, idx: int, desc: str) -> None:
        self.lbl_approval_prompt.setText(f"⚠️ Authorize Step {idx + 1}: {desc}")
        self.frame_approval.setVisible(True)

    @Slot(dict)
    def _on_task_completed(self, report: dict) -> None:
        self.frame_approval.setVisible(False)
        st = report.get("status", "COMPLETED")
        self.update_status(st)

    @Slot(str)
    def append_log(self, entry: str) -> None:
        """Append log message to text area."""
        self.txt_log.append(entry)
        sb = self.txt_log.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())

    @Slot(bytes)
    def on_screenshot_captured(self, jpeg_bytes: bytes) -> None:
        """Render raw JPEG desktop screenshot thumbnail into preview card."""
        try:
            pix = QPixmap()
            if pix.loadFromData(jpeg_bytes):
                scaled = pix.scaled(
                    140, 90,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.lbl_screenshot_preview.setPixmap(scaled)
        except Exception as e:
            logger.debug(f"Error displaying desktop preview: {e}")

    @Slot(str, str)
    def on_verification_status(self, msg: str, state: str) -> None:
        """Update live verification badge."""
        state_u = state.upper()
        self.lbl_verification_status.setText(msg[:24])
        self.lbl_verification_status.setToolTip(msg)
        if state_u in ("OK", "PASS", "SUCCESS"):
            self.lbl_verification_status.setStyleSheet(f"""
                background-color: #064E3B; color: #6EE7B7; border: 1px solid #059669;
                border-radius: 4px; padding: 2px 4px; font-size: 9px; font-weight: 700;
            """)
        elif state_u in ("OBSERVING", "CHECKING"):
            self.lbl_verification_status.setStyleSheet(f"""
                background-color: #1E2B4C; color: #93C5FD; border: 1px solid #3B82F6;
                border-radius: 4px; padding: 2px 4px; font-size: 9px; font-weight: 700;
            """)
        elif state_u in ("FAIL", "ERROR"):
            self.lbl_verification_status.setStyleSheet(f"""
                background-color: #7F1D1D; color: #FCA5A5; border: 1px solid #DC2626;
                border-radius: 4px; padding: 2px 4px; font-size: 9px; font-weight: 700;
            """)
        else:
            self.lbl_verification_status.setStyleSheet(f"""
                background-color: {INK_CANVAS}; color: {INK_SILVER_GRAY}; border: 1px solid {INK_COOL_GRAY};
                border-radius: 4px; padding: 2px 4px; font-size: 9px; font-weight: 700;
            """)
