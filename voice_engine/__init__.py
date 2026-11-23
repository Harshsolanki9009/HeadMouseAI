"""Jadoo Voice Engine subsystem for HeadMouseAI.

Provides offline speech-to-text dictation, multilingual recognition (Hindi,
English, Hinglish), voice command parsing, safe clipboard text injection,
and dedicated QThread execution.
"""

from voice_engine.audio_capture import AudioDeviceManager, AudioRecorder, EnergyVAD, HighPassFilter
from voice_engine.text_injector import TextInjector
from voice_engine.voice_commands import VoiceCommand, VoiceCommandMatcher
from voice_engine.voice_worker import VoiceWorker
from voice_engine.whisper_backend import WhisperBackend, WhisperBackendError, clean_whisper_text

__all__ = [
    "AudioDeviceManager",
    "AudioRecorder",
    "EnergyVAD",
    "HighPassFilter",
    "TextInjector",
    "VoiceCommand",
    "VoiceCommandMatcher",
    "VoiceWorker",
    "WhisperBackend",
    "WhisperBackendError",
    "clean_whisper_text",
]
