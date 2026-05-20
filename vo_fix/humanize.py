"""Pitch / amplitude humanization via pyworld decomposition.

The core idea: AI voices (SUNO, etc.) are too "clean" — pitch tracks land
perfectly on target and amplitude envelopes are uniform. We add controlled
sub-musical drift back in by:

  1. Decomposing the signal into f0 (pitch), spectral envelope, aperiodicity
     via WORLD.
  2. Modifying f0 with low-frequency noise (the drift a human voice has
     naturally) plus optional vibrato.
  3. Resynthesizing.
  4. Multiplying the time-domain signal by a slow shimmer envelope.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class HumanizeConfig:
    jitter_cents: float = 8.0
    """Stddev of slow random pitch drift, in cents (1 semitone = 100)."""

    jitter_rate_hz: float = 4.5
    """Cutoff of the drift LFO. Higher = faster wobble."""

    vibrato_depth_cents: float = 0.0
    """Extra vibrato to inject on top, in cents."""

    vibrato_rate_hz: float = 5.5

    shimmer: float = 0.03
    """Amplitude jitter as a fraction (0.03 = ±3%)."""

    shimmer_rate_hz: float = 7.0

    formant_jitter: float = 0.0
    """Mild formant variation. 0.0–0.05 sensible. Costly — off by default."""

    seed: int | None = None


def _smooth_noise(n: int, rate_hz: float, sr: int, rng: np.random.Generator) -> np.ndarray:
    """Generate slow band-limited noise via white noise + IIR low-pass.

    Cheap, no scipy dependency. Returns zero-mean unit-ish-std array.
    """
    white = rng.standard_normal(n).astype(np.float32)
    # one-pole low-pass: y[n] = (1-a)*x[n] + a*y[n-1]
    # cutoff ~ rate_hz
    rc = 1.0 / (2.0 * np.pi * max(rate_hz, 0.1))
    dt = 1.0 / sr
    a = rc / (rc + dt)
    out = np.empty_like(white)
    acc = 0.0
    for i in range(n):
        acc = (1.0 - a) * white[i] + a * acc
        out[i] = acc
    # rescale to ~unit std
    s = float(out.std())
    if s > 1e-9:
        out /= s
    return out


def _smooth_noise_fast(n: int, rate_hz: float, sr: int, rng: np.random.Generator) -> np.ndarray:
    """Vectorized smooth noise using FFT low-pass. Much faster than the loop."""
    white = rng.standard_normal(n).astype(np.float32)
    # FFT-based brick-wall low-pass at rate_hz
    freqs = np.fft.rfftfreq(n, d=1.0 / sr)
    spec = np.fft.rfft(white)
    # gentle roll-off: gaussian centered at 0 with sigma = rate_hz
    weights = np.exp(-0.5 * (freqs / max(rate_hz, 0.1)) ** 2)
    spec *= weights
    out = np.fft.irfft(spec, n=n).astype(np.float32)
    s = float(out.std())
    if s > 1e-9:
        out /= s
    return out


def apply_shimmer(
    samples: np.ndarray, sr: int, config: HumanizeConfig, rng: np.random.Generator
) -> np.ndarray:
    if config.shimmer <= 0:
        return samples
    env = _smooth_noise_fast(len(samples), config.shimmer_rate_hz, sr, rng)
    gain = 1.0 + config.shimmer * env
    return (samples * gain).astype(np.float32)


def apply_pitch_humanize(
    samples: np.ndarray, sr: int, config: HumanizeConfig, rng: np.random.Generator
) -> np.ndarray:
    """Use pyworld to decompose, modify f0, resynth."""
    if config.jitter_cents <= 0 and config.vibrato_depth_cents <= 0:
        return samples

    try:
        import pyworld as pw
    except ImportError as e:
        raise RuntimeError(
            "pyworld is required for pitch humanization. pip install pyworld"
        ) from e

    x = samples.astype(np.float64)
    frame_period = 5.0  # ms — pyworld default

    # 1. Decompose
    f0, t = pw.harvest(x, sr, frame_period=frame_period)
    f0 = pw.stonemask(x, f0, t, sr)
    sp = pw.cheaptrick(x, f0, t, sr)
    ap = pw.d4c(x, f0, t, sr)

    # 2. Modify f0
    n_frames = len(f0)
    frame_sr = 1000.0 / frame_period  # frames per second
    f0_mod = f0.copy()
    voiced = f0_mod > 0

    if config.jitter_cents > 0:
        drift = _smooth_noise_fast(n_frames, config.jitter_rate_hz, int(frame_sr), rng)
        # cents -> ratio: 2^(cents/1200)
        ratio = 2.0 ** ((config.jitter_cents * drift) / 1200.0)
        f0_mod[voiced] *= ratio[voiced]

    if config.vibrato_depth_cents > 0:
        t_axis = np.arange(n_frames) / frame_sr
        # Vibrato rate also drifts a bit so it doesn't sound mechanical
        rate_drift = 1.0 + 0.1 * _smooth_noise_fast(n_frames, 0.7, int(frame_sr), rng)
        phase = 2 * np.pi * config.vibrato_rate_hz * t_axis * rate_drift
        vib = np.sin(phase)
        ratio = 2.0 ** ((config.vibrato_depth_cents * vib) / 1200.0)
        f0_mod[voiced] *= ratio[voiced]

    # 3. Resynth
    y = pw.synthesize(f0_mod, sp, ap, sr, frame_period=frame_period)
    return y.astype(np.float32)


def humanize(samples: np.ndarray, sr: int, config: HumanizeConfig) -> np.ndarray:
    rng = np.random.default_rng(config.seed)
    out = apply_pitch_humanize(samples, sr, config, rng)
    out = apply_shimmer(out, sr, config, rng)
    return out
