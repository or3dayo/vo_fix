from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf


@dataclass
class AudioMeta:
    """Capture the input file's format so we can write back at the same quality.

    Without this, the pipeline used to flatten everything to 16-bit PCM @
    44.1 kHz which silently degrades 24-bit / 48 kHz / 96 kHz sources.
    """

    sample_rate: int
    subtype: str
    """soundfile subtype string, e.g. 'PCM_16', 'PCM_24', 'FLOAT'."""

    channels: int


def read_meta(path: str | Path) -> AudioMeta:
    info = sf.info(str(path))
    return AudioMeta(sample_rate=info.samplerate, subtype=info.subtype, channels=info.channels)


def load_wav(
    path: str | Path, target_sr: int | None = None
) -> tuple[np.ndarray, int, AudioMeta]:
    """Load a wav as float32 mono and report the source metadata.

    Resamples only if target_sr is given AND differs from the file's
    native rate. Callers that want to preserve the input sample rate
    should pass target_sr=None.
    """
    meta = read_meta(path)
    data, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if data.ndim == 2:
        data = data.mean(axis=1)
    if target_sr is not None and target_sr != sr:
        import librosa

        data = librosa.resample(data, orig_sr=sr, target_sr=target_sr)
        sr = target_sr
    return data.astype(np.float32), sr, meta


# soundfile subtype strings we expose to users + their friendly labels.
SUBTYPE_LABELS = {
    "PCM_16": "16-bit PCM (CD品質)",
    "PCM_24": "24-bit PCM (スタジオ標準)",
    "FLOAT": "32-bit float (最高品質)",
}

# Default subtype priority when "preserve input" can't apply (e.g. input
# was a format we can't roundtrip cleanly). FLOAT is the safest choice
# because the pipeline is internally float anyway.
DEFAULT_SUBTYPE = "FLOAT"


def _normalize_subtype(subtype: str | None, input_subtype: str | None) -> str:
    """Resolve which subtype to actually write.

    - explicit `subtype` wins if given and supported
    - else fall back to the input's subtype if it's a wav-roundtrippable one
    - else FLOAT
    """
    if subtype and sf.check_format("WAV", subtype):
        return subtype
    if input_subtype and sf.check_format("WAV", input_subtype):
        # Map oddball subtypes to common ones we display
        if input_subtype in ("PCM_16", "PCM_24", "PCM_32", "FLOAT", "DOUBLE"):
            return input_subtype
    return DEFAULT_SUBTYPE


def save_wav(
    path: str | Path,
    data: np.ndarray,
    sr: int,
    *,
    subtype: str | None = None,
    input_subtype: str | None = None,
) -> str:
    """Write a wav file. Returns the actual subtype used.

    If neither `subtype` nor `input_subtype` is supplied, we default to
    FLOAT (32-bit float) so no precision is lost.

    Headroom protection: any peak > 0.999 is normalised down. This is
    only meaningful for integer subtypes (FLOAT can hold +/-inf cleanly)
    but we apply it uniformly to keep clipped DAW imports from going
    over the line.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    effective = _normalize_subtype(subtype, input_subtype)

    peak = float(np.max(np.abs(data))) if data.size else 0.0
    if peak > 0.999 and effective.startswith("PCM"):
        data = data * (0.999 / peak)

    sf.write(str(p), data.astype(np.float32), sr, subtype=effective)
    return effective
