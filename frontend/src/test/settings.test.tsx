/**
 * SettingsPage (Phase 5.2 Step 8): backend connection info + editing
 * (persisted base URL), polling interval configuration (persisted), alert
 * threshold documentation and simulator runbook.
 */

import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { HEALTH_OK, READINESS_OK } from "@/test/mocks/fixtures";
import { ERROR_HANDLERS, NETWORK_ERROR_HANDLERS } from "@/test/mocks/handlers";
import { server } from "@/test/mocks/server";
import { renderFullPath } from "@/test/utils";

describe("SettingsPage", () => {
  it("shows connection info, base-URL input and operator documentation", async () => {
    renderFullPath(undefined, "/settings");

    expect(await screen.findByText("connected")).toBeInTheDocument();
    expect(screen.getByText(/v0\.2\.0 · models loaded/)).toBeInTheDocument();

    // Default connection: input mirrors the shared fixture API base.
    const input = screen.getByLabelText("API base URL");
    expect(input).toHaveValue("http://127.0.0.1:8000");
    expect(screen.getByText(/^Default: /)).toBeInTheDocument();
    expect(screen.getByText(/VITE_API_BASE_URL/)).toBeInTheDocument();

    // Alert thresholds documentation (backend-driven values).
    expect(screen.getByText("failure_probability ≥ 0.5")).toBeInTheDocument();
    expect(screen.getByText("failure_probability ≥ 0.8")).toBeInTheDocument();
    expect(screen.getByText("env: API_ALERT_ELEVATED_FAILURE")).toBeInTheDocument();
    expect(screen.getByText("env: API_ALERT_CRITICAL_FAILURE")).toBeInTheDocument();
    expect(screen.getByText(/1 active alert per \(machine, type\)/)).toBeInTheDocument();

    // Simulator runbook commands are exposed verbatim.
    expect(screen.getByText(/uvicorn predictive_maintenance\.api\.main:app/)).toBeInTheDocument();
    expect(screen.getByText(/run_simulator\.py start --machines 4/)).toBeInTheDocument();
    expect(screen.getByText(/run_simulator\.py scenario abnormal_vibration/)).toBeInTheDocument();
    expect(screen.getByText("is_simulated=true")).toBeInTheDocument();

    // Polling select defaults to the 5s global cadence with six options.
    const pollSelect = screen.getByLabelText("Global polling interval");
    expect(pollSelect).toHaveValue("5000");
  });

  it("exposes the six polling options", async () => {
    renderFullPath(undefined, "/settings");
    const pollSelect = await screen.findByLabelText("Global polling interval");
    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(6);
    expect(options.map((option) => option.textContent)).toEqual([
      "Off (manual only)",
      "1 second",
      "3 seconds",
      "5 seconds",
      "15 seconds",
      "30 seconds",
    ]);
    expect(pollSelect).toHaveValue("5000");
  });

  it("persists a changed polling interval", async () => {
    renderFullPath(undefined, "/settings");
    const pollSelect = await screen.findByLabelText("Global polling interval");

    await userEvent.setup().selectOptions(pollSelect, "30000");

    expect(pollSelect).toHaveValue("30000");
    expect(window.localStorage.getItem("pma.pollIntervalMs")).toBe("30000");
  });

  it("reports HTTP failure state without a retry button on the connectivity row", async () => {
    server.use(...ERROR_HANDLERS);
    renderFullPath(undefined, "/settings");

    expect(await screen.findByText("http failure")).toBeInTheDocument();
    expect(screen.getByText("simulated backend failure")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("reports network failure separately from HTTP failure", async () => {
    server.use(...NETWORK_ERROR_HANDLERS);
    renderFullPath(undefined, "/settings");

    expect(await screen.findByText("network failure")).toBeInTheDocument();
    expect(screen.getByText("backend unreachable")).toBeInTheDocument();
  });

  it("does not report services as fully healthy when readiness is false", async () => {
    server.use(
      http.get("http://127.0.0.1:8000/ready", () =>
        HttpResponse.json({
          ...READINESS_OK,
          ready: false,
          datasets: Object.fromEntries(
            Object.entries(READINESS_OK.datasets).map(([id, dataset]) => [
              id,
              { ...dataset, ready: false },
            ]),
          ),
        }),
      ),
    );
    renderFullPath(undefined, "/settings");

    expect(await screen.findByText("connected")).toBeInTheDocument();
    expect(screen.getByText(/services not ready/)).toBeInTheDocument();
  });

  it("applies a new backend base URL and keeps connectivity there", async () => {
    // Backend reachable at the alternative base as well.
    server.use(
      http.get("http://127.0.0.1:9000/health", () => HttpResponse.json(HEALTH_OK)),
      http.get("http://127.0.0.1:9000/ready", () => HttpResponse.json(READINESS_OK)),
    );
    renderFullPath(undefined, "/settings");

    const user = userEvent.setup();
    const input = await screen.findByLabelText("API base URL");
    await user.clear(input);
    await user.type(input, "http://127.0.0.1:9000");
    await user.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() =>
      expect(window.localStorage.getItem("pma.apiBaseUrl")).toBe("http://127.0.0.1:9000"),
    );
    expect(input).toHaveValue("http://127.0.0.1:9000");
    // The refetch against the new base succeeded → still connected.
    await waitFor(() => expect(screen.getAllByText("connected")).toHaveLength(1));
  });

  it("reverts to the default base URL when applying an empty value", async () => {
    renderFullPath(undefined, "/settings");

    const user = userEvent.setup();
    const input = await screen.findByLabelText("API base URL");
    await user.clear(input);
    await user.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => expect(window.localStorage.getItem("pma.apiBaseUrl")).toBeNull());
    expect(input).toHaveValue("");
    expect(screen.getByText("connected")).toBeInTheDocument();
  });
});
