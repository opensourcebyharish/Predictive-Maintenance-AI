"""Fetch the NASA C-MAPSS dataset files into ``data/raw/CMAPSSData``.

The official NASA PCoE URL has been on- and offline over the years, so the
downloader tries sources in order and stops at the first that works:

1. a per-file GitHub mirror of the official ``CMAPSSData`` bundle,
2. the original NASA ``CMAPSSData.zip`` archive.

Every downloaded file is format-validated afterwards, so a truncated mirror
response fails loudly instead of poisoning the loaders. For tests, the fetch
step is injectable via ``download_cmapss(..., fetch=fn(url, dest))``.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Callable

from urllib.error import URLError
from urllib.request import Request, urlopen

from predictive_maintenance import config

REQUEST_TIMEOUT_SECONDS = 120
USER_AGENT = "predictive-maintenance-ai/0.1 (educational study project)"

# Floor below which a response is considered an error page, not a data file.
# The smallest real artifact (RUL_FD001.txt) is ~430 bytes.
MIN_FILE_BYTES = 128

CMAPSS_FILES: tuple[str, ...] = (
    "readme.txt",
    *(f"train_FD{series}.txt" for series in ("001", "002", "003", "004")),
    *(f"test_FD{series}.txt" for series in ("001", "002", "003", "004")),
    *(f"RUL_FD{series}.txt" for series in ("001", "002", "003", "004")),
)

# Source 1: individual files (verified mirror of the official dataset bundle).
MIRROR_URL = "https://raw.githubusercontent.com/edwardzjl/CMAPSSData/master/"
# Source 2: the original NASA archive (kept for when the URL serves the zip again).
NASA_ZIP_URL = "https://ti.arc.nasa.gov/m/project/prognostic-repository/CMAPSSData.zip"


def _fetch(url: str) -> bytes:
    """GET ``url`` as bytes with a User-Agent (github raw + nasa want one)."""
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.read()


def _validate_file(path: Path) -> None:
    """Reject truncated or wrong-format downloads before they reach the loaders."""
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        first_line = handle.readline()

    if path.name == "readme.txt":
        if "Data Set" not in path.read_text(errors="replace"):
            raise ValueError(f"{path.name}: missing 'Data Set' header; likely an error page")
        return
    parts = first_line.split()
    expected_columns = 1 if path.name.startswith("RUL_") else 26  # RUL files: one value per line
    if len(parts) != expected_columns or not all(
        part.replace(".", "").replace("-", "").isdigit() for part in parts
    ):
        raise ValueError(f"{path.name}: unexpected format, first line: {first_line[:80]!r}")


def _default_fetch(url: str, dest: Path) -> Path:
    """Real fetch used at production time: GET, size-gate, validate, persist."""
    payload = _fetch(url)
    if len(payload) < MIN_FILE_BYTES:
        raise ValueError(f"{url}: response too small ({len(payload)} bytes), likely an error page")
    dest.write_bytes(payload)
    _validate_file(dest)
    return dest


def _download_from_nasa_zip(directory: Path) -> None:
    """Second source: the original single-file NASA archive."""
    with zipfile.ZipFile(io.BytesIO(_fetch(NASA_ZIP_URL))) as bundle:
        wanted = set(CMAPSS_FILES)
        members = [info for info in bundle.infolist() if Path(info.filename).name in wanted]
        if not members:
            raise ValueError(f"{NASA_ZIP_URL} does not contain the expected 13 files.")
        for info in members:
            (directory / Path(info.filename).name).write_bytes(bundle.read(info))
    for path in (directory / name for name in CMAPSS_FILES):
        _validate_file(path)


def download_cmapss(
    force: bool = False,
    directory: Path | None = None,
    fetch: Callable[[str, Path], Path] | None = None,
) -> list[Path]:
    """Ensure all 13 C-MAPSS files exist (default: under ``data/raw/CMAPSSData``).

    Already-present non-empty files are kept unless ``force=True``. A custom
    ``fetch(url, dest)`` hook replaces network I/O for tests. Raises
    ``RuntimeError`` when no source works, describing the manual fallback.
    """
    directory = config.CMAPSS_DATA_DIR if directory is None else Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    fetcher = _default_fetch if fetch is None else fetch
    targets = {name: directory / name for name in CMAPSS_FILES}

    def present(name: str) -> bool:
        target = targets[name]
        return target.exists() and target.stat().st_size > 0

    missing = [name for name in CMAPSS_FILES if force or not present(name)]
    errors: list[str] = []
    for name in missing:
        print(f"[download] mirror: {name}")
        try:
            fetcher(f"{MIRROR_URL}{name}", targets[name])
        except Exception as error:  # noqa: BLE001 - report per-file failures, keep the suite scrolling
            errors.append(f"mirror {name}: {error}")
            if fetch is None:  # production: fall back to the NASA zip for everything remaining
                print(f"[download] mirror failed ({error}); trying NASA zip...")
                try:
                    _download_from_nasa_zip(directory)
                except (URLError, OSError, ValueError, zipfile.BadZipFile) as nasa_error:
                    errors.append(f"nasa zip: {nasa_error}")
                break  # the zip either provided every remaining file or nothing did
            # tests: a custom fetch manages its own world; skip further enforcement

    if fetch is None and any(not present(name) for name in CMAPSS_FILES):
        raise RuntimeError(
            "Could not download the C-MAPSS dataset. Errors:\n  "
            + "\n  ".join(errors or ["(nothing attempted)"])
            + "\nManual fallback: fetch CMAPSSData.zip from the NASA PCoE repository "
            + "and extract it into " + str(directory)
        )
    return [targets[name] for name in CMAPSS_FILES]
