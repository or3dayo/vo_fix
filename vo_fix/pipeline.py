"""Orchestrates: load -> [RX clean] -> [RVC] -> humanize -> effects -> save."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .effects import EffectsConfig, apply_effects
from .humanize import HumanizeConfig, humanize
from .io import load_wav, save_wav
from .mix import MixConfig, mix_with_stems
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
    mix: MixConfig = field(default_factory=MixConfig)
    rvc_model_path: str | None = None
    rvc_index_path: str | None = None
    rvc_pitch_semitones: float = 0.0

    target_sr: int | None = None
    """Output sample rate. **None = preserve the input's sample rate.**
    Older saved presets may have 44100 here — set them to None to stop
    downsampling 48/96 kHz inputs.
    """

    output_subtype: str | None = None
    """soundfile subtype for the output wav. **None = preserve the input's
    bit depth** (e.g. PCM_24 stays PCM_24). Common explicit values:
    'PCM_16', 'PCM_24', 'FLOAT'.
    """

    skip_humanize: bool = False
    skip_effects: bool = False

    export_vocal_separately: bool = False
    """When True AND stems are mixed in, also write the pre-mix processed
    vocal as a separate file at ``<output>_vocal.<ext>``. Useful for
    keeping the vocal-only stem for later DAW work.
    """

    force_mono: bool = False
    """If True, stereo input is averaged to mono on load and output is
    mono. Default False = each channel is processed independently and
    stereo width is preserved. force_mono=True is ~2x faster for stereo
    sources.
    """


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


def _process_mono(
    samples: np.ndarray, sr: int, config: ProcessConfig
) -> tuple[np.ndarray, int]:
    """The original single-channel pipeline. Used as a building block for
    stereo via per-channel dispatch in `process_array`."""
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
            target_sr=config.target_sr or cur_sr,
        )

    if config.target_sr is not None and cur_sr != config.target_sr:
        import librosa

        out = librosa.resample(out, orig_sr=cur_sr, target_sr=config.target_sr)
        cur_sr = config.target_sr

    if not config.skip_humanize:
        out = humanize(out, cur_sr, config.humanize)

    out = apply_vocal_processing(out, cur_sr, config.vocal)

    if not config.skip_effects:
        out = apply_effects(out, cur_sr, config.effects)

    return out.astype(np.float32), cur_sr


def process_array(samples: np.ndarray, sr: int, config: ProcessConfig) -> tuple[np.ndarray, int]:
    """Run the pipeline. Returns (samples, sr).

    Accepts:
      - 1D (n,)          : mono - process directly
      - 2D (n, channels) : stereo / multi-channel - process each channel
        independently and stack back. Same RNG seed across channels so
        jitter/breath stay coherent across L and R.

    Set `config.force_mono=True` to collapse multi-channel to mono on the
    fly (~2x faster, loses stereo width).
    """
    if samples.ndim == 1:
        return _process_mono(samples, sr, config)

    if samples.ndim != 2:
        raise ValueError(f"Unsupported input array shape: {samples.shape}")

    if config.force_mono:
        # Collapse to mono and dispatch the single-channel path
        mono = samples.mean(axis=1)
        return _process_mono(mono, sr, config)

    n_channels = samples.shape[1]
    if n_channels == 1:
        # Edge case: 2D array with a single column. Treat as mono.
        out, out_sr = _process_mono(samples[:, 0], sr, config)
        return out.reshape(-1, 1), out_sr

    # Per-channel pass. We force a deterministic seed (if user didn't
    # set one) so L and R get the same jitter / vibrato / breath pattern;
    # otherwise the two channels would drift apart and sound wider than
    # intended.
    import copy

    channel_outputs: list[np.ndarray] = []
    out_sr = sr
    for ch in range(n_channels):
        ch_cfg = copy.deepcopy(config)
        if ch_cfg.humanize.seed is None:
            ch_cfg.humanize.seed = 0xC0FFEE
        if ch_cfg.vocal.breath_seed is None:
            ch_cfg.vocal.breath_seed = 0xC0FFEE
        ch_out, out_sr = _process_mono(np.ascontiguousarray(samples[:, ch]), sr, ch_cfg)
        channel_outputs.append(ch_out)

    # pyworld can produce slightly different lengths across runs due to
    # frame quantisation; clip to the shortest to keep channels aligned.
    min_len = min(len(o) for o in channel_outputs)
    stacked = np.stack([o[:min_len] for o in channel_outputs], axis=1)
    return stacked.astype(np.float32), out_sr


def _vocal_only_path(output_path: str | Path) -> Path:
    """Derive the side-car vocal-only path from the main output path.

    `out/song.wav` -> `out/song_vocal.wav`
    """
    p = Path(output_path)
    return p.with_name(f"{p.stem}_vocal{p.suffix}")


def process(
    input_path: str | Path,
    output_path: str | Path,
    config: ProcessConfig | None = None,
    vocal_only_path: str | Path | None = None,
) -> tuple[Path, Path | None]:
    """Run the full pipeline and write the result(s).

    Returns ``(main_path, vocal_only_path_actual)``.

    - ``main_path`` is always the final output (with stems mixed in if any).
    - ``vocal_only_path_actual`` is set when stems were applied AND either:
        * ``vocal_only_path`` was passed explicitly, OR
        * ``config.export_vocal_separately`` is True (path auto-derived).
      Otherwise it is None.
    """
    cfg = config or get_preset("natural")
    samples, sr, meta = load_wav(
        input_path,
        target_sr=cfg.target_sr,
        force_mono=cfg.force_mono,
    )
    out, out_sr = process_array(samples, sr, cfg)

    # Decide whether to also dump the pre-mix vocal as a separate file.
    want_vocal_only = (
        cfg.mix.enabled
        and cfg.mix.stem_paths
        and (vocal_only_path is not None or cfg.export_vocal_separately)
    )
    actual_vocal_path: Path | None = None
    if want_vocal_only:
        target = Path(vocal_only_path) if vocal_only_path else _vocal_only_path(output_path)
        save_wav(
            target,
            out,
            out_sr,
            subtype=cfg.output_subtype,
            input_subtype=meta.subtype,
        )
        actual_vocal_path = target

    # Final stage: mix in any instrumentals / STEMs the user supplied.
    out = mix_with_stems(out, out_sr, cfg.mix)

    save_wav(
        output_path,
        out,
        out_sr,
        subtype=cfg.output_subtype,
        input_subtype=meta.subtype,
    )
    return Path(output_path), actual_vocal_path
