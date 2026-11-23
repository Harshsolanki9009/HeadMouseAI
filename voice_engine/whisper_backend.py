"""Whisper.cpp inference wrapper for Jadoo Voice Engine.

Executes local, offline speech-to-text inference using optimized whisper.cpp
CPU binaries with thread capping (<= 2 threads), low process priority, and
safe UTF-8 Unicode decoding for English, Hindi (Devanagari), and Hinglish.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import time
from typing import Any, Dict, Optional, Tuple

import psutil

from ai_provider.groq_stt import GroqSTTClient
from utils.logger import logger
from utils.resource import get_resource_path

# Windows process creation flags
CREATE_NO_WINDOW = 0x08000000
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000


DEFAULT_HINGLISH_PROMPT = (
    "Hindi and English mixed speech, Hinglish conversation: "
    "Haan, main theek hoon, but aaj meeting attend nahi kar sakta."
)


def clean_whisper_text(raw_text: str) -> str:
    """Filter out non-speech tags, bracketed hallucinations, repetition loops, and punctuation-only strings.

    Strips Whisper artifact tags such as:
    - [BLANK_AUDIO], [MUSIC PLAYING], [XBOX SOUND], [APPLAUSE], etc.
    - (dramatic music), (eerie music), (bell dings), (sighs), etc.
    - <cough>, <whispering>, etc.
    Rejects runaway repetition loops while preserving natural spoken speech.
    Discards empty or punctuation-only strings.
    """
    if not raw_text:
        return ""
    # Strip square bracketed cues [...]
    text = re.sub(r"\[.*?\]", "", raw_text)
    # Strip parenthesized cues (...)
    text = re.sub(r"\(.*?\)", "", text)
    # Strip angle bracket cues <...>
    text = re.sub(r"<.*?>", "", text)
    # Collapse multiple whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # If no word characters (Latin or Devanagari) remain, treat as empty non-speech
    if not re.search(r"[\w\u0900-\u097F]", text):
        return ""

    # Reject runaway repetition loops (e.g. 'Vali, Vali, Vali, Vali...')
    words = re.findall(r"[\w\u0900-\u097F]+", text.lower())
    count = 1
    for i in range(1, len(words)):
        if words[i] == words[i - 1]:
            count += 1
            # Runaway loop: >= 4 repeats, or >= 3 in a very short utterance dominating > 50%
            if count >= 4 or (count >= 3 and len(words) <= 5):
                logger.debug(f"Rejected Whisper repetition loop ('{words[i]}' x{count}): {text}")
                return ""
        else:
            count = 1

    # Also reject 2-word phrase repeating >= 3 times (e.g., 'and then and then and then')
    if len(words) >= 6:
        for i in range(len(words) - 5):
            p1 = (words[i], words[i + 1])
            p2 = (words[i + 2], words[i + 3])
            p3 = (words[i + 4], words[i + 5])
            if p1 == p2 == p3:
                logger.debug(f"Rejected 2-word phrase repetition loop {p1}: {text}")
                return ""

    return text


class WhisperBackendError(Exception):
    """Raised when Whisper binary or inference fails."""
    pass


class WhisperBackend:
    """Hybrid Cloud/Offline STT Backend (Groq Cloud Whisper with local whisper-cli fallback)."""

    def __init__(
        self,
        model_name: str = "ggml-base.bin",
        threads: int = 2,
        language: str = "en",
        stt_mode: str = "cloud_first",
        groq_api_key: Optional[str] = None,
        binary_dir: Optional[str] = None,
        models_dir: Optional[str] = None,
    ) -> None:
        self.threads = min(2, max(1, int(threads)))  # Strict <= 2 thread constraint
        self.language = language
        self.model_name = model_name
        self.stt_mode = stt_mode  # "cloud_first" (Default), "auto", "cloud", "offline"

        # Cloud STT client
        self.groq_client = GroqSTTClient(api_key=groq_api_key)

        # Resolve paths via resource locator
        if binary_dir:
            self.binary_dir = os.path.abspath(binary_dir)
        else:
            self.binary_dir = str(get_resource_path(os.path.join("assets", "bin", "whisper")))

        if models_dir:
            self.models_dir = os.path.abspath(models_dir)
        else:
            self.models_dir = str(get_resource_path(os.path.join("assets", "models", "whisper")))

        self.executable_path = os.path.join(self.binary_dir, "whisper-cli.exe")
        self.model_path = os.path.join(self.models_dir, self.model_name)

        # Telemetry & Diagnostics
        self.last_inference_ms: float = 0.0
        self.last_cpu_percent: float = 0.0
        self.last_ram_mb: float = 0.0
        self.total_inferences: int = 0
        self.last_backend_used: str = "offline"

        self.verify_assets()

    def set_groq_api_key(self, api_key: str) -> None:
        """Update Groq API key dynamically."""
        self.groq_client.set_api_key(api_key)

    def set_stt_mode(self, mode: str) -> None:
        """Set STT mode ('cloud_first', 'auto', 'cloud', 'offline')."""
        if mode in ("cloud_first", "auto", "cloud", "offline"):
            self.stt_mode = mode
            logger.info(f"STT Mode updated to: {mode}")

    def verify_assets(self) -> Tuple[bool, str]:
        """Verify binary and model asset presence on disk."""
        if not os.path.isfile(self.executable_path):
            msg = f"Whisper binary not found at {self.executable_path}"
            logger.warning(msg)
            return False, msg

        if not os.path.isfile(self.model_path):
            msg = f"Whisper model not found at {self.model_path}"
            logger.warning(msg)
            return False, msg

        return True, "READY"

    @property
    def is_available(self) -> bool:
        """True if either cloud STT is configured or local binary/model are present."""
        if self.stt_mode in ("cloud_first", "auto", "cloud") and self.groq_client.is_configured:
            return True
        return os.path.isfile(self.executable_path) and os.path.isfile(self.model_path)

    def set_model(self, model_name: str) -> bool:
        """Switch active whisper model (e.g. ggml-tiny.bin vs ggml-base.bin)."""
        target_path = os.path.join(self.models_dir, model_name)
        if not os.path.isfile(target_path):
            logger.error(f"Cannot set model: {target_path} does not exist.")
            return False
        self.model_name = model_name
        self.model_path = target_path
        logger.info(f"WhisperBackend active model switched to: {model_name}")
        return True

    def set_language(self, language: str) -> None:
        """Set language code ('auto', 'en', 'hi')."""
        self.language = language

    def transcribe_wav_bytes(
        self,
        wav_bytes: bytes,
        language: Optional[str] = None,
        initial_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Transcribe 16-bit 16kHz mono WAV bytes via Cloud First Groq or Local Whisper fallback."""
        if not wav_bytes or len(wav_bytes) < 44:  # 44 bytes is minimum WAV header
            return {
                "text": "",
                "latency_ms": 0.0,
                "language": language or self.language,
                "backend": "none",
                "fallback_occurred": False,
                "fallback_reason": None,
                "error": "Empty audio data",
            }

        lang = language if language else self.language
        fallback_occurred = False
        fallback_reason = None

        # 1. Attempt Groq Cloud Whisper if permitted
        if self.stt_mode in ("cloud_first", "auto", "cloud"):
            if not self.groq_client.is_configured:
                if self.stt_mode == "cloud":
                    return {
                        "text": "",
                        "latency_ms": 0.0,
                        "language": lang,
                        "backend": "groq-cloud",
                        "fallback_occurred": False,
                        "fallback_reason": None,
                        "error": "GROQ_API_KEY not configured and offline fallback is disabled in Cloud-Only mode.",
                    }
                else:
                    logger.info("GROQ_API_KEY missing in cloud_first mode; immediately routing to local whisper.cpp")
                    fallback_occurred = True
                    fallback_reason = "API KEY MISSING"
            else:
                try:
                    res_cloud = self.groq_client.transcribe_wav_bytes(
                        wav_bytes,
                        language=lang,
                        prompt=initial_prompt,
                    )
                    raw_text = res_cloud.get("text", "")
                    cleaned = clean_whisper_text(raw_text)
                    cloud_err = res_cloud.get("error")

                    if not cloud_err:
                        self.last_inference_ms = res_cloud.get("latency_ms", 0.0)
                        self.last_backend_used = "groq-cloud"
                        self.total_inferences += 1
                        return {
                            "text": cleaned,
                            "latency_ms": self.last_inference_ms,
                            "language": lang,
                            "backend": "groq-cloud",
                            "fallback_occurred": False,
                            "fallback_reason": None,
                            "error": None,
                        }
                    else:
                        logger.info(f"Groq Cloud STT returned error ({cloud_err}); falling back to local whisper.cpp...")
                        fallback_occurred = True
                        fallback_reason = cloud_err
                except Exception as e:
                    logger.info(f"Groq Cloud STT connection failed ({e}); falling back to local whisper.cpp...")
                    fallback_occurred = True
                    fallback_reason = str(e)

        # If Cloud Only was explicitly demanded and failed
        if self.stt_mode == "cloud":
            return {
                "text": "",
                "latency_ms": 0.0,
                "language": lang,
                "backend": "groq-cloud",
                "fallback_occurred": False,
                "fallback_reason": None,
                "error": f"Groq Cloud STT failed ({fallback_reason}) and offline fallback is disabled in Cloud-Only mode.",
            }

        # 2. Local Whisper-CLI Fallback
        if not os.path.isfile(self.executable_path) or not os.path.isfile(self.model_path):
            raise WhisperBackendError("Whisper engine unavailable (Executable or Model missing)")

        # Write audio temporarily for whisper-cli input
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
            tmp_wav.write(wav_bytes)
            tmp_wav_path = tmp_wav.name

        try:
            res_local = self.transcribe_file(tmp_wav_path, language=lang, initial_prompt=initial_prompt)
            res_local["backend"] = "whisper-local"
            res_local["fallback_occurred"] = fallback_occurred
            res_local["fallback_reason"] = fallback_reason
            self.last_backend_used = "whisper-local"
            return res_local
        finally:
            if os.path.exists(tmp_wav_path):
                try:
                    os.remove(tmp_wav_path)
                except Exception:
                    pass

    def transcribe_file(
        self,
        wav_filepath: str,
        language: Optional[str] = None,
        initial_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute whisper-cli.exe on a WAV file with low process priority and thread capping."""
        if not os.path.isfile(wav_filepath):
            raise WhisperBackendError(f"WAV audio file not found: {wav_filepath}")

        lang = language if language else self.language

        # Map language to whisper-cli supported parameters
        cli_lang = lang
        effective_prompt = initial_prompt

        if lang == "hinglish":
            cli_lang = "auto"
            if not effective_prompt:
                effective_prompt = DEFAULT_HINGLISH_PROMPT
        elif lang == "auto":
            cli_lang = "auto"

        cmd = [
            self.executable_path,
            "-m", self.model_path,
            "-f", wav_filepath,
            "-t", str(self.threads),
            "-l", cli_lang,
            "-nt",                    # no timestamps
            "-np",                    # no prints/progress bars
            "--no-gpu",               # CPU inference
            "--max-context", "0",     # prevent previous context from poisoning next utterance
            "--no-speech-thold", "0.65",  # anti-hallucination threshold on quiet audio
            "--entropy-thold", "2.4",     # entropy threshold for decoder fail
            "--logprob-thold", "-1.0",    # log probability threshold for decoder fail
            "--temperature", "0.0",   # greedy deterministic decoding for highest accuracy
            "--suppress-nst",         # suppress non-speech tokens
        ]

        if effective_prompt:
            cmd.extend(["--prompt", effective_prompt])

        t_start = time.perf_counter()
        cpu_before = psutil.cpu_percent(interval=None)

        try:
            # Launch with low priority class and hidden window
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            # Measure peak RAM of whisper-cli process
            peak_ram_mb = 0.0
            try:
                p_proc = psutil.Process(proc.pid)
                while proc.poll() is None:
                    mem = p_proc.memory_info().rss / (1024 * 1024)
                    if mem > peak_ram_mb:
                        peak_ram_mb = mem
                    time.sleep(0.01)
            except Exception:
                pass

            stdout, stderr = proc.communicate(timeout=60)
            latency_ms = (time.perf_counter() - t_start) * 1000.0
            cpu_after = psutil.cpu_percent(interval=None)

            if proc.returncode != 0:
                logger.error(f"Whisper inference returned exit code {proc.returncode}: {stderr}")
                return {
                    "text": "",
                    "latency_ms": latency_ms,
                    "language": lang,
                    "backend": "whisper-local",
                    "error": f"Exit code {proc.returncode}: {stderr.strip()}",
                }

            # Clean up output text: filter out non-speech tags, bracketed cues, and empty whitespace
            cleaned_text = clean_whisper_text(stdout)

            self.last_inference_ms = latency_ms
            self.last_ram_mb = peak_ram_mb
            self.last_cpu_percent = (cpu_before + cpu_after) / 2.0
            self.total_inferences += 1

            if cleaned_text:
                logger.info(
                    f"Whisper STT [{self.model_name}] completed in {latency_ms:.1f}ms "
                    f"(Peak RAM: {peak_ram_mb:.1f}MB, Threads: {self.threads}): '{cleaned_text[:50]}...'"
                )
            else:
                logger.debug(
                    f"Whisper STT [{self.model_name}] completed in {latency_ms:.1f}ms: "
                    f"non-speech or empty output filtered (raw: '{stdout.strip()[:40]}')"
                )

            return {
                "text": cleaned_text,
                "latency_ms": latency_ms,
                "language": lang,
                "backend": "whisper-local",
                "ram_mb": peak_ram_mb,
                "cpu_percent": self.last_cpu_percent,
                "model": self.model_name,
                "error": None,
            }

        except subprocess.TimeoutExpired:
            proc.kill()
            logger.error("Whisper inference timed out after 60 seconds.")
            return {"text": "", "latency_ms": 60000.0, "language": lang, "backend": "whisper-local", "error": "Timeout"}
        except Exception as e:
            logger.error(f"Whisper transcription execution error: {e}")
            return {"text": "", "latency_ms": 0.0, "language": lang, "backend": "whisper-local", "error": str(e)}
