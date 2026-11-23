"""Audio capture and Voice Activity Detection (VAD) module for Jadoo Voice Engine.

Captures 16 kHz mono audio using sounddevice, performs real-time adaptive
energy-based VAD to reject room/fan noise, and provides clean 16-bit PCM scaling.
Prioritizes physical hardware microphones over virtual audio cables.
"""

from __future__ import annotations

import collections
import io
import time
import wave
from typing import Callable, List, Optional, Tuple

import numpy as np
import sounddevice as sd

from utils.logger import logger

SAMPLE_RATE = 16000
CHANNELS = 1
BLOCK_SIZE = 480  # 30 ms at 16 kHz
DTYPE = np.float32

# Device categorization keywords
DISFAVORED_KEYWORDS = [
    "iriun",
    "stereo mix",
    "virtual",
    "camo",
    "droidcam",
    "mapper",
    "primary sound capture",
    "midi",
    "line (",
    "line in",
]

PREFERRED_HARDWARE_KEYWORDS = [
    "usb microphone",
    "usb audio",
    "microphone array",
    "realtek",
    "headset",
    "high definition",
    "mic",
    "internal microphone",
]


class AudioCaptureError(Exception):
    """Raised when audio capture initialization or streaming fails."""
    pass


class AudioDeviceManager:
    """Manages audio input device enumeration and intelligent hardware selection."""

    @staticmethod
    def get_input_devices() -> List[dict]:
        """Return a list of available input audio devices with friendly details."""
        devices = []
        try:
            device_list = sd.query_devices()
            for idx, dev in enumerate(device_list):
                max_in = dev.get("max_input_channels", 0)
                if max_in > 0:
                    name = dev.get("name", f"Device {idx}")
                    name_lower = name.lower()
                    is_virtual = any(k in name_lower for k in DISFAVORED_KEYWORDS)
                    is_hardware = any(k in name_lower for k in PREFERRED_HARDWARE_KEYWORDS) and not is_virtual

                    hostapi_info = sd.query_hostapis(dev.get("hostapi", 0))
                    hostapi_name = hostapi_info.get("name", "Unknown")
                    devices.append({
                        "index": idx,
                        "name": name,
                        "channels": max_in,
                        "default_samplerate": dev.get("default_samplerate", 44100.0),
                        "hostapi": hostapi_name,
                        "is_hardware": is_hardware,
                        "is_virtual": is_virtual,
                    })
        except Exception as e:
            logger.error(f"Error enumerating audio devices: {e}")
        return devices

    @staticmethod
    def find_preferred_device(preferred_names: Optional[List[str]] = None) -> Optional[int]:
        """Intelligently find the best physical hardware input device, avoiding virtual/null devices."""
        devices = AudioDeviceManager.get_input_devices()
        if not devices:
            return None

        # 1. Check user-supplied preference list
        if preferred_names:
            for pref in preferred_names:
                pref_lower = pref.lower()
                for dev in devices:
                    if pref_lower in dev["name"].lower():
                        return dev["index"]

        # 2. Prefer confirmed real hardware microphones (e.g. USB Audio, Realtek, Mic Array)
        for dev in devices:
            if dev.get("is_hardware", False):
                logger.info(f"Auto-selected physical hardware microphone: [{dev['index']}] {dev['name']}")
                return dev["index"]

        # 3. Fallback to any non-virtual device
        for dev in devices:
            if not dev.get("is_virtual", False):
                logger.info(f"Auto-selected non-virtual microphone: [{dev['index']}] {dev['name']}")
                return dev["index"]

        # 4. Fallback to system default if valid
        try:
            default_dev = sd.default.device[0]
            if default_dev >= 0:
                logger.info(f"Fallback to system default audio input: {default_dev}")
                return int(default_dev)
        except Exception:
            pass

        return devices[0]["index"] if devices else None


class HighPassFilter:
    """First-order IIR high-pass filter (100 Hz cutoff at 16 kHz) to strip AC/fan hum."""

    def __init__(self, cutoff_hz: float = 100.0, sample_rate: int = SAMPLE_RATE) -> None:
        self.cutoff_hz = float(cutoff_hz)
        self.sample_rate = int(sample_rate)
        rc = 1.0 / (2.0 * np.pi * self.cutoff_hz)
        dt = 1.0 / self.sample_rate
        self.alpha = float(rc / (rc + dt))
        self.prev_x = 0.0
        self.prev_y = 0.0

    def reset(self) -> None:
        """Reset internal filter state."""
        self.prev_x = 0.0
        self.prev_y = 0.0

    def process(self, block: np.ndarray) -> np.ndarray:
        """Filter a 1D float32 block in-place or return a filtered array, preserving state."""
        if len(block) == 0:
            return block
        out = np.empty_like(block, dtype=np.float32)
        prev_x = self.prev_x
        prev_y = self.prev_y
        alpha = self.alpha
        for i in range(len(block)):
            curr_x = float(block[i])
            curr_y = alpha * (prev_y + curr_x - prev_x)
            out[i] = curr_y
            prev_x = curr_x
            prev_y = curr_y
        self.prev_x = prev_x
        self.prev_y = prev_y
        return out


