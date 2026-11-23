"""Comprehensive automated test suite for Jadoo Voice Engine subsystem.

Tests coverage:
1. Audio capture and device availability
2. Microphone disconnection / error handling
3. Empty / corrupted audio data
4. EnergyVAD speech segmentation and silence detection
5. WhisperBackend asset verification and execution
6. Multilingual transcription (English, Hindi Devanagari, Hinglish)
7. Voice command allowlist matching and phrase isolation
8. Dictation mode vs Command mode strict separation
9. Unicode text injection with clipboard preservation & restoration
10. Thread safety, lifecycle, and emergency stop integration
"""

from __future__ import annotations

import io
import os
import time
import wave
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import pyperclip

from config.settings import AppSettings, VoiceSettings
from voice_engine.audio_capture import AudioCaptureError, AudioDeviceManager, AudioRecorder, EnergyVAD, HighPassFilter
from voice_engine.text_injector import TextInjector
from voice_engine.voice_commands import VoiceCommand, VoiceCommandMatcher, normalize_text
from voice_engine.voice_worker import VoiceWorker
from voice_engine.whisper_backend import WhisperBackend, WhisperBackendError, clean_whisper_text


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


def make_silent_wav(duration_s: float = 0.5, sample_rate: int = 16000) -> bytes:
    """Generate 16-bit 16kHz mono silent WAV bytes."""
    waveform = np.zeros(int(sample_rate * duration_s), dtype=np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(waveform.tobytes())
    return buf.getvalue()


# ==============================================================================
# 1. Audio Device & Capture Tests
# ==============================================================================

class TestAudioCapture:
    """Test sounddevice enumeration, stream handling, and error resilience."""

    def test_audio_device_manager_enumeration(self) -> None:
        devices = AudioDeviceManager.get_input_devices()
        assert isinstance(devices, list)
        for dev in devices:
            assert "index" in dev
            assert "name" in dev
            assert "channels" in dev
            assert dev["channels"] > 0

    def test_audio_recorder_invalid_device(self) -> None:
        """Invalid device index should raise AudioCaptureError on start."""
        recorder = AudioRecorder(device_index=99999)
        with pytest.raises(AudioCaptureError):
            recorder.start()
        assert not recorder.is_recording

    def test_energy_vad_speech_and_silence_detection(self) -> None:
        """EnergyVAD correctly detects active speech and trailing silence transitions."""
        vad = EnergyVAD(energy_threshold=0.015, silence_duration_sec=0.2, min_speech_duration_sec=0.1)
        assert not vad.is_speech_active

        # Silent block
        silence_block = np.zeros(512, dtype=np.float32)
        now = 100.0
        is_speech, done, rms = vad.process_block(silence_block, now)
        assert not is_speech
        assert not done
        assert rms == 0.0

        # Speech blocks (0.3s)
        t = np.linspace(0, 0.032, 512, endpoint=False)
        speech_block = (0.2 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
        for _ in range(10):
            now += 0.032
            is_speech, done, rms = vad.process_block(speech_block, now)
            assert is_speech
            assert not done
            assert rms > 0.05

        # Continued silence to trigger utterance completion
        for _ in range(10):
            now += 0.032
            is_speech, done, rms = vad.process_block(silence_block, now)
            if done:
                break
        assert done
        assert not vad.is_speech_active

    def test_room_noise_does_not_trigger_vad(self) -> None:
        """Steady background room/fan noise (~20-25% mic level, RMS ~ 0.022) must NOT trigger VAD."""
        vad = EnergyVAD(energy_threshold=0.035, silence_duration_sec=0.5, min_speech_duration_sec=0.45)
        now = 10.0
        # Simulated fan noise blocks with RMS ~ 0.022
        noise_block = (np.random.uniform(-0.038, 0.038, 480)).astype(np.float32)
        for _ in range(30):
            now += 0.030
            is_speech, done, rms = vad.process_block(noise_block, now)
            assert not is_speech, f"Room noise erroneously triggered speech! (RMS={rms:.4f})"
            assert not done
        assert not vad.is_speech_active

    def test_high_pass_filter_and_raised_vad_threshold_blocks_ambient_noise(self) -> None:
        """100 Hz high-pass filter attenuates AC hum, and combined with raised threshold blocks steady 22% noise."""
        hpf = HighPassFilter(cutoff_hz=100.0, sample_rate=16000)
        vad = EnergyVAD(energy_threshold=0.035, silence_duration_sec=0.5, min_speech_duration_sec=0.45)

        # 1. Verify 50 Hz AC hum attenuation vs 1000 Hz speech pass-through
        t = np.linspace(0, 0.1, 1600, endpoint=False, dtype=np.float32)
        sig_50hz = (0.2 * np.sin(2 * np.pi * 50.0 * t)).astype(np.float32)
        sig_1000hz = (0.2 * np.sin(2 * np.pi * 1000.0 * t)).astype(np.float32)

        filtered_50 = hpf.process(sig_50hz)
        hpf.reset()
        filtered_1000 = hpf.process(sig_1000hz)

        # 50 Hz should have significant attenuation (> 45% amplitude reduction after settling)
        gain_50 = float(np.std(filtered_50[400:])) / float(np.std(sig_50hz[400:]))
        gain_1000 = float(np.std(filtered_1000[400:])) / float(np.std(sig_1000hz[400:]))

        assert gain_50 < 0.55, f"50 Hz hum not sufficiently attenuated: gain={gain_50:.3f}"
        assert gain_1000 > 0.90, f"1000 Hz speech signal attenuated too much: gain={gain_1000:.3f}"

        # 2. Combined pipeline: 50 Hz rumble + 22% random noise
        hpf.reset()
        now = 20.0
        for _ in range(30):
            now += 0.030
            t_block = np.linspace(0, 0.030, 480, endpoint=False, dtype=np.float32)
            rumble_block = (0.05 * np.sin(2 * np.pi * 50.0 * t_block) + np.random.uniform(-0.035, 0.035, 480)).astype(np.float32)
            filtered_block = hpf.process(rumble_block)
            is_speech, done, rms = vad.process_block(filtered_block, now)
            assert not is_speech, f"Ambient rumble erroneously triggered speech: RMS={rms:.4f}"
            assert not done
        assert not vad.is_speech_active

    def test_short_noise_burst_rejected(self) -> None:
        """Transient noise bursts < 0.45s (clicks, breath, desk bump) are discarded without triggering utterance."""
        vad = EnergyVAD(energy_threshold=0.028, silence_duration_sec=0.3, min_speech_duration_sec=0.45)
        now = 50.0
        silence_block = np.zeros(480, dtype=np.float32)
        loud_burst = (0.2 * np.ones(480, dtype=np.float32))

        # Loud burst for only 0.2s (6 blocks * 0.03s = 0.18s < 0.45s)
        for _ in range(6):
            now += 0.030
            vad.process_block(loud_burst, now)

        # Followed by trailing silence
        done = False
        for _ in range(15):
            now += 0.030
            _, is_done, _ = vad.process_block(silence_block, now)
            if is_done:
                done = True
                break

        # Utterance must NOT be completed because duration was under 0.45s
        assert not done
        assert not vad.is_speech_active

    def test_hardware_mic_prioritization(self) -> None:
        """Physical hardware microphone must be auto-selected over virtual or mapper inputs."""
        mock_devices = [
            {"name": "Microsoft Sound Mapper - Input", "max_input_channels": 2, "hostapi": 0},
            {"name": "Microphone (Iriun Webcam)", "max_input_channels": 2, "hostapi": 0},
            {"name": "Microphone (USB Audio Device)", "max_input_channels": 2, "hostapi": 0},
            {"name": "Stereo Mix (Realtek Audio)", "max_input_channels": 2, "hostapi": 0},
        ]
        with patch("sounddevice.query_devices", return_value=mock_devices), \
             patch("sounddevice.query_hostapis", return_value={"name": "MME"}):
            preferred = AudioDeviceManager.find_preferred_device()
            # Index 2 is 'Microphone (USB Audio Device)'
            assert preferred == 2

    def test_audio_recorder_build_wav(self) -> None:
        """_build_wav converts numpy blocks into valid 16kHz mono WAV bytes with peak normalization."""
        # Low volume block (peak 0.10)
        block = (0.10 * np.ones(512, dtype=np.float32))
        wav_bytes = AudioRecorder._build_wav([block, block], sample_rate=16000)
        assert wav_bytes is not None
        assert len(wav_bytes) > 44  # Header is 44 bytes

        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000
            assert wf.getnframes() == 1024
            # Verify amplification normalized the audio
            raw_data = np.frombuffer(wf.readframes(1024), dtype=np.int16)
            assert np.max(np.abs(raw_data)) > 5000  # Successfully amplified above quiet floor


# ==============================================================================
# 2. Whisper Backend & Transcription Tests
# ==============================================================================

class TestWhisperBackend:
    """Test WhisperBackend wrapper and whisper.cpp execution."""

    def test_whisper_backend_asset_presence(self) -> None:
        backend = WhisperBackend(model_name="ggml-tiny.bin", threads=2)
        assert backend.is_available
        assert os.path.isfile(backend.executable_path)
        assert os.path.isfile(backend.model_path)
        assert backend.threads <= 2

    def test_whisper_thread_capping(self) -> None:
        """Strict constraint: threads must never exceed 2."""
        b1 = WhisperBackend(threads=8)
        assert b1.threads == 2

        b2 = WhisperBackend(threads=0)
        assert b2.threads == 1

    def test_whisper_model_switch(self) -> None:
        backend = WhisperBackend(model_name="ggml-tiny.bin")
        assert backend.model_name == "ggml-tiny.bin"

        # Switch to base
        if os.path.isfile(os.path.join(backend.models_dir, "ggml-base.bin")):
            ok = backend.set_model("ggml-base.bin")
            assert ok
            assert backend.model_name == "ggml-base.bin"

        # Switch to nonexistent model fails safely
        ok = backend.set_model("ggml-nonexistent.bin")
        assert not ok
        assert backend.model_name == "ggml-base.bin"

    def test_whisper_empty_audio_handling(self) -> None:
        backend = WhisperBackend(model_name="ggml-tiny.bin")
        res = backend.transcribe_wav_bytes(b"")
        assert res["text"] == ""
        assert res["error"] == "Empty audio data"

        res_short = backend.transcribe_wav_bytes(b"RIFF1234")
        assert res_short["text"] == ""
        assert res_short["error"] == "Empty audio data"

    def test_whisper_transcribe_wav_bytes(self) -> None:
        """Transcribe generated 16kHz mono WAV bytes locally."""
        backend = WhisperBackend(model_name="ggml-tiny.bin", threads=2, language="en", stt_mode="offline")
        test_wav = make_test_wav(duration_s=1.0)
        res = backend.transcribe_wav_bytes(test_wav)
        assert res["error"] is None
        assert res["latency_ms"] > 0
        assert res["ram_mb"] > 0

    def test_clean_whisper_hallucination_tags(self) -> None:
        """Verify non-speech bracketed and parenthesized tags are stripped cleanly."""
        assert clean_whisper_text("[BLANK_AUDIO]") == ""
        assert clean_whisper_text("(dramatic music)") == ""
        assert clean_whisper_text("[MUSIC PLAYING]") == ""
        assert clean_whisper_text("[XBOX SOUND]") == ""
        assert clean_whisper_text("(eerie music)") == ""
        assert clean_whisper_text("[BLANK_AUDIO]   \n") == ""
        assert clean_whisper_text("(applause)") == ""
        assert clean_whisper_text("<cough>") == ""
        assert clean_whisper_text("[MUSIC] Hello Jadoo (bell dings)") == "Hello Jadoo"
        assert clean_whisper_text("(dramatic music) नमस्ते [cough]") == "नमस्ते"
        assert clean_whisper_text("   ... ???   ") == ""

    def test_repeated_word_hallucination_rejected(self) -> None:
        """Outputs with words repeated >= 3 times consecutively (e.g. 'Vali, Vali, Vali...') must be rejected."""
        # Single-word loops (3 or more)
        assert clean_whisper_text("Vali, Vali, Vali, Vali...") == ""
        assert clean_whisper_text("the the the") == ""
        assert clean_whisper_text("No, no, no!") == ""
        assert clean_whisper_text("stop stop stop stop") == ""

        # 2-word phrase loop (3 or more)
        assert clean_whisper_text("and then and then and then") == ""

        # Normal speech with non-repeating or 2 occurrences preserved
        assert clean_whisper_text("Hello hello world") == "Hello hello world"
        assert clean_whisper_text("Vali and Rama are walking together.") == "Vali and Rama are walking together."
        assert clean_whisper_text("नमस्ते, यह हेडमाउस परीक्षण है।") == "नमस्ते, यह हेडमाउस परीक्षण है।"

    def test_whisper_cli_anti_hallucination_flags(self) -> None:
        """Verify whisper-cli is invoked with strict anti-hallucination flags including --max-context 0."""
        backend = WhisperBackend(model_name="ggml-base.bin", threads=2, language="en", stt_mode="offline")
        test_wav = make_test_wav(duration_s=0.2)

        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.poll.return_value = 0
            mock_proc.communicate.return_value = ("Hello world", "")
            mock_proc.returncode = 0
            mock_popen.return_value = mock_proc

            backend.transcribe_wav_bytes(test_wav)

            mock_popen.assert_called_once()
            cmd_args = mock_popen.call_args[0][0]

            assert "--max-context" in cmd_args
            mc_idx = cmd_args.index("--max-context")
            assert cmd_args[mc_idx + 1] == "0"

            assert "--no-speech-thold" in cmd_args
            nth_idx = cmd_args.index("--no-speech-thold")
            assert cmd_args[nth_idx + 1] == "0.65"

            assert "--entropy-thold" in cmd_args
            et_idx = cmd_args.index("--entropy-thold")
            assert cmd_args[et_idx + 1] == "2.4"

            assert "--logprob-thold" in cmd_args
            lpt_idx = cmd_args.index("--logprob-thold")
            assert cmd_args[lpt_idx + 1] == "-1.0"

            assert "--suppress-nst" in cmd_args

    def test_hallucination_does_not_trigger_command_or_transcription(self) -> None:
        """Hallucinated bracket text filtered to empty string must never trigger commands or dictation."""
        matcher = VoiceCommandMatcher()
        cleaned = clean_whisper_text("[BLANK_AUDIO]")
        assert cleaned == ""
        cmd, score = matcher.match(cleaned)
        assert cmd is None
        assert score == 0.0

        cleaned_music = clean_whisper_text("(dramatic music)")
        assert cleaned_music == ""
        cmd_m, score_m = matcher.match(cleaned_music)
        assert cmd_m is None


# ==============================================================================
# 3. Voice Command Allowlist Tests
# ==============================================================================

class TestVoiceCommands:
    """Test voice command normalization, strict allowlist, and mode separation."""

    @pytest.fixture
    def matcher(self) -> VoiceCommandMatcher:
        return VoiceCommandMatcher()

    def test_normalize_text(self) -> None:
        assert normalize_text("  Recenter!  ") == "recenter"
        assert normalize_text("Emergency, Stop???") == "emergency stop"
        assert normalize_text("नमस्ते।") == "नमस्ते"

    def test_command_matching_english(self, matcher: VoiceCommandMatcher) -> None:
        assert matcher.match("recenter")[0] == VoiceCommand.RECENTER
        assert matcher.match("center cursor")[0] == VoiceCommand.RECENTER
        assert matcher.match("emergency stop")[0] == VoiceCommand.EMERGENCY_STOP
        assert matcher.match("stop")[0] == VoiceCommand.STOP
        assert matcher.match("start dictation")[0] == VoiceCommand.START_DICTATION
        assert matcher.match("stop dictation")[0] == VoiceCommand.STOP_DICTATION

    def test_command_matching_hindi(self, matcher: VoiceCommandMatcher) -> None:
        assert matcher.match("रीसेंटर")[0] == VoiceCommand.RECENTER
        assert matcher.match("इमरजेंसी स्टॉप")[0] == VoiceCommand.EMERGENCY_STOP
        assert matcher.match("रुकिए")[0] == VoiceCommand.STOP
        assert matcher.match("डिक्टेशन शुरू")[0] == VoiceCommand.START_DICTATION
        assert matcher.match("डिक्टेशन बंद")[0] == VoiceCommand.STOP_DICTATION

    def test_strict_allowlist_ignores_random_speech(self, matcher: VoiceCommandMatcher) -> None:
        """Random conversational speech must never trigger commands."""
        assert matcher.match("hello how are you")[0] is None
        assert matcher.match("the mouse is moving smoothly")[0] is None
        assert matcher.match("i like using this computer")[0] is None
        assert matcher.match("please don't click anything")[0] is None

    def test_dictation_mode_separation(self, matcher: VoiceCommandMatcher) -> None:
        """While is_dictating=True, normal commands are blocked to protect user typing."""
        # Words that would trigger commands in normal mode must NOT trigger in dictation mode
        assert matcher.match("recenter", is_dictating=True)[0] is None
        assert matcher.match("stop", is_dictating=True)[0] is None
        assert matcher.match("emergency stop", is_dictating=True)[0] is None
        assert matcher.match("center", is_dictating=True)[0] is None

        # ONLY stop_dictation is recognized to exit dictation mode
        assert matcher.match("stop dictation", is_dictating=True)[0] == VoiceCommand.STOP_DICTATION
        assert matcher.match("डिक्टेशन बंद", is_dictating=True)[0] == VoiceCommand.STOP_DICTATION


# ==============================================================================
# 4. Text Injector & Clipboard Preservation Tests
# ==============================================================================

class TestTextInjector:
    """Test Unicode text insertion and original clipboard preservation."""

    def test_unicode_clipboard_preservation(self) -> None:
        original = "Original User Clipboard Data 12345"
        pyperclip.copy(original)
        assert pyperclip.paste() == original

        injector = TextInjector(restore_clipboard=True, paste_delay_s=0.03)

        # Inject Unicode text with mocked pyautogui.hotkey so it doesn't trigger physical OS paste
        with patch("pyautogui.hotkey") as mock_hotkey:
            dictated_unicode = "नमस्ते Jadoo! यह एक टेस्ट है।"
            ok = injector.inject_text(dictated_unicode)
            assert ok
            mock_hotkey.assert_called_once_with("ctrl", "v")

        # Verify original clipboard was restored
        time.sleep(0.06)
        restored = pyperclip.paste()
        assert restored == original

    def test_empty_text_injection_ignored(self) -> None:
        injector = TextInjector()
        with patch("pyautogui.hotkey") as mock_hotkey:
            assert not injector.inject_text("")
            mock_hotkey.assert_not_called()

    def test_text_injector_only_external_prevention(self) -> None:
        """When only_external=True and HeadMouseAI is active window, Ctrl+V paste is skipped."""
        injector = TextInjector()

        with patch("pyautogui.hotkey") as mock_hotkey, \
             patch.object(injector, "is_app_foreground", return_value=True):
            # HeadMouseAI has focus: auto-paste must NOT fire synthetic Ctrl+V
            res = injector.inject_text("Hello Notepad", only_external=True)
            assert not res
            mock_hotkey.assert_not_called()

        with patch("pyautogui.hotkey") as mock_hotkey, \
             patch.object(injector, "is_app_foreground", return_value=False):
            # External application (Notepad/Chrome/Word) has focus: auto-paste fires Ctrl+V
            res = injector.inject_text("Hello Notepad", only_external=True)
            assert res
            mock_hotkey.assert_called_once_with("ctrl", "v")


# ==============================================================================
# 5. VoiceWorker Thread Lifecycle & Settings Tests
# ==============================================================================

class TestVoiceWorker:
    """Test VoiceWorker thread instantiation, states, and signal connections."""

    @pytest.fixture
    def app(self) -> None:
        from PySide6.QtWidgets import QApplication
        return QApplication.instance() or QApplication([])

    def test_voice_settings_initialization(self) -> None:
        settings = AppSettings()
        assert isinstance(settings.voice, VoiceSettings)
        assert settings.voice.enabled is True
        assert settings.voice.threads == 2
        assert settings.voice.model_name == "ggml-base.bin"
        assert settings.voice.language == "en"
        assert settings.voice.auto_paste is True
        assert settings.voice.energy_threshold == 0.035
        assert len(settings.validate()) == 0

    def test_voice_worker_state_transitions(self, app) -> None:
        worker = VoiceWorker()
        assert not worker.is_dictating

        worker.set_dictating(True)
        assert worker.is_dictating

        worker.set_dictating(False)
        assert not worker.is_dictating

        worker.toggle_dictation()
        assert worker.is_dictating

        worker.toggle_dictation()
        assert not worker.is_dictating

    def test_voice_worker_lifecycle(self, app) -> None:
        worker = VoiceWorker()
        # Mock recorder start to avoid hardware dependencies on headless/CI
        with patch.object(worker.recorder, "start", return_value=True), \
             patch.object(worker.recorder, "stop", return_value=None):
            worker.start()
            time.sleep(0.05)
            assert worker.isRunning()
            worker.stop()
            assert not worker.isRunning()
