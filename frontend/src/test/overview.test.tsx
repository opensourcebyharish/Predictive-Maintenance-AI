/**
 * OverviewPage (Phase 5.2 Step 3): counting tiles from /machines and
 * /alerts/summary, health distribution legend, fleet table, recent incidents,
 * plus empty and error reporting with retry.
 */

import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { API_BASE, EMPTY_HANDLERS } from "@/test/mocks/handlers";
import { server } from "@/test/mocks/server";
import { renderFullPath } from "@/test/utils";

describe("OverviewPage", () => {
  it("renders counted tiles, health legend, fleet table and recent incidents", async () => {
    renderFullPath(undefined, "/");

    // KPI tiles from fixtures: 3 machines (1 healthy / 1 warning / 1 critical)
    // and 2 active alerts out of 4 lifetime. The AppShell sidebar pill
    // contributes no extra text here, so "3" stays unique.
    await screen.findByText("Machines");
    await waitFor(() => {
      expect(screen.getByText("3")).toBeInTheDocument(); // Machines tile value
      expect(screen.getByLabelText("Active alerts: 2")).toBeInTheDocument();
      expect(screen.getByText(/4 lifetime/)).toBeInTheDocument();
      // "1" is the value of Healthy/Warning/Critical tiles plus the three
      // non-empty donut legend counts.
      expect(screen.getAllByText("1")).toHaveLength(6);
      // "2": the Active alerts tile value + one sidebar pill per nav copy.
      expect(screen.getAllByText("2")).toHaveLength(3);
    });

    // Donut legend lists only non-empty health buckets (lowercase labels).
    const legend = screen.getByLabelText("Health legend");
    expect(within(legend).getByText("healthy")).toBeInTheDocument();
    expect(within(legend).getByText("elevated risk")).toBeInTheDocument();
    expect(within(legend).getByText("critical risk")).toBeInTheDocument();

    // Fleet table: header + one row per machine, linking into device pages.
    await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(4));
    const rows = screen.getAllByRole("row");
    expect(within(rows[1]).getByRole("link", { name: "SIM-001" })).toHaveAttribute(
      "href",
      "/devices/SIM-001",
    );
    expect(within(rows[1]).getByText("FD001")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Healthy")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Elevated risk")).toBeInTheDocument();
    expect(within(rows[3]).getByText("Critical")).toBeInTheDocument();
    expect(within(rows[1]).getByText(/1–30/)).toBeInTheDocument();
    expect(within(rows[1]).getByText(/\dd ago/)).toBeInTheDocument();

    // Recent incidents: newest first (alert ids 2, 1, 3, 4 in fixtures).
    await waitFor(() => {
      expect(screen.getByText("Critical failure risk")).toBeInTheDocument();
      expect(screen.getByText("Anomaly detected")).toBeInTheDocument();
      expect(screen.getByText("Elevated failure risk")).toBeInTheDocument();
      expect(screen.getByText("Machine recovered")).toBeInTheDocument();
    });
    expect(screen.getByText("Medium")).toBeInTheDocument();
    expect(screen.getByText("High")).toBeInTheDocument();
    expect(screen.getByText("Low")).toBeInTheDocument();
    expect(screen.getAllByText("Active")).toHaveLength(2);
    expect(screen.getByText("Acknowledged")).toBeInTheDocument();
    expect(screen.getByText("Resolved")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View all →" })).toHaveAttribute("href", "/alerts");
  });

  it("renders empty fleet and incident states", async () => {
    server.use(...EMPTY_HANDLERS);
    renderFullPath(undefined, "/");

    // Tiles stay zero-valued. Five exact "0"s: Machines/Healthy/Warning/
    // Critical/Active tiles (the sidebar pill is hidden at 0 active).
    expect(await screen.findByLabelText("Active alerts: 0")).toBeInTheDocument();
    expect(screen.getAllByText("0")).toHaveLength(5);
    expect(screen.getByText(/0 lifetime/)).toBeInTheDocument();
    expect(await screen.findByText("No machines have ingested readings yet")).toBeInTheDocument();
    expect(screen.getByText("No machines ingested yet")).toBeInTheDocument();
    expect(screen.getByText("No alerts recorded in this database yet")).toBeInTheDocument();
  });

  it("surfaces machine fetch failures with a working retry", async () => {
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
    renderFullPath(undefined, "/");

    expect(await screen.findByText("simulated backend failure")).toBeInTheDocument();
    expect(machineRequests).toBe(1);

    await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(machineRequests).toBeGreaterThanOrEqual(2));
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("flags summary failures instead of silently showing zero alerts", async () => {
    server.use(
      http.get(`${API_BASE}/alerts/summary`, () =>
        HttpResponse.json(
          { detail: { error: "internal_error", message: "summary unavailable" } },
          { status: 500 },
        ),
      ),
    );
    renderFullPath(undefined, "/");

    // Machines still render; the active-alert tile degrades to 0 with an
    // explicit header badge so operators are not misled by 2 → 0.
    await screen.findByText("Machines");
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(await screen.findByText("Alert summary failed")).toBeInTheDocument();
    expect(screen.getByLabelText("Active alerts: 0")).toBeInTheDocument();
    expect(screen.getByText(/0 lifetime/)).toBeInTheDocument();
  });
});
