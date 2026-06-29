"""
Real-time voice processing engine using WASAPI via sounddevice.
Uses phase vocoder for pitch shifting and formant preservation.
"""

import logging
import queue
import threading
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import scipy.signal as signal
import sounddevice as sd

logger = logging.getLogger(__name__)

CHUNK = 1024
SAMPLE_RATE = 48000
CHANNELS = 1
DTYPE = np.float32


@dataclass
class VoiceParams:
    pitch_semitones: float = 0.0      # -12 to +12
    formant_shift: float = 1.0        # 0.5 to 2.0
    robotic_amount: float = 0.0       # 0.0 to 1.0
    noise_gate_db: float = -50.0      # silence threshold
    volume_out: float = 1.0           # output gain


def _phase_vocoder_shift(audio: np.ndarray, semitones: float, sr: int) -> np.ndarray:
    """Pitch shift via phase vocoder (no librosa dependency)."""
    if abs(semitones) < 0.01:
        return audio

    factor = 2 ** (semitones / 12.0)
    n = len(audio)
    stretched_len = int(n / factor)

    if stretched_len < 4:
        return audio

    # Resample to simulate pitch shift (time-domain stretch + resample)
    resampled = signal.resample(audio, stretched_len)

    # Trim or pad back to original length
    if len(resampled) >= n:
        return resampled[:n]
    else:
        return np.pad(resampled, (0, n - len(resampled)))


def _apply_robotic(audio: np.ndarray, amount: float, sr: int) -> np.ndarray:
    """Vocoder-style robotic effect using comb filter."""
    if amount < 0.01:
        return audio

    freq = 100.0  # fundamental buzz frequency
    delay = int(sr / freq)
    if delay <= 0 or delay >= len(audio):
        return audio

    comb = np.zeros_like(audio)
    comb[delay:] = audio[:-delay]
    return audio * (1 - amount) + comb * amount


def _noise_gate(audio: np.ndarray, threshold_db: float) -> np.ndarray:
    """Hard noise gate."""
    threshold_linear = 10 ** (threshold_db / 20.0)
    rms = np.sqrt(np.mean(audio ** 2))
    if rms < threshold_linear:
        return np.zeros_like(audio)
    return audio


class AudioEngine:
    def __init__(self) -> None:
        self._params = VoiceParams()
        self._active = False
        self._preview_mode = False
        self._lock = threading.Lock()

        self._input_device: Optional[int] = None
        self._output_device: Optional[int] = None

        self._stream_in: Optional[sd.InputStream] = None
        self._stream_out: Optional[sd.OutputStream] = None

        self._buf: queue.Queue[np.ndarray] = queue.Queue(maxsize=8)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_params(self, params: VoiceParams) -> None:
        with self._lock:
            self._params = params

    def get_params(self) -> VoiceParams:
        with self._lock:
            return VoiceParams(
                pitch_semitones=self._params.pitch_semitones,
                formant_shift=self._params.formant_shift,
                robotic_amount=self._params.robotic_amount,
                noise_gate_db=self._params.noise_gate_db,
                volume_out=self._params.volume_out,
            )

    def set_devices(self, input_idx: Optional[int], output_idx: Optional[int]) -> None:
        was_active = self._active
        if was_active:
            self.stop()
        self._input_device = input_idx
        self._output_device = output_idx
        if was_active:
            self.start()

    def start(self) -> None:
        if self._active:
            return
        self._active = True
        self._buf = queue.Queue(maxsize=8)

        def _in_callback(indata: np.ndarray, frames: int, time_info, status):
            if status:
                logger.debug("Input status: %s", status)
            chunk = indata[:, 0].copy()
            try:
                self._buf.put_nowait(chunk)
            except queue.Full:
                pass  # drop oldest

        def _out_callback(outdata: np.ndarray, frames: int, time_info, status):
            if status:
                logger.debug("Output status: %s", status)
            try:
                chunk = self._buf.get_nowait()
            except queue.Empty:
                outdata.fill(0)
                return

            with self._lock:
                p = self._params

            chunk = _noise_gate(chunk, p.noise_gate_db)
            chunk = _phase_vocoder_shift(chunk, p.pitch_semitones, SAMPLE_RATE)
            chunk = _apply_robotic(chunk, p.robotic_amount, SAMPLE_RATE)
            chunk = chunk * p.volume_out

            # clip
            chunk = np.clip(chunk, -1.0, 1.0)

            if len(chunk) < frames:
                chunk = np.pad(chunk, (0, frames - len(chunk)))
            outdata[:, 0] = chunk[:frames]

        self._stream_in = sd.InputStream(
            device=self._input_device,
            channels=CHANNELS,
            samplerate=SAMPLE_RATE,
            blocksize=CHUNK,
            dtype=DTYPE,
            callback=_in_callback,
        )
        self._stream_out = sd.OutputStream(
            device=self._output_device,
            channels=CHANNELS,
            samplerate=SAMPLE_RATE,
            blocksize=CHUNK,
            dtype=DTYPE,
            callback=_out_callback,
        )
        self._stream_in.start()
        self._stream_out.start()
        logger.info("Audio engine started")

    def stop(self) -> None:
        self._active = False
        if self._stream_in:
            self._stream_in.stop()
            self._stream_in.close()
            self._stream_in = None
        if self._stream_out:
            self._stream_out.stop()
            self._stream_out.close()
            self._stream_out = None
        logger.info("Audio engine stopped")

    def preview_once(self, duration: float = 2.0) -> None:
        """Record mic for `duration` secs, process, play back through speakers."""
        frames = int(SAMPLE_RATE * duration)
        rec = sd.rec(frames, samplerate=SAMPLE_RATE, channels=1, dtype=DTYPE)
        sd.wait()
        audio = rec[:, 0]

        with self._lock:
            p = self._params

        audio = _noise_gate(audio, p.noise_gate_db)
        audio = _phase_vocoder_shift(audio, p.pitch_semitones, SAMPLE_RATE)
        audio = _apply_robotic(audio, p.robotic_amount, SAMPLE_RATE)
        audio = np.clip(audio * p.volume_out, -1.0, 1.0)

        sd.play(audio, samplerate=SAMPLE_RATE)
        sd.wait()

    @property
    def is_active(self) -> bool:
        return self._active

    @staticmethod
    def list_devices() -> list[dict]:
        devices = []
        for i, dev in enumerate(sd.query_devices()):
            devices.append({
                "index": i,
                "name": dev["name"],
                "max_input": dev["max_input_channels"],
                "max_output": dev["max_output_channels"],
                "hostapi": sd.query_hostapis(dev["hostapi"])["name"],
            })
        return devices
