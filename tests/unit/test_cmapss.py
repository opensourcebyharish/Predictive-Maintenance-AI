"""Unit tests for the C-MAPSS loaders (no real dataset, no network)."""

from __future__ import annotations

import pytest

from predictive_maintenance.data.cmapss import (
    add_rul,
    load_cmapss,
    load_rul,
    raw_cmapss_columns,
    rul_path,
    subset_path,
)


def write_cmapss_subset(
    directory,
    split: str = "train",
    dataset_id: str = "FD001",
    lifespans: tuple[int, ...] = (4, 3),
) -> None:
    """Write a miniature C-MAPSS-format table: unit, cycle, 3 settings, 21 sensors."""
    lines = []
    for unit, last_cycle in enumerate(lifespans, start=1):
        for cycle in range(1, last_cycle + 1):
            settings = [0.002, -0.003, 100.0]
            sensors = [round(cycle * index / 10.0, 4) for index in range(1, 22)]
            values = [unit, cycle, *settings, *sensors]
            lines.append(" ".join(str(v) for v in values))
    (directory / f"{split}_{dataset_id}.txt").write_text("\n".join(lines) + "\n")


def test_raw_columns_are_space_separated_26_field_layout() -> None:
    columns = raw_cmapss_columns()
    assert len(columns) == 26
    assert columns[:2] == ("unit", "cycle")
    assert columns[2:5] == ("setting_1", "setting_2", "setting_3")
    assert columns[-1] == "s21"


def test_load_cmapss_returns_named_columns(tmp_path) -> None:
    write_cmapss_subset(tmp_path)
    df = load_cmapss("FD001", "train", directory=tmp_path)

    assert list(df.columns) == list(raw_cmapss_columns())
    assert len(df) == 7  # 4 cycles + 3 cycles
    assert df["unit"].dtype == "int64"
    assert df["cycle"].dtype == "int64"
    assert not df.isna().any().any()


def test_load_cmapss_missing_file_mentions_download_step(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="download_data"):
        load_cmapss("FD004", "train", directory=tmp_path)


def test_invalid_dataset_or_split_fails_fast(tmp_path) -> None:
    with pytest.raises(ValueError, match="Unknown dataset"):
        load_cmapss("FD999", "train", directory=tmp_path)
    with pytest.raises(ValueError, match="Unknown split"):
        load_cmapss("FD001", "validation", directory=tmp_path)
    with pytest.raises(ValueError, match="Unknown dataset"):
        rul_path("FD00X")
    assert subset_path("FD002", "test").name == "test_FD002.txt"


def test_add_rul_is_monotone_and_capped(tmp_path) -> None:
    write_cmapss_subset(tmp_path)
    df_with_rul = add_rul(load_cmapss("FD001", "train", directory=tmp_path), cap=3)

    grouped = df_with_rul.groupby("unit")["RUL"]
    assert grouped.apply(lambda series: series.is_monotonic_decreasing).all()
    # Unit 1 lives 4 cycles: uncapped RUL 3..0 -> capped at 3; unit 2 lives 3: 2..0.
    assert grouped.apply(lambda series: series.min()).tolist() == [0, 0]
    assert list(df_with_rul[df_with_rul["unit"] == 1]["RUL"]) == [3, 2, 1, 0]
    assert list(df_with_rul[df_with_rul["unit"] == 2]["RUL"]) == [2, 1, 0]


def test_add_rul_without_cap_keeps_full_range(tmp_path) -> None:
    write_cmapss_subset(tmp_path)
    df_with_rul = add_rul(load_cmapss("FD001", "train", directory=tmp_path), cap=None)
    assert list(df_with_rul[df_with_rul["unit"] == 1]["RUL"]) == [3, 2, 1, 0]


def test_load_rul_assigns_unit_order(tmp_path) -> None:
    (tmp_path / "RUL_FD001.txt").write_text("35\n82\n")
    labels = load_rul("FD001", directory=tmp_path)
    assert list(labels["unit"]) == [1, 2]
    assert list(labels["RUL"]) == [35, 82]
