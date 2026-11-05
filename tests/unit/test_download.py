"""Unit tests for the C-MAPSS downloader (network is mocked via the fetch hook)."""

from __future__ import annotations

from predictive_maintenance.data.download import CMAPSS_FILES, download_cmapss


def test_downloads_every_cmapss_file(tmp_path) -> None:
    calls: list[str] = []

    def fake_fetch(url: str, dest) -> object:
        calls.append(url)
        dest.write_bytes(b"x-data-" * 64)  # > MIN_FILE_BYTES
        return dest

    paths = download_cmapss(directory=tmp_path, fetch=fake_fetch)

    assert len(paths) == len(CMAPSS_FILES)
    assert len(calls) == len(CMAPSS_FILES)
    assert {path.name for path in paths} == set(CMAPSS_FILES)
    assert calls[0].endswith(f"/{CMAPSS_FILES[0]}")


def test_existing_files_are_not_refetched(tmp_path) -> None:
    (tmp_path / "train_FD001.txt").write_bytes(b"existing-data" * 64)

    def boom(url: str, dest) -> object:  # pragma: no cover - must never run
        raise AssertionError("fetch must not be called for an already-present file")

    paths = download_cmapss(directory=tmp_path, fetch=boom)

    assert (tmp_path / "train_FD001.txt").read_bytes() == b"existing-data" * 64
    assert len(paths) == len(CMAPSS_FILES)
