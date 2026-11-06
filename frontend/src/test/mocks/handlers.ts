/**
 * MSW request handlers replaying the FastAPI contracts in-memory.
 *
 * Import DEFAULT_HANDLERS for the working backend, then use
 * `server.use(...errorHandlers)` / `server.use(...emptyHandlers)` /
 * `server.use(...slowHandlers)` inside individual tests to simulate
 * offline, empty and slow scenarios.
 */

import { http, HttpResponse, delay } from "msw";

import type { AlertStatus } from "@/api/types";

import {
  ALERTS,
  ALERT_SUMMARY_OK,
  EVALUATION_INDEX_FIXTURE,
  EVALUATION_REPORT_FD001,
  HEALTH_OK,
  MACHINE_DETAILS,
  MACHINE_HEALTH_SNAPSHOTS,
  MACHINES,
  READINESS_OK,
  buildPredictions,
  buildReadings,
} from "@/test/mocks/fixtures";

/** Default dashboard <base URL>; setup.ts clears localStorage so this holds. */
export const API_BASE = "http://127.0.0.1:8000";

function url(path: string): string {
  return `${API_BASE}${path}`;
}

/** Backend-shaped reply: JSON-serializable body plus HTTP status. */
type MockReply = { status: number; body: Parameters<typeof HttpResponse.json>[0] };

/**
 * Acknowledgement responds through the same lifecycle the real backend
 * enforces (active-only). Non-mutating: fixtures keep their state between
 * tests so server.resetHandlers() fully restores semantics.
 */
function acknowledgeAlert(alertId: number): MockReply {
  const alert = ALERTS.find((a) => a.id === alertId);
  if (alert === undefined) {
    return {
      status: 404,
      body: { detail: { error: "alert_not_found", message: `no alert ${alertId}` } },
    };
  }
  if (alert.status !== "active") {
    return {
      status: 409,
      body: {
        detail: {
          error: "alert_not_active",
          message: `alert ${alertId} is ${alert.status}, cannot acknowledge`,
        },
      },
    };
  }
  return {
    status: 200,
    body: { alert_id: alert.id, status: "acknowledged", acknowledged_at: "2026-01-01T00:40:00.000Z" },
  };
}

