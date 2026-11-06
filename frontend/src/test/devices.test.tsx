/**
 * Device Management (Phase 5.2 Step 7): DevicesPage inventory cards with
 * navigation into DeviceDetailPage — identity/verdict tiles, prediction bars,
 * reading-history window (last 60 of a 200-reading request), pagination
 * params, Sim/Real provenance and error handling.
 */

import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { buildReadings } from "@/test/mocks/fixtures";
import { API_BASE, EMPTY_HANDLERS } from "@/test/mocks/handlers";
import { server } from "@/test/mocks/server";
import { renderFullPath } from "@/test/utils";

function paginatedReadings(machineId: string, count: number) {
  const readings = buildReadings(machineId, count);
  return { machine_id: machineId, readings, limit: count, offset: 0, total: count };
}

describe("DevicesPage", () => {
  it("renders an inventory card per machine with dataset and freshest-cycle data", async () => {
    renderFullPath(undefined, "/devices");

    for (const id of ["SIM-001", "SIM-002", "SIM-003"]) {
      expect(await screen.findByLabelText(`Open device ${id}`)).toBeInTheDocument();
    }
    const card1 = screen.getByLabelText("Open device SIM-001");
    expect(within(card1).getByText("FD001")).toBeInTheDocument();
    expect(within(card1).getByText("30")).toBeInTheDocument(); // reading count
    expect(within(card1).getByText("1 → 30")).toBeInTheDocument();
    expect(within(card1).getByText(/d ago$/)).toBeInTheDocument();
    expect(within(card1).getByText("healthy")).toBeInTheDocument();
    expect(within(card1).getByText("provenance shown per reading on detail")).toBeInTheDocument();

    const card3 = screen.getByLabelText("Open device SIM-003");
    expect(within(card3).getByText("FD003")).toBeInTheDocument();
    expect(within(card3).getByText("critical risk")).toBeInTheDocument();
  });

  it("navigates from a card into the device detail page", async () => {
    renderFullPath(undefined, "/devices");
    const card3 = await screen.findByLabelText("Open device SIM-003");

    await userEvent.setup().click(card3);

    expect(await screen.findByRole("heading", { name: "SIM-003" })).toBeInTheDocument();
    expect(await screen.findByText(/^Dataset FD003 · verdict critical risk$/)).toBeInTheDocument();
    // SIM-003 verdict: probability 0.879 → 87.900%, anomaly 0.808, rule hit.
    expect(screen.getByText("87.900%")).toBeInTheDocument();
    expect(screen.getByText("0.808")).toBeInTheDocument();
    expect(screen.getByText(/thresholds 0\.5 \/ 0\.8 mark elevated and critical risk/)).toBeInTheDocument();
    expect(screen.getByText(/failure rule triggered/)).toBeInTheDocument();
  });

  it("shows the empty state for a fresh database", async () => {
    server.use(...EMPTY_HANDLERS);
    renderFullPath(undefined, "/devices");

    expect(await screen.findByText("No devices registered yet")).toBeInTheDocument();
  });

  it("surfaces listing failures with a working retry", async () => {
    let machineRequests = 0;
    server.use(
      http.get(`${API_BASE}/machines`, () => {
        machineRequests += 1;
        return HttpResponse.json(
          { detail: { error: "internal_error", message: "simulated backend failure" } },
          { status: 500 },
        );
      }),
    );
    renderFullPath(undefined, "/devices");

    expect(await screen.findByText("simulated backend failure")).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(machineRequests).toBeGreaterThanOrEqual(2));
  });
});

