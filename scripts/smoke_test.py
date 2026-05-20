"""Generate a synthetic 'AI-clean' vocal and run the full pipeline.

A real test of humanization needs a vocal-like signal: harmonic content
with a clear f0 contour and intentionally robotic / quantized pitch. We
build one synthetically so the test doesn't need an external wav.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import soundfile as sf

from vo_fix.io import save_wav
from vo_fix.pipeline import PRESETS, ProcessConfig, process_array

SR = 44100
DUR = 3.0


def synthesize_robotic_vocal(seed: int = 0) -> np.ndarray:
    """Sustained notes A4, C5, E5, A4 — perfectly tuned, no jitter."""
    rng = np.random.default_rng(seed)
    notes_hz = [440.0, 523.25, 659.25, 440.0]
    seg = int(SR * DUR / len(notes_hz))
    t_seg = np.arange(seg) / SR
    parts = []
    for f in notes_hz:
        # 4 harmonics — vowel-ish
        sig = np.zeros(seg, dtype=np.float32)
        for k, amp in enumerate([1.0, 0.55, 0.32, 0.18], start=1):
            sig += amp * np.sin(2 * np.pi * f * k * t_seg).astype(np.float32)
        # subtle ADSR
        env = np.ones(seg, dtype=np.float32)
        attack = int(SR * 0.03)
        release = int(SR * 0.05)
        env[:attack] = np.linspace(0, 1, attack)
        env[-release:] = np.linspace(1, 0, release)
        sig *= env
        parts.append(sig)
    full = np.concatenate(parts)
    # Light noise floor so pyworld has something to analyze (real vocals always have breath)
    full += rng.standard_normal(len(full)).astype(np.float32) * 0.001
    full /= np.max(np.abs(full))
    return full * 0.6


def main():
    out_dir = Path(__file__).parent.parent / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    raw = synthesize_robotic_vocal()
    save_wav(out_dir / "00_input_robotic.wav", raw, SR)
    print(f"Wrote 00_input_robotic.wav  ({len(raw)/SR:.2f}s)")

    for preset_name in ["off", "natural", "intimate", "polished"]:
        cfg = PRESETS[preset_name]
        cfg.target_sr = SR
        cfg.humanize.seed = 42  # deterministic for the test
        out, sr = process_array(raw, SR, cfg)
        path = out_dir / f"01_{preset_name}.wav"
        save_wav(path, out, sr)
        print(f"Wrote {path.name}  ({len(out)/sr:.2f}s)")

    print("\nDone. Listen to out/ to compare presets vs. input.")


if __name__ == "__main__":
    main()
