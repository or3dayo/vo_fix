from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf


def load_wav(path: str | Path, target_sr: int | None = None) -> tuple[np.ndarray, int]:
    """Load a wav as float32 mono. Resample if target_sr given and differs."""
    data, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if data.ndim == 2:
        data = data.mean(axis=1)
    if target_sr is not None and target_sr != sr:
        import librosa

        data = librosa.resample(data, orig_sr=sr, target_sr=target_sr)
        sr = target_sr
    return data.astype(np.float32), sr


def save_wav(path: str | Path, data: np.ndarray, sr: int) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    if peak > 0.999:
        data = data * (0.999 / peak)
    sf.write(str(p), data.astype(np.float32), sr, subtype="PCM_16")
