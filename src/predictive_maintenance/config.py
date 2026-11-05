"""Project-wide configuration: paths, C-MAPSS dataset metadata, column names.

Every module resolves its inputs/outputs through this file so that the package
layout can change in one place only.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------

# src/predictive_maintenance/config.py -> the project root.
ROOT: Path = Path(__file__).resolve().parents[2]

DATA_DIR: Path = ROOT / "data"
RAW_DATA_DIR: Path = DATA_DIR / "raw"
# Where the 13 C-MAPSS text files end up after ``scripts/download_data.py``.
CMAPSS_DATA_DIR: Path = RAW_DATA_DIR / "CMAPSSData"
PROCESSED_DATA_DIR: Path = DATA_DIR / "processed"

REPORTS_DIR: Path = ROOT / "reports"
FIGURES_DIR: Path = REPORTS_DIR / "figures"

# Phase 2: trained Isolation Forest / XGBoost artefacts.
MODELS_DIR: Path = ROOT / "models"

# --------------------------------------------------------------------------
# dataset structure
# --------------------------------------------------------------------------

DATASET_IDS: tuple[str, ...] = ("FD001", "FD002", "FD003", "FD004")

# The standard piecewise-linear RUL cap used in the RUL-prediction literature.
RUL_CAP: int = 130


@dataclass(frozen=True)
class DatasetMeta:
    """Structural metadata of one C-MAPSS subset (per the official readme)."""

    dataset_id: str
    conditions: str  # distinct operating-condition regimes
    fault_modes: str  # simulated degradation mode(s)
    train_units: int  # run-to-failure engines in the training split
    test_units: int  # engines in the test split (= rows in RUL_<id>.txt)


# Counts come from the official CMAPSSData readme; the EDA pipeline warns when
# the actual files disagree (data is authoritative, metadata gets fixed).
DATASETS: dict[str, DatasetMeta] = {
    meta.dataset_id: meta
    for meta in (
        DatasetMeta("FD001", "ONE (Sea Level)", "ONE (HPC Degradation)", 100, 100),
        DatasetMeta("FD002", "SIX", "ONE (HPC Degradation)", 260, 259),
        DatasetMeta("FD003", "ONE (Sea Level)", "TWO (HPC + Fan Degradation)", 100, 100),
        DatasetMeta("FD004", "SIX", "TWO (HPC + Fan Degradation)", 249, 248),
    )
}

# --------------------------------------------------------------------------
# C-MAPSS sensor naming (columns 6..26 of the raw files are sensors s1..s21)
# --------------------------------------------------------------------------

# Official "Sensor Signal Descriptions" from the C-MAPSS readme.
SENSOR_LABELS: dict[int, str] = {
    1: "T2 fan-inlet temperature (R)",
    2: "T24 LPC-outlet temperature (R)",
    3: "T30 HPC-outlet temperature (R)",
    4: "T50 LPT-outlet temperature (R)",
    5: "P2 fan-inlet pressure (psia)",
    6: "P15 bypass-duct pressure (psia)",
    7: "P30 HPC-outlet pressure (psia)",
    8: "Nf physical fan speed (rpm)",
    9: "Nc physical core speed (rpm)",
    10: "epr engine pressure ratio (epr)",
    11: "Ps30 static HPC-outlet pressure (psia)",
    12: "phi fuel-flow / Ps30 (pps/psi)",
    13: "NRf corrected fan speed (rpm)",
    14: "NRc corrected core speed (rpm)",
    15: "BPR bypass ratio",
    16: "farB burner fuel-air ratio",
    17: "Bleed bleed enthalpy",
    18: "Nf_dmd demanded corrected fan speed (rpm)",
    19: "PCNfR_dmd demanded corrected fan speed (rpm)",
    20: "W31 HPT coolant bleed (lbm/s)",
    21: "W32 LPT coolant bleed (lbm/s)",
}


def sensor_label(sensor_index: int) -> str:
    """Human-readable label for sensor ``s<index>``, e.g. ``s3 T30 ...``."""
    try:
        return f"s{sensor_index} {SENSOR_LABELS[sensor_index]}"
    except KeyError as error:  # pragma: no cover - never hit by valid metadata
        raise ValueError(f"Unknown C-MAPSS sensor index: {sensor_index}") from error
