/**
 * Minimal typed fetch wrapper for the FastAPI backend.
 *
 * Responsibilities:
 * - JSON decode with exhaustive error surfacing (FastAPI `detail` objects)
 * - Request timeouts via AbortController
 * - A tiny connection-status signal other components can subscribe to
 */

import { getApiBaseUrl } from "@/api/settings";

export class ApiError extends Error {
  readonly status: number;
  /** FastAPI-style detail payload ({error, message}) when present. */
  readonly detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** Connection / disconnection event bus (used by the topbar status badge). */
type ConnectionListener = (connected: boolean) => void;

const listeners = new Set<ConnectionListener>();
let connected = false;

function emit(next: boolean): void {
  if (next !== connected) {
    connected = next;
    for (const fn of listeners) fn(next);
  }
}

export function onConnectionChange(fn: ConnectionListener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function isConnected(): boolean {
  return connected;
}

/** Test-only helper: reset the singleton between cases (fresh module state per test file). */
export function resetConnectionForTests(initial = false): void {
  connected = initial;
}

export interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  timeoutMs?: number;
  query?: Record<string, string | number | boolean | null | undefined>;
  signal?: AbortSignal;
}

function buildUrl(path: string, query: RequestOptions["query"]): string {
  const base = getApiBaseUrl().replace(/\/+$/, "");
  const url = new URL(base + path);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

function describeError(status: number, body: unknown): ApiError {
  let message = `HTTP ${status}`;
  let detail: unknown;
  if (body && typeof body === "object" && "detail" in body) {
    detail = (body as { detail: unknown }).detail;
    const d = detail;
    if (typeof d === "string") {
      message = d;
    } else if (d && typeof d === "object") {
      const err = d as { error?: string; message?: string };
      message = err.message ?? err.error ?? message;
    }
  }
  return new ApiError(status, message, detail);
}

export const api = {
  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const url = buildUrl(path, options.query);
    const controller = new AbortController();
    const timeoutMs = options.timeoutMs ?? 8000;
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    // Chain an external signal (component unmount) onto ours.
    const onOuterAbort = () => controller.abort();
    options.signal?.addEventListener("abort", onOuterAbort, { once: true });

    try {
      const response = await fetch(url, {
        method: options.method ?? "GET",
        headers: options.body !== undefined ? { "Content-Type": "application/json" } : undefined,
        body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
        signal: controller.signal,
      });
      const text = await response.text();
      const parsed: unknown = text === "" ? null : JSON.parse(text);
      if (!response.ok) {
        emit(true);
        throw describeError(response.status, parsed);
      }
      emit(true);
      return parsed as T;
    } catch (error) {
      if (error instanceof ApiError) {
        throw error;
      }
      // Our controller aborts on timeout or external cancel — Node/Browsers
      // report aborts differently, so detect it from the signal itself.
      if (controller.signal.aborted) {
        if (options.signal?.aborted) throw new ApiError(0, "cancelled");
        throw new ApiError(0, "request timed out");
      }
      emit(false);
      throw new ApiError(0, "backend unreachable");
    } finally {
      clearTimeout(timeout);
      options.signal?.removeEventListener("abort", onOuterAbort);
    }
  },
};
