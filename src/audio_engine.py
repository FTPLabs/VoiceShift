"""
Real-time voice processing engine.

Architecture: single duplex sd.Stream callback (eliminates clock drift
between separate InputStream/OutputStream that caused periodic glitches).

Processing chain per chunk:
  DC block → Noise gate → High-pass EQ → Pitch shift (resample_poly)
  → Formant shift (cepstral) → Robotic effect → Low-pass EQ
  → Compressor → Reverb → Volume / clip

Stateful IIR filters persist across chunks so there are no boundary
transients when the chunk boundary falls mid-filter.
"""

import logging
import threading
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

import numpy as np
import scipy.signal as signal
import sounddevice as sd

logger = logging.getLogger(__name__)

CHUNK = 2048          # ~42 ms @ 48 kHz – good balance of latency vs CPU
SAMPLE_RATE = 48000
CHANNELS = 1
DTYPE = np.float32


@dataclass
class VoiceParams:
    pitch_semitones: float = 0.0       # −12 … +12 semitones
    formant_shift: float = 1.0         # 0.5 … 2.0  (vocal-tract length factor)
    robotic_amount: float = 0.0        # 0.0 … 1.0
    noise_gate_db: float = -50.0       # dBFS silence threshold
    volume_out: float = 1.0            # output gain
    highpass_freq: float = 80.0        # Hz – low-cut (removes rumble / DC thump)
    lowpass_freq: float = 16000.0      # Hz – high-cut (removes hiss)
    compressor_threshold: float = -24.0  # dBFS
    compressor_ratio: float = 4.0      # N:1
    reverb_amount: float = 0.0         # 0.0 … 1.0


# ---------------------------------------------------------------------------
# Stateless DSP helpers
# ---------------------------------------------------------------------------

def _noise_gate(audio: np.ndarray, threshold_db: float) -> np.ndarray:
    """Hard gate: mute chunk if RMS is below threshold."""
    threshold_lin = 10.0 ** (threshold_db / 20.0)
    rms = float(np.sqrt(np.mean(audio ** 2)))
    return audio if rms >= threshold_lin else np.zeros_like(audio)


def _pitch_shift(audio: np.ndarray, semitones: float) -> np.ndarray:
    """
    Pitch-shift using polyphase resampling (resample_poly).

    resample_poly uses a causal FIR filter so it does NOT produce
    Gibbs ringing that scipy.signal.resample (FFT-based) does at chunk edges.
    The rational fraction approximation keeps filter order sane.
    """
    if abs(semitones) < 0.05:
        return audio

    factor = 2.0 ** (semitones / 12.0)
    # We want output_len = input_len / factor
    # resample_poly(x, up, down) → len(x) * up / down
    # So up/down = 1/factor
    frac = Fraction(1.0 / factor).limit_denominator(64)
    up, down = frac.numerator, frac.denominator

    out = signal.resample_poly(audio, up, down, padtype="line")
    n = len(audio)
    if len(out) >= n:
        return out[:n].astype(DTYPE)
    return np.pad(out, (0, n - len(out)), mode="edge").astype(DTYPE)


def _formant_shift(audio: np.ndarray, shift_factor: float) -> np.ndarray:
    """
    Shift vocal formants independently of pitch using cepstral liftering.

    Algorithm:
      1. Extract spectral envelope via real cepstrum (low-quefrency lifter).
      2. Warp the envelope in frequency by shift_factor.
      3. Apply the warped envelope to the signal's spectrum.

    shift_factor > 1.0 → formants move up   (brighter / child-like)
    shift_factor < 1.0 → formants move down  (deeper / larger vocal tract)
    """
    if abs(shift_factor - 1.0) < 0.02:
        return audio

    n = len(audio)
    win = np.hanning(n).astype(DTYPE)
    x_w = audio * win

    X = np.fft.rfft(x_w, n=n)
    log_mag = np.log(np.abs(X) + 1e-10)

    # Real cepstrum → separate fine structure from envelope
    cep = np.fft.irfft(log_mag)

    # Lifter: keep only low-quefrency (spectral envelope) part
    lifter = max(4, int(SAMPLE_RATE / 400))   # ~120 samples @ 48 kHz
    cep_env = np.zeros_like(cep)
    cep_env[:lifter] = cep[:lifter]
    if lifter < n:
        cep_env[-lifter:] = cep[-lifter:]

    log_env = np.fft.rfft(cep_env).real        # spectral envelope (log)

    # Warp envelope bins by shift_factor
    num_bins = len(log_env)
    src_idx = np.arange(num_bins, dtype=np.float64)
    shifted_idx = src_idx / shift_factor        # map to lower/higher bins
    shifted_idx = np.clip(shifted_idx, 0, num_bins - 1)
    shifted_env = np.interp(src_idx, shifted_idx, log_env)

    # Apply correction: multiply spectrum by exp(shifted_env - original_env)
    correction = np.exp((shifted_env - log_env).clip(-10, 10)).astype(np.float64)
    X_shifted = X * correction

    out = np.fft.irfft(X_shifted, n=n)
    return out.astype(DTYPE)


