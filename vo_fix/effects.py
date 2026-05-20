"""Effects chain via pedalboard.

Signal flow (when everything is enabled):

    [Multi-band EQ] -> [De-esser] -> [Compressor]
      -> [Lowpass (high_cut)] -> [Presence peak]
      -> [Saturation] -> [Chorus/Doubler]
      -> [Delay] -> [Reverb] -> [Output gain]

That ordering follows the conventional vocal mixing chain:
1. Tone shaping (EQ)        — fix problem frequencies first
2. Sibilance taming (de-ess) — before compression so dynamics don't
   accentuate harsh "s" sounds
3. Dynamics (compressor)     — even out levels
4. Color (saturation)        — add harmonic warmth
5. Modulation (chorus)       — width / doubling
6. Space (reverb)            — depth — always last
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class EffectsConfig:
    # ----- Existing simple chain -----
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

    # ----- Multi-band EQ (always applied, 0 dB = no change) -----
    eq_low_shelf_db: float = 0.0
    """Low shelf @ 120 Hz. +で太く / -で軽く。±6dB目安"""

    eq_low_mid_db: float = 0.0
    """Peak @ 400 Hz. -でこもり除去 / +で厚み"""

    eq_high_mid_db: float = 0.0
    """Peak @ 1500 Hz. +で抜け / -で鼻にかかった感じを抑制"""

    eq_high_shelf_db: float = 0.0
    """High shelf @ 8 kHz. +でエアリー / -で落ち着いた音"""

    # ----- Compressor (opt-in) -----
    compressor_enabled: bool = False
    compressor_threshold_db: float = -18.0
    """このdB値を超えた信号が圧縮対象。-18は標準的"""

    compressor_ratio: float = 3.0
    """圧縮比。2:1=軽い / 4:1=ボーカル定番 / 8:1+=リミッター寄り"""

    compressor_attack_ms: float = 5.0
    """反応の速さ。短い=パツッとした音、長い=自然"""

    compressor_release_ms: float = 80.0
    """解放の速さ。長いと安定、短いとパンプ感"""

    # ----- De-esser (opt-in) -----
    deesser_enabled: bool = False
    deesser_freq_hz: float = 6500.0
    """サ行が突き刺さる帯域。日本語声で5-8kHz、英語声で6-9kHz目安"""

    deesser_threshold_db: float = -25.0
    """この帯域がこのレベルを超えたら抑制開始"""

    deesser_ratio: float = 4.0
    """サ行の圧縮比。4:1が定番"""

    # ----- Chorus / Doubler (opt-in) -----
    chorus_enabled: bool = False
    chorus_rate_hz: float = 0.8
    """揺らぎの速度。ダブラー風なら 0.3-0.7、コーラスっぽくは 1-2"""

    chorus_depth: float = 0.25
    """揺らぎの深さ。0.1=ほぼダブラー、0.5+=分厚いコーラス"""

    chorus_centre_delay_ms: float = 15.0
    """中心となるディレイ時間。15-25ms がコーラス標準"""

    chorus_mix: float = 0.3
    """エフェクト混ぜ率。0.2=控えめ、0.5=半々"""


def _apply_deesser(
    samples: np.ndarray,
    sr: int,
    threshold_db: float,
    ratio: float,
    freq_hz: float,
) -> np.ndarray:
    """Frequency-split de-esser: split at freq_hz, compress only the
    high band, then recombine. Zero-phase filters keep the bands
    phase-coherent.

    pedalboard has no sidechain, so a crossover de-esser is the cleanest
    DIY approach. It catches sibilance peaks without affecting the body
    of the voice below the crossover.
    """
    from pedalboard import Compressor, Pedalboard
    from scipy.signal import butter, sosfiltfilt

    sos_hp = butter(4, freq_hz, btype="highpass", fs=sr, output="sos")
    sos_lp = butter(4, freq_hz, btype="lowpass", fs=sr, output="sos")

    high = sosfiltfilt(sos_hp, samples).astype(np.float32)
    low = sosfiltfilt(sos_lp, samples).astype(np.float32)

    comp = Pedalboard(
        [
            Compressor(
                threshold_db=float(threshold_db),
                ratio=float(ratio),
                attack_ms=1.0,
                release_ms=50.0,
            )
        ]
    )
    high_compressed = comp(high, sample_rate=sr)
    return (low + high_compressed).astype(np.float32)


def build_board(config: EffectsConfig, sr: int):
    """Compose the main effects chain (everything except the de-esser).

    The de-esser uses crossover filtering which is hard to express as a
    single Pedalboard plugin, so it's applied separately in apply_effects.
    """
    from pedalboard import (
        Chorus,
        Compressor,
        Delay,
        Distortion,
        Gain,
        HighShelfFilter,
        LowpassFilter,
        LowShelfFilter,
        PeakFilter,
        Pedalboard,
        Reverb,
    )

    plugins: list = []

    # 1. Multi-band EQ (always built; 0 dB bands are inert but cheap)
    if abs(config.eq_low_shelf_db) > 0.01:
        plugins.append(
            LowShelfFilter(cutoff_frequency_hz=120.0, gain_db=float(config.eq_low_shelf_db))
        )
    if abs(config.eq_low_mid_db) > 0.01:
        plugins.append(
            PeakFilter(cutoff_frequency_hz=400.0, gain_db=float(config.eq_low_mid_db), q=1.0)
        )
    if abs(config.eq_high_mid_db) > 0.01:
        plugins.append(
            PeakFilter(cutoff_frequency_hz=1500.0, gain_db=float(config.eq_high_mid_db), q=1.0)
        )
    if abs(config.eq_high_shelf_db) > 0.01:
        plugins.append(
            HighShelfFilter(cutoff_frequency_hz=8000.0, gain_db=float(config.eq_high_shelf_db))
        )

    # 2. Compressor (de-esser runs separately, before this in apply_effects)
    if config.compressor_enabled:
        plugins.append(
            Compressor(
                threshold_db=float(config.compressor_threshold_db),
                ratio=float(config.compressor_ratio),
                attack_ms=float(config.compressor_attack_ms),
                release_ms=float(config.compressor_release_ms),
            )
        )

    # 3. Existing tone chain
    if config.high_cut_hz > 0:
        plugins.append(LowpassFilter(cutoff_frequency_hz=float(config.high_cut_hz)))

    if abs(config.presence_db) > 0.01:
        plugins.append(
            PeakFilter(cutoff_frequency_hz=3000.0, gain_db=float(config.presence_db), q=0.9)
        )

    if config.saturation > 0:
        plugins.append(Distortion(drive_db=float(config.saturation) * 15.0))
        plugins.append(Gain(gain_db=-float(config.saturation) * 6.0))

    # 4. Chorus / Doubler (after color, before space)
    if config.chorus_enabled:
        plugins.append(
            Chorus(
                rate_hz=float(config.chorus_rate_hz),
                depth=float(config.chorus_depth),
                centre_delay_ms=float(config.chorus_centre_delay_ms),
                feedback=0.0,
                mix=float(config.chorus_mix),
            )
        )

    # 5. Spatial
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
    out = samples.astype(np.float32)

    # De-esser uses crossover, applied before the main chain
    if config.deesser_enabled:
        out = _apply_deesser(
            out,
            sr,
            threshold_db=config.deesser_threshold_db,
            ratio=config.deesser_ratio,
            freq_hz=config.deesser_freq_hz,
        )

    board = build_board(config, sr)
    if not list(board):
        return out
    return board(out, sample_rate=sr)
