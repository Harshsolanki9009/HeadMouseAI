"""Wake word detection module for Jadoo Assistant.

Detects 'Hey Jadoo' and its phonetic variants without duplicate mic streams.
"""

from wake_word.wake_detector import WakeWordDetector

__all__ = ["WakeWordDetector"]
