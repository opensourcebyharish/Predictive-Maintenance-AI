import { useEffect, useState } from "react";
import { Cloud, CloudOff, Radio } from "lucide-react";

import { onConnectionChange } from "@/api/client";
import { fetchHealth } from "@/api/endpoints";
import { useResource } from "@/api/hooks";
import { StatusDot } from "@/components/ui/StatusDot";

/** Topbar pill showing live backend connection state. */
export function ConnectionBadge() {
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => onConnectionChange((next) => setOnline(next)), []);

  const health = useResource(() => fetchHealth(), undefined, { pollMs: 30000 });

  // Only surface "connected" once a health request has actually succeeded.
  const connected = health.error === null && online !== false;

  const label = health.loading && online === null
    ? "Connecting…"
    : connected
      ? `Backend online · v${health.data?.version ?? "?"}`
      : "Backend offline";

  return (
    <div
      className="flex items-center gap-2 rounded border border-edge bg-panel-2 px-2.5 py-1 text-xs"
      role="status"
      aria-label={`Backend connection: ${label}`}
    >
      {connected ? (
        <>
          <StatusDot color="bg-healthy" pulse label="Connected" />
          <Cloud aria-hidden className="h-3.5 w-3.5 text-healthy" />
        </>
      ) : (
        <>
          <StatusDot color="bg-critical" pulse label="Disconnected" />
          <CloudOff aria-hidden className="h-3.5 w-3.5 text-critical" />
        </>
      )}
      <span className={connected ? "text-ink-dim" : "text-critical"}>{label}</span>
      {connected && health.data?.service_loaded === true && (
        <Radio aria-hidden className="h-3.5 w-3.5 text-accent" />
      )}
    </div>
  );
}
