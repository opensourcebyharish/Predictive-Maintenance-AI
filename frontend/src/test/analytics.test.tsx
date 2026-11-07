/**
 * AnalyticsPage (Phase 5.2 Step 5): evaluation report metrics, model
 * comparison fields, dataset/machine selectors, readiness artefacts and the
 * missing-report / empty-fleet states.
 */

import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { buildPredictions } from "@/test/mocks/fixtures";
import { API_BASE, EMPTY_EVALUATION_HANDLERS, EMPTY_HANDLERS } from "@/test/mocks/handlers";
import { server } from "@/test/mocks/server";
import { renderFullPath } from "@/test/utils";

function paginatedPredictions(machineId: string) {
  const predictions = buildPredictions(machineId);
  return { machine_id: machineId, predictions, limit: 200, offset: 0, total: predictions.length };
}

describe("AnalyticsPage", () => {
  it("renders benchmark metrics, confusion matrix and model artefacts", async () => {
    renderFullPath(undefined, "/analytics");

    // FD001 validation tiles (default dataset): f1/roc/pr/recall formatting.
    expect(await screen.findByText("81.000%")).toBeInTheDocument(); // Validation F1
    expect(screen.getByText("0.880")).toBeInTheDocument(); // ROC AUC
    expect(screen.getByText("0.790")).toBeInTheDocument(); // PR AUC
    expect(screen.getByText("86.000%")).toBeInTheDocument(); // Degraded recall

    // Confusion matrix cells straight from the report fixture.
    expect(screen.getByText("2900")).toBeInTheDocument();
    expect(screen.getByText("320")).toBeInTheDocument();
    expect(screen.getByText("85")).toBeInTheDocument();
    expect(screen.getByText("547")).toBeInTheDocument();

    // Benchmark split rows incl. the offline test split for comparison.
    await waitFor(() => expect(screen.getByText("FD001 · random_forest")).toBeInTheDocument());
    expect(screen.getByText("Test F1")).toBeInTheDocument();
    expect(screen.getByText("51.000%")).toBeInTheDocument();
    expect(screen.getByText("0.820")).toBeInTheDocument();
    expect(screen.getByText("30 cycles")).toBeInTheDocument(); // failure horizon row

    // All four dataset artefacts show up as ready with their default model.
    await waitFor(() => expect(screen.getAllByText("ready")).toHaveLength(4));
    expect(screen.getByText(/The dashboard never retrains/)).toBeInTheDocument();

    // Prediction history charts + machine selector.
    expect(await screen.findByRole("img", { name: "Failure probability history" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Anomaly score history" })).toBeInTheDocument();
    const machineSelect = await screen.findByLabelText("Machine for prediction history");
    await waitFor(() => expect(within(machineSelect).getAllByRole("option")).toHaveLength(3));
    expect(machineSelect).toHaveValue("SIM-001"); // first fleet entry
  });

  it("honours the dataset URL parameter on load", async () => {
    renderFullPath(undefined, "/analytics?dataset=FD003");

    // FD003's default supervised model is xgboost, so the displayed tiles are
    // the xgboost validation metrics (f1 .84), not random_forest's (.83).
    expect(await screen.findByText("84.000%")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("FD003 · xgboost")).toBeInTheDocument());
  });

  it.each([
    {
      dataset: "FD001",
      model: "random_forest",
      f1: "81.000%",
      testF1: "51.000%",
      confusion: ["2900", "320", "85", "547"] as const,
    },
    {
      dataset: "FD002",
      model: "random_forest",
      f1: "72.000%",
      testF1: "39.000%",
      confusion: ["3500", "640", "470", "1483"] as const,
    },
    {
      dataset: "FD003",
      model: "xgboost",
      f1: "84.000%",
      testF1: "57.000%",
      confusion: ["2740", "240", "106", "824"] as const,
    },
    {
      dataset: "FD004",
      model: "xgboost",
      f1: "70.000%",
      testF1: "34.000%",
      confusion: ["2140", "570", "540", "1530"] as const,
    },
  ])("uses the default supervised model for $dataset", async ({ dataset, model, f1, testF1, confusion }) => {
    renderFullPath(undefined, `/analytics?dataset=${dataset}`);

    // Benchmark label and metric source must describe the same model.
    expect(await screen.findByText(f1)).toBeInTheDocument();
    expect(screen.getByText(`${dataset} · ${model}`)).toBeInTheDocument();
    expect(screen.getByText(testF1)).toBeInTheDocument();
    for (const cell of confusion) {
      expect(screen.getByText(cell)).toBeInTheDocument();
    }
  });

  it("switches datasets through the select and refetches the report", async () => {
    renderFullPath(undefined, "/analytics");
    await screen.findByText("81.000%");

    const datasetSelect = screen.getByLabelText("C-MAPSS dataset");
    expect(within(datasetSelect).getAllByRole("option")).toHaveLength(4);
    await userEvent.setup().selectOptions(datasetSelect, "FD003");

    expect(await screen.findByText("84.000%")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("FD003 · xgboost")).toBeInTheDocument());
    expect(screen.queryByText("81.000%")).not.toBeInTheDocument();
  });

  it("errors with the backend detail when the report file is missing", async () => {
    server.use(...EMPTY_EVALUATION_HANDLERS);
    renderFullPath(undefined, "/analytics");

    expect(await screen.findByText("no evaluation report for FD001")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    // The page gates ALL panels on the report resource, so nothing else but
    // the error state and the page header is on screen.
    expect(screen.queryByLabelText("Machine for prediction history")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("C-MAPSS dataset")).toBeInTheDocument(); // header select
    expect(screen.queryByText("ready")).not.toBeInTheDocument();
  });

  it("shows the empty history panel for an empty fleet", async () => {
    server.use(...EMPTY_HANDLERS);
    renderFullPath(undefined, "/analytics");

    // Report endpoint is not in EMPTY_HANDLERS, so tiles still render.
    expect(await screen.findByText("No machines yet")).toBeInTheDocument();
    expect(screen.getByText("81.000%")).toBeInTheDocument();
  });

  it("refetches prediction history for the newly selected machine", async () => {
    let sim003Requests = 0;
    server.use(
      http.get(`${API_BASE}/machines/SIM-003/predictions`, () => {
        sim003Requests += 1;
        return HttpResponse.json(paginatedPredictions("SIM-003"));
      }),
    );
    renderFullPath(undefined, "/analytics");
    await screen.findByRole("img", { name: "Failure probability history" });
    expect(sim003Requests).toBe(0); // initial history is for SIM-001 only

    await userEvent
      .setup()
      .selectOptions(screen.getByLabelText("Machine for prediction history"), "SIM-003");

    // Selecting a machine rebinds the hook params → new request for SIM-003.
    const machineSelect = screen.getByLabelText("Machine for prediction history");
    await waitFor(() => expect(machineSelect).toHaveValue("SIM-003"));
    await waitFor(() => expect(sim003Requests).toBeGreaterThanOrEqual(1));
  });
});
