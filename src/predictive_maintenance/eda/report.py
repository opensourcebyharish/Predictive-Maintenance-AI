"""Generate the Phase 1 EDA report for the C-MAPSS dataset.

Outputs (all git-committed so reviewers see everything without re-running):

* ``reports/figures/fig01..fig10*.png`` - publication-grade figures.
* ``reports/eda_summary.md``            - auto-generated Markdown summary with
  the computed tables, figure links and data-derived takeaways.

Run from the repository root (venv active)::

    python -m predictive_maintenance.eda
    python scripts/run_eda.py
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: report generation must work on servers/CI

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from predictive_maintenance import config
from predictive_maintenance.data.cmapss import (
    SENSOR_COLUMNS,
    add_rul,
    load_cmapss,
    load_rul,
)
from predictive_maintenance.data.simulator import MACHINES, run_to_failure

FIGURE_DPI = 150
TOP_SENSORS_COUNT = 9
# A sensor with std below this across all training rows is a constant column.
NEAR_CONSTANT_STD = 1e-9
TOP_CORRELATED_SHOWN = 5

TRAJECTORY_FIGURES: dict[str, str] = {
    "FD001": "fig03_sensor_trends_fd001.png",
    "FD002": "fig04_sensor_trends_fd002.png",
    "FD003": "fig05_sensor_trends_fd003.png",
    "FD004": "fig06_sensor_trends_fd004.png",
}


# --------------------------------------------------------------------------
# computation
# --------------------------------------------------------------------------

def _load_full_dataset(directory: Path) -> dict[str, pd.DataFrame]:
    return {
        dataset_id: add_rul(load_cmapss(dataset_id, "train", directory), cap=None)
        for dataset_id in config.DATASET_IDS
    }


def dataset_overview(train: dict[str, pd.DataFrame], test: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Structural overview of every subset (units, rows, lifespan, conditions)."""
    rows = []
    for dataset_id in config.DATASET_IDS:
        train_df, test_df = train[dataset_id], test[dataset_id]
        lifespan = train_df.groupby("unit")["cycle"].max()
        meta = config.DATASETS[dataset_id]
        rows.append(
            {
                "dataset": dataset_id,
                "train units": int(len(lifespan)),
                "train rows": int(len(train_df)),
                "test units": int(test_df["unit"].nunique()),
                "test rows": int(len(test_df)),
                "conditions": meta.conditions,
                "fault modes": meta.fault_modes,
                "lifespan min": int(lifespan.min()),
                "lifespan median": int(lifespan.median()),
                "lifespan max": int(lifespan.max()),
            }
        )
    return pd.DataFrame(rows)


