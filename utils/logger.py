"""Centralized logging for HeadMouse AI.

Provides a single logger instance used across the whole project so that
errors and informational messages are written consistently to both the
console and a rotating log file.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "headmouse.log"

_DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str = "HeadMouse") -> logging.Logger:
    """Return a configured logger instance.

    The logger is cached on the logging module so that calling this function
    with the same name always returns the same object.
    """
    logger = logging.getLogger(name)
    if getattr(logger, "_headmouse_configured", False):
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    formatter = logging.Formatter(_DEFAULT_FORMAT, _DATE_FORMAT)

    # Console handler (INFO and above so it doesn't spam the terminal)
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # File handler (DEBUG and above, rotated)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger._headmouse_configured = True  # type: ignore[attr-defined]
    return logger


# A ready-to-use logger for modules that import this file
logger = get_logger()