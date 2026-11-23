"""Comprehensive test suite for Cloud-First Voice Recognition with Graceful Fallback.

Tests:
1. Default mode: cloud_first configured across Settings, config.toml, and WhisperBackend.
2. Cloud-first routing: valid API key calls Groq Cloud Whisper API.
3. Missing API key: immediate local whisper fallback with zero network requests and 'API KEY MISSING' reason.
4. Network error / Timeout fallback: gracefully falls back to local whisper with audio preserved.
5. API errors (401, 429, 500): fallback to local whisper with audio preserved.
6. Offline Only mode: verify zero network calls made even with API key present.
7. Language preservation across fallback: 'en', 'hi', 'hinglish', 'auto' preserved verbatim.
8. Groq API Hinglish safety: never passes invalid language code 'hinglish' to Groq API.
9. Verbatim text preservation: no LLM rewriting or translation during dictation.
10. UI badges and Provider selector: verify all states (CLOUD WHISPER, LOCAL WHISPER, OFFLINE FALLBACK,
    API KEY MISSING, CLOUD UNAVAILABLE, CONNECTING).
"""

from __future__ import annotations

import io
import os
import wave
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import toml
from PySide6.QtWidgets import QApplication

from ai_provider.groq_stt import DEFAULT_HINGLISH_PROMPT, GroqSTTClient
from config.settings import AppSettings, SETTINGS_FILE
from gui.main_window import MainWindow
from gui.widgets.settings_tab import SettingsTabWidget
from gui.widgets.voice_control_widget import VoiceControlWidget
from voice_engine.audio_capture import AudioRecorder, EnergyVAD
from voice_engine.whisper_backend import WhisperBackend, clean_whisper_text


# ------------------------------------------------------------------------------
# Fixtures & Helpers
# ------------------------------------------------------------------------------

