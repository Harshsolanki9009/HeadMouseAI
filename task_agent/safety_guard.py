"""Safety Guard and Policy Enforcement for Jadoo Task Agent.

Enforces strict boundaries against destructive operations, financial transactions,
unauthorized credential usage, and irreversible system actions.
"""

from __future__ import annotations

import re
from typing import Tuple

from task_agent.task_state import ActionType, TaskStep
from utils.logger import logger

# Keywords that indicate irreversible, risky, or high-consequence operations
RISKY_KEYWORDS = [
    # Deletion & Destruction
    r"\b(?:delete|remove|erase|format|wipe|destroy|unlink|drop)\b",
    # Financial & Purchases
    r"\b(?:pay|payment|purchase|buy|checkout|credit\s*card|bank|transfer|order)\b",
    # Communications & Publishing
    r"\b(?:send\s*email|send\s*message|publish|post|tweet|broadcast)\b",
    # System & Security Modification
    r"\b(?:install|uninstall|regedit|password|credentials|mfa|2fa|privilege|admin)\b",
]

COMPILED_RISKY_PATTERNS = [re.compile(p, re.IGNORECASE) for p in RISKY_KEYWORDS]

# Prohibited actions that cannot be executed even with confirmation
PROHIBITED_KEYWORDS = [
    r"\b(?:bypass\s*captcha|solve\s*captcha|bypass\s*mfa|crack|hack|exploit)\b",
    r"\b(?:enter\s*credit\s*card|submit\s*payment|authorize\s*charge)\b",
]

COMPILED_PROHIBITED = [re.compile(p, re.IGNORECASE) for p in PROHIBITED_KEYWORDS]


class SafetyGuard:
    """Enforces safety rules on planned and incoming actions."""

    @staticmethod
    def inspect_instruction(instruction: str) -> Tuple[bool, bool, str]:
        """Analyze a high-level user instruction for risk.

        Returns:
            Tuple of (is_allowed: bool, is_risky: bool, reason: str)
        """
        text = instruction.strip().lower()

        # Check strictly prohibited actions
        for pattern in COMPILED_PROHIBITED:
            if pattern.search(text):
                msg = "Instruction involves prohibited operations (CAPTCHA bypass or automated payments)."
                logger.warning(f"SafetyGuard blocked instruction: {msg}")
                return False, True, msg

        # Check risky / sensitive operations
        for pattern in COMPILED_RISKY_PATTERNS:
            if pattern.search(text):
                msg = "Instruction involves sensitive or irreversible operations requiring user approval."
                logger.info(f"SafetyGuard flagged instruction: {msg}")
                return True, True, msg

        return True, False, "Safe standard operation."

    @staticmethod
    def evaluate_step(step: TaskStep) -> Tuple[bool, bool, str]:
        """Evaluate an individual task step before execution.

        Returns:
            Tuple of (can_proceed: bool, requires_popup_approval: bool, reason: str)
        """
        desc = (step.description + " " + step.target + " " + str(step.value or "")).lower()

        # Check prohibited operations
        for pattern in COMPILED_PROHIBITED:
            if pattern.search(desc):
                return False, False, "Action violates safety policy (prohibited operation)."

        # Flagged as risky or requires explicit user confirmation
        if step.is_risky or step.requires_confirmation:
            return True, True, f"Step requires explicit authorization: {step.description}"

        for pattern in COMPILED_RISKY_PATTERNS:
            if pattern.search(desc):
                step.is_risky = True
                step.requires_confirmation = True
                return True, True, f"Operation contains sensitive action: {step.description}"

        # Standard non-destructive desktop operations
        return True, False, "Approved for automated execution."
