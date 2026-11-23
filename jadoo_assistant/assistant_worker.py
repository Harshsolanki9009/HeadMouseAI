"""Dedicated QThread worker for Online Jadoo AI Assistant.

Coordinates non-blocking calls to Gemini 2.5 Flash, on-demand screen capture,
Hinglish-to-English rewrites, and Windows SAPI TTS audio responses.
Fully isolated from VisionWorker and GUI main thread.
"""

from __future__ import annotations

import queue
import time
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal, Slot

from ai_provider.gemini_client import GeminiClient
from config.settings import AppSettings, get_settings
from jadoo_assistant.context_builder import ContextBuilder
from jadoo_assistant.screen_capture import ScreenCapture
from jadoo_assistant.tts_player import TTSPlayer
from utils.logger import logger


class JadooWorker(QThread):
    """Background worker thread orchestrating Jadoo AI requests and TTS output."""

    # Outgoing Signals to UI and VoiceWorker
    sig_jadoo_status = Signal(str)           # "ONLINE", "OFFLINE", "THINKING", "READY"
    sig_jadoo_response = Signal(str)         # Generated response text
    sig_jadoo_error = Signal(str)            # Error notification
    sig_speaking_state = Signal(bool)        # True while TTS is speaking (for half-duplex muting)

    def __init__(self, settings: Optional[AppSettings] = None, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.settings: AppSettings = settings if settings is not None else get_settings()

        # Internal state
        self._running: bool = False
        self._request_queue: queue.Queue[dict] = queue.Queue()
        self._current_request_aborted: bool = False

        # Subsystems
        j_cfg = getattr(self.settings, "jadoo", None)
        gemini_key = getattr(j_cfg, "gemini_api_key", "") if j_cfg else ""
        self.gemini = GeminiClient(api_key=gemini_key)
        self.tts = TTSPlayer()

    @property
    def is_online(self) -> bool:
        """True if Gemini client has an API key configured."""
        return self.gemini.is_configured

    @Slot(str, bool, bool)
    def ask(self, query: str, include_screen: bool = False, is_rewrite: bool = False) -> None:
        """Queue a user query to be processed by Jadoo."""
        if not query.strip() and not include_screen:
            return
        self._request_queue.put({
            "query": query.strip(),
            "include_screen": include_screen,
            "is_rewrite": is_rewrite,
            "timestamp": time.time(),
        })

    @Slot()
    def abort(self) -> None:
        """Immediate abort hook (F9 Emergency Stop)."""
        logger.info("JadooWorker abort requested: clearing queue and stopping TTS.")
        self._current_request_aborted = True
        # Clear pending queue
        while not self._request_queue.empty():
            try:
                self._request_queue.get_nowait()
            except queue.Empty:
                break
        self.tts.stop()
        self.sig_speaking_state.emit(False)
        self.sig_jadoo_status.emit("ONLINE" if self.is_online else "OFFLINE")

    @Slot(str)
    def set_gemini_api_key(self, api_key: str) -> None:
        """Update Gemini API key."""
        self.gemini.set_api_key(api_key)
        if hasattr(self.settings, "jadoo"):
            self.settings.jadoo.gemini_api_key = api_key.strip()
        self.sig_jadoo_status.emit("ONLINE" if self.is_online else "OFFLINE")

    @Slot(bool)
    def set_tts_enabled(self, enabled: bool) -> None:
        """Enable or disable SAPI TTS playback."""
        if hasattr(self.settings, "jadoo"):
            self.settings.jadoo.tts_enabled = enabled
        if not enabled:
            self.tts.stop()

    def run(self) -> None:
        """Main worker thread event loop."""
        self._running = True
        logger.info("JadooWorker background thread started.")
        self.sig_jadoo_status.emit("ONLINE" if self.is_online else "OFFLINE")

        while self._running:
            try:
                req = self._request_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if not self._running or req.get("stop"):
                break

            self._current_request_aborted = False
            query: str = req.get("query", "")
            include_screen: bool = req.get("include_screen", False)
            is_rewrite: bool = req.get("is_rewrite", False)

            if not self.gemini.is_configured:
                err = "GEMINI_API_KEY is not configured in Settings. Please enter your key."
                logger.warning(f"Jadoo request skipped: {err}")
                self.sig_jadoo_error.emit(err)
                self.sig_jadoo_status.emit("OFFLINE")
                continue

            self.sig_jadoo_status.emit("THINKING")

            # 1. Capture screen if explicitly requested
            img_b64: Optional[str] = None
            if include_screen:
                _, img_b64, screen_err = ScreenCapture.capture_screen_jpeg()
                if screen_err:
                    logger.warning(f"Screen capture issue: {screen_err}")

            if self._current_request_aborted:
                self.sig_jadoo_status.emit("ONLINE")
                continue

            # 2. Build prompt and system instructions
            system_instruction = ContextBuilder.build_system_instruction(
                is_rewrite=is_rewrite,
                include_screen=bool(img_b64),
            )
            formatted_prompt = ContextBuilder.format_user_prompt(
                query=query,
                is_rewrite=is_rewrite,
            )

            # 3. Call Gemini API
            res = self.gemini.generate_content(
                prompt=formatted_prompt,
                system_instruction=system_instruction,
                image_jpeg_base64=img_b64,
                temperature=0.3 if is_rewrite else 0.7,
            )

            if self._current_request_aborted:
                self.sig_jadoo_status.emit("ONLINE")
                continue

            error = res.get("error")
            text = res.get("text", "").strip()

            if error:
                logger.warning(f"Jadoo Assistant request failed: {error}")
                self.sig_jadoo_error.emit(error)
                self.sig_jadoo_status.emit("OFFLINE" if "Network error" in error else "ONLINE")
            elif text:
                logger.info(f"Jadoo Assistant answered ({len(text)} chars)")
                self.sig_jadoo_response.emit(text)
                self.sig_jadoo_status.emit("ONLINE")

                # 4. Optional TTS Playback with half-duplex mute signal
                j_cfg = getattr(self.settings, "jadoo", None)
                if j_cfg and getattr(j_cfg, "tts_enabled", False):
                    self.sig_speaking_state.emit(True)

                    def _on_tts_done():
                        self.sig_speaking_state.emit(False)

                    self.tts.speak(text, on_finished=_on_tts_done)
            else:
                self.sig_jadoo_status.emit("ONLINE")

        self.tts.stop()
        self.sig_speaking_state.emit(False)
        logger.info("JadooWorker background thread terminated cleanly.")

    def stop(self) -> None:
        """Stop worker thread cleanly."""
        self._running = False
        self.abort()
        self._request_queue.put({"stop": True})
        self.wait(3000)
