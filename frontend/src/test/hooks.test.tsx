/**
 * useResource behaviour: initial loading state, data arrival, error handling,
 * manual refetch, request suppression for hidden tabs, interval polling.
 */

import { describe, expect, it, vi, afterEach } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { useResource } from "@/api/hooks";
import { api } from "@/api/client";
import type { MachineSummary } from "@/api/types";
import { MACHINES } from "@/test/mocks/fixtures";
import { API_BASE } from "@/test/mocks/handlers";
import { server } from "@/test/mocks/server";

afterEach(() => {
  vi.useRealTimers();
});

afterEach(() => {
  Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true, writable: true });
});

function swapMachinesHandler(counter: { value: number }): void {
  server.use(
    http.get(`${API_BASE}/machines`, () => {
      counter.value += 1;
      return HttpResponse.json(MACHINES);
    }),
  );
}

describe("useResource fetching", () => {
  it("starts loading, then exposes data and lastUpdated", async () => {
    const counter = { value: 0 };
    swapMachinesHandler(counter);

    const { result } = renderHook(() =>
      useResource(() => api.request<MachineSummary[]>("/machines"), undefined, { pollMs: 0 }),
    );

    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull();

    await waitFor(() => expect(result.current.data).not.toBeNull());
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.lastUpdated).toBeGreaterThan(0);
    expect(result.current.data).toHaveLength(3);
    expect(counter.value).toBe(1);
  });

  it("stores ApiError from failing endpoints", async () => {
    server.use(
      http.get(`${API_BASE}/machines`, () =>
        HttpResponse.json(
          { detail: { error: "internal_error", message: "simulated backend failure" } },
          { status: 500 },
        ),
      ),
    );
    const { result } = renderHook(() =>
      useResource(() => api.request<MachineSummary[]>("/machines"), undefined, {}),
    );

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.status).toBe(500);
    expect(result.current.error?.message).toBe("simulated backend failure");
    expect(result.current.data).toBeNull();
  });

  it("maps network failures to ApiError(0, 'backend unreachable')", async () => {
    server.use(http.get(`${API_BASE}/machines`, () => HttpResponse.error()));
    const { result } = renderHook(() =>
      useResource(() => api.request<MachineSummary[]>("/machines"), undefined, {}),
    );

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.status).toBe(0);
    expect(result.current.error?.message).toBe("backend unreachable");
  });

  it("skips fetching when disabled and reports not-loading", async () => {
    const fetchSpy = vi.fn(async () => MACHINES);
    const { result } = renderHook(() =>
      useResource(fetchSpy, undefined, { enabled: false }),
    );

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(result.current.loading).toBe(false);
  });

  it("refetches on demand and keeps prior data", async () => {
    const counter = { value: 0 };
    swapMachinesHandler(counter);
    const { result } = renderHook(() =>
      useResource(() => api.request<MachineSummary[]>("/machines"), undefined, {}),
    );

    await waitFor(() => expect(result.current.data).not.toBeNull());
    act(() => result.current.refetch());
    await waitFor(() => expect(counter.value).toBe(2));
    expect(result.current.loading).toBe(false); // background refresh keeps data
    expect(result.current.data).not.toBeNull();
  });

  it("refetches when params change", async () => {
    const counter = { value: 0 };
    swapMachinesHandler(counter);
    const { rerender } = renderHook(
      ({ machineId }: { machineId: string }) =>
        useResource(() => api.request<MachineSummary[]>("/machines"), { machineId }),
      { initialProps: { machineId: "SIM-001" } },
    );

    rerender({ machineId: "SIM-002" });
    await waitFor(() => expect(counter.value).toBe(2));
  });
});

describe("useResource polling", () => {
  it("polls on interval when the tab is visible", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const counter = { value: 0 };
    swapMachinesHandler(counter);

    renderHook(() =>
      useResource(() => api.request<MachineSummary[]>("/machines"), undefined, { pollMs: 1000 }),
    );
    await waitFor(() => expect(counter.value).toBeGreaterThanOrEqual(1));

    act(() => {
      vi.advanceTimersByTime(3500);
    });
    // Interval ticks fire additional fetches; an in-flight refetch aborted by
    // the next tick may never reach the handler, so assert growth, not exact.
    await waitFor(() => expect(counter.value).toBeGreaterThanOrEqual(2));
  });

  it("suppresses requests while the tab is hidden", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const counter = { value: 0 };
    swapMachinesHandler(counter);

    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true, writable: true });

    renderHook(() =>
      useResource(() => api.request<MachineSummary[]>("/machines"), undefined, { pollMs: 1000 }),
    );
    // Initial fetch fires regardless of hidden state.
    await waitFor(() => expect(counter.value).toBe(1));

    act(() => {
      vi.advanceTimersByTime(5000);
    });

    // Give any wrongly-scheduled polls a chance to fire.
    await act(async () => {
      await Promise.resolve();
    });
    expect(counter.value).toBe(1);
  });

  it("refetches immediately when the tab becomes visible again", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const counter = { value: 0 };
    swapMachinesHandler(counter);

    renderHook(() =>
      useResource(() => api.request<MachineSummary[]>("/machines"), undefined, { pollMs: 60000 }),
    );
    await waitFor(() => expect(counter.value).toBe(1));

    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true, writable: true });
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await waitFor(() => expect(counter.value).toBe(2), { timeout: 2000 });
  });
});

export {};
