"""Jadoo Assistant package for HeadMouseAI.

Provides conversational AI assistant, Hinglish-to-English rewriting,
visual screen guidance, native Windows SAPI TTS, and JadooWorker QThread.
"""

from jadoo_assistant.assistant_worker import JadooWorker
from jadoo_assistant.context_builder import ContextBuilder
from jadoo_assistant.screen_capture import ScreenCapture
from jadoo_assistant.tts_player import TTSPlayer

__all__ = [
    "ContextBuilder",
    "JadooWorker",
    "ScreenCapture",
    "TTSPlayer",
]
