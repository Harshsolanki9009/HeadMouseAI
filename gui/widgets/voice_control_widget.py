"""Jadoo Voice Subsystem UI Control Widget for HeadMouseAI.

Provides a unified interface for offline speech-to-text dictation,
live microphone level visualization, command status, and safe Unicode
text insertion adhering to the Obsidian Chrome design system.
"""

from __future__ import annotations

import math
from typing import Optional

import pyperclip
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.widgets.telemetry_cards import StatusBadge
from utils.logger import logger


class VoiceControlWidget(QFrame):
    """Modern Obsidian Chrome voice dictation and control widget."""

    sig_toggle_dictation = Signal()
    sig_insert_text = Signal(str)
    sig_clear_text = Signal()
    sig_language_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("voice_control_card")
        self._is_dictating = False
        self._current_language = "en"
        self._pulse_phase = 0.0

        # Lightweight breathing animation timer (~20 FPS) for dictating state
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(50)
        self._pulse_timer.timeout.connect(self._on_pulse_tick)

        self._init_ui()

    def _init_ui(self) -> None:
        self.setStyleSheet(
            "QFrame#voice_control_card { background-color: #181A1F; border: 1px solid #2E323A; "
            "border-radius: 8px; padding: 10px; }"
        )

        v_layout = QVBoxLayout(self)
        v_layout.setContentsMargins(12, 10, 12, 10)
        v_layout.setSpacing(10)

        # ---------------- 1. Header Row ---------------- #
        hdr_layout = QHBoxLayout()
        hdr_layout.setSpacing(10)

        lbl_icon = QLabel("🎙️")
        lbl_icon.setStyleSheet("font-size: 16px;")
        hdr_layout.addWidget(lbl_icon)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(1)
        lbl_title = QLabel("Jadoo Voice Engine")
        lbl_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #F5F5F5; letter-spacing: -0.2px;")
        title_layout.addWidget(lbl_title)

        self.lbl_subtitle = QLabel("Hybrid Cloud & Offline STT | Hindi • English • Hinglish")
        self.lbl_subtitle.setStyleSheet("font-size: 11px; color: #A1A1AA; font-weight: 500;")
        title_layout.addWidget(self.lbl_subtitle)
        hdr_layout.addLayout(title_layout)

        hdr_layout.addStretch(1)

        self.badge_status = StatusBadge("IDLE")
        self.badge_status.setFixedWidth(100)
        hdr_layout.addWidget(self.badge_status)

        v_layout.addLayout(hdr_layout)

        # ---------------- 2. Language Selector & Engine Strip ---------------- #
        strip_layout = QHBoxLayout()
        strip_layout.setSpacing(8)

        lbl_lang = QLabel("Language:")
        lbl_lang.setStyleSheet("font-size: 11px; font-weight: 600; color: #A1A1AA;")
        strip_layout.addWidget(lbl_lang)

        self.combo_language = QComboBox()
        self.combo_language.addItem("English (en)", "en")
        self.combo_language.addItem("Hindi (hi)", "hi")
        self.combo_language.addItem("Hinglish (Hindi + English)", "hinglish")
        self.combo_language.addItem("Auto Detect", "auto")
        self.combo_language.setFixedHeight(26)
        self.combo_language.setStyleSheet(
            "QComboBox { background-color: #202226; color: #F5F5F5; border: 1px solid #2E323A; "
            "border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: 500; min-width: 135px; }"
            "QComboBox:disabled { color: #52525B; border-color: #27272A; background-color: #18191C; }"
            "QComboBox::drop-down { border: none; width: 18px; }"
            "QComboBox QAbstractItemView { background-color: #181A1F; color: #F5F5F5; border: 1px solid #2E323A; "
            "selection-background-color: #2E323A; font-size: 11px; }"
        )
        self.combo_language.currentIndexChanged.connect(self._on_combo_language_changed)
        strip_layout.addWidget(self.combo_language)

        # Prominent language indicator badge (visible during recording)
        self.badge_lang_indicator = StatusBadge("EN")
        self.badge_lang_indicator.setFixedWidth(80)
        strip_layout.addWidget(self.badge_lang_indicator)

        strip_layout.addStretch(1)

        lbl_engine_title = QLabel("Engine:")
        lbl_engine_title.setStyleSheet("font-size: 11px; font-weight: 600; color: #71717A;")
        strip_layout.addWidget(lbl_engine_title)

        self.badge_engine = StatusBadge("LOCAL WHISPER")
        self.badge_engine.setMinimumWidth(110)
        strip_layout.addWidget(self.badge_engine)

        v_layout.addLayout(strip_layout)

        # ---------------- 3. Audio Level Meter ---------------- #
        level_layout = QHBoxLayout()
        level_layout.setSpacing(8)

        lbl_mic = QLabel("Mic:")
        lbl_mic.setStyleSheet("font-size: 11px; font-weight: 600; color: #71717A; font-family: Consolas, monospace;")
        level_layout.addWidget(lbl_mic)

        self.level_bar = QProgressBar()
        self.level_bar.setRange(0, 100)
        self.level_bar.setValue(0)
        self.level_bar.setTextVisible(False)
        self.level_bar.setFixedHeight(6)
        self.level_bar.setStyleSheet(
            "QProgressBar { background-color: #202226; border: 1px solid #2E323A; border-radius: 3px; }"
            "QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #10B981); "
            "border-radius: 2px; }"
        )
        level_layout.addWidget(self.level_bar, 1)

        self.lbl_level_pct = QLabel("0%")
        self.lbl_level_pct.setFixedWidth(35)
        self.lbl_level_pct.setStyleSheet(
            "font-size: 10px; color: #71717A; font-family: Consolas, monospace; font-weight: 600;"
        )
        level_layout.addWidget(self.lbl_level_pct)

        v_layout.addLayout(level_layout)

        # ---------------- 3. Dictation Text Preview Box ---------------- #
        self.txt_preview = QPlainTextEdit()
        self.txt_preview.setReadOnly(True)
        self.txt_preview.setPlaceholderText(
            "Spoken dictation will appear here in real time (Devanagari Hindi, English, Hinglish)...\n"
            "Press 'Start Dictation' or use shortcut [Ctrl+Shift+D]."
        )
        self.txt_preview.setMaximumHeight(85)
        self.txt_preview.setMinimumHeight(60)
        self.txt_preview.setStyleSheet(
            "QPlainTextEdit { background-color: #121316; border: 1px solid #2E323A; border-radius: 6px; "
            "color: #F5F5F5; font-size: 12px; line-height: 1.4; padding: 6px; selection-background-color: #3F434C; }"
            "QPlainTextEdit:focus { border: 1px solid #A7B0BC; }"
        )
        v_layout.addWidget(self.txt_preview)

        # ---------------- 4. Action Buttons ---------------- #
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_toggle_dictation = QPushButton("▶ Start Dictation [Ctrl+Shift+D]")
        self.btn_toggle_dictation.setFixedHeight(30)
        self.btn_toggle_dictation.setStyleSheet(
            "QPushButton { background-color: #064E3B; color: #6EE7B7; border: 1px solid #059669; "
            "border-radius: 6px; font-size: 12px; font-weight: 600; padding: 4px 14px; }"
            "QPushButton:hover { background-color: #065F46; border-color: #10B981; color: #A7F3D0; }"
        )
        self.btn_toggle_dictation.clicked.connect(self._on_toggle_dictation_clicked)
        btn_layout.addWidget(self.btn_toggle_dictation, 2)

        self.btn_insert = QPushButton("Insert at Cursor")
        self.btn_insert.setFixedHeight(30)
        self.btn_insert.setStyleSheet(
            "QPushButton { background-color: #202226; color: #E4E4E7; border: 1px solid #2E323A; "
            "border-radius: 6px; font-size: 12px; font-weight: 600; padding: 4px 12px; }"
            "QPushButton:hover { background-color: #292C32; border-color: #3F434C; color: #FFFFFF; }"
        )
        self.btn_insert.clicked.connect(self._on_insert_clicked)
        btn_layout.addWidget(self.btn_insert, 1)

        self.btn_copy = QPushButton("Copy")
        self.btn_copy.setFixedHeight(30)
        self.btn_copy.setStyleSheet(
            "QPushButton { background-color: #202226; color: #A1A1AA; border: 1px solid #2E323A; "
            "border-radius: 6px; font-size: 11px; font-weight: 600; padding: 4px 10px; }"
            "QPushButton:hover { background-color: #292C32; color: #F5F5F5; }"
        )
        self.btn_copy.clicked.connect(self._on_copy_clicked)
        btn_layout.addWidget(self.btn_copy)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setFixedHeight(30)
        self.btn_clear.setStyleSheet(
            "QPushButton { background-color: #202226; color: #A1A1AA; border: 1px solid #2E323A; "
            "border-radius: 6px; font-size: 11px; font-weight: 600; padding: 4px 10px; }"
            "QPushButton:hover { background-color: #292C32; color: #F87171; }"
        )
        self.btn_clear.clicked.connect(self.clear_text)
        btn_layout.addWidget(self.btn_clear)

        v_layout.addLayout(btn_layout)

    @Slot()
    def _on_toggle_dictation_clicked(self) -> None:
        self.sig_toggle_dictation.emit()

    @Slot()
    def _on_insert_clicked(self) -> None:
        text = self.txt_preview.toPlainText().strip()
        if text:
            self.sig_insert_text.emit(text)

    @Slot()
    def _on_copy_clicked(self) -> None:
        text = self.txt_preview.toPlainText().strip()
        if text:
            try:
                pyperclip.copy(text)
                self.btn_copy.setText("Copied!")
                # Reset button text after 1.5 seconds
                from PySide6.QtCore import QTimer
                QTimer.singleShot(1500, lambda: self.btn_copy.setText("Copy"))
            except Exception as e:
                logger.warning(f"Failed to copy to clipboard: {e}")

    @Slot()
    def clear_text(self) -> None:
        self.txt_preview.clear()
        self.sig_clear_text.emit()

    @Slot(str)
    def append_text(self, text: str) -> None:
        """Append newly transcribed text chunk with proper spacing."""
        current = self.txt_preview.toPlainText().strip()
        if current:
            new_val = f"{current} {text.strip()}"
        else:
            new_val = text.strip()
        self.txt_preview.setPlainText(new_val)
        # Move cursor to end
        cursor = self.txt_preview.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.txt_preview.setTextCursor(cursor)

    @Slot(float)
    def update_audio_level(self, level: float) -> None:
        """Update live audio meter (0.0 to 1.0)."""
        pct = int(min(1.0, max(0.0, level)) * 100)
        self.level_bar.setValue(pct)
        self.lbl_level_pct.setText(f"{pct}%")

    @Slot(str)
    def set_status(self, status: str) -> None:
        """Update status badge based on voice state."""
        st_upper = status.upper()
        if "DICTAT" in st_upper:
            self.badge_status.set_state("ACTIVE", "DICTATING")
        elif "TRANSCRIB" in st_upper:
            self.badge_status.set_state("WARNING", "TRANSCRIBING")
        elif "LISTEN" in st_upper or "READY" in st_upper:
            self.badge_status.set_state("OK", "LISTENING")
        elif "PAUS" in st_upper:
            self.badge_status.set_state("NORMAL", "PAUSED")
        elif "MIC" in st_upper or "ERR" in st_upper or "FAIL" in st_upper:
            self.badge_status.set_state("ERROR", "MIC ERROR")
        else:
            self.badge_status.set_state("NORMAL", st_upper)

    @Slot(int)
    def _on_combo_language_changed(self, index: int) -> None:
        lang = self.combo_language.itemData(index)
        if lang:
            self._current_language = lang
            self._update_lang_indicator(lang)
            logger.info(f"VoiceControlWidget language selected: {lang}")
            self.sig_language_changed.emit(lang)

    def _update_lang_indicator(self, lang: str) -> None:
        lang_upper = lang.upper()
        if lang == "auto":
            self.badge_lang_indicator.set_state("NORMAL", "AUTO")
        elif lang == "hinglish":
            self.badge_lang_indicator.set_state("ACTIVE", "HINGLISH")
        elif lang == "hi":
            self.badge_lang_indicator.set_state("OK", "HI")
        elif lang == "en":
            self.badge_lang_indicator.set_state("OK", "EN")
        else:
            self.badge_lang_indicator.set_state("NORMAL", lang_upper)

    @Slot(str)
    def set_language(self, lang_code: str) -> None:
        """Programmatically set language in combo box without triggering cyclic signal."""
        for i in range(self.combo_language.count()):
            if self.combo_language.itemData(i) == lang_code:
                if self.combo_language.currentIndex() != i:
                    self.combo_language.blockSignals(True)
                    self.combo_language.setCurrentIndex(i)
                    self.combo_language.blockSignals(False)
                self._current_language = lang_code
                self._update_lang_indicator(lang_code)
                break

    @Slot(str)
    @Slot(str, str)
    def set_engine(self, engine_name: str, fallback_reason: str = "") -> None:
        """Update active engine status badge (Cloud Groq vs Local Whisper vs Fallback states)."""
        eng_raw = engine_name.strip()
        eng_upper = eng_raw.upper()

        if "CONNECTING" in eng_upper:
            self.badge_engine.set_state("ACTIVE", "CONNECTING")
            self.badge_engine.setToolTip("Connecting to Groq Cloud Whisper API...")
        elif "API KEY MISSING" in eng_upper or eng_upper == "API_KEY_MISSING":
            self.badge_engine.set_state("WARNING", "API KEY MISSING")
            self.badge_engine.setToolTip("Groq API key not configured; using local whisper.cpp")
        elif "CLOUD UNAVAILABLE" in eng_upper:
            self.badge_engine.set_state("WARNING", "CLOUD UNAVAILABLE")
            reason_tip = fallback_reason or "Network unreachable or service timeout; using local whisper.cpp"
            self.badge_engine.setToolTip(f"Cloud STT unavailable: {reason_tip}")
        elif "FALLBACK" in eng_upper:
            self.badge_engine.set_state("WARNING", "LOCAL WHISPER — OFFLINE FALLBACK")
            reason_tip = fallback_reason or "Cloud STT failed; switched to local whisper.cpp"
            self.badge_engine.setToolTip(f"Offline Fallback: {reason_tip}")
        elif "GROQ" in eng_upper or "CLOUD" in eng_upper:
            self.badge_engine.set_state("OK", "CLOUD WHISPER")
            self.badge_engine.setToolTip("Active Engine: Groq Cloud Whisper API (whisper-large-v3-turbo)")
        elif "LOCAL" in eng_upper or "WHISPER" in eng_upper or "OFFLINE" in eng_upper:
            self.badge_engine.set_state("LOCAL", "LOCAL WHISPER")
            self.badge_engine.setToolTip("Active Engine: Local whisper.cpp (100% offline)")
        else:
            self.badge_engine.set_state("NORMAL", eng_upper)
            self.badge_engine.setToolTip(f"Engine: {eng_upper}")

    def _on_pulse_tick(self) -> None:
        """Lightweight breathing pulse effect during active voice dictation."""
        self._pulse_phase += 0.12
        # Smooth sinusoidal factor between 0.0 and 1.0
        factor = 0.5 + 0.5 * math.sin(self._pulse_phase)
        # Interpolate border color between #C19A62 (Muted Amber) and #F2F0EA (Soft Ivory)
        r = int(193 * (1 - factor) + 242 * factor)
        g = int(154 * (1 - factor) + 240 * factor)
        b = int(98 * (1 - factor) + 234 * factor)
        border_hex = f"#{r:02X}{g:02X}{b:02X}"
        self.btn_toggle_dictation.setStyleSheet(
            f"QPushButton {{ background-color: #332415; color: #F2F0EA; border: 2px solid {border_hex}; "
            f"border-radius: 6px; font-size: 12px; font-weight: 700; padding: 4px 14px; }}"
        )

    @Slot(bool)
    def set_dictating_state(self, is_dictating: bool) -> None:
        """Update toggle button and language lock appearance based on dictation state."""
        self._is_dictating = is_dictating
        # Disallow switching language mid-dictation
        self.combo_language.setEnabled(not is_dictating)

        from config.settings import get_settings
        settings = get_settings()
        reduce_motion = getattr(getattr(settings, "accessibility", None), "reduce_motion", False)

        if is_dictating:
            self.btn_toggle_dictation.setText("⏹ Stop Dictation [Ctrl+Shift+D]")
            self.badge_status.set_state("ACTIVE", "DICTATING")
            # Highlight language indicator while recording
            lang_txt = self.combo_language.currentText().split()[0].upper()
            self.badge_lang_indicator.set_state("ACTIVE", f"REC: {lang_txt}")

            if not reduce_motion:
                self._pulse_phase = 0.0
                self._pulse_timer.start()
            else:
                self.btn_toggle_dictation.setStyleSheet(
                    "QPushButton { background-color: #332415; color: #F2F0EA; border: 2px solid #C19A62; "
                    "border-radius: 6px; font-size: 12px; font-weight: 700; padding: 4px 14px; }"
                )
        else:
            self._pulse_timer.stop()
            self.btn_toggle_dictation.setText("▶ Start Dictation [Ctrl+Shift+D]")
            self.btn_toggle_dictation.setStyleSheet(
                "QPushButton { background-color: #1A211D; color: #89958C; border: 1px solid #34383D; "
                "border-radius: 6px; font-size: 12px; font-weight: 600; padding: 4px 14px; }"
                "QPushButton:hover { background-color: #2D3137; border-color: #89958C; color: #F2F0EA; }"
            )
            self.badge_status.set_state("OK", "LISTENING")
            self._update_lang_indicator(self._current_language)