class EnergyVAD:
    """Lightweight real-time energy-based Voice Activity Detector with dynamic noise suppression."""

    def __init__(
        self,
        energy_threshold: float = 0.028,
        silence_duration_sec: float = 0.8,
        min_speech_duration_sec: float = 0.22,
        max_utterance_sec: float = 15.0,
    ) -> None:
        self.energy_threshold = float(energy_threshold)
        self.silence_duration_sec = float(silence_duration_sec)
        self.min_speech_duration_sec = float(min_speech_duration_sec)
        self.max_utterance_sec = float(max_utterance_sec)

        # Dynamic noise floor adaptation
        self.noise_floor: float = 0.010
        self.is_speech_active: bool = False
        self.speech_start_time: float = 0.0
        self.last_speech_time: float = 0.0
        self.current_energy: float = 0.0

    def reset(self) -> None:
        """Reset detection state."""
        self.is_speech_active = False
        self.speech_start_time = 0.0
        self.last_speech_time = 0.0
        self.current_energy = 0.0

    def process_block(self, audio_block: np.ndarray, timestamp: float) -> Tuple[bool, bool, float]:
        """Evaluate an audio block for voice activity.

        Returns:
            Tuple of (is_speech: bool, utterance_completed: bool, rms_energy: float)
        """
        rms = float(np.sqrt(np.mean(np.square(audio_block))))
        self.current_energy = rms

        # Adapt noise floor continuously during non-speech intervals
        if not self.is_speech_active:
            if rms > self.noise_floor:
                # Fast attack to track ambient hum
                self.noise_floor = 0.90 * self.noise_floor + 0.10 * rms
            else:
                # Slow decay
                self.noise_floor = 0.98 * self.noise_floor + 0.02 * rms

        # Speech threshold must comfortably clear the dynamic noise floor (>= 2.2x)
        # AND require clearing a hard minimum floor so ~20-25% fan/ambient noise never triggers
        effective_threshold = max(self.energy_threshold, self.noise_floor * 2.2 + 0.006)
        is_above_threshold = rms >= effective_threshold

        utterance_completed = False

        if is_above_threshold:
            if not self.is_speech_active:
                self.is_speech_active = True
                self.speech_start_time = timestamp
            self.last_speech_time = timestamp
        else:
            if self.is_speech_active:
                silence_gap = timestamp - self.last_speech_time
                active_speech_dur = self.last_speech_time - self.speech_start_time
                total_dur = timestamp - self.speech_start_time
                max_exceeded = total_dur >= self.max_utterance_sec

                if silence_gap >= self.silence_duration_sec or max_exceeded:
                    # Require minimum active speech duration (reject ultra-short clicks < 0.22s)
                    if active_speech_dur >= self.min_speech_duration_sec:
                        utterance_completed = True
                    self.is_speech_active = False

        return self.is_speech_active, utterance_completed, rms


