"""Sample-rate-domain vocal processing: consonant transient shaping
and automatic breath insertion.

These run AFTER humanize (so the breath we insert doesn't get re-pitched)
and BEFORE the effects chain (so breath/transients pick up the same EQ
and reverb as the voice).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class VocalProcessingConfig:
    # --- Consonant emphasis / suppression ---
    consonant_amount: float = 0.0
    """-1.0 = suppress consonants (softer attack) ... 0 = no change ...
    +1.0 = emphasize consonants (sharper diction). Typical range -0.4..+0.4.
    """

    consonant_sensitivity: float = 0.5
    """How sharp the transient detector is. 0.3=lenient / 1.0=picks only the
    strongest peaks. Default 0.5 catches normal speech transients.
    """

    # --- Automatic breath insertion ---
    breath_enabled: bool = False
    """Insert synthetic breath sounds in long silent gaps."""

    breath_threshold_db: float = -40.0
    """Silence detection threshold. Below this RMS for at least
    breath_min_silence_s, we consider it a gap to fill.
    """

    breath_min_silence_s: float = 0.4
    """Minimum silence length (seconds) before we add a breath."""

    breath_max_duration_s: float = 0.5
    """Cap on the breath length we generate, regardless of gap size."""

    breath_intensity: float = 0.05
    """Breath sample peak level (linear, ~0.03-0.08 sensible). 0.05 is
    audible but not distracting.
    """

    breath_seed: int | None = None


def apply_consonant_emphasis(
    samples: np.ndarray, sr: int, amount: float, sensitivity: float = 0.5
) -> np.ndarray:
    """Boost (+) or suppress (-) consonant transients.

    Approach: detect onset strength via librosa, smooth and resample to
    the sample rate, then apply a gain envelope that lifts (or lowers)
    transient frames.

    `amount` is multiplied by a gentle 0.5 factor internally so that
    +1.0 = roughly +6 dB at transient peaks (audible but not destructive).
    """
    if abs(amount) < 0.01:
        return samples

    import librosa

    hop = 512
    onset_env = librosa.onset.onset_strength(y=samples, sr=sr, hop_length=hop)
    peak = float(np.max(onset_env)) if onset_env.size else 0.0
    if peak <= 0:
        return samples
    onset_norm = onset_env / peak

    # Sensitivity sharpens the curve: higher = only the strongest peaks count
    onset_shaped = onset_norm ** max(0.1, sensitivity * 2.0)

    # Upsample envelope to per-sample resolution
    frame_centers = np.arange(len(onset_shaped)) * hop + hop // 2
    onset_full = np.interp(
        np.arange(len(samples)),
        frame_centers,
        onset_shaped,
        left=0.0,
        right=0.0,
    ).astype(np.float32)

    gain = 1.0 + 0.5 * float(amount) * onset_full
    # Clamp to keep sane levels
    gain = np.clip(gain, 0.2, 2.5)
    return (samples * gain).astype(np.float32)


def _find_silences(
    samples: np.ndarray,
    sr: int,
    threshold_db: float,
    min_duration_s: float,
) -> list[tuple[int, int]]:
    """Return list of (start_sample, end_sample) for silence regions
    longer than min_duration_s.
    """
    import librosa

    hop = 512
    rms = librosa.feature.rms(y=samples, frame_length=2048, hop_length=hop)[0]
    threshold_lin = 10.0 ** (threshold_db / 20.0)
    is_silent = rms < threshold_lin

    silences: list[tuple[int, int]] = []
    in_silence = False
    start_frame = 0
    for i, s in enumerate(is_silent):
        if s and not in_silence:
            start_frame = i
            in_silence = True
        elif not s and in_silence:
            end_frame = i
            duration_s = (end_frame - start_frame) * hop / sr
            if duration_s >= min_duration_s:
                silences.append((start_frame * hop, end_frame * hop))
            in_silence = False
    # Trailing silence
    if in_silence:
        end_frame = len(is_silent)
        duration_s = (end_frame - start_frame) * hop / sr
        if duration_s >= min_duration_s:
            silences.append((start_frame * hop, end_frame * hop))
    return silences


def _synthesize_breath(
    duration_s: float, sr: int, intensity: float, rng: np.random.Generator
) -> np.ndarray:
    """Generate a single synthetic breath: band-passed noise with an
    attack-sustain-release envelope. Sounds like an inhale when blended
    at low level.
    """
    from scipy.signal import butter, sosfiltfilt

    n = max(int(duration_s * sr), 64)
    noise = rng.standard_normal(n).astype(np.float32)
    sos = butter(4, [300.0, 3000.0], btype="bandpass", fs=sr, output="sos")
    noise = sosfiltfilt(sos, noise).astype(np.float32)

    env = np.ones(n, dtype=np.float32)
    attack = int(n * 0.25)
    release = int(n * 0.55)
    if attack > 0:
        env[:attack] = np.linspace(0.0, 1.0, attack) ** 2
    if release > 0:
        env[-release:] = np.linspace(1.0, 0.0, release) ** 1.5

    out = noise * env
    # Normalise to target peak intensity
    peak = float(np.max(np.abs(out)))
    if peak > 0:
        out *= float(intensity) / peak
    return out


def insert_breaths(
    samples: np.ndarray, sr: int, config: VocalProcessingConfig
) -> np.ndarray:
    """Mix synthetic breaths into silent regions of the input."""
    if not config.breath_enabled:
        return samples

    silences = _find_silences(
        samples, sr, config.breath_threshold_db, config.breath_min_silence_s
    )
    if not silences:
        return samples

    rng = np.random.default_rng(config.breath_seed)
    out = samples.copy()
    fade_samples = int(0.02 * sr)  # 20 ms edge fade on breath

    for start, end in silences:
        gap_s = (end - start) / sr
        # Use 70% of the gap, capped by max_duration
        breath_dur = min(gap_s * 0.7, config.breath_max_duration_s)
        if breath_dur < 0.05:
            continue

        breath = _synthesize_breath(breath_dur, sr, config.breath_intensity, rng)
        b_len = len(breath)
        center = (start + end) // 2
        ins_start = max(0, center - b_len // 2)
        ins_end = min(len(out), ins_start + b_len)
        actual_len = ins_end - ins_start
        if actual_len <= 0:
            continue

        # Apply soft fade on both sides of the breath to avoid pops
        env = np.ones(actual_len, dtype=np.float32)
        f = min(fade_samples, actual_len // 3)
        if f > 0:
            env[:f] = np.linspace(0.0, 1.0, f)
            env[-f:] = np.linspace(1.0, 0.0, f)

        out[ins_start:ins_end] = out[ins_start:ins_end] + breath[:actual_len] * env

    return out


def apply(samples: np.ndarray, sr: int, config: VocalProcessingConfig) -> np.ndarray:
    """Run consonant shaping + breath insertion in pipeline order."""
    out = samples.astype(np.float32)
    if abs(config.consonant_amount) > 0.01:
        out = apply_consonant_emphasis(
            out, sr, config.consonant_amount, config.consonant_sensitivity
        )
    out = insert_breaths(out, sr, config)
    return out
