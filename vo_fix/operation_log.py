"""Operation log: track parameter changes and conversion runs.

For an end-user, the most useful thing isn't a stream of slider events
(too noisy) but a snapshot at conversion time: "this is what I did to
get this output". We log:

- The preset selected as the starting point
- Each parameter that DIFFERS from that preset (so the user sees their
  intentional overrides)
- The output filename and basic stats

The log lives in memory per session. It's also appended to
``~/.vo_fix/logs/session-<date>.jsonl`` so users can review history later.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .pipeline import ProcessConfig

logger = logging.getLogger(__name__)


def _log_dir() -> Path:
    override = os.environ.get("VO_FIX_LOGS_DIR")
    if override:
        return Path(override)
    return Path.home() / ".vo_fix" / "logs"


def _config_to_flat(config: ProcessConfig) -> dict[str, float | bool | str | None]:
    """Flatten a ProcessConfig into a single dict for diffing."""
    flat: dict[str, float | bool | str | None] = {}
    for k, v in asdict(config.humanize).items():
        flat[f"humanize.{k}"] = v
    for k, v in asdict(config.effects).items():
        flat[f"effects.{k}"] = v
    for k, v in asdict(config.rx).items():
        flat[f"rx.{k}"] = v
    flat["target_sr"] = config.target_sr
    flat["skip_humanize"] = config.skip_humanize
    flat["skip_effects"] = config.skip_effects
    return flat


def diff_from_preset(
    preset: ProcessConfig, current: ProcessConfig
) -> dict[str, tuple]:
    """Return {param_key: (preset_value, current_value)} for differing params."""
    pre = _config_to_flat(preset)
    cur = _config_to_flat(current)
    out: dict[str, tuple] = {}
    for k in cur:
        if pre.get(k) != cur.get(k):
            out[k] = (pre.get(k), cur[k])
    return out


def format_diff_lines(diff: dict[str, tuple]) -> list[str]:
    """Pretty-print a diff dict as ['param: old -> new', ...]."""
    if not diff:
        return ["(プリセット値そのまま、上書きなし)"]
    lines = []
    for key, (old, new) in sorted(diff.items()):
        old_s = _fmt(old)
        new_s = _fmt(new)
        lines.append(f"  {key}: {old_s} → {new_s}")
    return lines


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.3g}"
    if isinstance(v, bool):
        return "ON" if v else "OFF"
    if v is None:
        return "(なし)"
    return str(v)


class OperationLog:
    """In-memory ring buffer + JSONL persistence of conversion events."""

    def __init__(self, max_entries: int = 50) -> None:
        self.max_entries = max_entries
        self.entries: list[str] = []

    def record_run(
        self,
        preset_name: str,
        preset_config: ProcessConfig,
        actual_config: ProcessConfig,
        input_path: str | None,
        output_path: str | None,
        duration_seconds: float | None,
    ) -> str:
        """Record one conversion run. Returns the human-readable log block."""
        diff = diff_from_preset(preset_config, actual_config)
        diff_lines = format_diff_lines(diff)
        timestamp = datetime.now().strftime("%H:%M:%S")
        header = (
            f"[{timestamp}] {Path(input_path).name if input_path else '(no input)'}"
            f"  preset={preset_name}"
        )
        if duration_seconds is not None:
            header += f"  ({duration_seconds:.2f}s)"
        block_lines = [header, "  --- 上書きしたパラメータ ---", *diff_lines]
        block = "\n".join(block_lines)

        # Push to in-memory ring
        self.entries.append(block)
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries :]

        # Persist as JSONL
        try:
            d = _log_dir()
            d.mkdir(parents=True, exist_ok=True)
            log_path = d / f"session-{datetime.now().strftime('%Y%m%d')}.jsonl"
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        {
                            "ts": datetime.now().isoformat(timespec="seconds"),
                            "preset": preset_name,
                            "input": input_path,
                            "output": output_path,
                            "duration_seconds": duration_seconds,
                            "diff": {k: list(v) for k, v in diff.items()},
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except Exception as e:
            logger.warning("Failed to persist log: %s", e)

        return block

    def as_text(self) -> str:
        """Render the in-memory log as a single string (newest at bottom)."""
        if not self.entries:
            return "(まだ変換していません)"
        return "\n\n".join(self.entries)

    def clear(self) -> None:
        self.entries.clear()
