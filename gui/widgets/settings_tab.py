"""Settings management panel for HeadMouseAI configuration."""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtMultimedia import QMediaDevices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from config.settings import AppSettings, get_settings
from utils.logger import logger
from voice_engine.audio_capture import AudioDeviceManager


def _make_hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("color: #71717A; font-size: 11px; margin-top: -2px; margin-bottom: 4px;")
    lbl.setWordWrap(True)
    return lbl


class SettingsTabWidget(QWidget):
    """Configuration interface organized into clear categories with helpful descriptions."""

    sig_settings_changed = Signal(dict)
    sig_camera_changed = Signal(int)
    sig_toggle_mesh = Signal(bool)
    sig_toggle_cursor = Signal(bool)
    sig_run_wizard = Signal()
    sig_voice_mic_changed = Signal(int)
    sig_voice_model_changed = Signal(str)
    sig_voice_lang_changed = Signal(str)
    sig_voice_enabled_changed = Signal(bool)
    sig_voice_autopaste_changed = Signal(bool)
    sig_voice_threshold_changed = Signal(float)
    sig_groq_key_changed = Signal(str)
    sig_gemini_key_changed = Signal(str)
    sig_stt_mode_changed = Signal(str)
    sig_tts_toggled = Signal(bool)
    sig_show_floating_panel = Signal()
    sig_floating_panel_toggled = Signal(bool)

    def __init__(self, settings: Optional[AppSettings] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.settings: AppSettings = settings if settings is not None else get_settings()
        self._init_ui()
        self.populate_from_settings(self.settings)

    def _init_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(14, 14, 14, 14)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(16)

        # ---------------- 1. Camera Settings ---------------- #
        grp_cam = QGroupBox("Camera Settings")
        form_cam = QFormLayout(grp_cam)
        form_cam.setSpacing(8)

        self.combo_camera = QComboBox()
        self._populate_camera_devices()
        self.combo_camera.currentIndexChanged.connect(self._on_camera_selected)
        form_cam.addRow("Active Video Camera:", self.combo_camera)
        form_cam.addRow("", _make_hint("Select your connected webcam or smartphone camera (Iriun Webcam)."))

        self.combo_resolution = QComboBox()
        self.combo_resolution.addItem("640 x 480 (Recommended — Minimum Latency)", "640x480")
        self.combo_resolution.addItem("1280 x 720 (HD Quality)", "1280x720")
        self.combo_resolution.currentIndexChanged.connect(self._on_resolution_changed)
        form_cam.addRow("Capture Resolution:", self.combo_resolution)
        form_cam.addRow("", _make_hint("640x480 yields the lowest MediaPipe inference latency and lowest CPU usage."))

        layout.addWidget(grp_cam)

        # ---------------- 2. Cursor Sensitivity ---------------- #
        grp_cursor = QGroupBox("Cursor Sensitivity && Dead Zone")
        form_cursor = QFormLayout(grp_cursor)
        form_cursor.setSpacing(8)

        # Sensitivity (1.0 to 10.0)
        self.slider_sens = QSlider(Qt.Orientation.Horizontal)
        self.slider_sens.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.slider_sens.setRange(10, 100)
        self.slider_sens.setValue(int(self.settings.nose_tracking.sensitivity * 10))
        self.lbl_sens_val = QLabel(f"{self.settings.nose_tracking.sensitivity:.1f}")
        self.lbl_sens_val.setFixedWidth(40)
        self.lbl_sens_val.setStyleSheet("font-weight: 600; color: #A7B0BC; font-family: Consolas, monospace;")
        self.slider_sens.valueChanged.connect(self._on_sens_changed)
        h_sens = QHBoxLayout()
        h_sens.addWidget(self.slider_sens)
        h_sens.addWidget(self.lbl_sens_val)
        form_cursor.addRow("Head Sensitivity:", h_sens)
        form_cursor.addRow("", _make_hint("Controls cursor distance moved relative to physical head rotation."))

        # Dead Zone (2 to 30 px)
        self.slider_deadzone = QSlider(Qt.Orientation.Horizontal)
        self.slider_deadzone.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.slider_deadzone.setRange(2, 30)
        self.slider_deadzone.setValue(int(self.settings.nose_tracking.dead_zone))
        self.lbl_deadzone_val = QLabel(f"{int(self.settings.nose_tracking.dead_zone)} px")
        self.lbl_deadzone_val.setFixedWidth(40)
        self.lbl_deadzone_val.setStyleSheet("font-weight: 600; color: #A7B0BC; font-family: Consolas, monospace;")
        self.slider_deadzone.valueChanged.connect(self._on_deadzone_changed)
        h_dz = QHBoxLayout()
        h_dz.addWidget(self.slider_deadzone)
        h_dz.addWidget(self.lbl_deadzone_val)
        form_cursor.addRow("Neutral Dead Zone:", h_dz)
        form_cursor.addRow("", _make_hint("Filters out natural head tremors and micro-movements when resting."))

        # Smoothing Strength (0.10 to 0.80)
        self.slider_smooth = QSlider(Qt.Orientation.Horizontal)
        self.slider_smooth.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.slider_smooth.setRange(10, 80)
        self.slider_smooth.setValue(int(self.settings.nose_tracking.smoothing_strength * 100))
        self.lbl_smooth_val = QLabel(f"{self.settings.nose_tracking.smoothing_strength:.2f}")
        self.lbl_smooth_val.setFixedWidth(40)
        self.lbl_smooth_val.setStyleSheet("font-weight: 600; color: #A7B0BC; font-family: Consolas, monospace;")
        self.slider_smooth.valueChanged.connect(self._on_smooth_changed)
        h_sm = QHBoxLayout()
        h_sm.addWidget(self.slider_smooth)
        h_sm.addWidget(self.lbl_smooth_val)
        form_cursor.addRow("Motion Smoothing:", h_sm)
        form_cursor.addRow("", _make_hint("Exponential filter gain: higher values feel snappier, lower values are smoother."))

        # Mouse Speed (1 to 10)
        self.slider_speed = QSlider(Qt.Orientation.Horizontal)
        self.slider_speed.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.slider_speed.setRange(1, 10)
        self.slider_speed.setValue(int(self.settings.mouse.cursor_speed))
        self.lbl_speed_val = QLabel(f"{int(self.settings.mouse.cursor_speed)}")
        self.lbl_speed_val.setFixedWidth(40)
        self.lbl_speed_val.setStyleSheet("font-weight: 600; color: #A7B0BC; font-family: Consolas, monospace;")
        self.slider_speed.valueChanged.connect(self._on_speed_changed)
        h_sp = QHBoxLayout()
        h_sp.addWidget(self.slider_speed)
        h_sp.addWidget(self.lbl_speed_val)
        form_cursor.addRow("OS Pointer Speed:", h_sp)
        form_cursor.addRow("", _make_hint("Windows mouse actuation speed multiplier."))

        layout.addWidget(grp_cursor)

        # ---------------- 3. Eye Gestures ---------------- #
        grp_clicks = QGroupBox("Eye Gestures && Clicks")
        form_clicks = QFormLayout(grp_clicks)
        form_clicks.setSpacing(8)

        # Left Wink Sensitivity
        self.slider_left_sens = QSlider(Qt.Orientation.Horizontal)
        self.slider_left_sens.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.slider_left_sens.setRange(40, 95)
        self.slider_left_sens.setValue(int(getattr(self.settings.eye_blink, "left_sensitivity", 0.75) * 100))
        self.lbl_left_sens_val = QLabel(f"{self.slider_left_sens.value() / 100:.2f}")
        self.lbl_left_sens_val.setFixedWidth(40)
        self.lbl_left_sens_val.setStyleSheet("font-weight: 600; color: #6EE7B7; font-family: Consolas, monospace;")
        self.slider_left_sens.valueChanged.connect(self._on_left_sens_changed)
        h_ls = QHBoxLayout()
        h_ls.addWidget(self.slider_left_sens)
        h_ls.addWidget(self.lbl_left_sens_val)
        form_clicks.addRow("Left Wink Sensitivity:", h_ls)
        form_clicks.addRow("", _make_hint("Sensitivity for left-eye wink detection (Left Click)."))

        # Right Wink Sensitivity
        self.slider_right_sens = QSlider(Qt.Orientation.Horizontal)
        self.slider_right_sens.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.slider_right_sens.setRange(40, 95)
        self.slider_right_sens.setValue(int(getattr(self.settings.eye_blink, "right_sensitivity", 0.75) * 100))
        self.lbl_right_sens_val = QLabel(f"{self.slider_right_sens.value() / 100:.2f}")
        self.lbl_right_sens_val.setFixedWidth(40)
        self.lbl_right_sens_val.setStyleSheet("font-weight: 600; color: #6EE7B7; font-family: Consolas, monospace;")
        self.slider_right_sens.valueChanged.connect(self._on_right_sens_changed)
        h_rs = QHBoxLayout()
        h_rs.addWidget(self.slider_right_sens)
        h_rs.addWidget(self.lbl_right_sens_val)
        form_clicks.addRow("Right Wink Sensitivity:", h_rs)
        form_clicks.addRow("", _make_hint("Sensitivity for right-eye wink detection (Right Click)."))

        # Drag Hold Duration
        self.slider_drag_hold = QSlider(Qt.Orientation.Horizontal)
        self.slider_drag_hold.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.slider_drag_hold.setRange(20, 80)
        self.slider_drag_hold.setValue(int(self.settings.eye_blink.drag_hold_sec * 100))
        self.lbl_drag_val = QLabel(f"{self.settings.eye_blink.drag_hold_sec:.2f}s")
        self.lbl_drag_val.setFixedWidth(40)
        self.lbl_drag_val.setStyleSheet("font-weight: 600; color: #6EE7B7; font-family: Consolas, monospace;")
        self.slider_drag_hold.valueChanged.connect(self._on_drag_hold_changed)
        h_dh = QHBoxLayout()
        h_dh.addWidget(self.slider_drag_hold)
        h_dh.addWidget(self.lbl_drag_val)
        form_clicks.addRow("Drag Hold Duration:", h_dh)
        form_clicks.addRow("", _make_hint("Hold left eye closed for this duration to engage mouse-down drag."))

        self.chk_stabilize = QCheckBox("Enable Click Position Stabilization Freeze")
        self.chk_stabilize.setChecked(True)
        form_clicks.addRow("", self.chk_stabilize)
        form_clicks.addRow("", _make_hint("Freezes cursor position during a wink to prevent accidental displacement."))

        layout.addWidget(grp_clicks)

        # ---------------- 4. Scroll & Zoom ---------------- #
        grp_gestures = QGroupBox("Scroll && Zoom")
        form_gestures = QFormLayout(grp_gestures)
        form_gestures.setSpacing(8)

        # Scroll Sensitivity
        self.slider_scroll_sens = QSlider(Qt.Orientation.Horizontal)
        self.slider_scroll_sens.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.slider_scroll_sens.setRange(1, 8)
        self.slider_scroll_sens.setValue(int(getattr(self.settings.zoom, "scroll_step", 2)))
        self.lbl_scroll_sens_val = QLabel(f"{self.slider_scroll_sens.value()} lines")
        self.lbl_scroll_sens_val.setFixedWidth(55)
        self.lbl_scroll_sens_val.setStyleSheet("font-weight: 600; color: #A7B0BC; font-family: Consolas, monospace;")
        self.slider_scroll_sens.valueChanged.connect(self._on_scroll_sens_changed)
        h_ss = QHBoxLayout()
        h_ss.addWidget(self.slider_scroll_sens)
        h_ss.addWidget(self.lbl_scroll_sens_val)
        form_gestures.addRow("Scroll Step Speed:", h_ss)
        form_gestures.addRow("", _make_hint("Lines scrolled per head tilt step during smile mode."))

        # Zoom Sensitivity
        self.slider_zoom_sens = QSlider(Qt.Orientation.Horizontal)
        self.slider_zoom_sens.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.slider_zoom_sens.setRange(1, 5)
        self.slider_zoom_sens.setValue(int(getattr(self.settings.zoom, "zoom_step", 1)))
        self.lbl_zoom_sens_val = QLabel(f"{self.slider_zoom_sens.value()}x")
        self.lbl_zoom_sens_val.setFixedWidth(45)
        self.lbl_zoom_sens_val.setStyleSheet("font-weight: 600; color: #A7B0BC; font-family: Consolas, monospace;")
        self.slider_zoom_sens.valueChanged.connect(self._on_zoom_sens_changed)
        h_zs = QHBoxLayout()
        h_zs.addWidget(self.slider_zoom_sens)
        h_zs.addWidget(self.lbl_zoom_sens_val)
        form_gestures.addRow("Zoom Step Size:", h_zs)
        form_gestures.addRow("", _make_hint("Magnification increments when tilting head with raised eyebrows."))

        # Smile / Teeth Sensitivity
        self.slider_smile_sens = QSlider(Qt.Orientation.Horizontal)
        self.slider_smile_sens.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.slider_smile_sens.setRange(80, 130)
        self.slider_smile_sens.setValue(int(getattr(self.settings.zoom, "smile_sensitivity", 1.0) * 100))
        self.lbl_smile_sens_val = QLabel(f"{self.slider_smile_sens.value() / 100:.2f}")
        self.lbl_smile_sens_val.setFixedWidth(45)
        self.lbl_smile_sens_val.setStyleSheet("font-weight: 600; color: #A7B0BC; font-family: Consolas, monospace;")
        self.slider_smile_sens.valueChanged.connect(self._on_smile_sens_changed)
        h_sm_sens = QHBoxLayout()
        h_sm_sens.addWidget(self.slider_smile_sens)
        h_sm_sens.addWidget(self.lbl_smile_sens_val)
        form_gestures.addRow("Smile Sensitivity:", h_sm_sens)
        form_gestures.addRow("", _make_hint("Mouth geometry threshold for engaging hands-free scroll/zoom."))

        layout.addWidget(grp_gestures)

        # ---------------- 5. Performance ---------------- #
        grp_perf = QGroupBox("Performance")
        form_perf = QFormLayout(grp_perf)
        form_perf.setSpacing(8)

        self.combo_perf_mode = QComboBox()
        self.combo_perf_mode.addItem("Balanced (Recommended)", "balanced")
        self.combo_perf_mode.addItem("High Performance (Minimal CPU)", "performance")
        self.combo_perf_mode.addItem("High Quality (Full Visuals)", "quality")
        self.combo_perf_mode.currentIndexChanged.connect(self._on_perf_mode_changed)
        form_perf.addRow("Processing Profile:", self.combo_perf_mode)
        form_perf.addRow("", _make_hint("Optimizes background landmark extraction versus system resource usage."))

        self.combo_refresh_rate = QComboBox()
        self.combo_refresh_rate.addItem("20 Hz (Balanced, Low CPU)", 20)
        self.combo_refresh_rate.addItem("30 Hz (Ultra Smooth)", 30)
        self.combo_refresh_rate.addItem("15 Hz (Power Saver)", 15)
        self.combo_refresh_rate.currentIndexChanged.connect(self._on_refresh_rate_changed)
        form_perf.addRow("UI Refresh Rate:", self.combo_refresh_rate)
        form_perf.addRow("", _make_hint("Frequency of UI dashboard and telemetry diagnostic refreshes."))

        layout.addWidget(grp_perf)

        # ---------------- 6. Appearance ---------------- #
        grp_appear = QGroupBox("Appearance")
        form_appear = QFormLayout(grp_appear)
        form_appear.setSpacing(8)

        self.chk_mesh = QCheckBox("Render Facial Landmark Mesh on Preview")
        self.chk_mesh.setChecked(True)
        self.chk_mesh.toggled.connect(self.sig_toggle_mesh.emit)
        form_appear.addRow("", self.chk_mesh)
        form_appear.addRow("", _make_hint("Displays tracking landmark points on your live face in the video view."))

        self.chk_cursor = QCheckBox("Render Virtual Cursor Reticle on Preview")
        self.chk_cursor.setChecked(True)
        self.chk_cursor.toggled.connect(self.sig_toggle_cursor.emit)
        form_appear.addRow("", self.chk_cursor)
        form_appear.addRow("", _make_hint("Displays the yellow/green tracking crosshair showing where your nose points."))

        layout.addWidget(grp_appear)

        # ---------------- 7. Jadoo Voice Engine ---------------- #
        grp_voice = QGroupBox("Jadoo Voice Engine (Offline Dictation && Commands)")
        form_voice = QFormLayout(grp_voice)
        form_voice.setSpacing(8)

        self.chk_voice_enabled = QCheckBox("Enable Voice Engine Subsystem")
        self.chk_voice_enabled.setChecked(getattr(self.settings.voice, "enabled", True))
        self.chk_voice_enabled.toggled.connect(self._on_voice_enabled_toggled)
        form_voice.addRow("", self.chk_voice_enabled)
        form_voice.addRow("", _make_hint("Enables offline speech recognition and voice commands on a dedicated background thread."))

        self.combo_voice_mic = QComboBox()
        self._populate_audio_devices()
        self.combo_voice_mic.currentIndexChanged.connect(self._on_voice_mic_selected)
        form_voice.addRow("Microphone Input:", self.combo_voice_mic)
        form_voice.addRow("", _make_hint("Select your audio input device for offline dictation and voice commands."))

        self.combo_voice_model = QComboBox()
        self.combo_voice_model.addItem("ggml-base.bin (141 MB — Standard Quality, Recommended)", "ggml-base.bin")
        self.combo_voice_model.addItem("ggml-tiny.bin (74 MB — Fast, Low RAM)", "ggml-tiny.bin")
        self.combo_voice_model.currentIndexChanged.connect(self._on_voice_model_selected)
        form_voice.addRow("Whisper Model:", self.combo_voice_model)
        form_voice.addRow("", _make_hint("Both models run 100% offline using optimized whisper.cpp CPU binaries (capped <= 2 threads)."))

        self.combo_voice_lang = QComboBox()
        self.combo_voice_lang.addItem("English (en — Recommended)", "en")
        self.combo_voice_lang.addItem("Hindi (hi)", "hi")
        self.combo_voice_lang.addItem("Hinglish (Hindi + English mixed)", "hinglish")
        self.combo_voice_lang.addItem("Auto-Detect (Hindi / English / Hinglish)", "auto")
        self.combo_voice_lang.currentIndexChanged.connect(self._on_voice_lang_selected)
        form_voice.addRow("Spoken Language:", self.combo_voice_lang)
        form_voice.addRow("", _make_hint("Whisper automatically transcribes speech into text in the detected or selected language."))

        self.chk_voice_autopaste = QCheckBox("Auto-Insert Dictation into Target Window (Ctrl+V)")
        self.chk_voice_autopaste.setChecked(getattr(self.settings.voice, "auto_paste", True))
        self.chk_voice_autopaste.toggled.connect(self._on_voice_autopaste_toggled)
        form_voice.addRow("", self.chk_voice_autopaste)
        form_voice.addRow("", _make_hint("When checked, finalized dictation automatically pastes at current active cursor position."))

        # VAD Sensitivity Preset
        self.combo_vad_preset = QComboBox()
        self.combo_vad_preset.addItem("Medium (Default — Normal Room / Fan Noise)", "medium")
        self.combo_vad_preset.addItem("Low Sensitivity (High Suppression — Loud Fan/AC)", "low")
        self.combo_vad_preset.addItem("High Sensitivity (Quiet Room)", "high")
        self.combo_vad_preset.currentIndexChanged.connect(self._on_vad_preset_selected)
        form_voice.addRow("Voice Detection Preset:", self.combo_vad_preset)
        form_voice.addRow("", _make_hint("Tunes the energy threshold to prevent continuous room, AC, or fan noise triggering."))

        # VAD Threshold Slider (0.010 to 0.100)
        self.slider_voice_threshold = QSlider(Qt.Orientation.Horizontal)
        self.slider_voice_threshold.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.slider_voice_threshold.setRange(10, 100)
        curr_thresh = int(getattr(self.settings.voice, "energy_threshold", 0.035) * 1000)
        self.slider_voice_threshold.setValue(curr_thresh)
        self.lbl_voice_threshold_val = QLabel(f"{curr_thresh / 1000:.3f}")
        self.lbl_voice_threshold_val.setFixedWidth(50)
        self.lbl_voice_threshold_val.setStyleSheet("font-weight: 600; color: #A7B0BC; font-family: Consolas, monospace;")
        self.slider_voice_threshold.valueChanged.connect(self._on_voice_threshold_slider_changed)
        h_vth = QHBoxLayout()
        h_vth.addWidget(self.slider_voice_threshold)
        h_vth.addWidget(self.lbl_voice_threshold_val)
        form_voice.addRow("Custom Energy Gate:", h_vth)
        form_voice.addRow("", _make_hint("Fine-tune RMS speech threshold (increase if ambient room noise triggers false transcriptions)."))

        layout.addWidget(grp_voice)

        # ---------------- 8. Online Jadoo AI Assistant & Cloud STT ---------------- #
        grp_jadoo = QGroupBox("Online Jadoo AI Assistant && Cloud STT")
        form_jadoo = QFormLayout(grp_jadoo)
        form_jadoo.setSpacing(8)

        # STT Engine Mode
        self.combo_stt_mode = QComboBox()
        self.combo_stt_mode.addItem("Cloud First (Default — Groq Whisper with Local Fallback)", "cloud_first")
        self.combo_stt_mode.addItem("Automatic (Dynamic Auto-Select based on availability)", "auto")
        self.combo_stt_mode.addItem("Offline Only (100% Local whisper.cpp, Zero Network Requests)", "offline")
        self.combo_stt_mode.addItem("Cloud Only (Groq Whisper Only, No Offline Fallback)", "cloud")
        self.combo_stt_mode.currentIndexChanged.connect(self._on_stt_mode_selected)
        form_jadoo.addRow("STT Engine Mode:", self.combo_stt_mode)
        form_jadoo.addRow("", _make_hint("Cloud First uses Groq Cloud Whisper (~300ms) with automatic local whisper.cpp fallback if offline or unconfigured."))

        # Groq API Key
        h_groq = QHBoxLayout()
        self.inp_groq_key = QLineEdit()
        self.inp_groq_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_groq_key.setPlaceholderText("gsk_...")
        self.inp_groq_key.textChanged.connect(self._on_groq_key_changed)
        h_groq.addWidget(self.inp_groq_key)
        self.btn_toggle_groq = QPushButton("Show")
        self.btn_toggle_groq.setFixedWidth(50)
        self.btn_toggle_groq.clicked.connect(lambda: self._toggle_echo_mode(self.inp_groq_key, self.btn_toggle_groq))
        h_groq.addWidget(self.btn_toggle_groq)
        form_jadoo.addRow("Groq API Key (Cloud STT):", h_groq)
        form_jadoo.addRow("", _make_hint("Optional. Free tier key from console.groq.com. Provides ultra-fast ~300ms voice transcription."))

        # Gemini API Key
        h_gemini = QHBoxLayout()
        self.inp_gemini_key = QLineEdit()
        self.inp_gemini_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_gemini_key.setPlaceholderText("AIza...")
        self.inp_gemini_key.textChanged.connect(self._on_gemini_key_changed)
        h_gemini.addWidget(self.inp_gemini_key)
        self.btn_toggle_gemini = QPushButton("Show")
        self.btn_toggle_gemini.setFixedWidth(50)
        self.btn_toggle_gemini.clicked.connect(lambda: self._toggle_echo_mode(self.inp_gemini_key, self.btn_toggle_gemini))
        h_gemini.addWidget(self.btn_toggle_gemini)
        form_jadoo.addRow("Gemini API Key (AI Assistant):", h_gemini)
        form_jadoo.addRow("", _make_hint("Key from aistudio.google.com for Jadoo conversational answers, Hinglish rewrite, and screen guidance."))

        # SAPI TTS Checkbox
        self.chk_tts_enabled = QCheckBox("Enable Windows SAPI Voice Responses (Spoken Answers)")
        self.chk_tts_enabled.setChecked(getattr(self.settings.jadoo, "tts_enabled", False) if hasattr(self.settings, "jadoo") else False)
        self.chk_tts_enabled.toggled.connect(self._on_tts_toggled)
        form_jadoo.addRow("", self.chk_tts_enabled)
        form_jadoo.addRow("", _make_hint("Uses native Windows Speech Synthesis to speak responses aloud. Automatically pauses microphone during speech."))

        layout.addWidget(grp_jadoo)

        # ---------------- 8b. Hands-Free Accessibility & Floating Panel ---------------- #
        grp_access = QGroupBox("Jadoo Hands-Free Accessibility && Floating Panel")
        form_access = QFormLayout(grp_access)
        form_access.setSpacing(8)

        self.chk_auto_show_panel = QCheckBox("Show Always-On-Top Floating Control Panel")
        self.chk_auto_show_panel.setChecked(getattr(self.settings.accessibility, "auto_show_panel", True))
        self.chk_auto_show_panel.toggled.connect(self._on_auto_show_panel_toggled)
        form_access.addRow("", self.chk_auto_show_panel)

        self.btn_toggle_panel_now = QPushButton("Toggle Floating Panel Visibility")
        self.btn_toggle_panel_now.setFixedHeight(32)
        self.btn_toggle_panel_now.clicked.connect(self.sig_show_floating_panel.emit)
        form_access.addRow("Quick Action:", self.btn_toggle_panel_now)

        self.chk_windows_startup = QCheckBox("Launch Jadoo Automatically on Windows Login")
        from utils.windows_startup import is_windows_startup_enabled
        self.chk_windows_startup.setChecked(is_windows_startup_enabled())
        self.chk_windows_startup.toggled.connect(self._on_windows_startup_toggled)
        form_access.addRow("", self.chk_windows_startup)
        form_access.addRow("", _make_hint("Registers HeadMouseAI in Windows Run registry key. Never installed without explicit user toggle."))

        self.chk_tts_feedback = QCheckBox("Spoken Voice Feedback for Voice && Panel Actions")
        self.chk_tts_feedback.setChecked(getattr(self.settings.accessibility, "tts_feedback", True))
        self.chk_tts_feedback.toggled.connect(self._on_tts_feedback_toggled)
        form_access.addRow("", self.chk_tts_feedback)

        self.combo_panel_btn_size = QComboBox()
        self.combo_panel_btn_size.addItem("Large (Recommended for Head Mouse)", "large")
        self.combo_panel_btn_size.addItem("Medium (Compact)", "medium")
        cur_btn_size = getattr(self.settings.accessibility, "button_size", "large")
        idx_size = 0 if cur_btn_size == "large" else 1
        self.combo_panel_btn_size.setCurrentIndex(idx_size)
        self.combo_panel_btn_size.currentIndexChanged.connect(self._on_btn_size_selected)
        form_access.addRow("Panel Button Size:", self.combo_panel_btn_size)

        layout.addWidget(grp_access)

        # ---------------- 9. Persistence & Actions ---------------- #
        grp_actions = QGroupBox("User Profiles && Calibration")
        v_actions = QVBoxLayout(grp_actions)
        v_actions.setSpacing(10)

        self.btn_wizard = QPushButton("Launch Calibration Wizard [C]")
        self.btn_wizard.setFixedHeight(38)
        self.btn_wizard.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1E3A8A, stop:1 #172554); "
            "border: 1px solid #3B82F6; color: #FFFFFF; font-weight: 700; border-radius: 6px; font-size: 13px; }"
            "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563EB, stop:1 #1E3A8A); border-color: #60A5FA; }"
            "QPushButton:focus { border: 2px solid #93C5FD; }"
        )
        self.btn_wizard.clicked.connect(self.sig_run_wizard.emit)
        v_actions.addWidget(self.btn_wizard)

        h_persist = QHBoxLayout()
        h_persist.setSpacing(10)

        self.btn_save = QPushButton("Save Settings to config.toml")
        self.btn_save.setFixedHeight(34)
        self.btn_save.clicked.connect(self._save_to_config)
        h_persist.addWidget(self.btn_save)

        self.btn_reload = QPushButton("Reload from config.toml")
        self.btn_reload.setFixedHeight(34)
        self.btn_reload.clicked.connect(self._reload_from_config)
        h_persist.addWidget(self.btn_reload)

        self.btn_reset = QPushButton("Reset to Factory Defaults")
        self.btn_reset.setFixedHeight(34)
        self.btn_reset.setStyleSheet(
            "QPushButton { background-color: #251214; color: #FCA5A5; border: 1px solid #7F1D1D; border-radius: 6px; font-weight: 600; }"
            "QPushButton:hover { background-color: #3B161B; border-color: #B91C1C; color: #FFFFFF; }"
            "QPushButton:focus { border: 2px solid #FCA5A5; }"
        )
        self.btn_reset.clicked.connect(self._on_reset_defaults)
        h_persist.addWidget(self.btn_reset)

        v_actions.addLayout(h_persist)

        self.lbl_save_status = QLabel("")
        self.lbl_save_status.setStyleSheet("color: #34D399; font-weight: 600; font-size: 12px;")
        v_actions.addWidget(self.lbl_save_status)

        layout.addWidget(grp_actions)

        layout.addStretch(1)
        scroll.setWidget(container)
        outer_layout.addWidget(scroll)

    def _populate_camera_devices(self) -> None:
        """Enumerate camera hardware using QMediaDevices."""
        self.combo_camera.clear()
        try:
            devices = QMediaDevices.videoInputs()
            if devices:
                for idx, dev in enumerate(devices):
                    self.combo_camera.addItem(f"Camera {idx}: {dev.description()}", idx)
            else:
                self.combo_camera.addItem("Camera 0 (Default)", 0)
        except Exception:
            self.combo_camera.addItem("Camera 0 (Default)", 0)
            self.combo_camera.addItem("Camera 1", 1)

    def _populate_audio_devices(self) -> None:
        """Enumerate audio input devices using AudioDeviceManager with hardware prioritization."""
        self.combo_voice_mic.clear()
        self.combo_voice_mic.addItem("Auto-Select (Best Hardware Microphone)", -1)
        try:
            devices = AudioDeviceManager.get_input_devices()
            if devices:
                for dev in devices:
                    prefix = "🎤 " if dev.get("is_hardware", False) else ("⚠️ [Virtual] " if dev.get("is_virtual", False) else "")
                    self.combo_voice_mic.addItem(f"{prefix}{dev['name']}", dev["index"])
        except Exception as e:
            logger.error(f"Error populating audio devices: {e}")

    def populate_from_settings(self, settings: AppSettings) -> None:
        """Sync UI controls with settings model."""
        self.settings = settings
        cam_idx = getattr(settings.camera, "camera_index", 0)
        for i in range(self.combo_camera.count()):
            if self.combo_camera.itemData(i) == cam_idx:
                self.combo_camera.setCurrentIndex(i)
                break

        self.slider_sens.setValue(int(settings.nose_tracking.sensitivity * 10))
        self.slider_deadzone.setValue(int(settings.nose_tracking.dead_zone))
        self.slider_smooth.setValue(int(settings.nose_tracking.smoothing_strength * 100))
        self.slider_speed.setValue(int(settings.mouse.cursor_speed))
        self.slider_left_sens.setValue(int(getattr(settings.eye_blink, "left_sensitivity", 0.75) * 100))
        self.slider_right_sens.setValue(int(getattr(settings.eye_blink, "right_sensitivity", 0.75) * 100))
        self.slider_drag_hold.setValue(int(settings.eye_blink.drag_hold_sec * 100))
        self.slider_scroll_sens.setValue(int(getattr(settings.zoom, "scroll_step", 2)))
        self.slider_zoom_sens.setValue(int(getattr(settings.zoom, "zoom_step", 1)))
        self.slider_smile_sens.setValue(int(getattr(settings.zoom, "smile_sensitivity", 1.0) * 100))

        # Resolution
        cam_res = f"{getattr(settings.camera, 'width', 640)}x{getattr(settings.camera, 'height', 480)}"
        for i in range(self.combo_resolution.count()):
            if self.combo_resolution.itemData(i) == cam_res:
                self.combo_resolution.setCurrentIndex(i)
                break

        # Performance Mode
        p_mode = getattr(settings.gui, "performance_mode", "balanced").lower()
        for i in range(self.combo_perf_mode.count()):
            if self.combo_perf_mode.itemData(i) == p_mode:
                self.combo_perf_mode.setCurrentIndex(i)
                break

        # UI Refresh Rate
        rf_hz = getattr(settings.gui, "ui_refresh_hz", 20)
        for i in range(self.combo_refresh_rate.count()):
            if self.combo_refresh_rate.itemData(i) == rf_hz:
                self.combo_refresh_rate.setCurrentIndex(i)
                break

        # Voice Settings
        v_cfg = self.settings.voice
        self.chk_voice_enabled.setChecked(v_cfg.enabled)
        self.chk_voice_autopaste.setChecked(v_cfg.auto_paste)

        # Voice Mic
        target_dev = v_cfg.device_index
        if target_dev is None or target_dev == -1:
            self.combo_voice_mic.setCurrentIndex(0)
        else:
            for i in range(self.combo_voice_mic.count()):
                if self.combo_voice_mic.itemData(i) == target_dev:
                    self.combo_voice_mic.setCurrentIndex(i)
                    break

        # Voice Model
        for i in range(self.combo_voice_model.count()):
            if self.combo_voice_model.itemData(i) == v_cfg.model_name:
                self.combo_voice_model.setCurrentIndex(i)
                break

        # Voice Language
        for i in range(self.combo_voice_lang.count()):
            if self.combo_voice_lang.itemData(i) == v_cfg.language:
                self.combo_voice_lang.setCurrentIndex(i)
                break

        # VAD Preset & Threshold
        preset = getattr(v_cfg, "vad_sensitivity", "medium").lower()
        for i in range(self.combo_vad_preset.count()):
            if self.combo_vad_preset.itemData(i) == preset:
                self.combo_vad_preset.setCurrentIndex(i)
                break
        thresh_int = int(getattr(v_cfg, "energy_threshold", 0.028) * 1000)
        self.slider_voice_threshold.setValue(thresh_int)
        self.lbl_voice_threshold_val.setText(f"{thresh_int / 1000:.3f}")

        # Jadoo Assistant & STT Settings
        j_cfg = getattr(settings, "jadoo", None)
        if j_cfg is not None:
            self.inp_groq_key.setText(j_cfg.groq_api_key or "")
            from ai_provider.groq_stt import resolve_groq_api_key
            if not j_cfg.groq_api_key and resolve_groq_api_key():
                self.inp_groq_key.setPlaceholderText("(Active via Windows Environment Variable)")
            else:
                self.inp_groq_key.setPlaceholderText("gsk_...")
            self.inp_gemini_key.setText(j_cfg.gemini_api_key or "")
            for i in range(self.combo_stt_mode.count()):
                if self.combo_stt_mode.itemData(i) == j_cfg.stt_mode:
                    self.combo_stt_mode.setCurrentIndex(i)
                    break
            self.chk_tts_enabled.setChecked(j_cfg.tts_enabled)

        # Accessibility Settings
        acc_cfg = getattr(settings, "accessibility", None)
        if acc_cfg is not None:
            self.chk_auto_show_panel.setChecked(acc_cfg.auto_show_panel)
            self.chk_tts_feedback.setChecked(acc_cfg.tts_feedback)
            idx_s = 0 if acc_cfg.button_size == "large" else 1
            self.combo_panel_btn_size.setCurrentIndex(idx_s)
        try:
            from utils.windows_startup import is_windows_startup_enabled
            self.chk_windows_startup.setChecked(is_windows_startup_enabled())
        except Exception:
            pass

    def _on_camera_selected(self, index: int) -> None:
        cam_id = self.combo_camera.itemData(index)
        if cam_id is not None:
            self.settings.camera.camera_index = int(cam_id)
            self.sig_camera_changed.emit(int(cam_id))

    def _on_sens_changed(self, val: int) -> None:
        sens = val / 10.0
        self.lbl_sens_val.setText(f"{sens:.1f}")
        self.settings.nose_tracking.sensitivity = sens
        self.sig_settings_changed.emit({"sensitivity": sens})

    def _on_deadzone_changed(self, val: int) -> None:
        self.lbl_deadzone_val.setText(f"{val} px")
        self.settings.nose_tracking.dead_zone = float(val)
        self.sig_settings_changed.emit({"dead_zone": float(val)})

    def _on_smooth_changed(self, val: int) -> None:
        smooth = val / 100.0
        self.lbl_smooth_val.setText(f"{smooth:.2f}")
        self.settings.nose_tracking.smoothing_strength = smooth
        self.sig_settings_changed.emit({"smoothing_strength": smooth})

    def _on_speed_changed(self, val: int) -> None:
        self.lbl_speed_val.setText(f"{val}")
        self.settings.mouse.cursor_speed = int(val)
        self.sig_settings_changed.emit({"cursor_speed": int(val)})

    def _on_left_sens_changed(self, val: int) -> None:
        sens = val / 100.0
        self.lbl_left_sens_val.setText(f"{sens:.2f}")
        self.settings.eye_blink.left_sensitivity = sens
        self.sig_settings_changed.emit({"left_sensitivity": sens})

    def _on_right_sens_changed(self, val: int) -> None:
        sens = val / 100.0
        self.lbl_right_sens_val.setText(f"{sens:.2f}")
        self.settings.eye_blink.right_sensitivity = sens
        self.sig_settings_changed.emit({"right_sensitivity": sens})

    def _on_drag_hold_changed(self, val: int) -> None:
        dh = val / 100.0
        self.lbl_drag_val.setText(f"{dh:.2f}s")
        self.settings.eye_blink.drag_hold_sec = dh
        self.sig_settings_changed.emit({"drag_hold_sec": dh})

    def _on_scroll_sens_changed(self, val: int) -> None:
        self.lbl_scroll_sens_val.setText(f"{val} lines")
        self.settings.zoom.scroll_step = val
        self.sig_settings_changed.emit({"scroll_step": val})

    def _on_zoom_sens_changed(self, val: int) -> None:
        self.lbl_zoom_sens_val.setText(f"{val}x")
        self.settings.zoom.zoom_step = val
        self.sig_settings_changed.emit({"zoom_step": val})

    def _on_smile_sens_changed(self, val: int) -> None:
        sm = val / 100.0
        self.lbl_smile_sens_val.setText(f"{sm:.2f}")
        self.settings.zoom.smile_sensitivity = sm
        self.sig_settings_changed.emit({"smile_sensitivity": sm})

    def _on_resolution_changed(self, index: int) -> None:
        res = self.combo_resolution.itemData(index)
        if res:
            parts = str(res).split("x")
            w, h = int(parts[0]), int(parts[1])
            self.settings.camera.width = w
            self.settings.camera.height = h
            self.sig_settings_changed.emit({"camera_resolution": res})

    def _on_perf_mode_changed(self, index: int) -> None:
        mode = self.combo_perf_mode.itemData(index)
        if mode:
            self.settings.gui.performance_mode = str(mode)
            self.sig_settings_changed.emit({"performance_mode": str(mode)})

    def _on_refresh_rate_changed(self, index: int) -> None:
        hz = self.combo_refresh_rate.itemData(index)
        if hz:
            self.settings.gui.ui_refresh_hz = int(hz)
            self.sig_settings_changed.emit({"ui_refresh_hz": int(hz)})

    def _on_voice_enabled_toggled(self, checked: bool) -> None:
        self.settings.voice.enabled = checked
        self.sig_voice_enabled_changed.emit(checked)
        self.sig_settings_changed.emit({"voice_enabled": checked})

    def _on_voice_mic_selected(self, index: int) -> None:
        dev_idx = self.combo_voice_mic.itemData(index)
        if dev_idx is not None and dev_idx >= 0:
            self.settings.voice.device_index = int(dev_idx)
            self.sig_voice_mic_changed.emit(int(dev_idx))
            self.sig_settings_changed.emit({"voice_device_index": int(dev_idx)})
        elif dev_idx == -1:
            self.settings.voice.device_index = None

    def _on_voice_model_selected(self, index: int) -> None:
        model = self.combo_voice_model.itemData(index)
        if model:
            self.settings.voice.model_name = str(model)
            self.sig_voice_model_changed.emit(str(model))
            self.sig_settings_changed.emit({"voice_model_name": str(model)})

    def _on_voice_lang_selected(self, index: int) -> None:
        lang = self.combo_voice_lang.itemData(index)
        if lang:
            self.settings.voice.language = str(lang)
            self.sig_voice_lang_changed.emit(str(lang))
            self.sig_settings_changed.emit({"voice_language": str(lang)})

    def set_voice_language(self, lang: str) -> None:
        """Programmatically update combo_voice_lang without triggering cyclic signals."""
        for i in range(self.combo_voice_lang.count()):
            if self.combo_voice_lang.itemData(i) == lang:
                if self.combo_voice_lang.currentIndex() != i:
                    self.combo_voice_lang.blockSignals(True)
                    self.combo_voice_lang.setCurrentIndex(i)
                    self.combo_voice_lang.blockSignals(False)
                break

    def _on_voice_autopaste_toggled(self, checked: bool) -> None:
        self.settings.voice.auto_paste = checked
        self.sig_voice_autopaste_changed.emit(checked)
        self.sig_settings_changed.emit({"voice_auto_paste": checked})

    def _on_vad_preset_selected(self, index: int) -> None:
        preset = self.combo_vad_preset.itemData(index)
        if not preset:
            return
        preset_str = str(preset)
        self.settings.voice.vad_sensitivity = preset_str
        if preset_str == "high":
            thresh = 0.022
        elif preset_str == "low":
            thresh = 0.055
        else:  # medium
            thresh = 0.035

        self.slider_voice_threshold.setValue(int(thresh * 1000))
        self.lbl_voice_threshold_val.setText(f"{thresh:.3f}")
        self.settings.voice.energy_threshold = thresh
        self.sig_voice_threshold_changed.emit(thresh)
        self.sig_settings_changed.emit({"voice_energy_threshold": thresh, "voice_vad_sensitivity": preset_str})

    def _on_voice_threshold_slider_changed(self, val: int) -> None:
        thresh = val / 1000.0
        self.lbl_voice_threshold_val.setText(f"{thresh:.3f}")
        self.settings.voice.energy_threshold = thresh
        self.sig_voice_threshold_changed.emit(thresh)
        self.sig_settings_changed.emit({"voice_energy_threshold": thresh})

    def _toggle_echo_mode(self, line_edit: QLineEdit, btn: QPushButton) -> None:
        """Toggle echo mode between Password and Normal for API key inputs."""
        if line_edit.echoMode() == QLineEdit.EchoMode.Password:
            line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            btn.setText("Hide")
        else:
            line_edit.setEchoMode(QLineEdit.EchoMode.Password)
            btn.setText("Show")

    def _on_stt_mode_selected(self, index: int) -> None:
        mode = self.combo_stt_mode.itemData(index) or "cloud_first"
        if hasattr(self.settings, "jadoo"):
            self.settings.jadoo.stt_mode = mode
        self.sig_stt_mode_changed.emit(mode)
        self.sig_settings_changed.emit({"jadoo_stt_mode": mode})

    def _on_groq_key_changed(self, text: str) -> None:
        clean_key = text.strip()
        if hasattr(self.settings, "jadoo"):
            self.settings.jadoo.groq_api_key = clean_key
        self.sig_groq_key_changed.emit(clean_key)

    def _on_gemini_key_changed(self, text: str) -> None:
        clean_key = text.strip()
        if hasattr(self.settings, "jadoo"):
            self.settings.jadoo.gemini_api_key = clean_key
        self.sig_gemini_key_changed.emit(clean_key)

    def _on_tts_toggled(self, checked: bool) -> None:
        if hasattr(self.settings, "jadoo"):
            self.settings.jadoo.tts_enabled = checked
        self.sig_tts_toggled.emit(checked)
        self.sig_settings_changed.emit({"jadoo_tts_enabled": checked})

    def _on_auto_show_panel_toggled(self, checked: bool) -> None:
        if hasattr(self.settings, "accessibility"):
            self.settings.accessibility.auto_show_panel = checked
        self.sig_floating_panel_toggled.emit(checked)
        self.sig_settings_changed.emit({"auto_show_panel": checked})

    def _on_windows_startup_toggled(self, checked: bool) -> None:
        try:
            from utils.windows_startup import set_windows_startup_enabled
            if checked:
                reply = QMessageBox.question(
                    self,
                    "Windows Startup Configuration",
                    "Do you want HeadMouseAI + Jadoo to automatically launch when you sign in to Windows?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    self.chk_windows_startup.setChecked(False)
                    return
            set_windows_startup_enabled(checked)
            if hasattr(self.settings, "accessibility"):
                self.settings.accessibility.windows_startup = checked
            self.sig_settings_changed.emit({"windows_startup": checked})
        except Exception as e:
            logger.warning(f"Error configuring Windows startup: {e}")

    def _on_tts_feedback_toggled(self, checked: bool) -> None:
        if hasattr(self.settings, "accessibility"):
            self.settings.accessibility.tts_feedback = checked
        self.sig_settings_changed.emit({"tts_feedback": checked})

    def _on_btn_size_selected(self, index: int) -> None:
        size = self.combo_panel_btn_size.itemData(index) or "large"
        if hasattr(self.settings, "accessibility"):
            self.settings.accessibility.button_size = str(size)
        self.sig_settings_changed.emit({"panel_button_size": str(size)})

    def _save_to_config(self) -> None:
        """Validate and persist current settings to config.toml."""
        try:
            if hasattr(self.settings, "jadoo"):
                self.settings.jadoo.groq_api_key = self.inp_groq_key.text().strip()
                self.settings.jadoo.gemini_api_key = self.inp_gemini_key.text().strip()
                self.settings.jadoo.stt_mode = self.combo_stt_mode.currentData() or "auto"
                self.settings.jadoo.tts_enabled = self.chk_tts_enabled.isChecked()

            if hasattr(self.settings, "accessibility"):
                self.settings.accessibility.auto_show_panel = self.chk_auto_show_panel.isChecked()
                self.settings.accessibility.tts_feedback = self.chk_tts_feedback.isChecked()
                self.settings.accessibility.button_size = self.combo_panel_btn_size.currentData() or "large"
                self.settings.accessibility.windows_startup = self.chk_windows_startup.isChecked()

            val_errors = self.settings.validate()
            if val_errors:
                self.lbl_save_status.setText(f"Validation error: {val_errors[0]}")
                self.lbl_save_status.setStyleSheet("color: #DC2626; font-weight: 600;")
                return

            self.settings.save()
            self.lbl_save_status.setText("✔ Settings saved successfully to config.toml!")
            self.lbl_save_status.setStyleSheet("color: #059669; font-weight: 600;")
            logger.info("Settings saved to config.toml successfully.")
        except Exception as e:
            self.lbl_save_status.setText(f"Error saving settings: {e}")
            self.lbl_save_status.setStyleSheet("color: #DC2626; font-weight: 600;")
            logger.error(f"Error saving settings to config.toml: {e}")

    def _reload_from_config(self) -> None:
        """Reload configuration from disk."""
        try:
            new_settings = AppSettings.load()
            self.populate_from_settings(new_settings)
            self.lbl_save_status.setText("✔ Settings reloaded from config.toml.")
            self.lbl_save_status.setStyleSheet("color: #059669; font-weight: 600;")
        except Exception as e:
            self.lbl_save_status.setText(f"Error reloading settings: {e}")
            self.lbl_save_status.setStyleSheet("color: #DC2626; font-weight: 600;")

    def _on_reset_defaults(self) -> None:
        """Prompt confirmation and reset all settings to default values."""
        ans = QMessageBox.question(
            self,
            "Reset All Settings",
            "Are you sure you want to reset all tracking, calibration, and mouse settings to factory defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.settings.reset_to_defaults()
            self.populate_from_settings(self.settings)
            self.lbl_save_status.setText("All settings reset to default values.")
            self.lbl_save_status.setStyleSheet("color: #059669; font-weight: 600;")
            self.sig_settings_changed.emit({
                "sensitivity": self.settings.nose_tracking.sensitivity,
                "dead_zone": self.settings.nose_tracking.dead_zone,
                "smoothing_strength": self.settings.nose_tracking.smoothing_strength,
                "cursor_speed": self.settings.mouse.cursor_speed,
                "left_sensitivity": self.settings.eye_blink.left_sensitivity,
                "right_sensitivity": self.settings.eye_blink.right_sensitivity,
                "drag_hold_sec": self.settings.eye_blink.drag_hold_sec,
                "scroll_step": self.settings.zoom.scroll_step,
                "zoom_step": self.settings.zoom.zoom_step,
                "smile_sensitivity": self.settings.zoom.smile_sensitivity,
                "camera_resolution": "640x480",
                "performance_mode": "balanced",
                "ui_refresh_hz": 20,
            })
            logger.info("Settings reset to defaults by user.")
