"""Comprehensive test suite for Phase 2: Online Jadoo AI Assistant, Groq Cloud STT, and Wake Word."""

from __future__ import annotations

import io
import json
import time
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest
from PySide6.QtWidgets import QApplication

from ai_provider.gemini_client import GeminiClient
from ai_provider.groq_stt import GroqSTTClient
from config.settings import AppSettings
from gui.widgets.jadoo_assistant_widget import JadooAssistantWidget
from gui.widgets.settings_tab import SettingsTabWidget
from jadoo_assistant.assistant_worker import JadooWorker
from jadoo_assistant.context_builder import ContextBuilder
from jadoo_assistant.screen_capture import ScreenCapture
from jadoo_assistant.tts_player import TTSPlayer
from wake_word.wake_detector import WakeWordDetector


@pytest.fixture(scope="session")
def qapp():
    """Ensure a QGuiApplication / QApplication instance exists for GUI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ==============================================================================
# 1. Groq Cloud STT Client Tests
# ==============================================================================

class TestGroqSTTClient:
    def test_unconfigured_groq_client(self):
        client = GroqSTTClient(api_key="")
        assert not client.is_configured
        res = client.transcribe_wav_bytes(b"dummy_wav")
        assert res["text"] == ""
        assert "not configured" in res["error"]

    def test_successful_groq_transcription(self):
        client = GroqSTTClient(api_key="gsk_test123")
        assert client.is_configured

        mock_resp_data = json.dumps({"text": "Hello world from Groq Whisper"}).encode("utf-8")
        mock_response = MagicMock()
        mock_response.read.return_value = mock_resp_data
        mock_response.__enter__.return_value = mock_response

        valid_wav_bytes = b"RIFF" + b"\x00" * 100
        with patch("urllib.request.urlopen", return_value=mock_response):
            res = client.transcribe_wav_bytes(valid_wav_bytes, language="en")
            assert res["text"] == "Hello world from Groq Whisper"
            assert res["error"] is None

    def test_groq_http_error(self):
        client = GroqSTTClient(api_key="gsk_invalid")
        http_err = HTTPError("https://api.groq.com", 401, "Unauthorized", {}, io.BytesIO(b'{"error": "Invalid API Key"}'))

        valid_wav_bytes = b"RIFF" + b"\x00" * 100
        with patch("urllib.request.urlopen", side_effect=http_err):
            res = client.transcribe_wav_bytes(valid_wav_bytes)
            assert res["text"] == ""
            assert "HTTP 401" in res["error"]

    def test_groq_network_timeout(self):
        client = GroqSTTClient(api_key="gsk_timeout")
        valid_wav_bytes = b"RIFF" + b"\x00" * 100
        with patch("urllib.request.urlopen", side_effect=URLError("Connection timed out")):
            res = client.transcribe_wav_bytes(valid_wav_bytes)
            assert res["text"] == ""
            assert "Connection timed out" in res["error"]


# ==============================================================================
# 2. Gemini AI Client Tests
# ==============================================================================

class TestGeminiClient:
    def test_unconfigured_gemini_client(self):
        client = GeminiClient(api_key="")
        assert not client.is_configured
        res = client.generate_content("Hello")
        assert res["text"] == ""
        assert "not configured" in res["error"]

    def test_successful_gemini_text_generation(self):
        client = GeminiClient(api_key="AIza_test123")
        assert client.is_configured

        gemini_response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "HeadMouseAI lets you control your desktop hands-free."}
                        ]
                    }
                }
            ]
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(gemini_response).encode("utf-8")
        mock_response.__enter__.return_value = mock_response

        with patch("urllib.request.urlopen", return_value=mock_response):
            res = client.generate_content("What is HeadMouseAI?", system_instruction="You are Jadoo.")
            assert "HeadMouseAI lets you control your desktop" in res["text"]
            assert res["error"] is None

    def test_gemini_multimodal_payload_construction(self):
        client = GeminiClient(api_key="AIza_test123")
        captured_data = {}

        def mock_urlopen(req, timeout=12):
            captured_data["body"] = json.loads(req.data.decode("utf-8"))
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({
                "candidates": [{"content": {"parts": [{"text": "I see the desktop window."}]}}]
            }).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            res = client.generate_content(
                prompt="Explain this screen",
                image_jpeg_base64="dGVzdF9qcGVnX2Jhc2U2NA==",
            )
            assert res["text"] == "I see the desktop window."
            parts = captured_data["body"]["contents"][0]["parts"]
            assert len(parts) == 2
            assert parts[0]["inlineData"]["mimeType"] == "image/jpeg"
            assert parts[0]["inlineData"]["data"] == "dGVzdF9qcGVnX2Jhc2U2NA=="

    def test_gemini_http_error(self):
        client = GeminiClient(api_key="AIza_invalid")
        http_err = HTTPError("https://generativelanguage.googleapis.com", 400, "Bad Request", {}, io.BytesIO(b'{"error": {"message": "Invalid argument"}}'))

        with patch("urllib.request.urlopen", side_effect=http_err):
            res = client.generate_content("Hello")
            assert res["text"] == ""
            assert "HTTP 400" in res["error"]


# ==============================================================================
# 3. Wake Word Detector Tests
# ==============================================================================

class TestWakeWordDetector:
    def test_exact_wake_word_matches(self):
        detector = WakeWordDetector()
        is_wake, query = detector.detect("hey jadoo")
        assert is_wake is True
        assert query == ""

    def test_wake_word_with_query_extraction(self):
        detector = WakeWordDetector()
        is_wake, query = detector.detect("Hey Jadoo, what is the capital of India?")
        assert is_wake is True
        assert query == "what is the capital of India?"

    def test_phonetic_variants(self):
        detector = WakeWordDetector()
        variants = [
            ("hey jadu open chrome", "open chrome"),
            ("hey jardu minimize this window", "minimize this window"),
            ("jadoo help me write an email", "help me write an email"),
            ("जादू स्क्रीन देखो", "स्क्रीन देखो"),
            ("हे जादू क्या हाल है", "क्या हाल है"),
        ]
        for phrase, expected_query in variants:
            is_wake, q = detector.detect(phrase)
            assert is_wake is True, f"Failed for phrase: '{phrase}'"
            assert expected_query.lower() in q.lower(), f"Expected '{expected_query}' in '{q}'"

    def test_non_wake_phrases_rejected(self):
        detector = WakeWordDetector()
        non_wake = [
            "hello world",
            "click left",
            "scroll down please",
            "just testing dictation without magic",
            "how are you today",
        ]
        for phrase in non_wake:
            is_wake, _ = detector.detect(phrase)
            assert is_wake is False, f"False positive wake trigger on: '{phrase}'"


# ==============================================================================
# 4. Context Builder Tests
# ==============================================================================

class TestContextBuilder:
    def test_base_system_instruction(self):
        instruction = ContextBuilder.build_system_instruction(is_rewrite=False, include_screen=False)
        assert "Jadoo" in instruction
        assert "hands-free" in instruction.lower()
        assert "[SCREEN CONTEXT]" not in instruction

    def test_rewrite_system_instruction(self):
        instruction = ContextBuilder.build_system_instruction(is_rewrite=True, include_screen=False)
        assert "Jadoo Professional Editor" in instruction
        assert "Hinglish" in instruction

    def test_screen_system_instruction(self):
        instruction = ContextBuilder.build_system_instruction(is_rewrite=False, include_screen=True)
        assert "[SCREEN CONTEXT]" in instruction

    def test_format_user_prompt(self):
        prompt = ContextBuilder.format_user_prompt("aaj meeting 5 baje hai", is_rewrite=True)
        assert "Rewrite the following into professional workplace English" in prompt
        assert "aaj meeting 5 baje hai" in prompt


# ==============================================================================
# 5. Screen Capture Tests
# ==============================================================================

class TestScreenCapture:
    def test_screen_capture_mock(self):
        from PIL import Image

        dummy_img = Image.new("RGB", (1920, 1080), color=(100, 150, 200))
        with patch("PIL.ImageGrab.grab", return_value=dummy_img):
            jpeg_bytes, b64_str, err = ScreenCapture.capture_screen_jpeg(max_dim=960, quality=70)
            assert err is None
            assert len(jpeg_bytes) > 0
            assert isinstance(b64_str, str)
            assert len(b64_str) > 50

            # Verify downscaled image dimensions
            reopened = Image.open(io.BytesIO(jpeg_bytes))
            assert reopened.width <= 960
            assert reopened.height <= 960


# ==============================================================================
# 6. TTS Player Tests
# ==============================================================================

class TestTTSPlayer:
    def test_clean_text_for_speech(self):
        player = TTSPlayer()
        raw = "Hello **world**! Check [this link](http://foo.com) and `print('done')`. Also (details) here."
        cleaned = player.clean_text_for_speech(raw)
        assert "**" not in cleaned
        assert "`" not in cleaned
        assert "http" not in cleaned
        assert "Hello world" in cleaned

    def test_tts_stop_resets_state(self):
        player = TTSPlayer()
        player.stop()
        assert not player.is_speaking


# ==============================================================================
# 7. JadooWorker Integration Tests
# ==============================================================================

class TestJadooWorker:
    def test_worker_initialization(self, qapp):
        settings = AppSettings()
        worker = JadooWorker(settings)
        assert worker.is_online == bool(settings.jadoo.gemini_api_key)
        assert not worker.isRunning()

    def test_worker_abort_clears_queue(self, qapp):
        settings = AppSettings()
        worker = JadooWorker(settings)
        worker.ask("Query 1")
        worker.ask("Query 2")
        assert not worker._request_queue.empty()

        worker.abort()
        assert worker._request_queue.empty()

    def test_worker_processing_with_mock_gemini(self, qapp):
        settings = AppSettings()
        settings.jadoo.gemini_api_key = "AIza_mock"
        worker = JadooWorker(settings)

        responses = []
        worker.sig_jadoo_response.connect(lambda txt: responses.append(txt))

        mock_gemini_res = {
            "text": "Meeting scheduled for 5:00 PM.",
            "error": None,
        }
        with patch.object(worker.gemini, "generate_content", return_value=mock_gemini_res):
            worker.start()
            worker.ask("Schedule meeting at 5")

            # Wait briefly for thread to process queue
            for _ in range(25):
                qapp.processEvents()
                if responses:
                    break
                time.sleep(0.04)

            worker.stop()

        assert len(responses) == 1
        assert "5:00 PM" in responses[0]


# ==============================================================================
# 8. GUI Widget & Settings Tab Tests
# ==============================================================================

class TestJadooGUI:
    def test_jadoo_assistant_widget_inputs(self, qapp):
        settings = AppSettings()
        widget = JadooAssistantWidget(settings)

        asked = []
        widget.sig_ask_query.connect(lambda q, s, r: asked.append((q, s, r)))

        widget.inp_query.setText("Test Query")
        widget.btn_ask.click()
        assert len(asked) == 1
        assert asked[0] == ("Test Query", False, False)

        widget.inp_query.setText("aaj kaam ho gaya")
        widget.btn_rewrite.click()
        assert len(asked) == 2
        assert asked[1] == ("aaj kaam ho gaya", False, True)

        widget.set_response("Today work was completed successfully.")
        assert widget._last_response == "Today work was completed successfully."

        widget.clear()
        assert widget._last_response == ""
        assert widget.txt_response.toPlainText() == ""

    def test_settings_tab_jadoo_controls(self, qapp):
        settings = AppSettings()
        tab = SettingsTabWidget(settings)

        # Verify Jadoo widgets are present
        assert hasattr(tab, "inp_groq_key")
        assert hasattr(tab, "inp_gemini_key")
        assert hasattr(tab, "combo_stt_mode")
        assert hasattr(tab, "chk_tts_enabled")

        # Test changing Groq key
        groq_emitted = []
        tab.sig_groq_key_changed.connect(lambda k: groq_emitted.append(k))
        tab.inp_groq_key.setText("gsk_tab_test")
        assert "gsk_tab_test" in groq_emitted
        assert tab.settings.jadoo.groq_api_key == "gsk_tab_test"

        # Test changing Gemini key
        gemini_emitted = []
        tab.sig_gemini_key_changed.connect(lambda k: gemini_emitted.append(k))
        tab.inp_gemini_key.setText("AIza_tab_test")
        assert "AIza_tab_test" in gemini_emitted
        assert tab.settings.jadoo.gemini_api_key == "AIza_tab_test"

        # Test changing STT mode
        stt_emitted = []
        tab.sig_stt_mode_changed.connect(lambda m: stt_emitted.append(m))
        for i in range(tab.combo_stt_mode.count()):
            if tab.combo_stt_mode.itemData(i) == "cloud":
                tab.combo_stt_mode.setCurrentIndex(i)
                break
        assert "cloud" in stt_emitted
        assert tab.settings.jadoo.stt_mode == "cloud"

        # Test changing TTS enabled
        tts_emitted = []
        tab.sig_tts_toggled.connect(lambda t: tts_emitted.append(t))
        tab.chk_tts_enabled.setChecked(True)
        assert True in tts_emitted
        assert tab.settings.jadoo.tts_enabled is True