/** Standard success responses for every consumed endpoint. */
export const DEFAULT_HANDLERS = [
  http.get(url("/health"), () => HttpResponse.json(HEALTH_OK)),
  http.get(url("/ready"), () => HttpResponse.json(READINESS_OK)),

  http.get(url("/machines"), () => HttpResponse.json(MACHINES)),
  http.get(url("/machines/:machineId"), ({ params }) => {
    const detail = MACHINE_DETAILS[String(params.machineId)];
    if (detail === undefined) {
      return HttpResponse.json(
        { detail: { error: "machine_not_found", message: `no machine ${String(params.machineId)}` } },
        { status: 404 },
      );
    }
    return HttpResponse.json(detail);
  }),
  http.get(url("/machines/:machineId/health"), ({ params }) => {
    const snapshot = MACHINE_HEALTH_SNAPSHOTS[String(params.machineId)];
    if (snapshot === undefined) {
      return HttpResponse.json(
        { detail: { error: "machine_not_found", message: `no machine ${String(params.machineId)}` } },
        { status: 404 },
      );
    }
    return HttpResponse.json(snapshot);
  }),
  http.get(url("/machines/:machineId/readings"), ({ params, request }) => {
    const machineId = String(params.machineId);
    const machine = MACHINE_DETAILS[machineId];
    if (machine === undefined) {
      return HttpResponse.json(
        { detail: { error: "machine_not_found", message: `no machine ${machineId}` } },
        { status: 404 },
      );
    }
    const limit = Number(new URL(request.url).searchParams.get("limit") ?? 50);
    const offset = Number(new URL(request.url).searchParams.get("offset") ?? 0);
    const all = buildReadings(machineId);
    return HttpResponse.json({
      machine_id: machineId,
      readings: all.slice(offset, offset + limit),
      limit,
      offset,
      total: all.length,
    });
  }),
  http.get(url("/machines/:machineId/predictions"), ({ params, request }) => {
    const machineId = String(params.machineId);
    const machine = MACHINE_DETAILS[machineId];
    if (machine === undefined) {
      return HttpResponse.json(
        { detail: { error: "machine_not_found", message: `no machine ${machineId}` } },
        { status: 404 },
      );
    }
    const limit = Number(new URL(request.url).searchParams.get("limit") ?? 50);
    const offset = Number(new URL(request.url).searchParams.get("offset") ?? 0);
    const all = buildPredictions(machineId);
    return HttpResponse.json({
      machine_id: machineId,
      predictions: all.slice(offset, offset + limit),
      limit,
      offset,
      total: all.length,
    });
  }),

  http.get(url("/alerts"), ({ request }) => {
    const params = new URL(request.url).searchParams;
    const machineId = params.get("machine_id");
    const status = params.get("status") as AlertStatus | null;
    const limit = Number(params.get("limit") ?? 50);
    const filtered = ALERTS.filter(
      (a) =>
        (machineId === null || a.machine_id === machineId) &&
        (status === null || a.status === status),
    );
    return HttpResponse.json(filtered.slice(0, limit));
  }),
  http.get(url("/alerts/summary"), () => HttpResponse.json(ALERT_SUMMARY_OK)),
  http.post(url("/alerts/:alertId/acknowledge"), ({ params }) => {
    const { status, body } = acknowledgeAlert(Number(params.alertId));
    return HttpResponse.json(body, { status });
  }),

  http.get(url("/evaluation"), () => HttpResponse.json(EVALUATION_INDEX_FIXTURE)),
  http.get(url("/evaluation/:datasetId"), ({ params }) => {
    if (String(params.datasetId) !== "FD001") {
      return HttpResponse.json(
        {
          detail: {
            error: "evaluation_report_missing",
            message: `no evaluation report for ${String(params.datasetId)}`,
          },
        },
        { status: 404 },
      );
    }
    return HttpResponse.json(EVALUATION_REPORT_FD001);
  }),
];

/** Every list-shaped endpoint returns nothing: dashboard empty states. */
export const EMPTY_HANDLERS = [
  http.get(url("/health"), () => HttpResponse.json(HEALTH_OK)),
  http.get(url("/ready"), () => HttpResponse.json(READINESS_OK)),
  http.get(url("/machines"), () => HttpResponse.json([])),
  http.get(url("/alerts"), () => HttpResponse.json([])),
  http.get(url("/alerts/summary"), () =>
    HttpResponse.json({
      total: 0,
      by_status: {},
      by_type: {},
      by_severity: {},
      active_by_machine: {},
    }),
  ),
  http.get(url("/evaluation"), () => HttpResponse.json({ datasets: [], by_dataset: {} })),
  http.get(url("/machines/:machineId"), () =>
    HttpResponse.json(
      { detail: { error: "machine_not_found", message: "empty database" } },
      { status: 404 },
    ),
  ),
  http.get(url("/machines/:machineId/*"), () =>
    HttpResponse.json(
      { detail: { error: "machine_not_found", message: "empty database" } },
      { status: 404 },
    ),
  ),
];

/** Generic backend outage: 500 + FastAPI-style detail payload. */
export const ERROR_HANDLERS = [
  http.get(url("/*"), () =>
    HttpResponse.json(
      { detail: { error: "internal_error", message: "simulated backend failure" } },
      { status: 500 },
    ),
  ),
  http.post(url("/*"), () =>
    HttpResponse.json(
      { detail: { error: "internal_error", message: "simulated backend failure" } },
      { status: 500 },
    ),
  ),
];

/** Network-level failure: responses throw before reaching the client. */
export const NETWORK_ERROR_HANDLERS = [
  http.get(url("/*"), () => HttpResponse.error()),
  http.post(url("/*"), () => HttpResponse.error()),
];

/** Server responds slower than the client timeout for timeout-path tests. */
export const SLOW_HANDLERS = [
  http.get(
    url("/*"),
    async () => {
      await delay(2000);
      return HttpResponse.json(HEALTH_OK);
    },
  ),
];
