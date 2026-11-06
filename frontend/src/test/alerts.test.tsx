/**
 * AlertsPage (Phase 5.2 Step 6): summary tiles, alert stream table with
 * severity/status chips, URL-linked filters, the acknowledge lifecycle
 * (success refresh + failure banner), duplicate-semantics coverage lives in
 * msw.test.tsx (409 alert_not_active), plus empty stream states.
 */

import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { API_BASE, EMPTY_HANDLERS } from "@/test/mocks/handlers";
import { server } from "@/test/mocks/server";
import { renderFullPath } from "@/test/utils";
import type { AlertRecord } from "@/api/types";

const PENDING_ACK_ALERT: AlertRecord = {
  id: 77,
  machine_id: "SIM-001",
  alert_type: "anomaly_detected",
  severity: "medium",
  status: "active",
  prediction_id: 5,
  model_version: "FD001:random_forest@fixtures0001",
  message: "Test alert awaiting acknowledgement",
  created_at: "2026-01-01T00:31:10.000Z",
  acknowledged_at: null,
  acknowledged_by: null,
  resolved_at: null,
  resolved_by: null,
};

describe("AlertsPage", () => {
  it("renders summary tiles, alert stream with chips and recovery history", async () => {
    renderFullPath(undefined, "/alerts");

    // Summary tiles (fixtures: 2 active / 1 acknowledged / 1 resolved / 4).
    // The AppShell sidebar pill adds one extra "2" text node per sidebar
    // copy, so "2" appears three times, "1" twice, "4" once.
    await screen.findByText("Total");
    expect(screen.getAllByText("2")).toHaveLength(3);
    expect(screen.getAllByText("1")).toHaveLength(2);
    expect(screen.getAllByText("4")).toHaveLength(1);

    // Stream table: header + all four fixture alerts.
    await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(5));
    expect(screen.getByText("Failure probability 0.851 exceeds critical threshold 0.8")).toBeInTheDocument();
    expect(screen.getByText("Anomaly detected (score=0.251) using random_forest")).toBeInTheDocument();
    expect(screen.getByText("Failure probability 0.552 exceeds elevated threshold 0.5")).toBeInTheDocument();
    expect(screen.getByText("Machine returned to healthy state")).toBeInTheDocument();

    // Severity chips (uppercase labels) per row.
    expect(screen.getByText("Critical")).toBeInTheDocument();
    expect(screen.getByText("Medium")).toBeInTheDocument();
    expect(screen.getByText("High")).toBeInTheDocument();
    expect(screen.getByText("Low")).toBeInTheDocument();

    // Acknowledgement provenance line for the ack'd fixture alerts.
    expect(screen.getAllByText(/by operator/)).toHaveLength(2);

    // Recovery history lists the single machine_recovered alert.
    expect(screen.getByText("Recovered")).toBeInTheDocument();
    const recoveryItem = screen.getByText("Recovered").closest("li");
    expect(recoveryItem !== null && within(recoveryItem).getByRole("link", { name: "SIM-002" })).toBeTruthy();

    // Active alerts only expose the acknowledge action.
    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: "Acknowledge" })).toHaveLength(2),
    );
  });

  it("filters by status and machine through URL-linked selects", async () => {
    const user = userEvent.setup();
    renderFullPath(undefined, "/alerts");
    await screen.findByText("Machine returned to healthy state");

    const statusSelect = screen.getByLabelText("Status filter");
    expect(within(statusSelect).getAllByRole("option")).toHaveLength(4);
    await user.selectOptions(statusSelect, "resolved");
    expect(statusSelect).toHaveValue("resolved");
    await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(2)); // header + alert 4
    expect(screen.getByText("Machine returned to healthy state")).toBeInTheDocument();

    const machineSelect = screen.getByLabelText("Machine filter");
    expect(within(machineSelect).getAllByRole("option")).toHaveLength(4); // All + 3 machines
    await user.selectOptions(machineSelect, "SIM-002");
    expect(screen.getAllByRole("row")).toHaveLength(2); // resolved alert is SIM-002 too

    // Combined filter: SIM-002 + acknowledged → alert 3.
    await user.selectOptions(statusSelect, "acknowledged");
    expect(await screen.findByText("Failure probability 0.552 exceeds elevated threshold 0.5")).toBeInTheDocument();

    // Clearing the machine filter with resolved still selected → alert 4.
    await user.selectOptions(machineSelect, "");
    await user.selectOptions(statusSelect, "resolved");
    expect(await screen.findByText("Machine returned to healthy state")).toBeInTheDocument();
  });

  it("applies the status filter from the URL on load", async () => {
    renderFullPath(undefined, "/alerts?status=active");

    expect(await screen.findByText("Failure probability 0.851 exceeds critical threshold 0.8")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(3); // header + alerts 2 & 1
    expect(screen.getByLabelText("Status filter")).toHaveValue("active");
    expect(screen.queryByText("Machine returned to healthy state")).not.toBeInTheDocument();
  });

  it("acknowledges an active alert and refreshes the stream", async () => {
    let local = [PENDING_ACK_ALERT];
    server.use(
      http.get(`${API_BASE}/alerts`, () => HttpResponse.json(local)),
      http.post(`${API_BASE}/alerts/77/acknowledge`, () => {
        local = [
          {
            ...local[0],
            status: "acknowledged",
            acknowledged_at: "2026-01-01T00:40:00.000Z",
            acknowledged_by: "dashboard",
          },
        ];
        return HttpResponse.json({
          alert_id: 77,
          status: "acknowledged",
          acknowledged_at: "2026-01-01T00:40:00.000Z",
        });
      }),
    );
    renderFullPath(undefined, "/alerts");

    const ackButton = await screen.findByRole("button", { name: "Acknowledge" });
    await userEvent.setup().click(ackButton);

    // Refetched list reflects the acknowledged status; action turns inactive.
    expect(await screen.findByText("acknowledged")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Acknowledge" })).not.toBeInTheDocument();
    expect(screen.getByText(/by dashboard/)).toBeInTheDocument();
  });

  it("shows a failure banner when acknowledgement fails", async () => {
    server.use(
      http.get(`${API_BASE}/alerts`, () => HttpResponse.json([PENDING_ACK_ALERT])),
      http.post(`${API_BASE}/alerts/77/acknowledge`, () =>
        HttpResponse.json(
          { detail: { error: "internal_error", message: "simulated backend failure" } },
          { status: 500 },
        ),
      ),
    );
    renderFullPath(undefined, "/alerts");

    await userEvent.setup().click(await screen.findByRole("button", { name: "Acknowledge" }));

    expect(await screen.findByText("Acknowledgement failed: simulated backend failure")).toBeInTheDocument();
    // Start-over state: banner alone, no retry request, button re-enabled.
    expect(screen.getByRole("button", { name: "Acknowledge" })).toBeEnabled();
    expect(screen.queryByText("Saving…")).not.toBeInTheDocument();
  });

  it("shows empty states for an empty database", async () => {
    server.use(...EMPTY_HANDLERS);
    renderFullPath(undefined, "/alerts");

    expect(await screen.findByText("No alerts recorded yet")).toBeInTheDocument();
    expect(screen.getAllByText("0")).toHaveLength(4); // 4 zero tiles
    expect(screen.getByText("No recovery events yet")).toBeInTheDocument();
  });

  it("shows the filtered-empty state when no alert matches", async () => {
    renderFullPath(undefined, "/alerts?machine=SIM-001&status=resolved");

    expect(await screen.findByText("No alerts match the selected filters")).toBeInTheDocument();
    expect(screen.queryByRole("row")).not.toBeInTheDocument();
  });
});
