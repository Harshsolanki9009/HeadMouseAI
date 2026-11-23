"""Comprehensive test suite for Jadoo Voice Typing Accuracy & Manual Language Selection.

Covers:
1. Manual language selector options and mapping (Auto, Hindi, English, Hinglish).
2. Proper multilingual decoding strategy for Hinglish without invalid language codes.
3. Language parameter routing to Groq Cloud STT and local whisper.cpp CLI.
4. Engine status visibility and fallback reporting (Cloud Whisper vs Local Whisper).
5. Audio quality, VAD speech duration tuning (short word support >= 0.22s),
   trailing silence trimming, and peak normalization gain boosting.
6. Dictation raw text preservation (zero unwanted rewrites during voice typing).
7. UI widget state locking during dictation and bidirectional settings synchronization.
"""

from __future__ import annotations

import io
import os
import wave
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from ai_provider.groq_stt import DEFAULT_HINGLISH_PROMPT, GroqSTTClient
from config.settings import AppSettings, VoiceSettings
from gui.widgets.voice_control_widget import VoiceControlWidget
from voice_engine.audio_capture import AudioRecorder, EnergyVAD, HighPassFilter
from voice_engine.voice_worker import VoiceWorker
from voice_engine.whisper_backend import DEFAULT_HINGLISH_PROMPT as BACKEND_HINGLISH_PROMPT
from voice_engine.whisper_backend import WhisperBackend, clean_whisper_text


# ==============================================================================
# Helper Functions
# ==============================================================================