def _apply_robotic(audio: np.ndarray, amount: float) -> np.ndarray:
    """Comb filter gives a metallic / vocoder buzz."""
    if amount < 0.01:
        return audio
    freq = 120.0
    delay = int(SAMPLE_RATE / freq)
    if delay <= 0 or delay >= len(audio):
        return audio
    comb = np.zeros_like(audio)
    comb[delay:] = audio[:-delay]
    return (audio * (1.0 - amount) + comb * amount).astype(DTYPE)


def _compress(audio: np.ndarray, threshold_db: float, ratio: float) -> np.ndarray:
    """
    RMS compressor with soft knee.
    Does nothing when ratio <= 1 or audio is below threshold.
    """
    if ratio <= 1.0:
        return audio
    threshold_lin = 10.0 ** (threshold_db / 20.0)
    rms = float(np.sqrt(np.mean(audio ** 2))) + 1e-10
    if rms <= threshold_lin:
        return audio
    # Gain reduction
    gain_db = (threshold_db - 20.0 * np.log10(rms)) * (1.0 - 1.0 / ratio)
    gain = 10.0 ** (gain_db / 20.0)
    return (audio * gain).astype(DTYPE)


def _reverb(audio: np.ndarray, amount: float) -> np.ndarray:
    """Simple parallel comb-filter reverb (Schroeder-style, lightweight)."""
    if amount < 0.01:
        return audio
    delays_ms = [37, 41, 53, 61]   # ms
    decay = 0.5
    wet = np.zeros_like(audio)
    for d_ms in delays_ms:
        d = int(SAMPLE_RATE * d_ms / 1000)
        if d >= len(audio):
            continue
        comb = np.zeros_like(audio)
        comb[d:] = audio[:-d] * decay
        wet += comb
    wet /= len(delays_ms)
    return (audio * (1.0 - amount) + wet * amount).astype(DTYPE)


# ---------------------------------------------------------------------------
# Stateful filter helpers (persist zi between chunks → no boundary clicks)
# ---------------------------------------------------------------------------

class _IIRFilter:
    """Butterworth IIR filter with persistent state across process() calls."""

    def __init__(self, btype: str, order: int = 4):
        self._btype = btype
        self._order = order
        self._sos: Optional[np.ndarray] = None
        self._zi: Optional[np.ndarray] = None
        self._last_cutoff: float = -1.0

    def process(self, audio: np.ndarray, cutoff_hz: float, sr: int) -> np.ndarray:
        nyq = sr / 2.0
        cutoff_norm = np.clip(cutoff_hz / nyq, 1e-4, 0.9999)

        # Rebuild filter only when cutoff changes significantly
        if abs(cutoff_hz - self._last_cutoff) > 0.5 or self._sos is None:
            self._sos = signal.butter(
                self._order, cutoff_norm, btype=self._btype, output="sos"
            )
            # Initial condition: steady-state for current input value
            self._zi = signal.sosfilt_zi(self._sos) * float(audio[0])
            self._last_cutoff = cutoff_hz

        out, self._zi = signal.sosfilt(self._sos, audio, zi=self._zi)
        return out.astype(DTYPE)

    def reset(self) -> None:
        self._zi = None
        self._last_cutoff = -1.0


class _DCBlock:
    """One-pole high-pass at ~30 Hz for DC offset removal."""

    def __init__(self, fc: float = 30.0, sr: int = SAMPLE_RATE):
        w = 2.0 * np.pi * fc / sr
        self._coeff = 1.0 - w   # pole location ≈ exp(−w)
        self._x_prev = 0.0
        self._y_prev = 0.0

    def process(self, audio: np.ndarray) -> np.ndarray:
        out = np.empty_like(audio)
        x_prev, y_prev, c = self._x_prev, self._y_prev, self._coeff
        for i, x in enumerate(audio):
            y = x - x_prev + c * y_prev
            out[i] = y
            x_prev = x
            y_prev = y
        self._x_prev = x_prev
        self._y_prev = y_prev
        return out


