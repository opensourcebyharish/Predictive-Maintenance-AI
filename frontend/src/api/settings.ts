/**
 * Backend connection settings, persisted in localStorage so operators can point
 * the dashboard at any backend instance without a rebuild.
 */

const BASE_URL_KEY = "pma.apiBaseUrl";
const POLL_KEY = "pma.pollIntervalMs";

export const DEFAULT_API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000";

export const DEFAULT_POLL_INTERVAL_MS = 5000;

export const POLL_INTERVAL_OPTIONS = [
  { label: "Off (manual only)", value: 0 },
  { label: "1 second", value: 1000 },
  { label: "3 seconds", value: 3000 },
  { label: "5 seconds", value: 5000 },
  { label: "15 seconds", value: 15000 },
  { label: "30 seconds", value: 30000 },
] as const;

function readString(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null; // private mode / storage disabled
  }
}

function writeString(key: string, value: string | null): void {
  try {
    if (value === null) {
      localStorage.removeItem(key);
    } else {
      localStorage.setItem(key, value);
    }
  } catch {
    // storage unavailable - settings simply do not persist
  }
}

/** Effective API base URL (stored > build-time env > default). */
export function getApiBaseUrl(): string {
  const stored = readString(BASE_URL_KEY);
  return stored && stored.trim() !== "" ? stored : DEFAULT_API_BASE_URL;
}

export function setApiBaseUrl(url: string): void {
  writeString(BASE_URL_KEY, url.trim() === "" ? null : url.trim());
}

/** Global polling interval in ms (0 = off). */
export function getPollIntervalMs(): number {
  const raw = readString(POLL_KEY);
  if (raw === null) return DEFAULT_POLL_INTERVAL_MS;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : DEFAULT_POLL_INTERVAL_MS;
}

export function setPollIntervalMs(ms: number): void {
  writeString(POLL_KEY, String(Math.max(0, Math.round(ms))));
}