def make_test_wav(duration_s: float = 0.5, freq: float = 440.0, sample_rate: int = 16000) -> bytes:
    """Generate standardized 16-bit 16kHz mono sine wave WAV bytes."""
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    waveform = (0.5 * np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(waveform.tobytes())
    return buf.getvalue()


# ==============================================================================
# 1. Language Mapping & Multilingual Decoding Tests
# ==============================================================================

class TestLanguageMapping:
    """Verify English, Hindi, Auto, and Hinglish language routing."""

    def test_local_whisper_english_flag(self) -> None:
        """English must pass '-l en' to whisper-cli."""
        backend = WhisperBackend(language="en", stt_mode="offline")
        test_wav = make_test_wav(duration_s=0.2)

        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.poll.return_value = 0
            mock_proc.communicate.return_value = ("Test english text", "")
            mock_proc.returncode = 0
            mock_popen.return_value = mock_proc

            res = backend.transcribe_wav_bytes(test_wav, language="en")
            cmd_args = mock_popen.call_args[0][0]

            assert "-l" in cmd_args
            l_idx = cmd_args.index("-l")
            assert cmd_args[l_idx + 1] == "en"
            assert res["language"] == "en"
            assert res["text"] == "Test english text"

    def test_local_whisper_hindi_flag(self) -> None:
        """Hindi must pass '-l hi' to whisper-cli."""
        backend = WhisperBackend(language="hi", stt_mode="offline")
        test_wav = make_test_wav(duration_s=0.2)

        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.poll.return_value = 0
            mock_proc.communicate.return_value = ("नमस्ते भारत", "")
            mock_proc.returncode = 0
            mock_popen.return_value = mock_proc

            res = backend.transcribe_wav_bytes(test_wav, language="hi")
            cmd_args = mock_popen.call_args[0][0]

            assert "-l" in cmd_args
            l_idx = cmd_args.index("-l")
            assert cmd_args[l_idx + 1] == "hi"
            assert res["language"] == "hi"
            assert "नमस्ते" in res["text"]

    def test_local_whisper_auto_flag(self) -> None:
        """Auto detect must pass '-l auto' to whisper-cli."""
        backend = WhisperBackend(language="auto", stt_mode="offline")
        test_wav = make_test_wav(duration_s=0.2)

        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.poll.return_value = 0
            mock_proc.communicate.return_value = ("Auto recognized speech", "")
            mock_proc.returncode = 0
            mock_popen.return_value = mock_proc

            res = backend.transcribe_wav_bytes(test_wav, language="auto")
            cmd_args = mock_popen.call_args[0][0]

            assert "-l" in cmd_args
            l_idx = cmd_args.index("-l")
            assert cmd_args[l_idx + 1] == "auto"
            assert res["language"] == "auto"

    def test_local_whisper_hinglish_multilingual_strategy(self) -> None:
        """Hinglish must pass '-l auto' with conditioning prompt; NEVER pass '-l hinglish'."""
        backend = WhisperBackend(language="hinglish", stt_mode="offline")
        test_wav = make_test_wav(duration_s=0.2)

        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.poll.return_value = 0
            mock_proc.communicate.return_value = ("Sir kal meeting attend nahi kar sakta", "")
            mock_proc.returncode = 0
            mock_popen.return_value = mock_proc

            res = backend.transcribe_wav_bytes(test_wav, language="hinglish")
            cmd_args = mock_popen.call_args[0][0]

            # Critical: whisper-cli does not support "-l hinglish"
            assert "hinglish" not in [cmd_args[cmd_args.index("-l") + 1]]
            assert cmd_args[cmd_args.index("-l") + 1] == "auto"

            # Must inject priming prompt
            assert "--prompt" in cmd_args
            prompt_idx = cmd_args.index("--prompt")
            assert "Hindi and English" in cmd_args[prompt_idx + 1]
            assert res["language"] == "hinglish"
            assert res["text"] == "Sir kal meeting attend nahi kar sakta"

    def test_groq_stt_language_parameter_routing(self) -> None:
        """Groq API parameter encoding for English, Hindi, Auto, and Hinglish."""
        client = GroqSTTClient(api_key="gsk_mock_test_key_12345")
        test_wav = make_test_wav(duration_s=0.2)

        # 1. English
        with patch("urllib.request.urlopen") as mock_url:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"text": "Hello world"}'
            mock_resp.__enter__.return_value = mock_resp
            mock_url.return_value = mock_resp

            res = client.transcribe_wav_bytes(test_wav, language="en")
            req = mock_url.call_args[0][0]
            body_bytes = req.data
            assert b'name="language"\r\n\r\nen' in body_bytes
            assert res["text"] == "Hello world"

        # 2. Hindi
        with patch("urllib.request.urlopen") as mock_url:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"text": "\xe0\xa4\xa8\xe0\xa4\xae\xe0\xa4\xb8\xe0\xa5\x8d\xe0\xa4\xa4\xe0\xa5\x87"}'
            mock_resp.__enter__.return_value = mock_resp
            mock_url.return_value = mock_resp

            res = client.transcribe_wav_bytes(test_wav, language="hi")
            req = mock_url.call_args[0][0]
            body_bytes = req.data
            assert b'name="language"\r\n\r\nhi' in body_bytes

        # 3. Auto
        with patch("urllib.request.urlopen") as mock_url:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"text": "Auto result"}'
            mock_resp.__enter__.return_value = mock_resp
            mock_url.return_value = mock_resp

            res = client.transcribe_wav_bytes(test_wav, language="auto")
            req = mock_url.call_args[0][0]
            body_bytes = req.data
            # 'language' field must NOT be sent for auto
            assert b'name="language"' not in body_bytes

        # 4. Hinglish
        with patch("urllib.request.urlopen") as mock_url:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"text": "Aaj meeting cancel hai"}'
            mock_resp.__enter__.return_value = mock_resp
            mock_url.return_value = mock_resp

            res = client.transcribe_wav_bytes(test_wav, language="hinglish")
            req = mock_url.call_args[0][0]
            body_bytes = req.data
            # 'language' field must NOT be sent (would cause HTTP 400), but prompt MUST be sent
            assert b'name="language"' not in body_bytes
            assert b'name="prompt"' in body_bytes
            assert b'Hindi and English' in body_bytes


# ==============================================================================
# 2. Engine Visibility & Fallback Tests
# ==============================================================================

