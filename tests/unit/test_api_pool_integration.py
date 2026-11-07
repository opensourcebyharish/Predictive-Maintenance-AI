"""Integration regression: DB-backed routes must not leak pooled SQLite sessions.

Pre-fix, every alerts / machines route acquired its session through a bare
``db.get_session`` callable dependency, which gives FastAPI no teardown hook.
The session is only reclaimed by GC, so under concurrent load (the dashboard
polls these routes in parallel) the SQLAlchemy default pool for file SQLite
(QueuePool: 5 + 10 overflow) drains; subsequent check-outs block for
``pool_timeout`` (30 s) and surface as HTTP 500.

Confirmed live (pre-fix): 24 concurrent GETs to ``/alerts/summary`` produced
6 failures with exactly ~30.1 s latency, and the wedged state persisted until
the server was restarted.

These tests run a real uvicorn server on an ephemeral port because GC
reclamation masks the problem under sequential access (TestClient). Routes
used here touch only the database, so the app is served with
``lifespan="off"`` to skip (heavy) model preloading.

After the fix, ``Depends(db.get_session_dependency)`` closes every session
deterministically and every request below returns 200 quickly.
"""

from __future__ import annotations

import socket
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

import pytest
import uvicorn
from uvicorn.config import Config

from predictive_maintenance.api import db
from predictive_maintenance.api.main import create_app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def live_server_url(tmp_path: Any) -> Any:
    """A real uvicorn server bound to an ephemeral port, temp-file SQLite."""
    db_path = tmp_path / "pooltest.db"
    if db_path.exists():
        db_path.unlink()
    db.init_db(f"sqlite:///{db_path}")

    app = create_app()
    config = Config(
        app=app,
        host="127.0.0.1",
        port=_free_port(),
        log_level="warning",
        lifespan="off",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30.0
    while not (server.started and thread.is_alive()):
        if time.monotonic() > deadline:
            raise RuntimeError("uvicorn server did not start in time")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{config.port}"
    server.should_exit = True
    thread.join(timeout=10.0)


def _status(url: str, timeout: float = 45.0) -> int:
    """GET a URL, mapping any transport failure to non-200."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status
    except Exception:  # noqa: BLE001 - test only cares about success/failure
        return 500


class TestPoolExhaustionRegression:
    def test_concurrent_db_routes_never_exhaust_the_pool(self, live_server_url: str) -> None:
        """24 parallel DB-backed GETs must all succeed (pool 5 + 10 overflow)."""
        endpoints = [
            f"{live_server_url}/alerts/summary",
            f"{live_server_url}/alerts",
            f"{live_server_url}/machines",
        ]
        with ThreadPoolExecutor(max_workers=24) as pool:
            results = list(pool.map(_status, [endpoints[i % len(endpoints)] for i in range(24)]))
        assert results == [200] * 24, results

    def test_sequential_db_routes_never_exhaust_the_pool(self, live_server_url: str) -> None:
        """Even sequential traffic must stay healthy (baseline sanity)."""
        for _ in range(20):
            assert _status(f"{live_server_url}/alerts/summary") == 200
            assert _status(f"{live_server_url}/machines") == 200
