"""Fetch the NASA C-MAPSS dataset files into ``data/raw/CMAPSSData``.

The official NASA PCoE URL has been on- and offline over the years, so the
downloader tries sources in order and stops at the first that works:

1. a per-file GitHub mirror of the official ``CMAPSSData`` bundle,
2. the original NASA ``CMAPSSData.zip`` archive.

Every downloaded file is shape-validated afterwards, so a truncated mirror
response fails loudly instead of poisoning the loaders.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from predictive_maintenance import config

REQUEST_TIMEOUT_SECONDS = 120
USER_AGENT = "predictive-maintenance-ai/0.1 (educational study project)"

_FILE_NAMES: list[str] = [
    "readme.txt",
    *(f"train_FD{index}.txt" for index in ("001", "002", "003", "004")),
    *(f"test_FD{index}.txt" for index in ("001", "002", "003", "004")),
    *(f"RUL_{index}.txt" for index in ("001", "002", "003", "004")),
]

# Source 1: individual files (verified mirror of the official dataset bundle).
MIRROR_URL = "https://raw.githubusercontent.com/edwardzjl/CMAPSSData/master/"
# Source 2: the original NASA archive (kept for when the URL serves the zip again).
NASA_ZIP_URL = "https://ti.arc.nasa.gov/m/project/prognostic-repository/CMAPSSData.zip"


def _fetch(url: str) -> bytes:
    """GET ``url`` as bytes with a browser-ish User-Agent (some hosts require one)."""
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.read()


def _validate_file(path: Path) -> None:
    """Reject truncated or wrong-format downloads before they reach the loaders."""
    if path.name == "readme.txt":
        return
    first_line = path.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    parts = first_line.split()
    if len(parts) != 26 or not all(part.replace(".", "").replace("-", "").isdigit() for part in parts):
        raise ValueError(f"{path.name}: unexpected format, first line: {first_line[:80]!r}")


def _download_from_mirror(target: Path) -> None:
    target.write_bytes(_fetch(f"{MIRROR_URL}{target.name}"))
    _validate_file(target)


def _download_from_nasa_zip(directory: Path) -> None:
    with zipfile.ZipFile(io.BytesIO(_fetch(NASA_ZIP_URL))) as bundle:
        wanted = set(_FILE_NAMES)
        members = [info for info in bundle.infolist() if Path(info.filename).name in wanted]
        if not members:
            raise ValueError(f"{NASA_ZIP_URL} does not contain the expected 13 files.")
        for info in members:
            (directory / Path(info.filename).name).write_bytes(bundle.read(info))
    for path in (directory / name for name in _FILE_NAMES):
        _validate_file(path)


def download_cmapss(force: bool = False) -> list[Path]:
    """Ensure all 13 C-MAPSS files exist under ``data/raw/CMAPSSData``.

    Already-present files are kept unless ``force=True``. Returns the paths of
    every file (downloaded or previously cached). Raises ``RuntimeError`` when
    no source works, so callers can surface a clear message.
    """
    directory = config.CMAPSS_DATA_DIR
    directory.mkdir(parents=True, exist_ok=True)
    targets = {name: directory / name for name in _FILE_NAMES}

    missing = [
        name
        for name, path in targets.items()
        if force or not path.exists() or path.stat().st_size == 0
    ]
    errors: list[str] = []
    if missing:
        try:
            for name in missing:
                print(f"[download] mirror: {name}")
                _download_from_mirror(targets[name])
        except (URLError, OSError, ValueError) as mirror_error:
            errors.append(f"mirror: {mirror_error}")
            print(f"[download] mirror failed ({mirror_error}); trying NASA zip...")
            try:
                _download_from_nasa_zip(directory)
            except (URLError, OSError, ValueError, zipfile.BadZipFile) as nasa_error:
                errors.append(f"nasa zip: {nasa_error}")

    if any(not (targets[name].exists() and targets[name].stat().st_size > 0) for name in _FILE_NAMES):
        raise RuntimeError(
            "Could not download the C-MAPSS dataset. Tried:\n  " + "\n  ".join(errors or ["(nothing attempted)"])
            + f". Manual fallback: fetch CMAPSSData.zip from the NASA PCoE repository "
            + "and extract it into " + str(directory)
        )
    return [targets[name] for name in _FILE_NAMES]