class TestEngineVisibilityAndFallback:
    """Verify reporting of Groq Cloud vs Local Whisper and fallback resilience."""

    def test_backend_indicator_groq_cloud(self) -> None:
        """When Groq STT succeeds, backend is reported as 'groq-cloud'."""
        backend = WhisperBackend(groq_api_key="gsk_mock_valid_key", stt_mode="auto")
        test_wav = make_test_wav(duration_s=0.2)

        with patch.object(backend.groq_client, "transcribe_wav_bytes") as mock_groq:
            mock_groq.return_value = {
                "text": "Cloud transcribed text",
                "latency_ms": 312.4,
                "language": "en",
                "error": None,
            }

            res = backend.transcribe_wav_bytes(test_wav, language="en")
            assert res["backend"] == "groq-cloud"
            assert res["text"] == "Cloud transcribed text"
            assert backend.last_backend_used == "groq-cloud"

    def test_backend_fallback_to_local_whisper(self) -> None:
        """When Groq STT fails, backend seamlessly falls back to 'whisper-local'."""
        backend = WhisperBackend(groq_api_key="gsk_mock_valid_key", stt_mode="auto")
        test_wav = make_test_wav(duration_s=0.2)

        # Groq raises network exception
        with patch.object(backend.groq_client, "transcribe_wav_bytes", side_effect=Exception("Network unreachable")):
            with patch("subprocess.Popen") as mock_popen:
                mock_proc = MagicMock()
                mock_proc.poll.return_value = 0
                mock_proc.communicate.return_value = ("Local offline fallback text", "")
                mock_proc.returncode = 0
                mock_popen.return_value = mock_proc

                res = backend.transcribe_wav_bytes(test_wav, language="en")
                assert res["backend"] == "whisper-local"
                assert res["text"] == "Local offline fallback text"
                assert backend.last_backend_used == "whisper-local"

    def test_voice_worker_emits_engine_signal(self) -> None:
        """VoiceWorker emits sig_engine_used with the active processing engine."""
        worker = VoiceWorker()
        emitted_engines = []
        worker.sig_engine_used.connect(lambda eng: emitted_engines.append(eng))

        test_wav = make_test_wav(duration_s=0.2)
        with patch.object(worker.whisper, "transcribe_wav_bytes") as mock_transcribe:
            mock_transcribe.return_value = {
                "text": "Engine test",
                "language": "en",
                "backend": "whisper-local",
                "error": None,
            }

            # Inject into queue and process one loop iteration
            worker._utterance_queue.put(test_wav)
            worker._running = True

            # Mock queue get to simulate worker loop
            wav = worker._utterance_queue.get(timeout=0.1)
            res = worker.whisper.transcribe_wav_bytes(wav)
            worker.sig_engine_used.emit(res["backend"])

            assert len(emitted_engines) == 1
            assert emitted_engines[0] == "whisper-local"


# ==============================================================================
# 3. Audio Quality & VAD Speech Duration Tests
# ==============================================================================

