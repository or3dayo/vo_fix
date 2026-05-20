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
    """Mild formant variation. 0.0-0.05 sensible. Costly - off by default."""

    formant_shift_ratio: float = 1.0
    """Static formant shift. 1.0 = no change.
    <1.0 = formants down (chestier, more masculine timbre).
    >1.0 = formants up (brighter, more feminine timbre).
    Useful range 0.85-1.18.
    """

    gender_shift: float = 0.0
    """Combined pitch + formant gender slider, -1.0 (deep male) to +1.0
    (high female). 0 = no change. Internally drives both pitch (up to
    +/-3 semitones) and formants (0.82-1.18). Multiplies with the
    explicit formant_shift_ratio if both are set.
    """

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


def _shift_formants(sp: np.ndarray, ratio: float) -> np.ndarray:
    """Warp the spectral envelope along the frequency axis.

    Shape: (n_frames, n_freq). ratio > 1 shifts formants up (brighter),
    ratio < 1 shifts them down (deeper). We do this by sampling sp at
    new positions: new[k] = sp[k / ratio], with linear interpolation.
    """
    if abs(ratio - 1.0) < 1e-3:
        return sp
    n_freq = sp.shape[1]
    src_idx = np.arange(n_freq) / ratio
    src_idx = np.clip(src_idx, 0.0, n_freq - 1.0)
    floor_idx = np.floor(src_idx).astype(np.int64)
    ceil_idx = np.minimum(floor_idx + 1, n_freq - 1)
    frac = (src_idx - floor_idx).astype(sp.dtype)
    # Linear interp along freq axis (vectorized over frames). pyworld
    # requires C-contiguous arrays for synthesize() so ascontiguousarray()
    # the result here rather than at the call site.
    new_sp = (1.0 - frac) * sp[:, floor_idx] + frac * sp[:, ceil_idx]
    return np.ascontiguousarray(new_sp)


def _resolve_gender_shift(gender: float) -> tuple[float, float]:
    """Map gender slider [-1, +1] to (pitch_semitones, formant_ratio)."""
    g = float(np.clip(gender, -1.0, 1.0))
    pitch_semitones = g * 3.0           # +/-3 semitones at extremes
    formant_ratio = 1.0 + g * 0.18      # 0.82..1.18 at extremes
    return pitch_semitones, formant_ratio


def apply_pitch_humanize(
    samples: np.ndarray, sr: int, config: HumanizeConfig, rng: np.random.Generator
) -> np.ndarray:
    """Use pyworld to decompose, modify f0/spectral envelope, resynth.

    We do a single pyworld pass that handles jitter, vibrato, formant
    shift, gender shift, and any explicit pitch shift coming from gender.
    Combining everything here avoids round-tripping audio through
    pyworld more than once.
    """
    gender_pitch_st, gender_formant = _resolve_gender_shift(config.gender_shift)
    effective_formant = config.formant_shift_ratio * gender_formant

    needs_pyworld = (
        config.jitter_cents > 0
        or config.vibrato_depth_cents > 0
        or abs(effective_formant - 1.0) > 1e-3
        or abs(gender_pitch_st) > 1e-3
    )
    if not needs_pyworld:
        return samples

    try:
        import pyworld as pw
    except ImportError as e:
        raise RuntimeError(
            "pyworld is required for pitch humanization. pip install pyworld"
        ) from e

    x = samples.astype(np.float64)
    frame_period = 5.0  # ms - pyworld default

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

    if abs(gender_pitch_st) > 1e-3:
        # Static pitch shift from gender control
        f0_mod[voiced] *= 2.0 ** (gender_pitch_st / 12.0)

    if config.jitter_cents > 0:
        drift = _smooth_noise_fast(n_frames, config.jitter_rate_hz, int(frame_sr), rng)
        ratio = 2.0 ** ((config.jitter_cents * drift) / 1200.0)
        f0_mod[voiced] *= ratio[voiced]

    if config.vibrato_depth_cents > 0:
        t_axis = np.arange(n_frames) / frame_sr
        rate_drift = 1.0 + 0.1 * _smooth_noise_fast(n_frames, 0.7, int(frame_sr), rng)
        phase = 2 * np.pi * config.vibrato_rate_hz * t_axis * rate_drift
        vib = np.sin(phase)
        ratio = 2.0 ** ((config.vibrato_depth_cents * vib) / 1200.0)
        f0_mod[voiced] *= ratio[voiced]

    # 3. Modify spectral envelope (formant shift)
    sp_mod = _shift_formants(sp, effective_formant)

    # 4. Resynth
    y = pw.synthesize(f0_mod, sp_mod, ap, sr, frame_period=frame_period)
    return y.astype(np.float32)


def humanize(samples: np.ndarray, sr: int, config: HumanizeConfig) -> np.ndarray:
    rng = np.random.default_rng(config.seed)
    out = apply_pitch_humanize(samples, sr, config, rng)
    out = apply_shimmer(out, sr, config, rng)
    return out
