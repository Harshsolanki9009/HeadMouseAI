"""Jadoo Assistant GUI Widget for HeadMouseAI.

Obsidian Chrome themed panel supporting conversational Q&A, Hinglish-to-English
professional rewrite, screen-aware analysis, and direct cursor text injection.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from config.settings import AppSettings, get_settings
from gui.widgets.telemetry_cards import StatusBadge
from utils.logger import logger


class JadooAssistantWidget(QFrame):
    """Obsidian Chrome UI widget for Jadoo AI Assistant."""

    sig_ask_query = Signal(str, bool, bool)   # (query, include_screen, is_rewrite)
    sig_insert_response = Signal(str)         # Response text to insert at external cursor
    sig_stop_tts = Signal()                   # Stop TTS playback

    def __init__(self, settings: Optional[AppSettings] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.settings: AppSettings = settings if settings is not None else get_settings()
        self._last_response: str = ""

        self.setObjectName("jadooAssistantWidget")
        self.setStyleSheet(
            "#jadooAssistantWidget {"
            "  background-color: #18191C;"
            "  border: 1px solid #2E323A;"
            "  border-radius: 8px;"
            "}"
        )

        v_layout = QVBoxLayout(self)
        v_layout.setContentsMargins(14, 12, 14, 12)
        v_layout.setSpacing(10)

        # ---------------- 1. Header Row ---------------- #
        hdr_layout = QHBoxLayout()
        hdr_layout.setSpacing(10)

        lbl_icon = QLabel("✨")
        lbl_icon.setStyleSheet("font-size: 16px;")
        hdr_layout.addWidget(lbl_icon)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(1)
        lbl_title = QLabel("Jadoo AI Assistant")
        lbl_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #F5F5F5; letter-spacing: -0.2px;")
        title_layout.addWidget(lbl_title)

        lbl_subtitle = QLabel("Online Intelligence • Hinglish/English • Screen-Aware Guidance")
        lbl_subtitle.setStyleSheet("font-size: 11px; color: #A1A1AA; font-weight: 500;")
        title_layout.addWidget(lbl_subtitle)
        hdr_layout.addLayout(title_layout)

        hdr_layout.addStretch(1)

        self.badge_status = StatusBadge("OFFLINE")
        self.badge_status.setFixedWidth(110)
        hdr_layout.addWidget(self.badge_status)

        v_layout.addLayout(hdr_layout)

        # ---------------- 2. Response View ---------------- #
        self.txt_response = QTextBrowser()
        self.txt_response.setOpenExternalLinks(True)
        self.txt_response.setMinimumHeight(80)
        self.txt_response.setMaximumHeight(140)
        self.txt_response.setPlaceholderText(
            "Jadoo responses will appear here...\n"
            "Say 'Hey Jadoo, ...' or press [Ctrl+Space] to ask questions or rewrite Hinglish."
        )
        self.txt_response.setStyleSheet(
            "QTextBrowser {"
            "  background-color: #121316;"
            "  border: 1px solid #2E323A;"
            "  border-radius: 6px;"
            "  color: #F5F5F5;"
            "  font-size: 12px;"
            "  line-height: 1.45;"
            "  padding: 8px;"
            "  selection-background-color: #3F434C;"
            "}"
        )
        v_layout.addWidget(self.txt_response)

        # ---------------- 3. Query Input Row ---------------- #
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        self.inp_query = QLineEdit()
        self.inp_query.setPlaceholderText("Ask Jadoo a question or type Hinglish notes... [Ctrl+Space]")
        self.inp_query.setFixedHeight(32)
        self.inp_query.setStyleSheet(
            "QLineEdit {"
            "  background-color: #202226;"
            "  border: 1px solid #2E323A;"
            "  border-radius: 6px;"
            "  color: #F5F5F5;"
            "  font-size: 12px;"
            "  padding: 0 10px;"
            "}"
            "QLineEdit:focus {"
            "  border: 1px solid #60A5FA;"
            "}"
        )
        self.inp_query.returnPressed.connect(self._on_ask_clicked)
        input_layout.addWidget(self.inp_query, 1)

        self.btn_ask = QPushButton("Ask Jadoo")
        self.btn_ask.setFixedHeight(32)
        self.btn_ask.setStyleSheet(
            "QPushButton {"
            "  background-color: #1E3A8A;"
            "  color: #93C5FD;"
            "  border: 1px solid #2563EB;"
            "  border-radius: 6px;"
            "  font-size: 12px;"
            "  font-weight: 600;"
            "  padding: 0 14px;"
            "}"
            "QPushButton:hover {"
            "  background-color: #2563EB;"
            "  color: #FFFFFF;"
            "}"
        )
        self.btn_ask.clicked.connect(self._on_ask_clicked)
        input_layout.addWidget(self.btn_ask)

        v_layout.addLayout(input_layout)

        # ---------------- 4. Options & Action Controls Row ---------------- #
        action_layout = QHBoxLayout()
        action_layout.setSpacing(8)

        self.chk_screen = QCheckBox("Include Screen Context")
        self.chk_screen.setStyleSheet("QCheckBox { color: #A1A1AA; font-size: 11px; font-weight: 500; }")
        action_layout.addWidget(self.chk_screen)

        action_layout.addStretch(1)

        self.btn_rewrite = QPushButton("Hinglish ➔ Pro English")
        self.btn_rewrite.setFixedHeight(28)
        self.btn_rewrite.setStyleSheet(
            "QPushButton {"
            "  background-color: #312E81;"
            "  color: #C7D2FE;"
            "  border: 1px solid #4338CA;"
            "  border-radius: 6px;"
            "  font-size: 11px;"
            "  font-weight: 600;"
            "  padding: 0 10px;"
            "}"
            "QPushButton:hover {"
            "  background-color: #3730A3;"
            "  color: #EEF2FF;"
            "}"
        )
        self.btn_rewrite.setToolTip("Transform Hinglish draft into clean professional workplace English")
        self.btn_rewrite.clicked.connect(self._on_rewrite_clicked)
        action_layout.addWidget(self.btn_rewrite)

        self.btn_insert = QPushButton("Insert Response at Cursor")
        self.btn_insert.setFixedHeight(28)
        self.btn_insert.setStyleSheet(
            "QPushButton {"
            "  background-color: #202226;"
            "  color: #E4E4E7;"
            "  border: 1px solid #2E323A;"
            "  border-radius: 6px;"
            "  font-size: 11px;"
            "  font-weight: 600;"
            "  padding: 0 10px;"
            "}"
            "QPushButton:hover {"
            "  background-color: #292C32;"
            "  border-color: #3F434C;"
            "  color: #FFFFFF;"
            "}"
        )
        self.btn_insert.clicked.connect(self._on_insert_clicked)
        action_layout.addWidget(self.btn_insert)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setFixedHeight(28)
        self.btn_clear.setStyleSheet(
            "QPushButton {"
            "  background-color: #202226;"
            "  color: #A1A1AA;"
            "  border: 1px solid #2E323A;"
            "  border-radius: 6px;"
            "  font-size: 11px;"
            "  font-weight: 600;"
            "  padding: 0 8px;"
            "}"
            "QPushButton:hover {"
            "  background-color: #292C32;"
            "  color: #F87171;"
            "}"
        )
        self.btn_clear.clicked.connect(self.clear)
        action_layout.addWidget(self.btn_clear)

        v_layout.addLayout(action_layout)

    @Slot()
    def focus_query_input(self) -> None:
        """Focus the input field for immediate typing (shortcut Ctrl+Space)."""
        self.inp_query.setFocus()
        self.inp_query.selectAll()

    @Slot()
    def _on_ask_clicked(self) -> None:
        q = self.inp_query.text().strip()
        include_screen = self.chk_screen.isChecked()
        if q or include_screen:
            self.sig_ask_query.emit(q, include_screen, False)
            self.inp_query.clear()

    @Slot()
    def _on_rewrite_clicked(self) -> None:
        q = self.inp_query.text().strip()
        if not q and self._last_response:
            q = self._last_response
        if q:
            self.sig_ask_query.emit(q, False, True)
            self.inp_query.clear()

    @Slot()
    def _on_insert_clicked(self) -> None:
        if self._last_response:
            self.sig_insert_response.emit(self._last_response)

    @Slot(str)
    def set_response(self, text: str) -> None:
        """Display assistant answer."""
        self._last_response = text
        self.txt_response.setPlainText(text)

    @Slot(str)
    def set_error(self, err_msg: str) -> None:
        """Display error banner."""
        self.txt_response.setHtml(
            f"<div style='color: #F87171; font-weight: 600;'>⚠ Jadoo Assistant Error: {err_msg}</div>"
        )

    @Slot(str)
    def set_status(self, status: str) -> None:
        """Update status badge."""
        st = status.upper()
        if "THINK" in st:
            self.badge_status.set_state("WARNING", "THINKING")
        elif "ONLINE" in st:
            self.badge_status.set_state("OK", "ONLINE")
        else:
            self.badge_status.set_state("NORMAL", "OFFLINE")

    @Slot()
    def clear(self) -> None:
        self._last_response = ""
        self.txt_response.clear()
        self.inp_query.clear()