# ---------------------------------------------------------------------------
# AudioEngine
# ---------------------------------------------------------------------------

class AudioEngine:
    def __init__(self) -> None:
        self._params = VoiceParams()
        self._lock = threading.Lock()
        self._active = False

        self._input_device: Optional[int] = None
        self._output_device: Optional[int] = None
        self._stream: Optional[sd.Stream] = None

        # Stateful DSP objects
        self._dc_block = _DCBlock()
        self._hp_filter = _IIRFilter("high", order=4)
        self._lp_filter = _IIRFilter("low", order=4)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_params(self, params: VoiceParams) -> None:
        with self._lock:
            self._params = params

    def get_params(self) -> VoiceParams:
        with self._lock:
            import dataclasses
            return dataclasses.replace(self._params)

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
        # Reset filter state so old state from previous session doesn't bleed in
        self._dc_block = _DCBlock()
        self._hp_filter.reset()
        self._lp_filter.reset()

        engine = self  # capture for closure

        def _callback(indata: np.ndarray, outdata: np.ndarray,
                      frames: int, time_info, status) -> None:
            if status:
                logger.debug("Stream status: %s", status)

            chunk = indata[:, 0].copy()

            with engine._lock:
                p = engine._params

            try:
                chunk = engine._dc_block.process(chunk)
                chunk = _noise_gate(chunk, p.noise_gate_db)

                if p.highpass_freq >= 20.0:
                    chunk = engine._hp_filter.process(chunk, p.highpass_freq, SAMPLE_RATE)

                chunk = _pitch_shift(chunk, p.pitch_semitones)
                chunk = _formant_shift(chunk, p.formant_shift)
                chunk = _apply_robotic(chunk, p.robotic_amount)

                if p.lowpass_freq <= SAMPLE_RATE / 2 - 200:
                    chunk = engine._lp_filter.process(chunk, p.lowpass_freq, SAMPLE_RATE)

                chunk = _compress(chunk, p.compressor_threshold, p.compressor_ratio)
                chunk = _reverb(chunk, p.reverb_amount)
                chunk = np.clip(chunk * p.volume_out, -1.0, 1.0).astype(DTYPE)
            except Exception as exc:
                logger.warning("DSP error: %s", exc)
                chunk = np.zeros(frames, dtype=DTYPE)

            if len(chunk) < frames:
                chunk = np.pad(chunk, (0, frames - len(chunk)))
            outdata[:, 0] = chunk[:frames]

        try:
            self._stream = sd.Stream(
                device=(self._input_device, self._output_device),
                samplerate=SAMPLE_RATE,
                blocksize=CHUNK,
                dtype=DTYPE,
                channels=(CHANNELS, CHANNELS),
                callback=_callback,
                latency="low",
            )
            self._stream.start()
            logger.info("Audio engine started (duplex, blocksize=%d)", CHUNK)
        except Exception as exc:
            self._active = False
            logger.error("Failed to start audio stream: %s", exc)
            raise

    def stop(self) -> None:
        self._active = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as exc:
                logger.debug("Stream close error: %s", exc)
            self._stream = None
        logger.info("Audio engine stopped")

    def preview_once(self, duration: float = 2.0) -> None:
        """Record mic for `duration` seconds, process, play back."""
        frames = int(SAMPLE_RATE * duration)
        rec = sd.rec(frames, samplerate=SAMPLE_RATE, channels=1, dtype=DTYPE,
                     device=self._input_device)
        sd.wait()
        audio = rec[:, 0].copy()

        with self._lock:
            p = self._params

        dc = _DCBlock()
        audio = dc.process(audio)
        audio = _noise_gate(audio, p.noise_gate_db)

        hp = _IIRFilter("high")
        if p.highpass_freq >= 20.0:
            audio = hp.process(audio, p.highpass_freq, SAMPLE_RATE)

        audio = _pitch_shift(audio, p.pitch_semitones)
        audio = _formant_shift(audio, p.formant_shift)
        audio = _apply_robotic(audio, p.robotic_amount)

        lp = _IIRFilter("low")
        if p.lowpass_freq <= SAMPLE_RATE / 2 - 200:
            audio = lp.process(audio, p.lowpass_freq, SAMPLE_RATE)

        audio = _compress(audio, p.compressor_threshold, p.compressor_ratio)
        audio = _reverb(audio, p.reverb_amount)
        audio = np.clip(audio * p.volume_out, -1.0, 1.0).astype(DTYPE)

        sd.play(audio, samplerate=SAMPLE_RATE, device=self._output_device)
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
