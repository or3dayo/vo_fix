"""Effects chain via pedalboard. Mirrors a light vocal mixing chain."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class EffectsConfig:
    high_cut_hz: float = 9000.0
    """Low-pass cutoff to tame AI-vocal high-frequency sizzle. 0 disables."""

    presence_db: float = 0.0
    """Mid-presence bump around 3 kHz (dB). Small positive value adds clarity."""

    saturation: float = 0.15
    """Tape-style soft saturation drive, 0–1."""

    reverb_mix: float = 0.08
    """Reverb wet mix, 0–1."""

    reverb_room: float = 0.35
    """Reverb room size 0–1."""

    delay_ms: float = 0.0
    """Slap delay in ms (0 disables)."""

    delay_mix: float = 0.12

    output_gain_db: float = 0.0


def build_board(config: EffectsConfig, sr: int):
    from pedalboard import (
        Chorus,
        Delay,
        Distortion,
        Gain,
        HighShelfFilter,
        LowpassFilter,
        PeakFilter,
        Pedalboard,
        Reverb,
    )

    plugins: list = []

    if config.high_cut_hz > 0:
        plugins.append(LowpassFilter(cutoff_frequency_hz=float(config.high_cut_hz)))

    if abs(config.presence_db) > 0.01:
        plugins.append(
            PeakFilter(cutoff_frequency_hz=3000.0, gain_db=float(config.presence_db), q=0.9)
        )

    if config.saturation > 0:
        # Drive maps 0..1 -> 0..15 dB
        plugins.append(Distortion(drive_db=float(config.saturation) * 15.0))
        # Distortion can lift level — pull back proportionally
        plugins.append(Gain(gain_db=-float(config.saturation) * 6.0))

    if config.delay_ms > 0:
        plugins.append(
            Delay(
                delay_seconds=float(config.delay_ms) / 1000.0,
                feedback=0.15,
                mix=float(config.delay_mix),
            )
        )

    if config.reverb_mix > 0:
        plugins.append(
            Reverb(
                room_size=float(config.reverb_room),
                damping=0.5,
                wet_level=float(config.reverb_mix),
                dry_level=1.0 - float(config.reverb_mix) * 0.5,
                width=1.0,
            )
        )

    if abs(config.output_gain_db) > 0.01:
        plugins.append(Gain(gain_db=float(config.output_gain_db)))

    return Pedalboard(plugins)


def apply_effects(samples: np.ndarray, sr: int, config: EffectsConfig) -> np.ndarray:
    board = build_board(config, sr)
    if not list(board):
        return samples
    return board(samples.astype(np.float32), sample_rate=sr)
