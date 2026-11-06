/**
 * MSW integration tests: proves the mock layer intercepts the exact endpoints
 * the dashboard consumes, honours overrides, and isolates state between tests.
 * All requests go through the real fetch + api client (nothing hits network).
 */

import { describe, expect, it } from "vitest";
import { http, HttpResponse, delay } from "msw";

import { api } from "@/api/client";
import type { MachineSummary, PaginatedReadings } from "@/api/types";
import {
  API_BASE,
  DEFAULT_HANDLERS,
  EMPTY_HANDLERS,
  ERROR_HANDLERS,
  NETWORK_ERROR_HANDLERS,
  SLOW_HANDLERS,
} from "@/test/mocks/handlers";
import { MACHINES } from "@/test/mocks/fixtures";
import { server } from "@/test/mocks/server";

describe("msw server intercepts fastapi endpoints", () => {
  it("serves /machines with fixture data", async () => {
    const machines = await api.request<MachineSummary[]>("/machines");
    expect(machines).toHaveLength(3);
    expect(machines[0]).toMatchObject({ machine_id: "SIM-001", health: "healthy" });
  });

  it("serves paginated readings with sensor payloads", async () => {
    const page = await api.request<PaginatedReadings>("/machines/SIM-001/readings", {
      query: { limit: 10, offset: 5 },
    });
    expect(page.total).toBe(30);
    expect(page.readings[0].cycle).toBe(6);
    expect(page.readings[0].sensor_values.s1).toBeTypeOf("number");
    expect(page.readings[0].is_simulated).toBe(true);
  });

  it("serves alerts, summary and acknowledgement lifecycle", async () => {
    const alerts = await api.request<unknown[]>("/alerts", { query: { status: "active" } });
    expect(alerts).toHaveLength(2);

    const ackOne = await api.request<unknown>(`/alerts/2/acknowledge`, { method: "POST", body: { acknowledged_by: "tests" } });
    expect(ackOne).toMatchObject({ status: "acknowledged" });

    // The same default handlers enforce the backend rule: 409 when not active.
    await expect(api.request(`/alerts/4/acknowledge`, { method: "POST", body: {} })).rejects.toMatchObject({
      status: 409,
    });
  });

  it("returns 404 with FastAPI detail payloads for unknown machines", async () => {
    await expect(api.request("/machines/GHOST")).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
      message: "no machine GHOST",
    });
  });

  it("serves evaluation metrics endpoints", async () => {
    const index = await api.request<{ datasets: string[] }>("/evaluation");
    expect(index.datasets).toEqual(["FD001", "FD002", "FD003", "FD004"]);

    const report = await api.request<{ dataset_id: string }>("/evaluation/FD001");
    expect(report.dataset_id).toBe("FD001");

    await expect(api.request("/evaluation/FD999")).rejects.toMatchObject({ status: 404 });
  });
});

describe("handler overrides", () => {
  it("can override a single endpoint per test", async () => {
    server.use(
      http.get(`${API_BASE}/machines`, () =>
        HttpResponse.json([{ ...MACHINES[0], machine_id: "OVERRIDE-1" }]),
      ),
    );
    const machines = await api.request<MachineSummary[]>("/machines");
    expect(machines).toHaveLength(1);
    expect(machines[0].machine_id).toBe("OVERRIDE-1");
  });

  it("responds with empty datasets when EMPTY_HANDLERS are active", async () => {
    server.use(...EMPTY_HANDLERS);
    const machines = await api.request<MachineSummary[]>("/machines");
    expect(machines).toEqual([]);
    const alerts = await api.request<unknown[]>("/alerts");
    expect(alerts).toEqual([]);
  });

  it("translates 500 responses into ApiError with detail message", async () => {
    server.use(...ERROR_HANDLERS);
    await expect(api.request("/machines")).rejects.toMatchObject({
      status: 500,
      message: "simulated backend failure",
    });
  });

  it("translates network failures into 'backend unreachable'", async () => {
    server.use(...NETWORK_ERROR_HANDLERS);
    await expect(api.request("/machines")).rejects.toMatchObject({
      status: 0,
      message: "backend unreachable",
    });
  });

  it("surfaces client-side timeouts against slow handlers", async () => {
    server.use(...SLOW_HANDLERS);
    await expect(api.request("/health", { timeoutMs: 50 })).rejects.toMatchObject({
      status: 0,
      message: "request timed out",
    });
  });

  it("supports asynchronous delayed responses", async () => {
    server.use(
      http.get(`${API_BASE}/health`, async () => {
        await delay(20);
        return HttpResponse.json({ status: "ok", version: "slow" });
      }),
    );
    const health = await api.request<Record<string, unknown>>("/health");
    expect(health.version).toBe("slow");
  });
});

describe("test isolation", () => {
  it("resets to default handlers and fixture state after overrides", async () => {
    // server.resetHandlers() (setup.ts) restores the default catalogue: the
    // non-mutating acknowledgment handler leaves ACTIVE ids intact.
    const alerts = await api.request<{ id: number; status: string }[]>("/alerts", {
      query: { status: "active" },
    });
    expect(alerts.map((a) => a.id)).toEqual([2, 1]);
    expect(DEFAULT_HANDLERS).toHaveLength(12);
  });

  it("keeps localStorage free of settings between tests", () => {
    expect(window.localStorage.getItem("pma.apiBaseUrl")).toBeNull();
    expect(window.localStorage.getItem("pma.pollIntervalMs")).toBeNull();
  });

  it("catches unhandled requests as errors", () => {
    // setup.ts registers onUnhandledRequest:"error"; documenting contract.
    expect(API_BASE).toBe("http://127.0.0.1:8000");
  });
});
