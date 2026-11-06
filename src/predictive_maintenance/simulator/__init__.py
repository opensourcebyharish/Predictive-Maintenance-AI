"""Phase 4: IoT sensor simulator for the Predictive Maintenance AI project.

The simulator generates synthetic engine-cycle readings and sends them to the
existing FastAPI backend (``POST /readings`` / ``POST /readings/batch``).

It is a *software simulator* - the values it produces are synthetic and are
clearly marked with ``is_simulated=true``. They are not physical measurements
and must not be interpreted as validated industrial sensor data.

Package layout::

  simulator/
    __init__.py
    config.py          simulator settings from environment variables
    scenarios.py       scenario generators (normal, degradation, anomalies, ...)
    machine.py         per-machine simulation state and reading generation
    client.py          HTTP client posting to the ingestion API
    simulator.py       orchestrator managing multiple machines
    cli.py             command-line interface (start, stop, scenario, status)
"""

from predictive_maintenance.simulator.config import SimulatorConfig

__all__ = ["SimulatorConfig"]
