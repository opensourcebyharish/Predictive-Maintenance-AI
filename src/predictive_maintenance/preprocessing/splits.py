"""Splitting engine runs into train/validation at *engine* granularity.

Row-level random splits are forbidden for time-series run data: consecutive
cycles of the same engine are near-duplicates, so random row splits leak
future information into validation (inflated metrics). The split here allocates
*whole engines* with a seeded, deterministic permutation, so the same seed and
frame always produce the same partition.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from predictive_maintenance.preprocessing.features import ENGINE_COLUMN


def engine_group_split(
    frame: pd.DataFrame,
    *,
    test_fraction: float = 0.2,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Partition engines (never rows) into train/hold-out by seeded permutation.

    Both returned frames keep the input's row order, columns and index range;
    engine ids are disjoint and together cover the input exactly.
    """
    if not 0.0 < test_fraction < 1.0:
        raise ValueError(f"test_fraction must be in (0, 1), got {test_fraction}")
    units = np.sort(frame[ENGINE_COLUMN].unique())
    if len(units) < 2:
        raise ValueError(f"need at least 2 engines to split, got {len(units)}")
    shuffled = np.random.default_rng(seed).permutation(units)
    test_count = max(1, int(round(test_fraction * len(units))))
    test_units = set(shuffled[:test_count].tolist())
    train_mask = ~frame[ENGINE_COLUMN].isin(test_units)
    return frame[train_mask].copy(), frame[~train_mask].copy()