class AudioRecorder:
    """Continuous audio capture worker handling device streams and utterance chunking."""

    def __init__(
        self,
        device_index: Optional[int] = None,
        sample_rate: int = SAMPLE_RATE,
        on_utterance_ready: Optional[Callable[[bytes, float], None]] = None,
        on_level_update: Optional[Callable[[float], None]] = None,
        energy_threshold: float = 0.028,
        silence_duration_sec: float = 0.8,
        min_speech_duration_sec: float = 0.22,
    ) -> None:
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.on_utterance_ready = on_utterance_ready
        self.on_level_update = on_level_update

        self.high_pass = HighPassFilter(cutoff_hz=100.0, sample_rate=sample_rate)
        self.vad = EnergyVAD(
            energy_threshold=energy_threshold,
            silence_duration_sec=silence_duration_sec,
            min_speech_duration_sec=min_speech_duration_sec,
        )

        self._stream: Optional[sd.InputStream] = None
        self._is_recording = False
        self._pre_buffer: collections.deque = collections.deque(maxlen=int(0.4 * sample_rate / BLOCK_SIZE))
        self._speech_buffer: list[np.ndarray] = []
        self._last_voiced_idx: int = -1

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def start(self) -> None:
        """Start audio stream."""
        if self._is_recording:
            return

        # Auto-select physical hardware microphone if device_index is None
        dev_idx = self.device_index
        if dev_idx is None:
            dev_idx = AudioDeviceManager.find_preferred_device()

        self.high_pass.reset()
        self.vad.reset()
        self._pre_buffer.clear()
        self._speech_buffer.clear()
        self._last_voiced_idx = -1

        try:
            self._stream = sd.InputStream(
                device=dev_idx,
                channels=CHANNELS,
                samplerate=self.sample_rate,
                blocksize=BLOCK_SIZE,
                dtype=DTYPE,
                callback=self._audio_callback,
            )
            self._stream.start()
            self._is_recording = True
            logger.info(f"AudioRecorder started on device index {dev_idx} ({self.sample_rate} Hz)")
        except Exception as e:
            logger.error(f"Failed to start audio stream on device {dev_idx}: {e}")
            self._is_recording = False
            raise AudioCaptureError(f"Could not open audio device {dev_idx}: {e}")

    def stop(self) -> Optional[bytes]:
        """Stop audio stream and return any buffered speech utterance as WAV bytes."""
        self._is_recording = False
        final_wav = None

        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.debug(f"Audio stream close exception: {e}")
            self._stream = None

        if len(self._speech_buffer) > 0:
            if self._last_voiced_idx >= 0:
                pad_blocks = 6
                trim_limit = min(len(self._speech_buffer), self._last_voiced_idx + 1 + pad_blocks)
                speech_blocks = self._speech_buffer[:trim_limit]
            else:
                speech_blocks = self._speech_buffer
            final_wav = self._build_wav(speech_blocks, self.sample_rate)
            self._speech_buffer.clear()
            self._last_voiced_idx = -1

        self._pre_buffer.clear()
        logger.info("AudioRecorder stopped.")
        return final_wav

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info: dict, status: sd.CallbackFlags) -> None:
        """Process incoming audio block from sounddevice."""
        if not self._is_recording:
            return

        if status:
            logger.debug(f"sounddevice stream status flag: {status}")

        raw_block = indata[:, 0].copy()
        # Apply 100 Hz high-pass filter to strip low-frequency fan/AC hum before VAD and buffer
        block = self.high_pass.process(raw_block)
        now = time.monotonic()

        is_speech, utterance_done, rms = self.vad.process_block(block, now)

        if self.on_level_update:
            self.on_level_update(rms)

        if is_speech:
            if len(self._speech_buffer) == 0 and len(self._pre_buffer) > 0:
                self._speech_buffer.extend(list(self._pre_buffer))
                self._pre_buffer.clear()
            self._speech_buffer.append(block)
            effective_thresh = max(self.vad.energy_threshold, self.vad.noise_floor * 2.2 + 0.006)
            if rms >= effective_thresh:
                self._last_voiced_idx = len(self._speech_buffer) - 1
        else:
            self._pre_buffer.append(block)

        if utterance_done and len(self._speech_buffer) > 0:
            # Trim excessive trailing silence (keep ~180ms / 6 blocks of padding after last voiced block)
            if self._last_voiced_idx >= 0:
                pad_blocks = 6
                trim_limit = min(len(self._speech_buffer), self._last_voiced_idx + 1 + pad_blocks)
                speech_blocks = self._speech_buffer[:trim_limit]
            else:
                speech_blocks = self._speech_buffer

            wav_bytes = self._build_wav(speech_blocks, self.sample_rate)
            self._speech_buffer.clear()
            self._last_voiced_idx = -1
            if self.on_utterance_ready and wav_bytes:
                self.on_utterance_ready(wav_bytes, now)

    @staticmethod
    def _build_wav(blocks: list[np.ndarray], sample_rate: int = SAMPLE_RATE) -> Optional[bytes]:
        """Convert float32 numpy blocks into normalized 16-bit 16kHz mono WAV bytes."""
        if not blocks:
            return None
        try:
            full_arr = np.concatenate(blocks, axis=0)

            # Peak normalization with safe gain clamp (target peak ~0.85) to enhance real speech
            peak = float(np.max(np.abs(full_arr)))
            if peak > 0.005:
                target_peak = 0.85
                gain = min(target_peak / peak, 15.0)
                full_arr = full_arr * gain

            int16_arr = np.clip(full_arr * 32767.0, -32768.0, 32767.0).astype(np.int16)

            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(sample_rate)
                wf.writeframes(int16_arr.tobytes())
            return buf.getvalue()
        except Exception as e:
            logger.error(f"Error generating WAV bytes: {e}")
            return None
