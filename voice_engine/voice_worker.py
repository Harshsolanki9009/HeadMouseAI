"""Dedicated Voice Worker Thread for HeadMouseAI + Jadoo.

Decouples sounddevice microphone capture, EnergyVAD speech segmentation,
offline whisper.cpp STT inference, and command matching from the Qt GUI
and VisionWorker threads.
"""

from __future__ import annotations

import queue
import time
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal, Slot

from config.settings import AppSettings, get_settings
from utils.logger import logger
from voice_engine.audio_capture import AudioCaptureError, AudioDeviceManager, AudioRecorder
from voice_engine.command_engine import CommandEngine
from voice_engine.command_registry import AccessibilityCommand
from voice_engine.mode_manager import JadooOperatingMode, ModeRouter
from voice_engine.text_injector import TextInjector
from voice_engine.voice_commands import VoiceCommand, VoiceCommandMatcher
from voice_engine.whisper_backend import WhisperBackend
from wake_word.wake_detector import WakeWordDetector


class VoiceWorker(QThread):
    """Background worker thread running local audio capture, VAD, and Whisper STT."""

    # Outgoing Signals to Qt UI
    sig_status = Signal(str)                  # "Ready", "Listening...", "Dictating", "Transcribing...", etc.
    sig_audio_level = Signal(float)          # 0.0 to 1.0 RMS amplitude for mic visualizer
    sig_transcription = Signal(str, str)     # (transcribed_text, language)
    sig_command = Signal(str)                # Canonical voice command string
    sig_wake_word = Signal(str)              # Query extracted from "Hey Jadoo"
    sig_error = Signal(str)                  # Error description
    sig_dictation_state = Signal(bool)       # True if dictating, False if command/idle mode
    sig_engine_used = Signal(str)            # "groq-cloud" or "whisper-local"
    sig_mode_changed = Signal(str)           # "DICTATION_MODE", "COMMAND_MODE", "WAKE_LISTENING", etc.

    def __init__(self, settings: Optional[AppSettings] = None, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.settings: AppSettings = settings if settings is not None else get_settings()

        # Thread state
        self._running: bool = False
        self._paused: bool = False
        self._is_dictating: bool = False
        self._pending_device_switch: Optional[int] = None
        self._utterance_queue: queue.Queue[bytes] = queue.Queue()

        # Subsystems
        voice_cfg = self.settings.voice
        j_cfg = getattr(self.settings, "jadoo", None)
        stt_mode = getattr(j_cfg, "stt_mode", "cloud_first") if j_cfg else "cloud_first"
        raw_key = getattr(j_cfg, "groq_api_key", "") if j_cfg else ""
        groq_key = raw_key.strip() if raw_key and raw_key.strip() else None

        self.whisper = WhisperBackend(
            model_name=voice_cfg.model_name,
            threads=voice_cfg.threads,
            language=voice_cfg.language,
            stt_mode=stt_mode,
            groq_api_key=groq_key,
        )
        self.wake_detector = WakeWordDetector()
        self.recorder = AudioRecorder(
            device_index=voice_cfg.device_index,
            sample_rate=16000,
            on_utterance_ready=self._on_utterance_ready,
            on_level_update=self._on_level_update,
            energy_threshold=voice_cfg.energy_threshold,
            silence_duration_sec=voice_cfg.silence_duration_s,
            min_speech_duration_sec=getattr(voice_cfg, "min_speech_duration_s", 0.22),
        )
        self.command_matcher = VoiceCommandMatcher()
        self.command_engine = CommandEngine()
        self.mode_router = ModeRouter(
            initial_mode=JadooOperatingMode.DICTATION_MODE if self._is_dictating else JadooOperatingMode.WAKE_LISTENING,
            command_engine=self.command_engine,
        )
        self.text_injector = TextInjector(
            restore_clipboard=voice_cfg.restore_clipboard,
        )

    def _on_utterance_ready(self, wav_bytes: bytes, timestamp: float) -> None:
        """Callback from audio capture stream when VAD detects end of utterance."""
        if self._running and not self._paused:
            self._utterance_queue.put(wav_bytes)

    def _on_level_update(self, rms: float) -> None:
        """Callback for real-time audio amplitude."""
        if self._running and not self._paused:
            # Scale RMS (typically 0.001 to 0.1) into 0.0 - 1.0 range
            scaled = min(1.0, max(0.0, rms * 15.0))
            self.sig_audio_level.emit(scaled)

    @property
    def is_dictating(self) -> bool:
        """True if dictation mode is currently active."""
        return self._is_dictating

    @property
    def is_active(self) -> bool:
        """True if voice thread is running and not paused."""
        return self._running and not self._paused

    @Slot(bool)
    def set_dictating(self, active: bool) -> None:
        """Activate or deactivate dictation mode."""
        if self._is_dictating != active:
            self._is_dictating = active
            new_mode = JadooOperatingMode.DICTATION_MODE if active else JadooOperatingMode.COMMAND_MODE
            self.mode_router.set_mode(new_mode)
            self.sig_dictation_state.emit(self._is_dictating)
            self.sig_mode_changed.emit(new_mode.value)
            status_text = "Dictating" if self._is_dictating else "Listening"
            self.sig_status.emit(status_text)
            logger.info(f"VoiceWorker dictation state changed to: {self._is_dictating} (mode: {new_mode.value})")

    @Slot()
    def toggle_dictation(self) -> None:
        """Toggle between dictation and command mode."""
        self.set_dictating(not self._is_dictating)

    @Slot(int)
    def switch_device(self, device_index: int) -> None:
        """Request microphone device switch on next loop cycle."""
        self._pending_device_switch = device_index
        logger.info(f"VoiceWorker queued device switch to index: {device_index}")

    @Slot(str)
    def switch_model(self, model_name: str) -> bool:
        """Switch active whisper model (e.g. ggml-tiny.bin vs ggml-base.bin)."""
        ok = self.whisper.set_model(model_name)
        if ok:
            self.settings.voice.model_name = model_name
        return ok

    @Slot(str)
    def switch_language(self, language: str) -> None:
        """Set language code ('auto', 'hi', 'en', 'hinglish')."""
        self.whisper.set_language(language)
        self.settings.voice.language = language
        logger.info(f"VoiceWorker language switched to: {language}")

    @Slot(str)
    def set_groq_api_key(self, api_key: str) -> None:
        """Update Groq API key for cloud STT."""
        self.whisper.set_groq_api_key(api_key)
        if hasattr(self.settings, "jadoo"):
            self.settings.jadoo.groq_api_key = api_key.strip()

    @Slot(str)
    def set_stt_mode(self, mode: str) -> None:
        """Set STT mode ('auto', 'cloud', 'offline')."""
        self.whisper.set_stt_mode(mode)
        if hasattr(self.settings, "jadoo"):
            self.settings.jadoo.stt_mode = mode

    @Slot(float)
    def set_vad_threshold(self, threshold: float) -> None:
        """Update VAD energy sensitivity threshold."""
        val = max(0.005, min(0.15, float(threshold)))
        self.recorder.vad.energy_threshold = val
        self.settings.voice.energy_threshold = val
        logger.info(f"VoiceWorker VAD threshold updated to: {val:.3f}")

    @Slot(bool)
    def set_paused(self, paused: bool) -> None:
        """Pause or resume audio listening."""
        self._paused = paused
        if paused:
            self.sig_status.emit("Paused")
            self.sig_audio_level.emit(0.0)
        else:
            self.sig_status.emit("Dictating" if self._is_dictating else "Listening")

    def run(self) -> None:
        """Main audio utterance processing and transcription loop."""
        self._running = True
        logger.info("VoiceWorker background thread started.")

        # Check whisper assets
        if not self.whisper.is_available:
            msg = "Whisper binary or model files missing."
            logger.warning(msg)
            self.sig_error.emit(msg)
            self.sig_status.emit("Unavailable")
            self._running = False
            return

        if not self._running:
            return

        # Start microphone stream
        try:
            self.recorder.start()
            self.sig_status.emit("Listening")
        except AudioCaptureError as e:
            logger.warning(f"VoiceWorker mic start error: {e}")
            self.sig_error.emit(str(e))
            self.sig_status.emit("Mic Error")

        while self._running:
            # Handle queued device switches
            if self._pending_device_switch is not None:
                new_idx = self._pending_device_switch
                self._pending_device_switch = None
                self.recorder.stop()
                self.recorder.device_index = new_idx
                self.settings.voice.device_index = new_idx
                try:
                    self.recorder.start()
                    logger.info(f"Successfully switched voice input to device index {new_idx}")
                    self.sig_status.emit("Dictating" if self._is_dictating else "Listening")
                except AudioCaptureError as e:
                    self.sig_error.emit(f"Failed to switch to audio device {new_idx}: {e}")
                    self.sig_status.emit("Mic Error")

            if self._paused or not self.settings.voice.enabled:
                time.sleep(0.05)
                continue

            # Check for new utterances from audio queue
            try:
                wav_bytes = self._utterance_queue.get(timeout=0.05)
            except queue.Empty:
                continue

            if not self._running:
                break

            if not wav_bytes or len(wav_bytes) <= 44:
                continue

            # Process utterance through Whisper STT
            if self.whisper.stt_mode in ("cloud_first", "auto", "cloud") and self.whisper.groq_client.is_configured:
                self.sig_engine_used.emit("CONNECTING")
            self.sig_status.emit("Transcribing...")
            try:
                result = self.whisper.transcribe_wav_bytes(wav_bytes)
                text = result.get("text", "").strip()
                lang = result.get("language", "auto")
                backend = result.get("backend", "whisper-local")
                fallback_occurred = result.get("fallback_occurred", False)
                fallback_reason = result.get("fallback_reason")
                error = result.get("error")

                if fallback_occurred:
                    if fallback_reason == "API KEY MISSING":
                        self.sig_engine_used.emit("API KEY MISSING")
                    elif fallback_reason and any(k in str(fallback_reason).lower() for k in ("network", "connection", "offline", "50", "timeout", "timed out")):
                        self.sig_engine_used.emit("CLOUD UNAVAILABLE")
                    else:
                        self.sig_engine_used.emit("LOCAL WHISPER — OFFLINE FALLBACK")
                else:
                    self.sig_engine_used.emit(backend)

                if error:
                    logger.warning(f"Voice transcription warning: {error}")

                if text:
                    logger.info(f"Voice utterance transcribed via [{backend}] (lang: {lang}): '{text[:60]}'")
                    route_action, cmd, payload = self.mode_router.route_speech(text)

                    if route_action == "DICTATE_TEXT":
                        # Strictly literal dictation text - no commands executed
                        logger.info(f"Dictation text captured: '{payload}' ({lang})")
                        self.sig_transcription.emit(payload, lang)
                        if self.settings.voice.auto_paste:
                            self.text_injector.inject_text(payload, only_external=True)

                    elif route_action == "EXECUTE_COMMAND" and cmd is not None:
                        logger.info(f"Voice command identified: {cmd.value}")
                        if cmd == AccessibilityCommand.TYPING_ON:
                            self.set_dictating(True)
                            self.sig_command.emit("start_dictation")
                        elif cmd == AccessibilityCommand.TYPING_OFF:
                            self.set_dictating(False)
                            self.sig_command.emit("stop_dictation")
                        elif cmd in (AccessibilityCommand.EMERGENCY_STOP, AccessibilityCommand.STOP_ALL):
                            self.set_dictating(False)
                            self.sig_command.emit("emergency_stop")
                        elif cmd == AccessibilityCommand.RECENTER:
                            self.sig_command.emit("recenter")
                        else:
                            self.sig_command.emit(cmd.value)

                    elif route_action == "WAKE_QUERY":
                        logger.info(f"Wake word 'Hey Jadoo' recognized (query: '{payload}')")
                        self.sig_wake_word.emit(payload)

                    else:
                        logger.debug(f"Speech unhandled or ignored: '{text}'")

            except Exception as e:
                logger.error(f"VoiceWorker error during transcription: {e}")

            # Restore status
            self.sig_status.emit("Dictating" if self._is_dictating else "Listening")

        # Cleanup on exit
        self.recorder.stop()
        self.sig_audio_level.emit(0.0)
        self.sig_status.emit("Stopped")
        logger.info("VoiceWorker background thread terminated cleanly.")

    def stop(self) -> None:
        """Gracefully stop the background worker thread."""
        logger.info("VoiceWorker stop requested...")
        self._running = False
        self.recorder.stop()
        self._utterance_queue.put(b"")
        self.wait(3000)
