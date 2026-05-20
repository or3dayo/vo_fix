"""Orchestrates: load -> [RX clean] -> [RVC] -> humanize -> effects -> save."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .effects import EffectsConfig, apply_effects
from .humanize import HumanizeConfig, humanize
from .io import load_wav, save_wav
from .vocal_processing import VocalProcessingConfig, apply as apply_vocal_processing

logger = logging.getLogger(__name__)


@dataclass
class RXConfig:
    """iZotope RX pre-processing. Off by default — opt-in per module."""

    voice_denoise_enabled: bool = False
    voice_denoise_reduction_db: float = 6.0
    """0–20 dB. 6 is gentle, 10 is moderate, 15+ can sound processed."""

    voice_denoise_adaptive: bool = True
    declick_enabled: bool = False
    declick_sensitivity: float = 3.0
    """0.5–10. Lower = less aggressive."""

    plugin_dir: str | None = None


@dataclass
class ProcessConfig:
    humanize: HumanizeConfig = field(default_factory=HumanizeConfig)
    effects: EffectsConfig = field(default_factory=EffectsConfig)
    vocal: VocalProcessingConfig = field(default_factory=VocalProcessingConfig)
    rx: RXConfig = field(default_factory=RXConfig)
    rvc_model_path: str | None = None
    rvc_index_path: str | None = None
    rvc_pitch_semitones: float = 0.0
    target_sr: int = 44100
    skip_humanize: bool = False
    skip_effects: bool = False


PRESETS: dict[str, ProcessConfig] = {
    "off": ProcessConfig(skip_humanize=True, skip_effects=True),
    "natural": ProcessConfig(
        humanize=HumanizeConfig(jitter_cents=8.0, shimmer=0.03),
        effects=EffectsConfig(
            high_cut_hz=9000, saturation=0.15, reverb_mix=0.08, presence_db=0.5
        ),
    ),
    "intimate": ProcessConfig(
        humanize=HumanizeConfig(
            jitter_cents=12.0, shimmer=0.05, vibrato_depth_cents=6.0
        ),
        effects=EffectsConfig(
            high_cut_hz=8500, saturation=0.2, reverb_mix=0.15, reverb_room=0.5
        ),
    ),
    "polished": ProcessConfig(
        humanize=HumanizeConfig(jitter_cents=4.0, shimmer=0.02),
        effects=EffectsConfig(
            high_cut_hz=10000, saturation=0.08, reverb_mix=0.05, presence_db=1.0
        ),
    ),
}


def get_preset(name: str) -> ProcessConfig:
    if name not in PRESETS:
        raise ValueError(f"Unknown preset: {name}. Choose from {list(PRESETS)}")
    return PRESETS[name]


def apply_rx(samples: np.ndarray, sr: int, config: RXConfig) -> np.ndarray:
    """Run RX cleaning plugins. Returns samples unchanged if RX unavailable.

    We deliberately swallow load/auth failures here — RX is opt-in and the
    pipeline should keep working if a user enables RX without having it
    installed, just with a warning.
    """
    if not (config.voice_denoise_enabled or config.declick_enabled):
        return samples

    from pedalboard import Pedalboard

    from . import vst

    found = vst.find_rx_plugins(config.plugin_dir)
    plugins = []
    if config.voice_denoise_enabled:
        path = found.get("voice_denoise")
        if path is None:
            logger.warning("Voice De-noise enabled but plugin not found in %s", config.plugin_dir or vst.DEFAULT_RX_DIR)
        else:
            try:
                plugins.append(
                    vst.get_voice_denoise(
                        path,
                        reduction_db=config.voice_denoise_reduction_db,
                        adaptive=config.voice_denoise_adaptive,
                    )
                )
            except Exception as e:
                logger.warning("Voice De-noise load failed: %s", e)

    if config.declick_enabled:
        path = found.get("declick")
        if path is None:
            logger.warning("De-click enabled but plugin not found")
        else:
            try:
                plugins.append(
                    vst.get_declick(path, sensitivity=config.declick_sensitivity)
                )
            except Exception as e:
                logger.warning("De-click load failed: %s", e)

    if not plugins:
        return samples

    board = Pedalboard(plugins)
    return board(samples.astype(np.float32), sample_rate=sr)


def process_array(samples: np.ndarray, sr: int, config: ProcessConfig) -> tuple[np.ndarray, int]:
    """Run the pipeline on an in-memory array. Returns (samples, sr)."""
    out = samples
    cur_sr = sr

    # RX cleaning must come BEFORE humanize: we want pyworld's f0 estimator
    # to see clean audio, and we don't want denoise to remove the jitter we
    # add later.
    out = apply_rx(out, cur_sr, config.rx)

    if config.rvc_model_path:
        from .rvc import apply_rvc

        out, cur_sr = apply_rvc(
            out,
            cur_sr,
            model_path=config.rvc_model_path,
            index_path=config.rvc_index_path,
            pitch_semitones=config.rvc_pitch_semitones,
            target_sr=config.target_sr,
        )

    if cur_sr != config.target_sr:
        import librosa

        out = librosa.resample(out, orig_sr=cur_sr, target_sr=config.target_sr)
        cur_sr = config.target_sr

    if not config.skip_humanize:
        out = humanize(out, cur_sr, config.humanize)

    # Sample-domain vocal processing (consonant shaping + breath insertion)
    # sits between humanize and the effects chain so the inserted breaths
    # get the same EQ / reverb treatment as the voice.
    out = apply_vocal_processing(out, cur_sr, config.vocal)

    if not config.skip_effects:
        out = apply_effects(out, cur_sr, config.effects)

    return out.astype(np.float32), cur_sr


def process(
    input_path: str | Path, output_path: str | Path, config: ProcessConfig | None = None
) -> Path:
    cfg = config or get_preset("natural")
    samples, sr = load_wav(input_path, target_sr=cfg.target_sr)
    out, out_sr = process_array(samples, sr, cfg)
    save_wav(output_path, out, out_sr)
    return Path(output_path)
