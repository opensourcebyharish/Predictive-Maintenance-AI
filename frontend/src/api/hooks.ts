/**
 * useResource - data fetching for the dashboard.
 *
 * Features required by the product spec:
 * - loading / error / data / lastUpdated state
 * - explicit refetch
 * - optional background polling that pauses while the tab is hidden
 *   (avoids unnecessary API requests) and stops when unmounted (abort)
 * - no request coalescing needed: a new fetch aborts the previous one
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/api/client";

export interface ResourceState<T> {
  data: T | null;
  error: ApiError | null;
  // True only when there is no data to show yet (initial load). Background
  // refetches keep the previous data on screen instead. Derived during
  // render from data/error/enabled (no cascading setState in effects).
  loading: boolean;
  lastUpdated: number | null;
  refetch: () => void;
}

export interface UseResourceOptions {
  /** Polling interval in ms; 0 disables polling. */
  pollMs?: number;
  /** Skip fetching entirely (e.g. no machine selected yet). */
  enabled?: boolean;
}

export function useResource<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  params: Record<string, unknown> | undefined,
  options: UseResourceOptions = {},
): ResourceState<T> {
  const { pollMs = 0, enabled = true } = options;
  const paramKey = params ? JSON.stringify(params) : "";

  // Keep the freshest fetcher for the effect below without adding it to its
  // deps. The sync effect is declared before the fetching effect, so effects
  // run in order: the ref is updated before each fetch.
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  // Version counter bumped by every refetch trigger (poll, manual, deps).
  const [tick, setTick] = useState(0);

  const refetch = useCallback(() => setTick((n) => n + 1), []);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    let cancelled = false;

    void (async () => {
      try {
        const result = await fetcherRef.current(controller.signal);
        if (cancelled) return;
        setData(result);
        setError(null);
        setLastUpdated(Date.now());
      } catch (caught) {
        if (cancelled) return;
        if (caught instanceof ApiError && caught.status === 0 && caught.message === "cancelled") {
          return; // superseded by a newer request or unmount
        }
        setError(caught instanceof ApiError ? caught : new ApiError(0, String(caught)));
        setLastUpdated(Date.now());
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [enabled, paramKey, tick]);

  // Polling: only fire when the tab is visible and no initial load is running.
  useEffect(() => {
    if (!enabled || pollMs <= 0) return;
    const handle = window.setInterval(() => {
      if (document.visibilityState === "visible") refetch();
    }, pollMs);
    // Also refresh immediately when the tab becomes visible after being away.
    const onVisible = () => {
      if (document.visibilityState === "visible") refetch();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(handle);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [enabled, pollMs, refetch]);

  // Derived: true only for the very first load (nothing to show yet).
  const loading = enabled && data === null && error === null;

  return { data, error, loading, lastUpdated, refetch };
}
