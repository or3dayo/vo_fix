"""User preset persistence: save/load/list/delete to JSON files.

Storage location:
- Default: ``~/.vo_fix/presets/<name>.json``
- Override via ``VO_FIX_PRESETS_DIR`` env var (mostly for tests)

We persist the full ProcessConfig (humanize + effects + rx) so the user
can restore an exact reproduction. Built-in presets (off/natural/etc.)
remain code-defined; user presets live on disk and are merged into the
dropdown at runtime.
"""

from __future__ import annotations

import json
import logging
import os
import re
import zipfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .effects import EffectsConfig
from .humanize import HumanizeConfig
from .pipeline import PRESETS, ProcessConfig, RXConfig

logger = logging.getLogger(__name__)

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_\-]+")


def _presets_dir() -> Path:
    override = os.environ.get("VO_FIX_PRESETS_DIR")
    if override:
        return Path(override)
    return Path.home() / ".vo_fix" / "presets"


def get_presets_dir() -> Path:
    """Public accessor so the UI can show users where presets live."""
    return _presets_dir()


def safe_filename(name: str) -> str:
    """Map an arbitrary display name to a filesystem-safe stem.

    Japanese / Unicode names are kept as-is on most filesystems, but we
    replace path-hostile chars (slashes, colons, control chars) with `_`.
    """
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("Preset name must not be empty")
    cleaned = cleaned.replace("/", "_").replace("\\", "_")
    cleaned = cleaned.replace(":", "_").replace("*", "_")
    cleaned = cleaned.replace("?", "_").replace('"', "_")
    cleaned = cleaned.replace("<", "_").replace(">", "_").replace("|", "_")
    # Drop control chars
    cleaned = "".join(c for c in cleaned if c.isprintable())
    return cleaned[:80]  # filesystem-friendly length


def list_user_presets() -> list[str]:
    """Return the list of user preset display names, sorted."""
    d = _presets_dir()
    if not d.exists():
        return []
    names: list[str] = []
    for f in d.glob("*.json"):
        try:
            with f.open(encoding="utf-8") as fh:
                data = json.load(fh)
            display_name = data.get("display_name") or f.stem
            names.append(display_name)
        except Exception as e:
            logger.warning("Skipping unreadable preset %s: %s", f, e)
    return sorted(names)


def save_user_preset(name: str, config: ProcessConfig) -> Path:
    """Serialize a ProcessConfig to disk under `name`. Returns the path."""
    safe = safe_filename(name)
    d = _presets_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{safe}.json"
    payload = {
        "display_name": name,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "config": {
            "humanize": asdict(config.humanize),
            "effects": asdict(config.effects),
            "rx": asdict(config.rx),
            "target_sr": config.target_sr,
            "skip_humanize": config.skip_humanize,
            "skip_effects": config.skip_effects,
        },
    }
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return path


def load_user_preset(name: str) -> ProcessConfig:
    """Reconstruct a ProcessConfig from disk. Raises FileNotFoundError if missing."""
    safe = safe_filename(name)
    path = _presets_dir() / f"{safe}.json"
    if not path.exists():
        # Try looking up by display_name (in case the file stem differs)
        for f in _presets_dir().glob("*.json"):
            try:
                with f.open(encoding="utf-8") as fh:
                    data = json.load(fh)
                if data.get("display_name") == name:
                    path = f
                    break
            except Exception:
                continue
        else:
            raise FileNotFoundError(f"User preset not found: {name}")

    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)

    cfg_data = data["config"]
    return ProcessConfig(
        humanize=HumanizeConfig(**cfg_data["humanize"]),
        effects=EffectsConfig(**cfg_data["effects"]),
        rx=RXConfig(**cfg_data["rx"]),
        target_sr=cfg_data.get("target_sr", 44100),
        skip_humanize=cfg_data.get("skip_humanize", False),
        skip_effects=cfg_data.get("skip_effects", False),
    )


def delete_user_preset(name: str) -> bool:
    """Delete a user preset. Returns True if removed, False if missing."""
    safe = safe_filename(name)
    path = _presets_dir() / f"{safe}.json"
    if path.exists():
        path.unlink()
        return True
    # Lookup by display_name
    for f in _presets_dir().glob("*.json"):
        try:
            with f.open(encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("display_name") == name:
                f.unlink()
                return True
        except Exception:
            continue
    return False


def all_preset_names() -> list[str]:
    """Built-in + user preset names, with user ones prefixed by 'user: '."""
    return list(PRESETS.keys()) + [f"user: {n}" for n in list_user_presets()]


def export_all_presets(output_path: str | Path) -> Path:
    """Zip every preset JSON under the presets dir into one archive.

    Returns the path to the archive. The zip is flat (no nested dirs).
    If no presets exist, an empty archive is still produced so the user
    has a placeholder file they can use to confirm "yes the system saw
    zero presets" (vs. "I don't know if anything ran").
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    src = _presets_dir()
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if src.exists():
            for f in sorted(src.glob("*.json")):
                zf.write(f, arcname=f.name)
    return output_path


def import_presets(
    archive_path: str | Path, *, overwrite: bool = False
) -> tuple[int, int]:
    """Restore presets from a zip created by export_all_presets.

    Returns (imported, skipped). `skipped` counts files that already
    existed and were not overwritten.
    """
    archive_path = Path(archive_path)
    if not archive_path.exists():
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    dest = _presets_dir()
    dest.mkdir(parents=True, exist_ok=True)
    imported = 0
    skipped = 0
    with zipfile.ZipFile(archive_path, "r") as zf:
        for name in zf.namelist():
            # Strip any directory components from the archive path to
            # prevent path-traversal from a maliciously crafted zip.
            base = Path(name).name
            if not base.endswith(".json"):
                continue
            target = dest / base
            if target.exists() and not overwrite:
                skipped += 1
                continue
            with zf.open(name) as src_f, target.open("wb") as dst_f:
                dst_f.write(src_f.read())
            imported += 1
    return imported, skipped


def resolve_preset(name: str) -> ProcessConfig:
    """Look up a preset by name. Accepts 'user: foo' or built-in names."""
    if name.startswith("user: "):
        return load_user_preset(name[len("user: ") :])
    if name in PRESETS:
        # Return a copy so the caller can mutate without affecting the canonical
        base = PRESETS[name]
        return ProcessConfig(
            humanize=HumanizeConfig(**asdict(base.humanize)),
            effects=EffectsConfig(**asdict(base.effects)),
            rx=RXConfig(**asdict(base.rx)),
            target_sr=base.target_sr,
            skip_humanize=base.skip_humanize,
            skip_effects=base.skip_effects,
        )
    raise KeyError(f"Unknown preset: {name}")
