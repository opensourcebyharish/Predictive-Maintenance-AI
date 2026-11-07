import type { ApiHealth, ApiReadiness } from "@/api/types";
import type { ResourceState } from "@/api/hooks";

export type BackendStatusKey =
  | "connecting"
  | "network-failure"
  | "http-failure"
  | "not-ready"
  | "healthy";

interface BackendStatusInput {
  health: ResourceState<ApiHealth>;
  readiness: ResourceState<ApiReadiness>;
  online: boolean | null;
}

/**
 * Backend connectivity and service readiness are separate concerns.
 *
 * - Offline network failures use ApiError.status 0 (the client distinguishes
 *   network errors from HTTP responses).
 * - A successful HTTP response is not proof that the service is ready.
 */
export function classifyBackendStatus(input: BackendStatusInput): BackendStatusKey {
  const { health, readiness, online } = input;
  const networkFailure =
    health.error?.status === 0 || readiness.error?.status === 0 || online === false;

  if (networkFailure) return "network-failure";

  const httpFailure = (health.error?.status ?? 0) > 0 || (readiness.error?.status ?? 0) > 0;
  if (httpFailure) return "http-failure";

  const notReady =
    (health.data !== null && (health.data.status !== "ok" || !health.data.service_loaded)) ||
    (readiness.data !== null && !readiness.data.ready);
  if (notReady) return "not-ready";

  if (health.data !== null && readiness.data !== null) return "healthy";
  return "connecting";
}
