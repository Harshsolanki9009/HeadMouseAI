"""Predefined Voice Command Recognition Engine for Jadoo Accessibility System.

Handles text normalization, command matching against the command registry,
duplicate suppression, cooldown tracking, and safe separation from dictation.
"""

from __future__ import annotations

import re
import time
import unicodedata
from typing import Dict, List, Optional, Tuple

from utils.logger import logger
from voice_engine.command_registry import AccessibilityCommand, CommandRegistry


def normalize_command_text(text: str) -> str:
    """Normalize input speech text for deterministic command comparison.

    - Applies Unicode NFKC normalization.
    - Converts to lowercase.
    - Replaces punctuation with whitespace (English and Devanagari punctuation).
    - Collapses consecutive whitespace characters.
    """
    if not text:
        return ""

    # NFKC Unicode normalization
    norm = unicodedata.normalize("NFKC", text.strip().lower())

    # Replace punctuation characters with spaces
    # Standard ASCII punctuation + Hindi danda (।) and double danda (॥) + typographic quotes
    norm = re.sub(r"[\.,\/#!$%\^&\*;:{}=\-_`~()?'\"“”—–…।॥\\|\[\]<>]", " ", norm)

    # Collapse whitespace
    norm = re.sub(r"\s+", " ", norm).strip()
    return norm


class CommandEngine:
    """Matches speech utterances against canonical accessibility commands."""

    def __init__(
        self,
        registry: Optional[CommandRegistry] = None,
        cooldown_sec: float = 0.75,
    ) -> None:
        self.registry = registry or CommandRegistry()
        self.cooldown_sec = max(0.0, float(cooldown_sec))

        # Internal state for cooldown & duplicate suppression
        self._last_command: Optional[AccessibilityCommand] = None
        self._last_command_time: float = 0.0

        # Precompile lookup maps
        self._exact_lookup: Dict[str, AccessibilityCommand] = {}
        self._phrase_list: List[Tuple[str, re.Pattern, AccessibilityCommand]] = []
        self._rebuild_indices()

    def _rebuild_indices(self) -> None:
        """Compile fast lookup dictionaries and regex patterns for all command aliases."""
        self._exact_lookup.clear()
        self._phrase_list.clear()

        all_aliases = self.registry.get_all_aliases()
        for cmd, aliases in all_aliases.items():
            for alias in aliases:
                norm_alias = normalize_command_text(alias)
                if not norm_alias:
                    continue

                self._exact_lookup[norm_alias] = cmd

                # For multi-word phrases, prepare regex boundary matching
                words = norm_alias.split()
                if len(words) > 1:
                    pattern = re.compile(rf"(?:^|\s){re.escape(norm_alias)}(?:\s|$)", re.IGNORECASE)
                    self._phrase_list.append((norm_alias, pattern, cmd))

        # Sort phrase list by length descending so longer, more specific phrases match first
        self._phrase_list.sort(key=lambda item: len(item[0].split()), reverse=True)

    def match(
        self,
        text: str,
        enforce_cooldown: bool = True,
        update_history: bool = True,
    ) -> Tuple[Optional[AccessibilityCommand], float, str]:
        """Match input speech text to an accessibility command.

        Args:
            text: Transcribed speech text.
            enforce_cooldown: If True, suppresses duplicate or rapid successive commands.
            update_history: If True, updates internal last_command and timestamp.

        Returns:
            Tuple of (matched_command, confidence 0.0-1.0, extracted_query_or_remainder).
            If no command matches, returns (None, 0.0, text).
        """
        norm_text = normalize_command_text(text)
        if not norm_text:
            return None, 0.0, ""

        now = time.monotonic()
        matched_cmd: Optional[AccessibilityCommand] = None
        confidence: float = 0.0
        remainder: str = ""

        # 1. Exact match
        if norm_text in self._exact_lookup:
            matched_cmd = self._exact_lookup[norm_text]
            confidence = 1.0
            remainder = ""

        # 2. Wake-word extraction check (e.g. "hey jadoo what time is it")
        if matched_cmd is None:
            wake_aliases = self.registry.get_aliases(AccessibilityCommand.WAKE_UP)
            for w_alias in wake_aliases:
                norm_w = normalize_command_text(w_alias)
                if not norm_w:
                    continue
                # If text starts with wake phrase
                if norm_text == norm_w:
                    matched_cmd = AccessibilityCommand.WAKE_UP
                    confidence = 1.0
                    remainder = ""
                    break
                elif norm_text.startswith(norm_w + " "):
                    matched_cmd = AccessibilityCommand.WAKE_UP
                    confidence = 0.95
                    # Extract query following wake phrase
                    remainder = norm_text[len(norm_w):].strip()
                    break

        # 3. Multi-word phrase boundary matching
        if matched_cmd is None:
            for norm_alias, pattern, cmd in self._phrase_list:
                m = pattern.search(norm_text)
                if m:
                    matched_cmd = cmd
                    confidence = 0.9
                    # Extract remaining text outside the matched command
                    start, end = m.span()
                    remainder = (norm_text[:start] + " " + norm_text[end:]).strip()
                    break

        # If no command matched
        if matched_cmd is None:
            return None, 0.0, text

        # 4. Cooldown and duplicate suppression check
        if enforce_cooldown:
            time_since_last = now - self._last_command_time
            if time_since_last < self.cooldown_sec:
                # Same command repeated too quickly -> suppress duplicate
                if matched_cmd == self._last_command:
                    logger.debug(
                        f"Suppressed duplicate voice command '{matched_cmd.value}' "
                        f"(interval {time_since_last:.2f}s < {self.cooldown_sec}s)"
                    )
                    return None, 0.0, text
                # Allow safety commands and mode switches to bypass cross-command cooldown
                bypass_cmds = (
                    AccessibilityCommand.EMERGENCY_STOP,
                    AccessibilityCommand.STOP_ALL,
                    AccessibilityCommand.TYPING_ON,
                    AccessibilityCommand.TYPING_OFF,
                )
                min_cross_gap = min(self.cooldown_sec, 0.2)
                if min_cross_gap > 0 and self._last_command not in (AccessibilityCommand.TYPING_ON, AccessibilityCommand.TYPING_OFF):
                    if matched_cmd not in bypass_cmds and time_since_last < min_cross_gap:
                        logger.debug(
                            f"Suppressed rapid command '{matched_cmd.value}' "
                            f"(interval {time_since_last:.2f}s < {min_cross_gap:.2f}s)"
                        )
                        return None, 0.0, text

        # Update last command history if requested
        if update_history:
            self._last_command = matched_cmd
            self._last_command_time = now

        logger.info(
            f"Voice command recognized: {matched_cmd.value} (conf={confidence:.2f}, remainder='{remainder}')"
        )
        return matched_cmd, confidence, remainder

    def reset_history(self) -> None:
        """Reset command history and cooldown timer."""
        self._last_command = None
        self._last_command_time = 0.0
