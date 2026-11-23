"""Google Gemini API client for Jadoo Assistant.

Supports gemini-2.5-flash for conversational Q&A, Hinglish-to-English rewrite,
and screen-aware visual guidance using standard library urllib.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from utils.logger import logger

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


class GeminiError(Exception):
    """Raised when Gemini API request fails."""
    pass


class GeminiClient:
    """Non-blocking HTTP client for Google Gemini 2.5 Flash."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_GEMINI_MODEL,
        timeout_s: float = 25.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model = model
        self.timeout_s = max(5.0, float(timeout_s))

    @property
    def is_configured(self) -> bool:
        """True if an API key is present."""
        return bool(self.api_key and self.api_key.strip())

    def set_api_key(self, api_key: str) -> None:
        """Update Gemini API key."""
        self.api_key = api_key.strip()

    def generate_content(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        image_jpeg_base64: Optional[str] = None,
        temperature: float = 0.7,
        max_output_tokens: int = 2048,
    ) -> Dict[str, Any]:
        """Generate content from Gemini 2.5 Flash with optional image and system instructions.

        Returns:
            Dict containing: text, latency_ms, model, error.
        """
        if not self.is_configured:
            return {
                "text": "",
                "latency_ms": 0.0,
                "model": self.model,
                "error": "GEMINI_API_KEY not configured",
            }

        if not prompt and not image_jpeg_base64:
            return {
                "text": "",
                "latency_ms": 0.0,
                "model": self.model,
                "error": "Empty prompt",
            }

        url = f"{GEMINI_API_BASE}/{self.model}:generateContent?key={self.api_key}"

        parts = []
        if image_jpeg_base64:
            parts.append({
                "inlineData": {
                    "mimeType": "image/jpeg",
                    "data": image_jpeg_base64,
                }
            })
        if prompt:
            parts.append({"text": prompt})

        payload: Dict[str, Any] = {
            "contents": [
                {
                    "parts": parts,
                }
            ],
            "generationConfig": {
                "temperature": float(temperature),
                "maxOutputTokens": int(max_output_tokens),
            },
        }

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [
                    {"text": system_instruction}
                ]
            }

        body_bytes = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers={
                "Content-Type": "application/json",
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

                candidates = data.get("candidates", [])
                if not candidates:
                    return {
                        "text": "",
                        "latency_ms": latency_ms,
                        "model": self.model,
                        "error": "No response candidates returned by Gemini",
                    }

                parts_out = candidates[0].get("content", {}).get("parts", [])
                text_out = "".join(p.get("text", "") for p in parts_out).strip()

                logger.info(f"Gemini API ({self.model}) responded in {latency_ms:.1f}ms: '{text_out[:50]}...'")
                return {
                    "text": text_out,
                    "latency_ms": latency_ms,
                    "model": self.model,
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
            logger.warning(f"Gemini API HTTP error: {error_msg}")
            return {
                "text": "",
                "latency_ms": latency_ms,
                "model": self.model,
                "error": error_msg,
            }

        except urllib.error.URLError as e:
            latency_ms = (time.perf_counter() - t_start) * 1000.0
            logger.warning(f"Gemini API network error (offline?): {e.reason}")
            return {
                "text": "",
                "latency_ms": latency_ms,
                "model": self.model,
                "error": f"Network error: {e.reason}",
            }

        except Exception as e:
            latency_ms = (time.perf_counter() - t_start) * 1000.0
            logger.error(f"Gemini API unexpected error: {e}")
            return {
                "text": "",
                "latency_ms": latency_ms,
                "model": self.model,
                "error": str(e),
            }

    def check_connectivity(self) -> bool:
        """Quick connectivity check to verify Internet and API access."""
        if not self.is_configured:
            return False
        res = self.generate_content("Ping", max_output_tokens=5, temperature=0.0)
        return res.get("error") is None