@pytest.fixture(scope="session")
def qapp():
    """Shared QApplication fixture for GUI widget tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def generate_test_wav_bytes(duration_s: float = 0.5, freq: float = 300.0, sample_rate: int = 16000) -> bytes:
    """Generate valid 16-bit 16 kHz mono PCM WAV bytes with a continuous sine tone."""
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    samples = (np.sin(2 * np.pi * freq * t) * 32767 * 0.7).astype(np.int16)

    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())
    return bio.getvalue()


# ==============================================================================
# 1. Default Configuration & Validation
# ==============================================================================

class TestDefaultModeAndConfiguration:
    """Verify cloud_first is the standard default mode across the application."""

    def test_default_stt_mode_is_cloud_first(self) -> None:
        """AppSettings default stt_mode must be 'cloud_first'."""
        settings = AppSettings()
        assert settings.jadoo.stt_mode == "cloud_first"
        assert len(settings.validate()) == 0

    def test_config_toml_stt_mode_is_cloud_first(self) -> None:
        """config.toml must specify stt_mode = 'cloud_first'."""
        assert SETTINGS_FILE.is_file(), "config.toml must exist"
        data = toml.load(str(SETTINGS_FILE))
        assert "jadoo" in data
        assert data["jadoo"].get("stt_mode") == "cloud_first"

    def test_settings_validation_stt_modes(self) -> None:
        """AppSettings accepts 'cloud_first', 'auto', 'offline', 'cloud' and rejects invalid modes."""
        settings = AppSettings()
        for valid_mode in ("cloud_first", "auto", "offline", "cloud"):
            settings.jadoo.stt_mode = valid_mode
            assert len(settings.validate()) == 0

        settings.jadoo.stt_mode = "unsupported_mode"
        errs = settings.validate()
        assert any("stt mode" in e.lower() for e in errs)

    def test_whisper_backend_default_mode(self) -> None:
        """WhisperBackend initializes with stt_mode='cloud_first' by default."""
        backend = WhisperBackend()
        assert backend.stt_mode == "cloud_first"


# ==============================================================================
# 2. Cloud First Routing & Automatic Fallback
# ==============================================================================

class TestCloudFirstRoutingAndFallback:
    """Test Cloud First Groq STT routing, missing key detection, and fallback mechanics."""

    def test_cloud_first_with_valid_key_calls_groq(self) -> None:
        """With configured API key, cloud_first successfully routes to Groq Cloud STT."""
        backend = WhisperBackend(stt_mode="cloud_first", groq_api_key="gsk_test_valid_key")
        wav_bytes = generate_test_wav_bytes(0.5)

        mock_groq_resp = {
            "text": "Hello this is Cloud Whisper",
            "latency_ms": 320.5,
            "language": "en",
            "error": None,
        }

        with patch.object(backend.groq_client, "transcribe_wav_bytes", return_value=mock_groq_resp) as mock_transcribe, \
             patch.object(backend, "transcribe_file") as mock_local:

            result = backend.transcribe_wav_bytes(wav_bytes, language="en")

            mock_transcribe.assert_called_once()
            mock_local.assert_not_called()
            assert result["backend"] == "groq-cloud"
            assert result["text"] == "Hello this is Cloud Whisper"
            assert result["latency_ms"] == 320.5
            assert result["fallback_occurred"] is False
            assert result["fallback_reason"] is None

    def test_cloud_first_missing_key_immediate_local_fallback(self) -> None:
        """When GROQ_API_KEY is empty/missing, immediately fall back to local whisper with zero network calls."""
        # Ensure environment and registry have no key for this test
        with patch.dict(os.environ, {}, clear=True), patch("ai_provider.groq_stt.resolve_groq_api_key", return_value=""):
            backend = WhisperBackend(stt_mode="cloud_first", groq_api_key="")
            assert not backend.groq_client.is_configured

            wav_bytes = generate_test_wav_bytes(0.5)
            mock_local_resp = {
                "text": "Offline Local Speech",
                "latency_ms": 1100.0,
                "language": "en",
                "model": "ggml-base.bin",
                "error": None,
            }

            with patch.object(backend.groq_client, "transcribe_wav_bytes") as mock_groq, \
                 patch.object(backend, "transcribe_file", return_value=mock_local_resp) as mock_local:

                result = backend.transcribe_wav_bytes(wav_bytes, language="en")

                # Verify Groq STT was NEVER called
                mock_groq.assert_not_called()
                mock_local.assert_called_once()
                assert result["backend"] == "whisper-local"
                assert result["fallback_occurred"] is True
                assert result["fallback_reason"] == "API KEY MISSING"
                assert result["text"] == "Offline Local Speech"

    def test_cloud_first_network_failure_fallback_preserves_audio(self) -> None:
        """When Groq network connection fails, audio is preserved and passed to local whisper."""
        backend = WhisperBackend(stt_mode="cloud_first", groq_api_key="gsk_test_key")
        wav_bytes = generate_test_wav_bytes(0.5)

        mock_groq_err = {
            "text": "",
            "latency_ms": 45.0,
            "language": "en",
            "error": "Network error: Temporary failure in name resolution",
        }

        mock_local_resp = {
            "text": "Recovered by offline engine",
            "latency_ms": 1250.0,
            "language": "en",
            "error": None,
        }

        captured_audio = []

        def mock_transcribe_file(filepath, **kwargs):
            assert os.path.isfile(filepath)
            with open(filepath, "rb") as f:
                captured_audio.append(f.read())
            return mock_local_resp

        with patch.object(backend.groq_client, "transcribe_wav_bytes", return_value=mock_groq_err), \
             patch.object(backend, "transcribe_file", side_effect=mock_transcribe_file) as mock_local:

            result = backend.transcribe_wav_bytes(wav_bytes, language="en")

            mock_local.assert_called_once()
            assert len(captured_audio) == 1
            assert captured_audio[0] == wav_bytes
            assert result["backend"] == "whisper-local"
            assert result["fallback_occurred"] is True
            assert "Network error" in result["fallback_reason"]
            assert result["text"] == "Recovered by offline engine"

    def test_cloud_first_timeout_fallback(self) -> None:
        """When Groq cloud request times out, fallback to local whisper triggers smoothly."""
        backend = WhisperBackend(stt_mode="cloud_first", groq_api_key="gsk_test_key")
        wav_bytes = generate_test_wav_bytes(0.5)

        mock_groq_timeout = {
            "text": "",
            "latency_ms": 12000.0,
            "language": "en",
            "error": "HTTP timeout after 12.0s",
        }

        mock_local_resp = {
            "text": "Transcribed locally after cloud timeout",
            "latency_ms": 980.0,
            "language": "en",
            "error": None,
        }

        with patch.object(backend.groq_client, "transcribe_wav_bytes", return_value=mock_groq_timeout), \
             patch.object(backend, "transcribe_file", return_value=mock_local_resp):

            result = backend.transcribe_wav_bytes(wav_bytes, language="en")
            assert result["backend"] == "whisper-local"
            assert result["fallback_occurred"] is True
            assert "timeout" in result["fallback_reason"].lower()
            assert result["text"] == "Transcribed locally after cloud timeout"

    def test_cloud_first_http_401_invalid_key_fallback(self) -> None:
        """HTTP 401 Unauthorized triggers immediate fallback with invalid key notice."""
        backend = WhisperBackend(stt_mode="cloud_first", groq_api_key="gsk_invalid_key")
        wav_bytes = generate_test_wav_bytes(0.5)

        mock_groq_401 = {
            "text": "",
            "latency_ms": 110.0,
            "language": "en",
            "error": "HTTP 401: Invalid API Key provided",
        }

        with patch.object(backend.groq_client, "transcribe_wav_bytes", return_value=mock_groq_401), \
             patch.object(backend, "transcribe_file", return_value={"text": "Local result", "latency_ms": 800.0, "language": "en", "error": None}):

            result = backend.transcribe_wav_bytes(wav_bytes, language="en")
            assert result["backend"] == "whisper-local"
            assert result["fallback_occurred"] is True
            assert "401" in result["fallback_reason"]

    def test_cloud_first_http_429_rate_limit_fallback(self) -> None:
        """HTTP 429 Rate Limit triggers fallback to local whisper."""
        backend = WhisperBackend(stt_mode="cloud_first", groq_api_key="gsk_rate_limited")
        wav_bytes = generate_test_wav_bytes(0.5)

        mock_groq_429 = {
            "text": "",
            "latency_ms": 90.0,
            "language": "en",
            "error": "HTTP 429: Rate limit reached for whisper-large-v3-turbo",
        }

        with patch.object(backend.groq_client, "transcribe_wav_bytes", return_value=mock_groq_429), \
             patch.object(backend, "transcribe_file", return_value={"text": "Local text", "latency_ms": 850.0, "language": "en", "error": None}):

            result = backend.transcribe_wav_bytes(wav_bytes, language="en")
            assert result["backend"] == "whisper-local"
            assert result["fallback_occurred"] is True
            assert "429" in result["fallback_reason"]

    def test_cloud_first_http_500_server_error_fallback(self) -> None:
        """HTTP 500 Cloud Service Error triggers fallback to local whisper."""
        backend = WhisperBackend(stt_mode="cloud_first", groq_api_key="gsk_server_error")
        wav_bytes = generate_test_wav_bytes(0.5)

        mock_groq_500 = {
            "text": "",
            "latency_ms": 150.0,
            "language": "en",
            "error": "HTTP 500: Internal Server Error",
        }

        with patch.object(backend.groq_client, "transcribe_wav_bytes", return_value=mock_groq_500), \
             patch.object(backend, "transcribe_file", return_value={"text": "Local text", "latency_ms": 850.0, "language": "en", "error": None}):

            result = backend.transcribe_wav_bytes(wav_bytes, language="en")
            assert result["backend"] == "whisper-local"
            assert result["fallback_occurred"] is True
            assert "500" in result["fallback_reason"]

    def test_offline_only_mode_zero_network_calls(self) -> None:
        """In 'offline' mode, zero network calls must be attempted even with a valid API key present."""
        backend = WhisperBackend(stt_mode="offline", groq_api_key="gsk_valid_key")
        wav_bytes = generate_test_wav_bytes(0.5)

        mock_local_resp = {
            "text": "100% Offline transcription",
            "latency_ms": 900.0,
            "language": "en",
            "error": None,
        }

        with patch.object(backend.groq_client, "transcribe_wav_bytes") as mock_groq, \
             patch.object(backend, "transcribe_file", return_value=mock_local_resp) as mock_local:

            result = backend.transcribe_wav_bytes(wav_bytes, language="en")

            mock_groq.assert_not_called()
            mock_local.assert_called_once()
            assert result["backend"] == "whisper-local"
            assert result["fallback_occurred"] is False
            assert result["fallback_reason"] is None
            assert result["text"] == "100% Offline transcription"

    def test_cloud_only_mode_fails_without_fallback(self) -> None:
        """In 'cloud' mode, fallback to local whisper is strictly disabled."""
        backend = WhisperBackend(stt_mode="cloud", groq_api_key="gsk_key")
        wav_bytes = generate_test_wav_bytes(0.5)

        mock_groq_err = {
            "text": "",
            "latency_ms": 50.0,
            "language": "en",
            "error": "Network error",
        }

        with patch.object(backend.groq_client, "transcribe_wav_bytes", return_value=mock_groq_err), \
             patch.object(backend, "transcribe_file") as mock_local:

            result = backend.transcribe_wav_bytes(wav_bytes, language="en")

            mock_local.assert_not_called()
            assert result["backend"] == "groq-cloud"
            assert "disabled in Cloud-Only mode" in result["error"]


# ==============================================================================
# 3. Language Preservation Across Fallback
# ==============================================================================

class TestLanguagePreservationAcrossFallback:
    """Verify selected language ('en', 'hi', 'hinglish', 'auto') is preserved across fallback."""

    def test_fallback_preserves_english(self) -> None:
        """English selection is preserved during cloud failure and passed to local whisper."""
        backend = WhisperBackend(stt_mode="cloud_first", groq_api_key="gsk_key", language="en")
        wav_bytes = generate_test_wav_bytes(0.5)

        with patch.object(backend.groq_client, "transcribe_wav_bytes", return_value={"error": "timeout"}), \
             patch.object(backend, "transcribe_file", return_value={"text": "Hello", "latency_ms": 500, "language": "en", "error": None}) as mock_local:

            result = backend.transcribe_wav_bytes(wav_bytes, language="en")
            assert mock_local.call_args[1]["language"] == "en"
            assert result["language"] == "en"

    def test_fallback_preserves_hindi(self) -> None:
        """Hindi selection is preserved during cloud failure and passed to local whisper."""
        backend = WhisperBackend(stt_mode="cloud_first", groq_api_key="gsk_key", language="hi")
        wav_bytes = generate_test_wav_bytes(0.5)

        with patch.object(backend.groq_client, "transcribe_wav_bytes", return_value={"error": "timeout"}), \
             patch.object(backend, "transcribe_file", return_value={"text": "नमस्ते", "latency_ms": 600, "language": "hi", "error": None}) as mock_local:

            result = backend.transcribe_wav_bytes(wav_bytes, language="hi")
            assert mock_local.call_args[1]["language"] == "hi"
            assert result["language"] == "hi"

    def test_fallback_preserves_hinglish(self) -> None:
        """Hinglish selection is preserved during cloud failure and passed to local whisper."""
        backend = WhisperBackend(stt_mode="cloud_first", groq_api_key="gsk_key", language="hinglish")
        wav_bytes = generate_test_wav_bytes(0.5)

        with patch.object(backend.groq_client, "transcribe_wav_bytes", return_value={"error": "timeout"}), \
             patch.object(backend, "transcribe_file", return_value={"text": "Meeting cancel ho gaya", "latency_ms": 700, "language": "hinglish", "error": None}) as mock_local:

            result = backend.transcribe_wav_bytes(wav_bytes, language="hinglish")
            assert mock_local.call_args[1]["language"] == "hinglish"
            assert result["language"] == "hinglish"

    def test_groq_never_receives_invalid_hinglish_code(self) -> None:
        """GroqSTTClient must never pass 'hinglish' or 'auto' in HTTP form fields."""
        client = GroqSTTClient(api_key="gsk_test")
        wav_bytes = generate_test_wav_bytes(0.5)

        # Mock urllib.request.urlopen to inspect Request body and headers
        captured_requests = []

        def mock_urlopen(req, timeout=12.0):
            captured_requests.append(req)
            resp = MagicMock()
            resp.read.return_value = b'{"text": "Aaj meeting cancel hai"}'
            return resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            # 1. Test language='hinglish'
            client.transcribe_wav_bytes(wav_bytes, language="hinglish")
            assert len(captured_requests) == 1
            body_1 = captured_requests[0].data.decode("utf-8", errors="replace")
            # Must NOT contain name="language"\r\n\r\nhinglish
            assert 'name="language"\r\n\r\nhinglish' not in body_1
            # Must contain prompt with Hinglish priming context
            assert "Hindi and English mixed speech" in body_1

            # 2. Test language='auto'
            client.transcribe_wav_bytes(wav_bytes, language="auto")
            assert len(captured_requests) == 2
            body_2 = captured_requests[1].data.decode("utf-8", errors="replace")
            assert 'name="language"\r\n\r\nauto' not in body_2

            # 3. Test explicit language='en'
            client.transcribe_wav_bytes(wav_bytes, language="en")
            assert len(captured_requests) == 3
            body_3 = captured_requests[2].data.decode("utf-8", errors="replace")
            assert 'name="language"\r\n\r\nen' in body_3


# ==============================================================================
# 4. Verbatim Text Integrity & Anti-Hallucination
# ==============================================================================

class TestVerbatimSpeechIntegrity:
    """Verify raw spoken text is typed verbatim without alterations."""

    def test_spoken_hindi_preserved_verbatim(self) -> None:
        """Hindi text in Devanagari is kept verbatim without translation."""
        hindi = "कृपया विंडो बंद करें और फ़ाइल सहेजें"
        assert clean_whisper_text(hindi) == hindi
        assert "close" not in clean_whisper_text(hindi).lower()

    def test_spoken_hinglish_preserved_verbatim(self) -> None:
        """Hinglish code-switched text is kept verbatim."""
        hinglish = "Main kal presentation deliver karunga because slides ready hain."
        assert clean_whisper_text(hinglish) == hinglish

    def test_spoken_english_preserved_verbatim(self) -> None:
        """English speech is kept verbatim."""
        english = "HeadMouseAI allows hands free control using MediaPipe."
        assert clean_whisper_text(english) == english

    def test_whisper_hallucination_tags_stripped_safely(self) -> None:
        """Artifact tags like [BLANK_AUDIO] or (dramatic music) are stripped, real words kept."""
        noisy = "[BLANK_AUDIO] Hello world (music playing) this is working [APPLAUSE]"
        cleaned = clean_whisper_text(noisy)
        assert cleaned == "Hello world this is working"


# ==============================================================================
# 5. UI Status Indicators & Provider Selection
# ==============================================================================

class TestUIStatusIndicatorsAndProviderSelection:
    """Test VoiceControlWidget engine badges, SettingsTab options, and MainWindow engine state."""

    def test_settings_tab_provider_options(self, qapp) -> None:
        """Settings tab contains 'Cloud First (Default)', 'Automatic', and 'Offline Only'."""
        settings = AppSettings()
        tab = SettingsTabWidget(settings)

        items = [tab.combo_stt_mode.itemText(i) for i in range(tab.combo_stt_mode.count())]
        datas = [tab.combo_stt_mode.itemData(i) for i in range(tab.combo_stt_mode.count())]

        assert "cloud_first" in datas
        assert "auto" in datas
        assert "offline" in datas

        # Cloud First is first and marked Recommended/Default
        assert datas[0] == "cloud_first"
        assert "Cloud First" in items[0]
        assert "Default" in items[0]

    def test_voice_widget_status_badges(self, qapp) -> None:
        """VoiceControlWidget engine badge displays all required semantic states."""
        widget = VoiceControlWidget()

        # 1. Active Cloud Whisper (Green)
        widget.set_engine("CLOUD WHISPER")
        assert widget.badge_engine.text() == "CLOUD WHISPER"
        assert widget.badge_engine._current_category == "OK"

        widget.set_engine("groq-cloud")
        assert widget.badge_engine.text() == "CLOUD WHISPER"

        # 2. Local Whisper (Blue)
        widget.set_engine("LOCAL WHISPER")
        assert widget.badge_engine.text() == "LOCAL WHISPER"
        assert widget.badge_engine._current_category == "LOCAL"

        widget.set_engine("whisper-local")
        assert widget.badge_engine.text() == "LOCAL WHISPER"

        # 3. Offline Fallback (Amber / Warning)
        widget.set_engine("LOCAL WHISPER — OFFLINE FALLBACK")
        assert "FALLBACK" in widget.badge_engine.text().upper()
        assert widget.badge_engine._current_category == "WARNING"

        # 4. API Key Missing (Warning)
        widget.set_engine("API KEY MISSING")
        assert widget.badge_engine.text() == "API KEY MISSING"
        assert widget.badge_engine._current_category == "WARNING"

        # 5. Cloud Unavailable (Warning)
        widget.set_engine("CLOUD UNAVAILABLE")
        assert widget.badge_engine.text() == "CLOUD UNAVAILABLE"
        assert widget.badge_engine._current_category == "WARNING"

        # 6. Connecting (Active / Green)
        widget.set_engine("CONNECTING")
        assert widget.badge_engine.text() == "CONNECTING"
        assert widget.badge_engine._current_category == "ACTIVE"

    def test_main_window_initial_engine_badge_when_key_missing(self, qapp) -> None:
        """When API key is missing at launch, MainWindow displays 'API KEY MISSING'."""
        with patch.dict(os.environ, {}, clear=True), patch("ai_provider.groq_stt.resolve_groq_api_key", return_value=""):
            settings = AppSettings()
            settings.jadoo.stt_mode = "cloud_first"
            settings.jadoo.groq_api_key = ""

            win = MainWindow(settings)
            try:
                assert win.voice_widget.badge_engine.text() == "API KEY MISSING"
            finally:
                win.cleanup()
                win.deleteLater()