def sensor_std_table(train: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Standard deviation of every sensor column across all rows of a subset."""
    return pd.DataFrame(
        {dataset_id: train[dataset_id][SENSOR_COLUMNS].std(ddof=0) for dataset_id in config.DATASET_IDS}
    ).T


def constant_sensors(stds: pd.DataFrame) -> dict[str, list[str]]:
    """Sensors whose readings never change within a subset (no training value)."""
    return {
        dataset_id: sorted(
            [sensor for sensor, std in row.items() if std < NEAR_CONSTANT_STD], key=_sensor_index
        )
        for dataset_id, row in stds.iterrows()
    }


def _sensor_index(sensor: str) -> int:
    return int(sensor.removeprefix("s"))


def _unit_deltas(df: pd.DataFrame) -> pd.DataFrame:
    """Per-unit sensor deltas (value - first-cycle value) plus unit-relative RUL."""
    grouped = df.groupby("unit", sort=False)
    deltas = df[SENSOR_COLUMNS] - grouped[SENSOR_COLUMNS].transform("first")
    deltas["RUL"] = grouped["cycle"].transform("max") - df["cycle"]
    return deltas


def rul_delta_correlations(df: pd.DataFrame) -> pd.Series:
    """Pearson correlation between *degradation deltas* and remaining cycles.

    Correlating raw sensor values would conflate operating-condition offsets
    with degradation; correlating per-unit deltas against RUL isolates the
    degradation trend. Returns one value per sN (NaN for constant sensors).
    """
    deltas = _unit_deltas(df)
    return deltas.corr(numeric_only=True)["RUL"].drop("RUL")


def top_corr_sensors(per_dataset_corr: dict[str, pd.Series]) -> dict[str, list[tuple[str, float]]]:
    """Top-N sensors by |corr(delta, RUL)| per dataset, ordered by value."""
    selected: dict[str, list[tuple[str, float]]] = {}
    for dataset_id, corr in per_dataset_corr.items():
        usable = corr.dropna().sort_values(ascending=False)
        selected[dataset_id] = [
            (sensor, float(value))
            for sensor, value in zip(usable.index[:TOP_SENSORS_COUNT], usable.iloc[:TOP_SENSORS_COUNT])
        ]
    return selected


# --------------------------------------------------------------------------
# figures
# --------------------------------------------------------------------------

def _apply_report_style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.grid": True,
            "grid.alpha": 0.25,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "legend.fontsize": 8,
        }
    )


def fig_lifespans(train: dict[str, pd.DataFrame], path: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    for ax, dataset_id in zip(axes.flat, config.DATASET_IDS):
        lifespan = train[dataset_id].groupby("unit")["cycle"].max()
        ax.boxplot(
            lifespan,
            vert=False,
            widths=0.5,
            patch_artist=True,
            boxprops={"facecolor": "#a8c7e7"},
            medianprops={"color": "#1f4e79", "lw": 2},
        )
        ax.scatter(lifespan, np.ones(len(lifespan)), s=4, alpha=0.25, color="#1f4e79")
        ax.set_title(f"{dataset_id} (n={len(lifespan)} engines)")
        ax.set_xlabel("engine lifespan (cycles)")
        ax.set_yticks([])
    fig.suptitle("Fig 1 - Run-to-failure lifespan per engine", fontsize=14)
    fig.savefig(path, dpi=FIGURE_DPI)
    plt.close(fig)


def fig_operating_conditions(train: dict[str, pd.DataFrame], path: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), constrained_layout=True)
    for ax, dataset_id in zip(axes.flat, config.DATASET_IDS):
        df = train[dataset_id]
        meta = config.DATASETS[dataset_id]
        ax.scatter(df["setting_1"], df["setting_2"], s=3, alpha=0.2, color="#1f4e79")
        ax.set_title(f"{dataset_id} - {meta.conditions} condition(s)")
        ax.set_xlabel("setting 1 (altitude)")
        ax.set_ylabel("setting 2 (Mach number)")
    fig.suptitle("Fig 2 - Operating-condition space of the four subsets", fontsize=14)
    fig.savefig(path, dpi=FIGURE_DPI)
    plt.close(fig)


def fig_sensor_trends(
    dataset_id: str,
    train_df: pd.DataFrame,
    selected: list[str],
    path: Path,
) -> None:
    """Mean +/-1 std of per-unit degradation deltas vs RUL for the top sensors."""
    deltas = _unit_deltas(train_df)
    agg = deltas.groupby("RUL")[SENSOR_COLUMNS].agg(["mean", "std"])

    fig, axes = plt.subplots(3, 3, figsize=(14, 10.5), constrained_layout=True)
    engines = int(train_df["unit"].nunique())
    sample_units = sorted(train_df["unit"].unique())[:6]

    for ax, sensor in zip(axes.flat, selected):
        mean, std = agg[(sensor, "mean")], agg[(sensor, "std")]
        ax.plot(mean.index, mean.values, color="#1f4e79", lw=1.8)
        ax.fill_between(mean.index, mean - std, mean + std, color="#1f4e79", alpha=0.18)
        for unit in sample_units:
            unit_index = train_df.index[train_df["unit"] == unit]
            unit_rows = deltas[deltas.index.isin(unit_index)]
            ax.plot(unit_rows["RUL"], unit_rows[sensor], color="grey", lw=0.5, alpha=0.5)
        ax.invert_xaxis()
        ax.set_title(config.sensor_label(int(sensor[1:])), fontsize=9)
        if ax is axes[2, 1]:
            ax.set_xlabel("RUL (cycles remaining)")
            ax.legend(["fleet mean \u00b11 std", "6 example engines"], loc="lower left")
        ax.tick_params(labelsize=8)
    fig.suptitle(
        f"{dataset_id}: sensor degradation vs remaining useful life "
        f"(\u0394 from first cycle; {engines} engines)",
        fontsize=13,
    )
    fig.savefig(path, dpi=FIGURE_DPI)
    plt.close(fig)


def fig_sample_units(
    train_df: pd.DataFrame,
    selected: list[str],
    path: Path,
    dataset_id: str = "FD001",
    n_units: int = 6,
) -> None:
    """Raw sensor trajectories over cycles for the first n engines."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), constrained_layout=True)
    for ax, sensor in zip(axes.flat, selected[:4]):
        for unit in range(1, n_units + 1):
            unit_df = train_df[train_df["unit"] == unit]
            ax.plot(unit_df["cycle"], unit_df[sensor], lw=1, alpha=0.85)
        ax.set_title(config.sensor_label(int(sensor[1:])))
        ax.set_xlabel("cycle")
    fig.suptitle(f"{dataset_id}: first {n_units} engines, raw sensor trajectories", fontsize=13)
    fig.savefig(path, dpi=FIGURE_DPI)
    plt.close(fig)


def fig_constant_sensors(stds: pd.DataFrame, path: Path) -> None:
    log_std = np.log10(stds[SENSOR_COLUMNS].to_numpy(float) + 1e-12)
    fig, ax = plt.subplots(figsize=(13, 4.2), constrained_layout=True)
    image = ax.imshow(log_std, aspect="auto", cmap="viridis")
    fig.colorbar(image, ax=ax, label="\u00b2log\u2081\u2080(std)")
    for row, dataset_id in enumerate(stds.index):
        for col, sensor in enumerate(SENSOR_COLUMNS):
            if stds.loc[dataset_id, sensor] < NEAR_CONSTANT_STD:
                ax.text(
                    col,
                    row,
                    "\u22480",
                    ha="center",
                    va="center",
                    color="#ff5252",
                    fontsize=8,
                    fontweight="bold",
                )
    ax.set_xticks(range(len(SENSOR_COLUMNS)), labels=list(SENSOR_COLUMNS), rotation=90)
    ax.set_yticks(range(len(stds.index)), labels=list(stds.index))
    ax.set_title("Sensor variability per subset (\u22480 marks constant columns)", fontsize=12)
    fig.savefig(path, dpi=FIGURE_DPI)
    plt.close(fig)


def fig_correlations(per_dataset_corr: dict[str, pd.Series], path: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), constrained_layout=True)
    for ax, dataset_id in zip(axes.flat, config.DATASET_IDS):
        corr = per_dataset_corr[dataset_id].dropna()
        corr = corr.sort_values(ascending=False)
        colors = ["#2e7d32" if value > 0 else "#c62828" for value in corr.values]
        ax.barh(corr.index, corr.values, color=colors, height=0.7)
        ax.axvline(0.0, color="black", lw=0.7)
        ax.set_title(f"{dataset_id}")
        ax.set_xlabel("corr(\u0394sensor, RUL)")
        ax.invert_yaxis()
        ax.tick_params(labelsize=7)
    fig.suptitle("Which sensors actually degrade? (\u0394 vs RUL correlation)", fontsize=13)
    fig.savefig(path, dpi=FIGURE_DPI)
    plt.close(fig)


