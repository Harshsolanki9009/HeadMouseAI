"""Safe diagnostic utility for Groq API authentication and configuration.

Reports only high-level status flags and failure categories without ever printing
or exposing API keys in terminal, logs, or UI.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional
import urllib.error
import urllib.request

from ai_provider.groq_stt import DEFAULT_GROQ_MODEL, resolve_groq_api_key
from utils.logger import logger

GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"


def run_groq_diagnostic(api_key: Optional[str] = None) -> Dict[str, Any]:
    """Execute safe diagnostic check for Groq Cloud API.

    Reports:
    - env_var_present: bool
    - client_initialized: bool
    - auth_success: bool
    - failure_category: str ('NONE', 'MISSING_KEY', 'INVALID_KEY_401', 'FORBIDDEN_403',
                            'RATE_LIMIT_429', 'NETWORK_ERROR', 'SERVER_ERROR_5XX')
    - model_available: bool (verifies whisper-large-v3-turbo presence)
    - key_length: int

    NEVER prints or exposes the API key string.
    """
    resolved_key = resolve_groq_api_key(api_key)
    env_present = bool(os.environ.get("GROQ_API_KEY", "").strip())
    client_init = bool(resolved_key)
    key_len = len(resolved_key) if resolved_key else 0

    if not client_init:
        return {
            "env_var_present": env_present,
            "client_initialized": False,
            "auth_success": False,
            "failure_category": "MISSING_KEY",
            "model_available": False,
            "key_length": 0,
        }

    # Execute lightweight authentication ping to Groq Models API
    req = urllib.request.Request(
        GROQ_MODELS_URL,
        headers={
            "Authorization": f"Bearer {resolved_key}",
            "User-Agent": "HeadMouseAI-Jadoo/1.0",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            if resp.status == 200:
                body = resp.read().decode("utf-8", errors="replace")
                data = json.loads(body)
                model_ids = [m.get("id") for m in data.get("data", [])]
                model_ok = DEFAULT_GROQ_MODEL in model_ids

                logger.info(f"Groq API diagnostic: Authentication SUCCESS (Target model '{DEFAULT_GROQ_MODEL}' available: {model_ok})")
                return {
                    "env_var_present": env_present,
                    "client_initialized": True,
                    "auth_success": True,
                    "failure_category": "NONE",
                    "model_available": model_ok,
                    "key_length": key_len,
                }
            else:
                return {
                    "env_var_present": env_present,
                    "client_initialized": True,
                    "auth_success": False,
                    "failure_category": f"HTTP_{resp.status}",
                    "model_available": False,
                    "key_length": key_len,
                }

    except urllib.error.HTTPError as e:
        cat = "UNKNOWN_HTTP_ERROR"
        if e.code == 401:
            cat = "INVALID_KEY_401"
        elif e.code == 403:
            cat = "FORBIDDEN_403"
        elif e.code == 429:
            cat = "RATE_LIMIT_429"
        elif 500 <= e.code <= 599:
            cat = "SERVER_ERROR_5XX"

        logger.warning(f"Groq API diagnostic: Authentication FAILED ({cat}, HTTP {e.code})")
        return {
            "env_var_present": env_present,
            "client_initialized": True,
            "auth_success": False,
            "failure_category": cat,
            "model_available": False,
            "key_length": key_len,
        }

    except urllib.error.URLError as e:
        logger.warning(f"Groq API diagnostic: Network connection failure ({e.reason})")
        return {
            "env_var_present": env_present,
            "client_initialized": True,
            "auth_success": False,
            "failure_category": "NETWORK_ERROR",
            "model_available": False,
            "key_length": key_len,
        }

    except Exception as e:
        logger.error(f"Groq API diagnostic unexpected error: {e}")
        return {
            "env_var_present": env_present,
            "client_initialized": True,
            "auth_success": False,
            "failure_category": "UNEXPECTED_ERROR",
            "model_available": False,
            "key_length": key_len,
        }
