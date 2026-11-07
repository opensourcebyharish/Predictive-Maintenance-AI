"""HTTP client for submitting simulated readings to the FastAPI backend.

Uses only the standard library (``urllib.request``) so the simulator has no
runtime dependencies beyond the project's existing ones.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from predictive_maintenance.api.schemas import BatchReadingIngestResponse, ReadingIngest


class SimulatorClient:
    """Client for the predictive maintenance ingestion API."""

    def __init__(self, api_url: str, timeout: float = 10.0) -> None:
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
        self.readings_sent: int = 0
        self.readings_stored: int = 0
        self.readings_duplicate: int = 0
        self.readings_rejected: int = 0
        self.errors: int = 0
        self.last_error: str | None = None

    def submit_batch(self, readings: list[ReadingIngest]) -> BatchReadingIngestResponse:
        """Submit a batch of readings to ``POST /readings/batch``."""
        payload = {
            "readings": [reading.model_dump(mode="json") for reading in readings]
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.api_url}/readings/batch",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                response = BatchReadingIngestResponse(**body)
        except urllib.error.HTTPError as exc:
            body = json.loads(exc.read().decode("utf-8")) if exc.fp else {}
            raise SimulatorClientError(
                f"HTTP {exc.code}: {body.get('detail', {}).get('message', str(exc))}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
            # TimeoutError / OSError cover socket read timeouts and dropped
            # connections, which are NOT urllib.error.URLError subclasses; a
            # transient backend stall must surface as SimulatorClientError so
            # the orchestrator run loop survives and retries the next round.
            raise SimulatorClientError(f"request failed: {exc}") from exc

        self.readings_sent += len(readings)
        self.readings_stored += response.stored
        self.readings_duplicate += response.duplicates
        self.readings_rejected += response.rejected
        return response

    def submit_single(self, reading: ReadingIngest) -> Any:
        """Submit a single reading to ``POST /readings``."""
        payload = reading.model_dump()
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.api_url}/readings",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = json.loads(exc.read().decode("utf-8")) if exc.fp else {}
            raise SimulatorClientError(
                f"HTTP {exc.code}: {body.get('detail', {}).get('message', str(exc))}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
            raise SimulatorClientError(f"request failed: {exc}") from exc

    def health(self) -> dict[str, Any]:
        """Query ``GET /health`` to check the backend is reachable."""
        req = urllib.request.Request(f"{self.api_url}/health", method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
            raise SimulatorClientError(f"health check failed: {exc}") from exc

    def stats(self) -> dict[str, int]:
        return {
            "sent": self.readings_sent,
            "stored": self.readings_stored,
            "duplicates": self.readings_duplicate,
            "rejected": self.readings_rejected,
            "errors": self.errors,
        }


class SimulatorClientError(Exception):
    """Raised when the simulator client cannot communicate with the API."""