def fig_simulator_fleet(path: Path) -> None:
    """Overview of the Phase 1 IoT simulator: full lifecycles of the fleet."""
    channels: tuple[tuple[str, str], ...] = (
        ("temperature_c", "temperature (\u00b0C)"),
        ("vibration_mm_s", "vibration (mm/s)"),
        ("pressure_bar", "pressure (bar)"),
        ("rpm", "RPM"),
    )
    colors = ("#1f4e79", "#2e7d32", "#c62828")

    fig, axes = plt.subplots(2, 2, figsize=(12, 7), constrained_layout=True)
    for machine_index, profile in enumerate(MACHINES):
        history = readings_to_dataframe(run_to_failure(profile))
        history["life_fraction"] = (history["step"] + 1) / len(history)
        for ax, (channel, label) in zip(axes.flat, channels):
            ax.plot(
                history["life_fraction"],
                history[channel],
                lw=1.2,
                color=colors[machine_index],
                label=profile.machine_id,
            )
            ax.set_ylabel(label, fontsize=8)
            ax.tick_params(labelsize=8)
    axes[0, 0].legend(loc="upper left")
    axes[1, 1].set_xlabel("life fraction (0 = healthy start, 1 = failure)")
    fig.suptitle("Phase 1 IoT simulator: three machines, run-to-failure", fontsize=13)
    fig.savefig(path, dpi=FIGURE_DPI)
    plt.close(fig)


