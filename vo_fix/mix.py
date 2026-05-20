"""Final-mix stage: combine the processed vocal with one or more
instrumental / STEM tracks to produce a finished song.

Design notes:
- This runs as the LAST stage of the pipeline. The vocal has already
  been humanized + effected.
- Each stem is loaded fresh (no processing); only level + sample-rate
  + channel adjustments are applied.
- Output channel count = max(vocal, any stem). Mono sources are upmixed
  to stereo by duplication if needed.
- Output length = max(vocal, longest stem). Shorter signals are padded
  with trailing silence so intros / outros from the instrumental survive.
- Soft-clip protection at peak > 0.99 via simple normalization.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)


@dataclass
class MixConfig:
    enabled: bool = False
    """When False, the mix stage is skipped entirely (no stems loaded)."""

    stem_paths: list[str] = field(default_factory=list)
    """Absolute paths of instrumental / STEM wav files to layer in."""

    vocal_gain_db: float = 0.0
    """Trim applied to the processed vocal before summing (dB)."""

    stems_gain_db: float = 0.0
    """Trim applied uniformly to all stems before summing (dB)."""

    master_gain_db: float = 0.0
    """Trim applied to the post-sum mix (dB)."""

    normalize_on_clip: bool = True
    """If peak > 0.99 after master gain, scale down to fit."""


def _db_to_linear(db: float) -> float:
    return 10.0 ** (float(db) / 20.0)


def _ensure_2d(samples: np.ndarray, target_channels: int) -> np.ndarray:
    """Make `samples` a (n, target_channels) array.

    Mono -> duplicate across all channels.
    Channel count mismatch -> tile / take first channels.
    """
    if samples.ndim == 1:
        return np.repeat(samples[:, None], target_channels, axis=1)
    n, ch = samples.shape
    if ch == target_channels:
        return samples
    if ch == 1:
        return np.repeat(samples, target_channels, axis=1)
    if ch > target_channels:
        return samples[:, :target_channels]
    # ch < target_channels but > 1: tile the existing channels
    tiles = (target_channels + ch - 1) // ch
    return np.tile(samples, (1, tiles))[:, :target_channels]


def _pad_or_align(samples: np.ndarray, target_len: int) -> np.ndarray:
    """Pad with trailing silence to reach target_len. No truncation."""
    cur = samples.shape[0]
    if cur >= target_len:
        return samples
    pad_shape = list(samples.shape)
    pad_shape[0] = target_len - cur
    pad = np.zeros(pad_shape, dtype=samples.dtype)
    return np.concatenate([samples, pad], axis=0)


def _load_stem(path: str | Path, target_sr: int) -> np.ndarray:
    """Load a stem and resample to target_sr. Returns float32 array
    of shape (n,) for mono or (n, channels) for multi-channel.
    """
    data, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if sr != target_sr:
        import librosa

        if data.ndim == 1:
            data = librosa.resample(data, orig_sr=sr, target_sr=target_sr)
        else:
            per_ch = [
                librosa.resample(data[:, ch], orig_sr=sr, target_sr=target_sr)
                for ch in range(data.shape[1])
            ]
            data = np.stack(per_ch, axis=1)
    return data.astype(np.float32)


def mix_with_stems(
    vocal: np.ndarray, sr: int, config: MixConfig
) -> np.ndarray:
    """Mix the (already processed) vocal with the configured stems.

    Returns the mixed array. Channel count = max of vocal + stems;
    length = max of vocal + stems (shorter signals padded with silence).

    No-op if config.enabled is False or stem_paths is empty.
    """
    if not config.enabled or not config.stem_paths:
        return vocal

    # Decide output dimensions
    arrays: list[np.ndarray] = []
    arrays.append(vocal)

    for path in config.stem_paths:
        try:
            arrays.append(_load_stem(path, sr))
        except Exception as e:
            logger.warning("Could not load stem %s: %s", path, e)

    if len(arrays) <= 1:
        return vocal  # all stems failed to load

    out_channels = max((a.shape[1] if a.ndim == 2 else 1) for a in arrays)
    out_length = max(a.shape[0] for a in arrays)

    # Normalize each input array to (out_length, out_channels)
    normalized: list[np.ndarray] = []
    for a in arrays:
        a2 = _ensure_2d(a, out_channels)
        a2 = _pad_or_align(a2, out_length)
        normalized.append(a2)

    vocal_lin = _db_to_linear(config.vocal_gain_db)
    stems_lin = _db_to_linear(config.stems_gain_db)
    master_lin = _db_to_linear(config.master_gain_db)

    mix = normalized[0] * vocal_lin
    for a2 in normalized[1:]:
        mix = mix + a2 * stems_lin

    mix = mix * master_lin

    if config.normalize_on_clip:
        peak = float(np.max(np.abs(mix))) if mix.size else 0.0
        if peak > 0.99:
            mix = mix * (0.99 / peak)

    return mix.astype(np.float32)
