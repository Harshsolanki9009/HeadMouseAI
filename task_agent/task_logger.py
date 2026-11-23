"""Secure Task Activity Logger for Jadoo Task Agent.

Maintains live activity logs for the dashboard while sanitizing and redacting
sensitive tokens, API keys, passwords, and private data.
"""

from __future__ import annotations

import re
import time
from typing import List

from utils.logger import logger

# Redaction patterns for sensitive strings
REDACT_PATTERNS = [
    (re.compile(r"gsk_[a-zA-Z0-9_-]{20,}", re.IGNORECASE), "gsk_[REDACTED_API_KEY]"),
    (re.compile(r"AIza[a-zA-Z0-9_-]{35}", re.IGNORECASE), "AIza[REDACTED_GEMINI_KEY]"),
    (re.compile(r"password\s*[:=]\s*\S+", re.IGNORECASE), "password: [REDACTED]"),
    (re.compile(r"\b(?:\d[ -]*?){13,16}\b"), "[REDACTED_CARD_NUMBER]"),
]


def sanitize_text(text: str) -> str:
    """Sanitize and redact sensitive data from strings."""
    if not text:
        return ""
    clean = text
    for pattern, replacement in REDACT_PATTERNS:
        clean = pattern.sub(replacement, clean)
    return clean


class TaskLogger:
    """In-memory activity logger maintaining a buffer for the desktop UI."""

    def __init__(self, max_entries: int = 150) -> None:
        self.max_entries = max_entries
        self._entries: List[str] = []

    def log(self, message: str) -> str:
        """Add a sanitized message to the activity log."""
        timestamp = time.strftime("%H:%M:%S")
        sanitized = sanitize_text(message)
        entry = f"[{timestamp}] {sanitized}"
        self._entries.append(entry)
        if len(self._entries) > self.max_entries:
            self._entries.pop(0)

        logger.info(f"TaskAgent: {sanitized}")
        return entry

    def get_entries(self) -> List[str]:
        """Return full list of recent activity entries."""
        return list(self._entries)

    def clear(self) -> None:
        """Clear log entries."""
        self._entries.clear()
