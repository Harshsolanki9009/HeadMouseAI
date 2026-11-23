"""Lightweight wake word detector for 'Hey Jadoo'.

Detects wake phrases and phonetic variants ('hey jadu', 'hey jardu', 'hey jadoo',
'हे जादू', etc.) directly from transcribed speech text without running
a separate microphone capture stream.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional, Pattern, Tuple

from utils.logger import logger

# Regex patterns for phonetic variants of 'Hey Jadoo'
WAKE_PATTERNS = [
    # English & Romanized Hinglish
    r"^\s*(?:hey|hay|hai|hi|hello|ok|okay)\s+(?:jadoo|jadu|jardu|jado|zaadu|zadu)(?:[\b\s,:]|$)",
    r"^\s*(?:jadoo|jadu|jardu)(?:[\b\s,:]|$)",
    # Hindi Devanagari script
    r"^\s*(?:हे|हाय|हेलो|ओके|नमस्ते|सुनो)\s*(?:जादू|जादु|जादो|जादूं)(?:[\s,:]|$)",
    r"^\s*(?:जादू|जादु|जादो)(?:[\s,:]|$)",
]

COMPILED_WAKE_REGEX = [re.compile(p, re.IGNORECASE | re.UNICODE) for p in WAKE_PATTERNS]


class WakeWordDetector:
    """Detects 'Hey Jadoo' wake word and extracts attached user query."""

    def __init__(self, patterns: Optional[list[str]] = None) -> None:
        if patterns:
            self._compiled = [re.compile(p, re.IGNORECASE | re.UNICODE) for p in patterns]
        else:
            self._compiled = COMPILED_WAKE_REGEX

    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalize text for consistent phonetic comparison."""
        if not text:
            return ""
        # Unicode NFKC normalization
        norm = unicodedata.normalize("NFKC", text)
        # Collapse whitespace
        norm = re.sub(r"\s+", " ", norm).strip()
        return norm

    def detect_and_extract(self, text: str) -> Tuple[bool, str]:
        """Detect if text begins with 'Hey Jadoo' and extract the remaining user query.

        Args:
            text: Transcribed speech text from STT.

        Returns:
            Tuple of (wake_word_detected: bool, query_text: str).
            If only wake word was spoken, query_text is empty string.
        """
        if not text:
            return False, ""

        clean_text = self.normalize_text(text)

        for regex in self._compiled:
            match = regex.search(clean_text)
            if match:
                # Wake phrase matched at beginning
                end_pos = match.end()
                remainder = clean_text[end_pos:].strip()
                # Strip leading commas, colons, question marks from remainder
                remainder = re.sub(r"^[\s,:\-–—\?]+", "", remainder).strip()

                logger.info(f"Wake word detected ('{match.group(0).strip()}'). Extracted query: '{remainder}'")
                return True, remainder

        return False, ""

    def detect(self, text: str) -> Tuple[bool, str]:
        """Alias for detect_and_extract."""
        return self.detect_and_extract(text)

    def is_wake_word_only(self, text: str) -> bool:
        """True if the text contains strictly the wake word without a trailing question."""
        detected, query = self.detect_and_extract(text)
        return detected and len(query) == 0
