"""Windows Native SAPI Text-To-Speech (TTS) engine.

Uses native Windows PowerShell System.Speech.Synthesis.SpeechSynthesizer
for 100% offline text-to-speech playback without additional pip packages.
Provides instant cancellation for F9 emergency stop.
"""

from __future__ import annotations

import re
import subprocess
import threading
from typing import Callable, Optional

from utils.logger import logger

CREATE_NO_WINDOW = 0x08000000


def clean_text_for_speech(text: str) -> str:
    """Strip markdown code blocks, Mermaid diagrams, URLs, and formatting for clean speech."""
    if not text:
        return ""
    # Remove code blocks including mermaid
    cleaned = re.sub(r"```[\s\S]*?```", " Code block omitted. ", text)
    # Remove inline code
    cleaned = re.sub(r"`.*?`", "", cleaned)
    # Remove markdown links, keep text: [title](url) -> title
    cleaned = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", cleaned)
    # Remove standalone URLs
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    # Remove markdown headers and formatting symbols (*, _, #)
    cleaned = re.sub(r"[#*_~>`]", "", cleaned)
    # Collapse multiple whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


class TTSPlayer:
    """Lightweight Windows SAPI text-to-speech player."""

    clean_text_for_speech = staticmethod(clean_text_for_speech)

    def __init__(self) -> None:
        self._current_proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._is_speaking = False

    @property
    def is_speaking(self) -> bool:
        """True if speech audio is currently playing."""
        with self._lock:
            return self._is_speaking and self._current_proc is not None and self._current_proc.poll() is None

    def speak(self, text: str, on_finished: Optional[Callable[[], None]] = None) -> None:
        """Speak text asynchronously in background thread."""
        speech_text = clean_text_for_speech(text)
        if not speech_text:
            if on_finished:
                on_finished()
            return

        # Stop any existing speech
        self.stop()

        def _worker():
            with self._lock:
                self._is_speaking = True

            # Escape single quotes for PowerShell script literal
            safe_text = speech_text.replace("'", "''").replace('"', '`"')
            ps_script = (
                "Add-Type -AssemblyName System.Speech; "
                "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$synth.Speak('{safe_text}');"
            )

            try:
                proc = subprocess.Popen(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW,
                )
                with self._lock:
                    self._current_proc = proc

                proc.wait()

            except Exception as e:
                logger.warning(f"TTS execution error: {e}")

            finally:
                with self._lock:
                    self._is_speaking = False
                    self._current_proc = None

                if on_finished:
                    try:
                        on_finished()
                    except Exception:
                        pass

        th = threading.Thread(target=_worker, daemon=True)
        th.start()

    def stop(self) -> None:
        """Immediately abort and stop active speech playback (e.g. on F9 emergency stop)."""
        with self._lock:
            if self._current_proc is not None:
                try:
                    self._current_proc.kill()
                    logger.info("TTS speech playback terminated.")
                except Exception as e:
                    logger.debug(f"TTS process kill error: {e}")
                self._current_proc = None
            self._is_speaking = False
