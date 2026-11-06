/**
 * Reactive settings hooks. localStorage is not reactive by nature, so writes
 * dispatch a custom "pma.settings" event that every mounted hook listens to.
 */

import { useSyncExternalStore } from "react";
import type { Dispatch, SetStateAction } from "react";

import {
  DEFAULT_API_BASE_URL,
  DEFAULT_POLL_INTERVAL_MS,
  getApiBaseUrl,
  getPollIntervalMs,
  setApiBaseUrl,
  setPollIntervalMs,
} from "@/api/settings";

const SETTINGS_EVENT = "pma.settings";

function subscribeConfigured(next: () => void): () => void {
  window.addEventListener(SETTINGS_EVENT, next);
  window.addEventListener("storage", next);
  return () => {
    window.removeEventListener(SETTINGS_EVENT, next);
    window.removeEventListener("storage", next);
  };
}

function notifySettings(): void {
  window.dispatchEvent(new Event(SETTINGS_EVENT));
}

/** Global alert-summary polling interval, in ms (0 = off). */
export function usePollInterval(): [number, Dispatch<SetStateAction<number>>] {
  const value = useSyncExternalStore(subscribeConfigured, getPollIntervalMs);
  const setter: Dispatch<SetStateAction<number>> = (next) => {
    const resolved = typeof next === "function" ? (next as (prev: number) => number)(value) : next;
    setPollIntervalMs(resolved);
    notifySettings();
  };
  return [value ?? DEFAULT_POLL_INTERVAL_MS, setter];
}

export function useApiBaseUrl(): [string, Dispatch<SetStateAction<string>>] {
  const value = useSyncExternalStore(subscribeConfigured, getApiBaseUrl);
  const setter: Dispatch<SetStateAction<string>> = (next) => {
    const resolved = typeof next === "function" ? (next as (prev: string) => string)(value) : next;
    setApiBaseUrl(resolved);
    notifySettings();
  };
  return [value ?? DEFAULT_API_BASE_URL, setter];
}

/** Convenience alias used by polling consumers. */
export function usePollIntervalMs(): number {
  return usePollInterval()[0];
}