# --------------------------------------------------------------------------
# markdown report
# --------------------------------------------------------------------------

def _md_table(frame: pd.DataFrame) -> str:
    def fmt(value: object) -> str:
        if isinstance(value, float):
            if pd.isna(value):
                return "\u2014"
            text = f"{value:.3f}".rstrip("0").rstrip(".")
            return text if text not in {"-0", ""} else "0"
        return str(value)

    header = "| " + " | ".join(str(col) for col in frame.columns) + " |"
    separator = "|" + "|".join(["---"] * len(frame.columns)) + "|"
    rows = ["| " + " | ".join(fmt(v) for v in row) + " |" for _, row in frame.iterrows()]
    return "\n".join([header, separator, *rows])


def _corr_table(selected: dict[str, list[tuple[str, float]]]) -> pd.DataFrame:
    rows = {
        dataset_id: [f"{sensor} ({value:+.2f})" for sensor, value in pairs[:TOP_CORRELATED_SHOWN]]
        for dataset_id, pairs in selected.items()
    }
    return pd.DataFrame(rows)


def build_markdown_report(
    overview: pd.DataFrame,
    constants: dict[str, list[str]],
    selected: dict[str, list[tuple[str, float]]],
    figures: list[str],
) -> str:
    """Assemble ``reports/eda_summary.md`` from computed artefacts."""
    corr_table = _corr_table(selected)
    constant_rows = pd.DataFrame(
        [
            {
                "dataset": dataset_id,
                "constant sensors": ", ".join(values) if values else "\u2014",
                "count": len(values),
            }
            for dataset_id, values in constants.items()
        ]
    )

    top3 = [dict(pairs[:3]) for pairs in selected.values()]
    shared = [sensor for sensor in top3[0] if all(sensor in d for d in top3[1:])]

    lines = [
        "# C-MAPSS exploratory data analysis (Phase 1)",
        "",
        f"Generated automatically by `python -m predictive_maintenance.eda` on {date.today().isoformat()}.",
        "All numbers below are computed from the downloaded dataset - nothing is hand-typed.",
        "",
        "## Dataset overview",
        "",
        _md_table(overview),
        "",
        "Fig 2 (operating-condition space) visualises the *conditions* column.",
        "",
        "## Constant (non-informative) sensors",
        "",
        "Sensors with zero variance carry no degradation signal; Phase 2's preprocessing",
        "pipeline will drop them per subset before scaling.",
        "",
        _md_table(constant_rows),
        "",
        "## Sensors that degrade (delta vs RUL correlation)",
        "",
        "Correlating each sensor's change from its first cycle against engine RUL ranks",
        "channels by degradation informativeness:",
        "",
        _md_table(corr_table),
        "",
        f"Sensors in the top-3 for every subset: {', '.join(shared) if shared else '(none shared by all four)'}.",
        "",
        "## Figures",
        "",
        *[f"![{name}](figures/{name})" for name in figures],
        "",
        "## Methods and caveats",
        "",
        "- **RUL** here is *uncapped* (lifespan - cycle) because degradation analysis wants the",
        "  full range; model training in Phase 2 will apply the standard 130-cycle cap.",
        "- Degradation values are *per-unit deltas from the first cycle*: raw sensor levels mix",
        "  operating-condition offsets with degradation, deltas do not.",
        "- Correlation is a linear screen only - non-monotonic or condition-dependent channels",
        "  need the Phase 2 feature engineering to surface.",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# orchestration
# --------------------------------------------------------------------------

def main(
    data_directory: Path = config.CMAPSS_DATA_DIR,
    figures_dir: Path = config.FIGURES_DIR,
    report_path: Path = config.REPORTS_DIR / "eda_summary.md",
) -> int:
    """Run the whole EDA pass; returns a process exit code."""
    try:
        train_raw = {ds: load_cmapss(ds, "train", data_directory) for ds in config.DATASET_IDS}
        test_raw = {ds: load_cmapss(ds, "test", data_directory) for ds in config.DATASET_IDS}
        rul_labels = {ds: load_rul(ds, data_directory) for ds in config.DATASET_IDS}
    except FileNotFoundError as error:
        print(f"[eda] dataset not available yet: {error}")
        return 1
    except ValueError as error:
        print(f"[eda] unexpected dataset format: {error}")
        return 1

    figures_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    _apply_report_style()

    train = {ds: add_rul(df, cap=None) for ds, df in train_raw.items()}
    overview = dataset_overview(train, test_raw)
    stds = sensor_std_table(train)
    constants = constant_sensors(stds)
    per_dataset_corr = {ds: rul_delta_correlations(train[ds]) for ds in config.DATASET_IDS}
    selected = top_corr_sensors(per_dataset_corr)

    figures: list[str] = []

    def save(builder, path: Path) -> Path:
        builder(path)
        figures.append(path.name)
        return path

    save(fig_lifespans, figures_dir / "fig01_lifespans.png")
    save(fig_operating_conditions, figures_dir / "fig02_operating_conditions.png")
    for ds in config.DATASET_IDS:
        selected_sensors = [sensor for sensor, _ in selected[ds]]
        save(
            lambda p, ds=ds, sensors=selected_sensors: fig_sensor_trends(ds, train[ds], sensors, p),
            figures_dir / TRAJECTORY_FIGURES[ds],
        )
    save(
        lambda p: fig_sample_units(train["FD001"], [s for s, _ in selected["FD001"]], p),
        figures_dir / "fig07_sample_units_fd001.png",
    )
    save(fig_constant_sensors, figures_dir / "fig08_constant_sensors.png")
    save(fig_correlations, figures_dir / "fig09_delta_rul_correlations.png")
    save(fig_simulator_fleet, figures_dir / "fig10_simulator_fleet.png")

    markdown = build_markdown_report(overview, constants, selected, figures)
    report_path.write_text(markdown, encoding="utf-8")

    # Sanity echo: test-set labels must line up with the official unit counts.
    for ds in config.DATASET_IDS:
        expected = config.DATASETS[ds].n_test_units
        actual = len(rul_labels[ds])
        if actual != expected:
            print(f"[eda] WARNING: RUL_{ds}: {actual} labels, readme says {expected} engines.")
        actual_units = int(test_raw[ds]["unit"].nunique())
        if actual_units != expected:
            print(f"[eda] WARNING: test_{ds}: {actual_units} engines, readme says {expected}.")

    total_engines = int(overview["train units"].sum())
    print(
        f"[eda] report: {report_path} ({len(figures)} figures). "
        f"{total_engines} engines across {len(config.DATASET_IDS)} subsets; "
        f"top degrading sensors: {', '.join(s for s, _ in selected['FD001'][:3])} (FD001)."
    )
    return 0