describe("DeviceDetailPage", () => {
  it("renders identity, verdict tiles, prediction and full reading history", async () => {
    renderFullPath(undefined, "/devices/SIM-001");

    expect(await screen.findByRole("heading", { name: "SIM-001" })).toBeInTheDocument();
    expect(await screen.findByText(/^Dataset FD001 · verdict healthy$/)).toBeInTheDocument();

    // Barrier: wait for the reading history before precise tile counts
    // (detail data and reading history resolve independently).
    expect(await screen.findByLabelText("Sensor values")).toBeInTheDocument();

    // Tiles: readings 30, cycle 30, 1 active alert, healthy verdict.
    expect(screen.getByText("Readings")).toBeInTheDocument();
    expect(screen.getAllByText("30")).toHaveLength(3); // 2 tiles + newest history row (cycle 30)
    expect(screen.getAllByText("1")).toHaveLength(2); // Active alerts tile + oldest row (cycle 1)
    expect(screen.getByText("Active alerts")).toBeInTheDocument();
    expect(screen.getByText("healthy")).toBeInTheDocument();

    // Latest prediction: 0.179 → 17.900%, anomaly score display 0.108.
    expect(screen.getByText("17.900%")).toBeInTheDocument();
    expect(screen.getByText("0.108")).toBeInTheDocument();
    expect(screen.getByText(/failure rule not triggered/)).toBeInTheDocument();

    // Latest reading panel: provenance + sensors of cycle 30.
    expect(screen.getByText("Simulated (Phase 4 simulator)")).toBeInTheDocument();
    expect(screen.getByText(/20\/20 simulated \(100%\)/)).toBeInTheDocument();
    const grid = screen.getByLabelText("Sensor values");
    expect(within(grid).getByText("580.0")).toBeInTheDocument(); // s2 at cycle 30

    // Reading history: 30 rows, newest cycle first, Sim chip per row.
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(31); // header + 30 cycles
    expect(within(rows[1]).getByLabelText("Simulated data")).toBeInTheDocument();
    expect(within(rows.at(-1) as HTMLElement).getByText("1")).toBeInTheDocument();
  });

  it("requests a 200-reading window and shows only the last 60 cycles", async () => {
    const searchParams: string[] = [];
    server.use(
      http.get(`${API_BASE}/machines/SIM-001/readings`, ({ request }) => {
        searchParams.push(new URL(request.url).search);
        return HttpResponse.json(paginatedReadings("SIM-001", 260));
      }),
    );
    renderFullPath(undefined, "/devices/SIM-001");

    // Pagination contract of the detailed view: one 200-limit window request.
    await waitFor(() => expect(searchParams.length).toBeGreaterThanOrEqual(1));
    expect(searchParams[0]).toBe("?limit=200&offset=0");

    // The table keeps the freshest 60 rows (cycles 201..260 newest first) and
    // the latest-reading panel reflect cycle 260.
    expect(await screen.findByText(/cycle 260 · stored/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(61));
    // Rows are reversed: newest (260) first, oldest of the window (201) last.
    expect(within(screen.getAllByRole("row")[1]).getByText("260")).toBeInTheDocument();
    expect(within(screen.getAllByRole("row").at(-1) as HTMLElement).getByText("201")).toBeInTheDocument();
  });

  it("marks real (non-simulated) payloads with Real provenance", async () => {
    const realReadings = buildReadings("SIM-001").map((reading) => ({ ...reading, is_simulated: false }));
    server.use(
      http.get(`${API_BASE}/machines/SIM-001/readings`, () =>
        HttpResponse.json(paginatedEnvelope(realReadings)),
      ),
    );
    renderFullPath(undefined, "/devices/SIM-001");

    expect(await screen.findByText("Real device payload")).toBeInTheDocument();
    expect(screen.getByText(/recent readings: real/)).toBeInTheDocument();
    // 30 history rows + the latest-reading panel badge.
    expect(await screen.findAllByLabelText("Real sensor data")).toHaveLength(31);
  });

  it("falls back to the machine-not-found error state", async () => {
    renderFullPath(undefined, "/devices/GHOST-9");

    expect(await screen.findByRole("heading", { name: "GHOST-9" })).toBeInTheDocument();
    expect(await screen.findByText("no machine GHOST-9")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All devices" })).toHaveAttribute("href", "/devices");
  });

  it("returns to the inventory through the All devices link", async () => {
    const user = userEvent.setup();
    renderFullPath(undefined, "/devices/SIM-001");
    await screen.findByRole("heading", { name: "SIM-001" });

    await user.click(screen.getByRole("link", { name: "All devices" }));

    expect(await screen.findByRole("heading", { name: "Device Management" })).toBeInTheDocument();
  });
});

/** Wraps raw readings in the PaginatedReadings envelope shape. */
function paginatedEnvelope(readings: ReturnType<typeof buildReadings>) {
  return { machine_id: "SIM-001", readings, limit: 200, offset: 0, total: readings.length };
}
