/**
 * LiveMonitoringPage (Phase 5.2 Step 4): machine selection, sensor channel
 * reading, model verdict bars, health chip, provenance, auto-refresh polling
 * (fake timers) plus missing-machine, error and empty-fleet handling.
 */

import userEvent from "@testing-library/user-event";
import { act } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import {
  MACHINE_HEALTH_SNAPSHOTS,
  buildReadings,
} from "@/test/mocks/fixtures";
import { API_BASE, EMPTY_HANDLERS } from "@/test/mocks/handlers";
import { server } from "@/test/mocks/server";
import { renderFullPath } from "@/test/utils";

afterEach(() => {
  vi.useRealTimers();
});

function paginatedReadings(machineId: string, count = 30) {
  const readings = buildReadings(machineId, count);
  return { machine_id: machineId, readings, limit: 100, offset: 0, total: count };
}

describe("LiveMonitoringPage", () => {
  it("shows model verdicts, health chip, sensor grid and provenance", async () => {
    renderFullPath(undefined, "/monitoring");

    // Model verdict for the auto-selected SIM-001 (fixtures: latest failure
    // probability 0.179 → 17.900%, anomaly score 0.108, inlier caption).
    // Generous timeout: the first render also compiles the whole app route.
    expect(await screen.findByText("17.900%", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByText("0.108")).toBeInTheDocument();
    expect(screen.getByText("Detected inlier")).toBeInTheDocument();
    expect(screen.getByText("random_forest · FD001:random_forest@fixtures0001")).toBeInTheDocument();
    expect(screen.getByText("reading #30")).toBeInTheDocument();
    expect(screen.getByText(/Predicted \d+d ago/)).toBeInTheDocument();

    // Barrier: wait for the readings batch before asserting current-health
    // panel contents (health and readings resolve independently).
    expect(await screen.findByText(/^cycle 30$/)).toBeInTheDocument();
    expect(screen.getByText("No failure rule triggered")).toBeInTheDocument();

    // Health chip + last-reading context for SIM-001 (healthy, 0 active).
    expect(screen.getByText("healthy")).toBeInTheDocument();
    expect(screen.getByText(/^last reading \d+d ago$/)).toBeInTheDocument();

    // Current health panel: latest stored reading with Sim provenance.
    expect(screen.getByLabelText("Simulated data")).toBeInTheDocument();
    expect(screen.getByText("Stored at")).toBeInTheDocument();
    expect(screen.getByText(/^\d+d ago$/)).toBeInTheDocument();

    // Sensor trend defaults to s2 with 21 selectable channels.
    expect(await screen.findByRole("img", { name: "s2 trend over stored cycles" })).toBeInTheDocument();
    const sensorSelect = screen.getByLabelText("Sensor channel");
    expect(within(sensorSelect).getAllByRole("option")).toHaveLength(21);

    // Grid shows the 21 sensor values of cycle 30 (deterministic synthetics:
    // s2 = 500 + 2*10 + 30*2 = 580 → "580.0").
    const grid = screen.getByLabelText("Sensor values");
    expect(within(grid).getByText("s2")).toBeInTheDocument();
    expect(within(grid).getByText("580.0")).toBeInTheDocument();
  });

  it("switches the sensor channel and updates the trend chart", async () => {
    renderFullPath(undefined, "/monitoring");
    await screen.findByRole("img", { name: "s2 trend over stored cycles" });

    const sensorSelect = screen.getByLabelText("Sensor channel");
    await userEvent.setup().selectOptions(sensorSelect, "s9");

    expect(await screen.findByRole("img", { name: "s9 trend over stored cycles" })).toBeInTheDocument();
  });

  it("selects another machine and refetches its data", async () => {
    renderFullPath(undefined, "/monitoring");
    await screen.findByText("17.900%");

    const machineSelect = screen.getByLabelText("Select machine");
    expect(within(machineSelect).getAllByRole("option")).toHaveLength(3);
    await userEvent.setup().selectOptions(machineSelect, "SIM-002");

    // SIM-002 verdict: probability 0.579 → 57.900%, flagged anomalous,
    // elevated risk health chip with no active-alert suffix.
    expect(await screen.findByText("57.900%")).toBeInTheDocument();
    expect(screen.getByText("Detector flags this reading anomalous")).toBeInTheDocument();
    expect(screen.getByText("elevated risk")).toBeInTheDocument();
    expect(screen.queryByText(/· 0 active/)).not.toBeInTheDocument();
  });

  it("reports error states for a machine id that no longer exists", async () => {
    renderFullPath(undefined, "/monitoring?machine=GHOST");

    expect(await screen.findByText("no machine GHOST")).toBeInTheDocument();
    expect(screen.getByText("No prediction stored for this machine yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("renders the empty-fleet state without a machine selector", async () => {
    server.use(...EMPTY_HANDLERS);
    renderFullPath(undefined, "/monitoring");

    expect(await screen.findByText("No machines have ingested readings yet")).toBeInTheDocument();
    expect(screen.queryByLabelText("Select machine")).not.toBeInTheDocument();
  });

  it("surfaces readings failures with a working retry", async () => {
    let readingRequests = 0;
    server.use(
      http.get(`${API_BASE}/machines/SIM-001/readings`, () => {
        readingRequests += 1;
        return HttpResponse.json(
          { detail: { error: "internal_error", message: "simulated backend failure" } },
          { status: 500 },
        );
      }),
    );
    renderFullPath(undefined, "/monitoring");

    expect(await screen.findByText("simulated backend failure")).toBeInTheDocument();
    expect(readingRequests).toBe(1);

    await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(readingRequests).toBeGreaterThanOrEqual(2));
  });

  it("auto-refreshes health and readings on the global polling cadence", async () => {
    const counts = { readings: 0, health: 0 };
    server.use(
      http.get(`${API_BASE}/machines/SIM-001/readings`, () => {
        counts.readings += 1;
        return HttpResponse.json(paginatedReadings("SIM-001"));
      }),
      http.get(`${API_BASE}/machines/SIM-001/health`, () => {
        counts.health += 1;
        return HttpResponse.json(MACHINE_HEALTH_SNAPSHOTS["SIM-001"]);
      }),
    );

    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderFullPath(undefined, "/monitoring");

    // Initial load.
    await waitFor(() => expect(counts.readings).toBe(1));
    await waitFor(() => expect(counts.health).toBe(1));

    // Default global cadence is 5s; both polled resources refetch.
    act(() => {
      vi.advanceTimersByTime(5500);
    });
    await waitFor(() => expect(counts.readings).toBeGreaterThanOrEqual(2));
    expect(counts.health).toBeGreaterThanOrEqual(2);
  });

  it("pauses auto-refresh when the page-level override is Off", async () => {
    const counts = { readings: 0, health: 0 };
    server.use(
      http.get(`${API_BASE}/machines/SIM-001/readings`, () => {
        counts.readings += 1;
        return HttpResponse.json(paginatedReadings("SIM-001"));
      }),
      http.get(`${API_BASE}/machines/SIM-001/health`, () => {
        counts.health += 1;
        return HttpResponse.json(MACHINE_HEALTH_SNAPSHOTS["SIM-001"]);
      }),
    );

    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: (ms: number) => vi.advanceTimersByTime(ms) });
    renderFullPath(undefined, "/monitoring");

    await waitFor(() => expect(counts.readings).toBe(1));

    // "Off (manual only)" has value 0 → both intervals stop.
    await user.selectOptions(screen.getByLabelText("Polling interval"), "0");
    act(() => {
      vi.advanceTimersByTime(12000);
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(counts.readings).toBe(1);
    expect(counts.health).toBe(1);
  });

  it("offers the global value plus the six override cadences", async () => {
    renderFullPath(undefined, "/monitoring");
    await screen.findByRole("img", { name: "s2 trend over stored cycles" });

    const pollSelect = screen.getByLabelText("Polling interval");
    const options = within(pollSelect).getAllByRole("option");
    expect(options).toHaveLength(7); // Global + 6 POLL_INTERVAL_OPTIONS
    expect(within(options[0]).getByText(/Global \(5s\)/)).toBeInTheDocument();
    expect(within(options[1]).getByText("Off (manual only)")).toBeInTheDocument();
    expect(options.map((option) => option.getAttribute("value"))).toEqual([
      "__global__",
      "0",
      "1000",
      "3000",
      "5000",
      "15000",
      "30000",
    ]);
    expect(screen.getByLabelText("Polling interval")).toHaveValue("__global__");
  });
});
