"""RVC (Retrieval-based Voice Conversion) placeholder.

We intentionally don't ship RVC inside vo_fix:

- RVC requires fairseq, which has no Windows wheels and needs a full
  Visual C++ toolchain to build from source.
- The RVC ecosystem (rvc-python etc.) is unstable and lags behind the
  community forks.

Instead, the recommended workflow is:

  SUNO  ->  Applio (voice conversion)  ->  vo_fix (humanize + mix)

Applio (https://applio.org/) is a maintained one-click GUI for RVC. Run
your stem through it, save the converted wav, then feed that wav into
vo_fix for the humanization + effects polish.

If a clean pip-installable RVC alternative appears later, fill in
`apply_rvc` below and the rest of the pipeline picks it up unchanged —
the signature is intentionally stable.
"""

from __future__ import annotations

import numpy as np


def apply_rvc(
    samples: np.ndarray,
    sr: int,
    *,
    model_path: str,
    index_path: str | None = None,
    pitch_semitones: float = 0.0,
    target_sr: int = 44100,
) -> tuple[np.ndarray, int]:
    raise NotImplementedError(
        "vo_fix does not bundle RVC. Run voice conversion in Applio "
        "(https://applio.org/) and pass the converted wav into vo_fix. "
        "See README for the recommended workflow."
    )
