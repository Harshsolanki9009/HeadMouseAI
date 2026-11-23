"""Voice command parser and allowlist for Jadoo Voice Engine.

Enforces a strict, conservative offline command allowlist to prevent accidental
command execution during speech. Separates command mode from dictation mode.
"""

from __future__ import annotations

import re
import unicodedata
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from utils.logger import logger


class VoiceCommand(str, Enum):
    """Strict allowlist of supported offline voice commands."""
    RECENTER = "recenter"
    EMERGENCY_STOP = "emergency_stop"
    STOP = "stop"
    START_DICTATION = "start_dictation"
    STOP_DICTATION = "stop_dictation"


# Normalized aliases mapping to canonical VoiceCommand
COMMAND_ALIASES: Dict[VoiceCommand, List[str]] = {
    VoiceCommand.RECENTER: [
        "recenter",
        "re center",
        "center",
        "re-center",
        "recenter cursor",
        "center cursor",
        "रीसेंटर",
        "सेंटर",
        "बीच में",
    ],
    VoiceCommand.EMERGENCY_STOP: [
        "emergency stop",
        "emergency halt",
        "emergency",
        "इमरजेंसी स्टॉप",
        "इमरजेंसी",
        "आपातकालीन रोक",
    ],
    VoiceCommand.STOP: [
        "stop",
        "halt",
        "pause",
        "रुकिए",
        "रुकें",
        "रुको",
        "ठहरो",
    ],
    VoiceCommand.START_DICTATION: [
        "start dictation",
        "begin dictation",
        "dictation start",
        "dictation on",
        "start typing",
        "डिक्टेशन शुरू",
        "बोलना शुरू",
        "टाइप शुरू",
    ],
    VoiceCommand.STOP_DICTATION: [
        "stop dictation",
        "end dictation",
        "finish dictation",
        "dictation stop",
        "dictation off",
        "stop typing",
        "डिक्टेशन बंद",
        "बोलना बंद",
        "टाइप बंद",
    ],
}


def normalize_text(text: str) -> str:
    """Normalize text for consistent comparison.
    
    Converts to lowercase, removes ASCII and Unicode punctuation, normalizes
    whitespace, and removes trailing periods/commas/question marks.
    """
    if not text:
        return ""

    # Normalize unicode (NFKC)
    text = unicodedata.normalize("NFKC", text.strip().lower())

    # Remove standard punctuation but keep Devanagari and Latin letters/numbers/spaces
    text = re.sub(r"[.,\/#!$%\^&\*;:{}=\-_`~()?'\"।॥]", " ", text)
    # Collapse multiple whitespaces
    text = re.sub(r"\s+", " ", text).strip()
    return text


class VoiceCommandMatcher:
    """Matches transcribed speech against the strict offline command allowlist."""

    def __init__(self) -> None:
        # Precompute normalized alias lookup table
        self._lookup: Dict[str, VoiceCommand] = {}
        for cmd, aliases in COMMAND_ALIASES.items():
            for alias in aliases:
                norm_alias = normalize_text(alias)
                if norm_alias:
                    self._lookup[norm_alias] = cmd

    def match(self, text: str, is_dictating: bool = False) -> Tuple[Optional[VoiceCommand], float]:
        """Match input text against command allowlist.
        
        Args:
            text: Transcribed speech text.
            is_dictating: If True, only exit commands (STOP_DICTATION) are permitted,
                          preventing dictation words from accidentally triggering commands.
                          
        Returns:
            Tuple of (matched_command, confidence_score 0.0 to 1.0).
            If no match, returns (None, 0.0).
        """
        norm_text = normalize_text(text)
        if not norm_text:
            return None, 0.0

        # When dictating, ONLY allow STOP_DICTATION
        if is_dictating:
            stop_aliases = [normalize_text(a) for a in COMMAND_ALIASES[VoiceCommand.STOP_DICTATION]]
            for alias in stop_aliases:
                if norm_text == alias or norm_text.endswith(alias):
                    logger.info(f"Dictation exit command recognized: '{norm_text}' -> STOP_DICTATION")
                    return VoiceCommand.STOP_DICTATION, 1.0
            return None, 0.0

        # Exact normalized match
        if norm_text in self._lookup:
            cmd = self._lookup[norm_text]
            logger.info(f"Exact voice command match: '{norm_text}' -> {cmd.value}")
            return cmd, 1.0

        # Substring / boundary match for multi-word commands (e.g. "please recenter", "jadoo emergency stop")
        for alias, cmd in self._lookup.items():
            # Only match if alias appears as a distinct word boundary phrase
            pattern = r"(?:^|\s)" + re.escape(alias) + r"(?:\s|$)"
            if re.search(pattern, norm_text):
                # For short single-word commands like 'stop' or 'center', require exact match
                if len(alias.split()) == 1 and norm_text != alias:
                    # Ignore embedded single words to avoid false triggers
                    continue
                logger.info(f"Phrase voice command match: '{norm_text}' -> {cmd.value} (via '{alias}')")
                return cmd, 0.9

        return None, 0.0
