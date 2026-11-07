import { useEffect, useState } from "react";
import { Cloud, CloudOff, Radio } from "lucide-react";

import { onConnectionChange } from "@/api/client";
import { fetchHealth, fetchReadiness } from "@/api/endpoints";
import { useResource } from "@/api/hooks";
import { classifyBackendStatus } from "@/lib/backendStatus";
import { StatusDot } from "@/components/ui/StatusDot";

/** Topbar pill showing live backend connection and service-readiness state. */
export function ConnectionBadge() {
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => onConnectionChange((next) => setOnline(next)), []);

  const health = useResource(() => fetchHealth(), undefined, { pollMs: 30000 });
  const readiness = useResource(() => fetchReadiness(), undefined, { pollMs: 30000 });
  const status = classifyBackendStatus({ health, readiness, online });

  const networkFailure = status === "network-failure";
  const httpFailure = status === "http-failure";
  const notReady = status === "not-ready";
  const servicesReady = status === "healthy";
  const connected = servicesReady || notReady;

  const label = networkFailure
    ? "Backend offline · network failure"
    : httpFailure
      ? `Backend HTTP failure · ${health.error?.status ?? readiness.error?.status ?? "unknown"}`
      : notReady
        ? "Backend connected · service not ready"
        : servicesReady
          ? `Backend online · v${health.data?.version ?? "?"} · services ready`
          : "Connecting…";

  return (
    <div
      className={`flex items-center gap-2 rounded-md border px-2.5 py-1 text-xs shadow-panel ${
        connected
          ? notReady
            ? "border-warning/25 bg-warning/5"
            : "border-edge bg-panel-2"
          : "border-critical/25 bg-critical/5"
      }`}
      role="status"
      aria-label={`Backend connection: ${label}`}
      data-backend-status={
        networkFailure
          ? "network-failure"
          : httpFailure
            ? "http-failure"
            : notReady
              ? "not-ready"
              : servicesReady
                ? "healthy"
                : "connecting"
      }
    >
      {connected ? (
        <>
          <StatusDot
            color={notReady ? "bg-warning" : "bg-healthy"}
            pulse
            label={notReady ? "Connected" : "Connected"}
          />
          <Cloud
            aria-hidden
            className={`h-3.5 w-3.5 ${notReady ? "text-warning" : "text-healthy"}`}
          />
        </>
      ) : (
        <>
          <StatusDot color="bg-critical" pulse label="Disconnected" />
          <CloudOff aria-hidden className="h-3.5 w-3.5 text-critical" />
        </>
      )}
      <span className={servicesReady ? "text-ink-dim" : connected ? "text-warning" : "text-critical"}>
        {label}
      </span>
      {servicesReady && <Radio aria-hidden className="h-3.5 w-3.5 text-accent" />}
    </div>
  );
}
