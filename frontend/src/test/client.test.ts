/**
 * API-client behaviour tests: JSON contract errors, timeout semantics,
 * query serialization, cancel-on-signal, and connection event emission.
 */

import { describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { waitFor } from "@testing-library/react";

import { ApiError, api, isConnected, onConnectionChange, resetConnectionForTests } from "@/api/client";
import { API_BASE } from "@/test/mocks/handlers";
import { server } from "@/test/mocks/server";

describe("fetch error contracts", () => {
  it("extracts {error,message} from FastAPI detail objects", async () => {
    server.use(
      http.get(`${API_BASE}/machines/GHOST`, () =>
        HttpResponse.json(
          { detail: { error: "machine_not_found", message: "no machine GHOST" } },
          { status: 404 },
        ),
      ),
    );
    const error = await api.request("/machines/GHOST").catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    expect(apiError.status).toBe(404);
    expect(apiError.message).toBe("no machine GHOST");
    expect(apiError.detail).toMatchObject({ error: "machine_not_found" });
  });

  it("falls back to string details", async () => {
    server.use(
      http.get(`${API_BASE}/health`, () =>
        HttpResponse.json({ detail: "plain string failure" }, { status: 418 }),
      ),
    );
    await expect(api.request("/health")).rejects.toMatchObject({
      status: 418,
      message: "plain string failure",
    });
  });

  it("falls back to HTTP-code messages for empty bodies", async () => {
    server.use(
      http.get(`${API_BASE}/alerts`, () => new HttpResponse(null, { status: 503 })),
    );
    await expect(api.request("/alerts")).rejects.toMatchObject({
      status: 503,
      message: "HTTP 503",
    });
  });
});

describe("request options", () => {
  it("serializes query parameters and omits null/undefined", async () => {
    const observed: URL[] = [];
    server.use(
      http.get(`${API_BASE}/alerts`, ({ request }) => {
        observed.push(new URL(request.url));
        return HttpResponse.json([]);
      }),
    );
    await api.request("/alerts", { query: { status: "active", machine_id: null, limit: 25, offset: undefined } });
    expect(observed).toHaveLength(1);
    expect(observed[0].searchParams.get("status")).toBe("active");
    expect(observed[0].searchParams.get("limit")).toBe("25");
    expect(observed[0].searchParams.has("machine_id")).toBe(false);
    expect(observed[0].searchParams.has("offset")).toBe(false);
  });

  it("posts JSON bodies with content-type header", async () => {
    let body: unknown = null;
    server.use(
      http.post(`${API_BASE}/alerts/9/acknowledge`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ alert_id: 9, status: "acknowledged", acknowledged_at: "z" });
      }),
    );
    await api.request("/alerts/9/acknowledge", { method: "POST", body: { acknowledged_by: "tester" } });
    expect(body).toEqual({ acknowledged_by: "tester" });
  });

  it("aborts when the outer signal fires", async () => {
    const controller = new AbortController();
    const pending = api.request("/health", { signal: controller.signal });
    controller.abort();
    await expect(pending).rejects.toMatchObject({ status: 0, message: "cancelled" });
  });
});

describe("connection signalling", () => {
  it("emits connected after success and disconnected after failure", async () => {
    // Earlier expectations in this file flip the singleton; start clean.
    resetConnectionForTests(false);
    const listener = vi.fn();
    const off = onConnectionChange(listener);

    await api.request("/health");
    await waitFor(() => expect(isConnected()).toBe(true));

    server.use(
      http.get(`${API_BASE}/machines`, () => HttpResponse.error()),
    );
    await api.request("/machines").catch(() => undefined);
    await waitFor(() => expect(isConnected()).toBe(false));

    expect(listener).toHaveBeenCalledWith(true);
    expect(listener).toHaveBeenCalledWith(false);
    off();
  });
});
