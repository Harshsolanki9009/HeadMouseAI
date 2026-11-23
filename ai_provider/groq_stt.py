"""Groq Whisper Cloud Speech-to-Text client.

Ultra-fast (~300ms) cloud transcription via Groq API (whisper-large-v3-turbo)
using standard library urllib for zero-dependency execution.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, Optional, Tuple

from utils.logger import logger

GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
DEFAULT_GROQ_MODEL = "whisper-large-v3-turbo"
DEFAULT_HINGLISH_PROMPT = (
    "Hindi and English mixed speech, Hinglish conversation: "
    "Haan, main theek hoon, but aaj meeting attend nahi kar sakta."
)


def resolve_groq_api_key(explicit_key: Optional[str] = None) -> str:
    """Robustly resolve GROQ_API_KEY across explicit arguments, os.environ, .env, and Windows Registry.

    Never exposes or logs the key. Returns the sanitized key string or empty string if not found.
    """
    if explicit_key and explicit_key.strip():
        return explicit_key.strip()

    # 1. Check os.environ
    env_key = os.environ.get("GROQ_API_KEY", "").strip()
    if env_key:
        return env_key

    # 2. Check local .env file in project root or parent
    try:
        from pathlib import Path
        for candidate in (Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"):
            if candidate.is_file():
                with open(candidate, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("GROQ_API_KEY="):
                            val = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if val:
                                os.environ["GROQ_API_KEY"] = val
                                return val
    except Exception:
        pass

    # 3. Check Windows Registry (User Environment & System Environment)
    if os.name == "nt":
        try:
            import winreg

            # User Environment Variables (HKCU\Environment)
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as reg_key:
                    val, _ = winreg.QueryValueEx(reg_key, "GROQ_API_KEY")
                    if val and str(val).strip():
                        clean_val = str(val).strip()
                        os.environ["GROQ_API_KEY"] = clean_val
                        return clean_val
            except Exception:
                pass

            # System Environment Variables (HKLM\...\Environment)
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
                ) as reg_key:
                    val, _ = winreg.QueryValueEx(reg_key, "GROQ_API_KEY")
                    if val and str(val).strip():
                        clean_val = str(val).strip()
                        os.environ["GROQ_API_KEY"] = clean_val
                        return clean_val
            except Exception:
                pass
        except Exception:
            pass

    return ""


class GroqSTTError(Exception):
    """Raised when Groq STT API request fails."""
    pass


def encode_multipart_formdata(fields: Dict[str, str], files: Dict[str, Tuple[str, bytes, str]]) -> Tuple[bytes, str]:
    """Encode multipart/form-data for HTTP file uploads without external dependencies."""
    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    body = bytearray()

    # Text fields
    for key, value in fields.items():
        if value is None:
            continue
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        body.extend(f"{value}\r\n".encode("utf-8"))

    # File fields: key -> (filename, bytes_data, content_type)
    for key, (filename, file_data, content_type) in files.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'.encode("utf-8"))
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        body.extend(file_data)
        body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    content_type_header = f"multipart/form-data; boundary={boundary}"
    return bytes(body), content_type_header


class GroqSTTClient:
    """Fast Cloud Speech-to-Text client powered by Groq's Whisper API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_GROQ_MODEL,
        timeout_s: float = 12.0,
    ) -> None:
        if api_key is None:
            self.api_key = resolve_groq_api_key()
        else:
            self.api_key = api_key.strip()
        self.model = model
        self.timeout_s = max(2.0, float(timeout_s))

    @property
    def is_configured(self) -> bool:
        """True if an API key is present."""
        return bool(self.api_key and self.api_key.strip())

    def set_api_key(self, api_key: str) -> None:
        """Update Groq API key, falling back to environment/registry if empty."""
        clean = (api_key or "").strip()
        if clean:
            self.api_key = clean
        else:
            self.api_key = resolve_groq_api_key(None)

    def transcribe_wav_bytes(
        self,
        wav_bytes: bytes,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Transcribe 16-bit 16kHz mono WAV bytes via Groq Cloud Whisper API.

        Returns:
            Dict containing: text, latency_ms, language, error.
        """
        if not self.is_configured:
            return {
                "text": "",
                "latency_ms": 0.0,
                "language": language or "en",
                "error": "GROQ_API_KEY not configured",
            }

        if not wav_bytes or len(wav_bytes) <= 44:
            return {
                "text": "",
                "latency_ms": 0.0,
                "language": language or "en",
                "error": "Empty audio data",
            }

        fields: Dict[str, str] = {
            "model": self.model,
            "response_format": "json",
            "temperature": "0.0",
        }
        # Only pass valid ISO-639-1 code when explicit (e.g. 'en', 'hi').
        # Whisper API returns HTTP 400 if passed 'auto' or 'hinglish'.
        if language and language not in ("auto", "hinglish"):
            fields["language"] = language

        # For Hinglish, inject priming prompt to decode code-switched Hindi/English without translating
        effective_prompt = prompt
        if not effective_prompt and language == "hinglish":
            effective_prompt = DEFAULT_HINGLISH_PROMPT

        if effective_prompt:
            fields["prompt"] = effective_prompt

        files = {
            "file": ("audio.wav", wav_bytes, "audio/wav")
        }

        body_bytes, content_type = encode_multipart_formdata(fields, files)

        req = urllib.request.Request(
            GROQ_TRANSCRIPTION_URL,
            data=body_bytes,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": content_type,
                "User-Agent": "HeadMouseAI-Jadoo/1.0",
            },
            method="POST",
        )

        t_start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as response:
                latency_ms = (time.perf_counter() - t_start) * 1000.0
                resp_bytes = response.read()
                data = json.loads(resp_bytes.decode("utf-8", errors="replace"))
                text = data.get("text", "").strip()

                logger.info(f"Groq Cloud STT ({self.model}) transcribed in {latency_ms:.1f}ms: '{text[:40]}...'")
                return {
                    "text": text,
                    "latency_ms": latency_ms,
                    "language": language or "auto",
                    "error": None,
                }

        except urllib.error.HTTPError as e:
            latency_ms = (time.perf_counter() - t_start) * 1000.0
            error_msg = f"HTTP {e.code}: {e.reason}"
            try:
                err_body = e.read().decode("utf-8", errors="replace")
                err_json = json.loads(err_body)
                if "error" in err_json and "message" in err_json["error"]:
                    error_msg = f"HTTP {e.code}: {err_json['error']['message']}"
            except Exception:
                pass
            logger.warning(f"Groq Cloud STT HTTP error: {error_msg}")
            return {
                "text": "",
                "latency_ms": latency_ms,
                "language": language or "auto",
                "error": error_msg,
            }

        except urllib.error.URLError as e:
            latency_ms = (time.perf_counter() - t_start) * 1000.0
            logger.warning(f"Groq Cloud STT network error (offline?): {e.reason}")
            return {
                "text": "",
                "latency_ms": latency_ms,
                "language": language or "auto",
                "error": f"Network error: {e.reason}",
            }

        except Exception as e:
            latency_ms = (time.perf_counter() - t_start) * 1000.0
            logger.error(f"Groq Cloud STT unexpected error: {e}")
            return {
                "text": "",
                "latency_ms": latency_ms,
                "language": language or "auto",
                "error": str(e),
            }