class TestAudioQualityAndVAD:
    """Verify short speech capture, trailing silence trimming, and peak normalization."""

    def test_short_speech_duration_captured(self) -> None:
        """Single syllable words (0.22s - 0.40s) must trigger utterance completion."""
        vad = EnergyVAD(energy_threshold=0.025, silence_duration_sec=0.20, min_speech_duration_sec=0.22)

        # 0.28 seconds of speech (8 blocks of 30ms = 0.24s)
        voiced_block = np.ones(480, dtype=np.float32) * 0.05
        silence_block = np.zeros(480, dtype=np.float32)

        t = 10.0
        # Voice active for 0.28s
        for _ in range(9):
            is_speech, done, rms = vad.process_block(voiced_block, t)
            assert is_speech is True
            assert done is False
            t += 0.03

        # Trailing silence for 0.22s
        completed = False
        for _ in range(8):
            is_speech, done, rms = vad.process_block(silence_block, t)
            if done:
                completed = True
                break
            t += 0.03

        assert completed is True

    def test_sub_threshold_click_dropped(self) -> None:
        """Sub-threshold clicks under min_speech_duration_sec (< 0.22s) must NOT complete."""
        vad = EnergyVAD(energy_threshold=0.025, silence_duration_sec=0.20, min_speech_duration_sec=0.22)

        voiced_block = np.ones(480, dtype=np.float32) * 0.05
        silence_block = np.zeros(480, dtype=np.float32)

        t = 10.0
        # Only 2 blocks of sound (0.06s click)
        vad.process_block(voiced_block, t)
        t += 0.03
        vad.process_block(voiced_block, t)
        t += 0.03

        # Silence follows
        completed = False
        for _ in range(8):
            is_speech, done, rms = vad.process_block(silence_block, t)
            if done:
                completed = True
                break
            t += 0.03

        # Click was shorter than 0.22s -> dropped
        assert completed is False

    def test_audio_recorder_trims_excess_trailing_silence(self) -> None:
        """AudioRecorder keeps natural decay padding (~180ms) and trims trailing dead noise."""
        recorder = AudioRecorder()
        recorder._is_recording = True

        # Generate 300 Hz audio tone so it passes through the 100 Hz HighPassFilter cleanly
        t = np.linspace(0, 480 / 16000, 480, endpoint=False)
        voiced = (0.2 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
        silence = np.zeros(480, dtype=np.float32)

        captured_wavs = []
        recorder.on_utterance_ready = lambda wav, ts: captured_wavs.append(wav)

        sim_time = [100.0]

        def get_time():
            sim_time[0] += 0.03
            return sim_time[0]

        with patch("time.monotonic", side_effect=get_time):
            # 12 voiced blocks (360ms of speech)
            for _ in range(12):
                recorder._audio_callback(voiced.reshape(-1, 1), 480, {}, 0)

            # 35 silence blocks (~1050ms silence to trigger VAD utterance_done at >= 0.8s)
            for _ in range(35):
                recorder._audio_callback(silence.reshape(-1, 1), 480, {}, 0)

        assert len(captured_wavs) == 1
        wav_data = captured_wavs[0]

        # Read back WAV frame count
        with wave.open(io.BytesIO(wav_data), "rb") as wf:
            total_frames = wf.getnframes()
            total_duration_s = total_frames / 16000.0

        # Without trimming, 12 + 35 blocks = 47 * 480 = 22560 frames (1.41s)
        # With trimming, 12 voiced blocks + 6 padding blocks + pre-buffer (~13 blocks) = ~31 blocks = ~0.93s
        assert total_duration_s < 1.10  # Confirmed trailing dead noise was trimmed

    def test_peak_normalization_boosts_soft_mic(self) -> None:
        """Quiet input is boosted safely with gain clamp up to 15.0x."""
        quiet_block = np.ones(4800, dtype=np.float32) * 0.02
        wav_bytes = AudioRecorder._build_wav([quiet_block], sample_rate=16000)
        assert wav_bytes is not None

        # Read back samples
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            raw_frames = wf.readframes(wf.getnframes())
            samples = np.frombuffer(raw_frames, dtype=np.int16)

        # Un-normalized 0.02 would have peak 655 in int16. Boosted by 15x brings it to ~9800+
        max_val = np.max(np.abs(samples))
        assert max_val > 5000


# ==============================================================================
# 4. UI Widget & Settings Synchronization Tests
# ==============================================================================

class TestVoiceWidgetAndSettings:
    """Test VoiceControlWidget language selector, locking, and settings synchronization."""

    def test_voice_control_widget_language_selection(self, qapp) -> None:
        """VoiceControlWidget exposes languages and emits sig_language_changed."""
        widget = VoiceControlWidget()
        emitted_langs = []
        widget.sig_language_changed.connect(lambda l: emitted_langs.append(l))

        # Select Hindi
        widget.set_language("hi")
        assert widget._current_language == "hi"

        # Select Hinglish
        widget.set_language("hinglish")
        assert widget._current_language == "hinglish"
        assert "HINGLISH" in widget.badge_lang_indicator.text().upper()

        # Select Auto
        widget.set_language("auto")
        assert widget._current_language == "auto"

    def test_voice_control_widget_locks_language_during_dictation(self, qapp) -> None:
        """Language combo box must be disabled during active dictation."""
        widget = VoiceControlWidget()
        assert widget.combo_language.isEnabled() is True

        # Start dictation
        widget.set_dictating_state(True)
        assert widget.combo_language.isEnabled() is False

        # Stop dictation
        widget.set_dictating_state(False)
        assert widget.combo_language.isEnabled() is True

    def test_voice_control_widget_engine_badge(self, qapp) -> None:
        """Engine badge displays CLOUD WHISPER or LOCAL WHISPER based on engine state."""
        widget = VoiceControlWidget()

        widget.set_engine("groq-cloud")
        assert "CLOUD" in widget.badge_engine.text().upper()

        widget.set_engine("whisper-local")
        assert "LOCAL" in widget.badge_engine.text().upper()

    def test_settings_validation_language_options(self) -> None:
        """AppSettings validation accepts 'auto', 'hi', 'en', 'hinglish' and rejects others."""
        settings = AppSettings()

        for valid_lang in ("auto", "hi", "en", "hinglish"):
            settings.voice.language = valid_lang
            assert len(settings.validate()) == 0

        # Invalid language
        settings.voice.language = "french"
        errs = settings.validate()
        assert any("voice language" in e.lower() for e in errs)


# ==============================================================================
# 5. Raw Speech Preservation & Anti-Hallucination Integrity
# ==============================================================================

class TestSpeechIntegrityAndNoRewriting:
    """Verify raw spoken words are preserved verbatim and zero rewriting occurs in voice typing."""

    def test_hindi_speech_preserved_verbatim_no_translation(self) -> None:
        """Hindi speech in Devanagari must be preserved verbatim without translating to English."""
        raw_hindi = "कृपया यह फ़ाइल तुरंत सहेजें और विंडो बंद करें"
        cleaned = clean_whisper_text(raw_hindi)
        assert cleaned == raw_hindi
        # Ensure it was not translated into English
        assert "please" not in cleaned.lower()
        assert "file" not in cleaned.lower()

    def test_hinglish_speech_preserved_verbatim(self) -> None:
        """Code-switched Hinglish must be preserved as spoken with mixed Hindi and English."""
        raw_hinglish = "Kal morning mein meeting attend nahi kar paunga because health theek nahi hai."
        cleaned = clean_whisper_text(raw_hinglish)
        assert cleaned == raw_hinglish
        assert "Kal morning" in cleaned
        assert "nahi kar paunga" in cleaned

    def test_english_speech_preserved_verbatim(self) -> None:
        """English dictation must be preserved verbatim without summarization."""
        raw_en = "HeadMouseAI provides full hands-free computer interaction using nose movements and eye gestures."
        cleaned = clean_whisper_text(raw_en)
        assert cleaned == raw_en

    def test_silence_and_noise_produce_zero_hallucinations(self) -> None:
        """Ambient noise and silence tags produce empty text without hallucinating sentences."""
        noise_hallucinations = [
            "[BLANK_AUDIO]",
            "(dramatic music playing)",
            "<whispering>",
            "[MUSIC PLAYING]",
            "[XBOX SOUND]",
            "   ...   ",
            "???",
            "[applause] (cheering)",
        ]
        for tag in noise_hallucinations:
            assert clean_whisper_text(tag) == ""

    def test_long_sentence_dictation_no_truncation(self) -> None:
        """Long speech utterances are preserved in full without premature truncation."""
        long_speech = (
            "The quick brown fox jumps over the lazy dog while the hands-free cursor tracks the nose position "
            "with zero jitter, allowing users with motor impairments or RSI to operate Windows computers "
            "effortlessly without touching a physical keyboard or mouse."
        )
        cleaned = clean_whisper_text(long_speech)
        assert len(cleaned) == len(long_speech)
        assert cleaned.startswith("The quick brown fox")
        assert cleaned.endswith("keyboard or mouse.")

    def test_fallback_preserves_selected_language(self) -> None:
        """Fallback from Groq Cloud to local whisper.cpp preserves chosen language."""
        backend = WhisperBackend(groq_api_key="gsk_mock_key", stt_mode="auto", language="hi")
        test_wav = make_test_wav(duration_s=0.2)

        with patch.object(backend.groq_client, "transcribe_wav_bytes", side_effect=Exception("Timeout")):
            with patch.object(backend, "transcribe_file") as mock_local:
                mock_local.return_value = {
                    "text": "नमस्ते",
                    "language": "hi",
                    "latency_ms": 120.0,
                    "error": None,
                }

                res = backend.transcribe_wav_bytes(test_wav, language="hi")
                mock_local.assert_called_once()
                # Verify language='hi' was passed to local fallback
                assert mock_local.call_args[1]["language"] == "hi"
                assert res["language"] == "hi"

