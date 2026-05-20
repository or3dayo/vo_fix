"""iZotope RX VST3 integration via pedalboard.

We treat RX modules as optional pre-processing — if not installed or not
authorized, the pipeline skips them with a warning rather than crashing.

Loading a VST3 plugin takes ~1 second. We cache instances per-path so
repeated UI runs don't re-load. Pedalboard plugins keep internal state
(noise profile, filter history), so we call `reset()` before each use.
"""

from __future__ import annotations

import logging
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def _default_rx_dirs() -> list[Path]:
    """Standard iZotope VST3 install locations by OS.

    Multiple paths can be returned (e.g. macOS has both system-wide and
    user-local plugin folders). They are searched in order, first match wins.
    """
    if sys.platform == "win32":
        return [Path(r"C:\Program Files\Common Files\VST3\iZotope")]
    if sys.platform == "darwin":
        return [
            Path("/Library/Audio/Plug-Ins/VST3/iZotope"),
            Path.home() / "Library" / "Audio" / "Plug-Ins" / "VST3" / "iZotope",
        ]
    # Linux: RX doesn't officially support it, but allow a sane override target
    return [
        Path.home() / ".vst3" / "iZotope",
        Path("/usr/lib/vst3/iZotope"),
    ]


DEFAULT_RX_DIRS: list[Path] = _default_rx_dirs()

#: Primary default for display / single-path callers. macOS/Linux may have
#: additional fall-back paths in :data:`DEFAULT_RX_DIRS`.
DEFAULT_RX_DIR: Path = DEFAULT_RX_DIRS[0]

KNOWN_RX_MODULES = {
    "voice_denoise": "RX 8 Voice De-noise.vst3",
    "declick": "RX 8 De-click.vst3",
    "declip": "RX 8 De-clip.vst3",
    "dehum": "RX 8 De-hum.vst3",
}


def _scan_one_dir(base: Path) -> dict[str, Path]:
    """Look for known RX modules under `base`. Returns {module_key: path}."""
    found: dict[str, Path] = {}
    if not base.exists():
        return found
    for key, fname in KNOWN_RX_MODULES.items():
        p = base / fname
        if p.exists():
            found[key] = p
            continue
        # Tolerate version differences (RX 9, RX 10, RX 11)
        matched = False
        for candidate in base.glob(fname.replace("RX 8 ", "RX * ")):
            if candidate.exists():
                found[key] = candidate
                matched = True
                break
        if matched:
            continue
        # Last resort: search without any version prefix
        stem = fname.replace("RX 8 ", "").replace(".vst3", "")
        for candidate in base.glob(f"*{stem}*.vst3"):
            found[key] = candidate
            break
    return found


def find_rx_plugins(base_dir: str | Path | None = None) -> dict[str, Path]:
    """Return a dict of {module_key: full_path} for RX VST3s that exist.

    If `base_dir` is given, only that directory is scanned. Otherwise the
    OS-appropriate default locations are scanned in priority order
    (system-wide first, user-local second on macOS).
    """
    if base_dir:
        return _scan_one_dir(Path(base_dir))

    found: dict[str, Path] = {}
    for base in DEFAULT_RX_DIRS:
        for key, path in _scan_one_dir(base).items():
            # Earlier directories win — don't overwrite
            found.setdefault(key, path)
    return found


@lru_cache(maxsize=8)
def _load_cached(path_str: str):
    from pedalboard import load_plugin

    return load_plugin(path_str)


def load_plugin(path: str | Path):
    """Cached plugin loader. Returns a fresh-reset plugin instance.

    The plugin instance is shared across calls (cached), but we reset its
    state before returning so each pipeline run starts clean.
    """
    plugin = _load_cached(str(path))
    if hasattr(plugin, "reset"):
        plugin.reset()
    return plugin


def get_voice_denoise(
    path: str | Path,
    reduction_db: float = 6.0,
    master_threshold_db: float = 0.0,
    adaptive: bool = True,
):
    """Configure RX Voice De-noise. reduction_db: 0..20."""
    p = load_plugin(path)
    try:
        p.reduction = float(np.clip(reduction_db, 0.0, 20.0))
        p.master_threshold = float(np.clip(master_threshold_db, -20.0, 10.0))
        p.adaptive_mode = bool(adaptive)
    except AttributeError as e:
        logger.warning("Voice De-noise parameter set failed: %s", e)
    return p


def get_declick(
    path: str | Path,
    sensitivity: float = 3.0,
    frequency_skew: float = 0.0,
    click_widening: float = 0.0,
):
    """Configure RX De-click. sensitivity: 0.5..10."""
    p = load_plugin(path)
    try:
        p.sensitivity = float(np.clip(sensitivity, 0.5, 10.0))
        p.frequency_skew = float(np.clip(frequency_skew, -10.0, 10.0))
        p.click_widening = float(np.clip(click_widening, 0.0, 5.0))
    except AttributeError as e:
        logger.warning("De-click parameter set failed: %s", e)
    return p
