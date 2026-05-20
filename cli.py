"""CLI entrypoint. Usage:

  python cli.py --input in.wav --output out.wav --preset natural
"""

from __future__ import annotations

from pathlib import Path

import click

from vo_fix.effects import EffectsConfig
from vo_fix.humanize import HumanizeConfig
from vo_fix.pipeline import PRESETS, ProcessConfig, get_preset, process


@click.command()
@click.option("--input", "-i", "input_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--output", "-o", "output_path", required=True, type=click.Path(dir_okay=False))
@click.option(
    "--preset",
    type=click.Choice(list(PRESETS.keys())),
    default="natural",
    help="Starting preset. Other flags override its values.",
)
@click.option("--jitter-cents", type=float, default=None, help="Pitch jitter stddev in cents")
@click.option("--shimmer", type=float, default=None, help="Amplitude jitter (0-0.1)")
@click.option("--vibrato-depth", type=float, default=None, help="Added vibrato depth in cents")
@click.option("--vibrato-rate", type=float, default=None, help="Added vibrato rate in Hz")
@click.option("--high-cut", type=float, default=None, help="High-frequency cutoff Hz (0 disables)")
@click.option("--saturation", type=float, default=None, help="Saturation drive (0-1)")
@click.option("--reverb-mix", type=float, default=None, help="Reverb wet (0-1)")
@click.option("--reverb-room", type=float, default=None, help="Reverb room size (0-1)")
@click.option("--presence-db", type=float, default=None, help="3 kHz peak boost (dB)")
@click.option("--target-sr", type=int, default=None, help="Target sample rate")
@click.option("--rx-denoise", type=float, default=None, help="RX Voice De-noise reduction in dB (0-20). Enables the module.")
@click.option("--rx-declick", type=float, default=None, help="RX De-click sensitivity (0.5-10). Enables the module.")
@click.option("--rx-plugin-dir", type=click.Path(file_okay=False), default=None, help="Override iZotope VST3 directory")
# --- Multi-band EQ (in dB, 0 = flat) ---
@click.option("--eq-low-shelf", type=float, default=None, help="EQ low shelf @120Hz (dB). + = warmer, - = thinner")
@click.option("--eq-low-mid", type=float, default=None, help="EQ peak @400Hz (dB). - = clear muddiness")
@click.option("--eq-high-mid", type=float, default=None, help="EQ peak @1.5kHz (dB). + = upfront")
@click.option("--eq-high-shelf", type=float, default=None, help="EQ high shelf @8kHz (dB). + = airy")
# --- Compressor ---
@click.option("--comp", is_flag=True, help="Enable compressor with default settings")
@click.option("--comp-threshold", type=float, default=None, help="Compressor threshold (dB, default -18)")
@click.option("--comp-ratio", type=float, default=None, help="Compressor ratio (default 3.0)")
@click.option("--comp-attack", type=float, default=None, help="Compressor attack (ms, default 5)")
@click.option("--comp-release", type=float, default=None, help="Compressor release (ms, default 80)")
# --- De-esser ---
@click.option("--deess", is_flag=True, help="Enable de-esser")
@click.option("--deess-freq", type=float, default=None, help="De-esser frequency (Hz, default 6500)")
@click.option("--deess-threshold", type=float, default=None, help="De-esser threshold (dB, default -25)")
@click.option("--deess-ratio", type=float, default=None, help="De-esser ratio (default 4.0)")
# --- Chorus / Doubler ---
@click.option("--chorus", is_flag=True, help="Enable chorus/doubler")
@click.option("--chorus-rate", type=float, default=None, help="Chorus rate (Hz, default 0.8)")
@click.option("--chorus-depth", type=float, default=None, help="Chorus depth 0-1 (default 0.25)")
@click.option("--chorus-mix", type=float, default=None, help="Chorus mix 0-1 (default 0.3)")
@click.option("--rvc-model", type=click.Path(exists=True, dir_okay=False), default=None)
@click.option("--rvc-index", type=click.Path(exists=True, dir_okay=False), default=None)
@click.option("--rvc-pitch", type=float, default=0.0, help="RVC pitch shift in semitones")
@click.option("--seed", type=int, default=None)
@click.option("--no-humanize", is_flag=True)
@click.option("--no-effects", is_flag=True)
def main(
    input_path: str,
    output_path: str,
    preset: str,
    jitter_cents: float | None,
    shimmer: float | None,
    vibrato_depth: float | None,
    vibrato_rate: float | None,
    high_cut: float | None,
    saturation: float | None,
    reverb_mix: float | None,
    reverb_room: float | None,
    presence_db: float | None,
    target_sr: int | None,
    rx_denoise: float | None,
    rx_declick: float | None,
    rx_plugin_dir: str | None,
    eq_low_shelf: float | None,
    eq_low_mid: float | None,
    eq_high_mid: float | None,
    eq_high_shelf: float | None,
    comp: bool,
    comp_threshold: float | None,
    comp_ratio: float | None,
    comp_attack: float | None,
    comp_release: float | None,
    deess: bool,
    deess_freq: float | None,
    deess_threshold: float | None,
    deess_ratio: float | None,
    chorus: bool,
    chorus_rate: float | None,
    chorus_depth: float | None,
    chorus_mix: float | None,
    rvc_model: str | None,
    rvc_index: str | None,
    rvc_pitch: float,
    seed: int | None,
    no_humanize: bool,
    no_effects: bool,
) -> None:
    cfg = get_preset(preset)
    # Patch overrides
    h = cfg.humanize
    e = cfg.effects
    if jitter_cents is not None:
        h.jitter_cents = jitter_cents
    if shimmer is not None:
        h.shimmer = shimmer
    if vibrato_depth is not None:
        h.vibrato_depth_cents = vibrato_depth
    if vibrato_rate is not None:
        h.vibrato_rate_hz = vibrato_rate
    if seed is not None:
        h.seed = seed
    if high_cut is not None:
        e.high_cut_hz = high_cut
    if saturation is not None:
        e.saturation = saturation
    if reverb_mix is not None:
        e.reverb_mix = reverb_mix
    if reverb_room is not None:
        e.reverb_room = reverb_room
    if presence_db is not None:
        e.presence_db = presence_db
    if target_sr is not None:
        cfg.target_sr = target_sr
    if rx_denoise is not None:
        cfg.rx.voice_denoise_enabled = True
        cfg.rx.voice_denoise_reduction_db = rx_denoise
    if rx_declick is not None:
        cfg.rx.declick_enabled = True
        cfg.rx.declick_sensitivity = rx_declick
    if rx_plugin_dir:
        cfg.rx.plugin_dir = rx_plugin_dir

    # Multi-band EQ
    if eq_low_shelf is not None:
        e.eq_low_shelf_db = eq_low_shelf
    if eq_low_mid is not None:
        e.eq_low_mid_db = eq_low_mid
    if eq_high_mid is not None:
        e.eq_high_mid_db = eq_high_mid
    if eq_high_shelf is not None:
        e.eq_high_shelf_db = eq_high_shelf

    # Compressor
    if comp or any(x is not None for x in (comp_threshold, comp_ratio, comp_attack, comp_release)):
        e.compressor_enabled = True
    if comp_threshold is not None:
        e.compressor_threshold_db = comp_threshold
    if comp_ratio is not None:
        e.compressor_ratio = comp_ratio
    if comp_attack is not None:
        e.compressor_attack_ms = comp_attack
    if comp_release is not None:
        e.compressor_release_ms = comp_release

    # De-esser
    if deess or any(x is not None for x in (deess_freq, deess_threshold, deess_ratio)):
        e.deesser_enabled = True
    if deess_freq is not None:
        e.deesser_freq_hz = deess_freq
    if deess_threshold is not None:
        e.deesser_threshold_db = deess_threshold
    if deess_ratio is not None:
        e.deesser_ratio = deess_ratio

    # Chorus
    if chorus or any(x is not None for x in (chorus_rate, chorus_depth, chorus_mix)):
        e.chorus_enabled = True
    if chorus_rate is not None:
        e.chorus_rate_hz = chorus_rate
    if chorus_depth is not None:
        e.chorus_depth = chorus_depth
    if chorus_mix is not None:
        e.chorus_mix = chorus_mix

    if rvc_model:
        cfg.rvc_model_path = rvc_model
        cfg.rvc_index_path = rvc_index
        cfg.rvc_pitch_semitones = rvc_pitch
    cfg.skip_humanize = no_humanize
    cfg.skip_effects = no_effects

    click.echo(f"Processing {input_path} -> {output_path} (preset={preset})")
    out = process(input_path, output_path, cfg)
    click.echo(f"Wrote {out}")


if __name__ == "__main__":
    main()
