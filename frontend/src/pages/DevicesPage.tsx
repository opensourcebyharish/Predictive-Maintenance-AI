import { Clock, Database, Layers } from "lucide-react";
import { Link } from "react-router-dom";

import { fetchMachines } from "@/api/endpoints";
import { useResource } from "@/api/hooks";
import { usePollIntervalMs } from "@/api/useSettings";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { formatAgo, healthLabel, shortId } from "@/lib/format";
import { healthStyle } from "@/lib/health";

/** Device inventory with dataset association and last-seen state. */
export function DevicesPage() {
  const pollMs = usePollIntervalMs();
  const machines = useResource(() => fetchMachines(), undefined, { pollMs });
  const data = machines.data ?? [];

  return (
    <>
      <PageHeader
        title="Device Management"
        description="Every machine that has ingested at least one reading. Reading-level Sim/Real provenance is shown on the device detail page."
      />

      {machines.error ? (
        <ErrorState message={machines.error.message} onRetry={machines.refetch} />
      ) : machines.data === null ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} className="h-44" />
          ))}
        </div>
      ) : data.length === 0 ? (
        <Panel title="Devices">
          <EmptyState
            title="No devices registered yet"
            hint="Devices appear automatically the first time a reading is ingested for a machine id."
          />
        </Panel>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {data.map((machine) => {
            const style = healthStyle(machine.health);
            return (
              <Link
                key={machine.machine_id}
                to={`/devices/${encodeURIComponent(machine.machine_id)}`}
                className="group rounded-lg border border-edge bg-panel/80 p-4 transition hover:border-accent/40 focus-visible:border-accent"
                aria-label={`Open device ${machine.machine_id}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2 text-sm font-semibold text-ink group-hover:text-accent">
                    <span className={`h-2.5 w-2.5 rounded-full ${style.dot}`} aria-hidden="true" />
                    {shortId(machine.machine_id)}
                  </span>
                  <span className={`rounded border px-1.5 py-0.5 text-[11px] ${style.chip}`}>{healthLabel(machine.health)}</span>
                </div>

                <dl className="mt-3 space-y-1.5 text-xs">
                  <div className="flex items-center justify-between">
                    <dt className="flex items-center gap-1.5 text-ink-faint">
                      <Database aria-hidden className="h-3.5 w-3.5" />
                      Dataset
                    </dt>
                    <dd className="font-medium text-ink">{machine.dataset_id}</dd>
                  </div>
                  <div className="flex items-center justify-between">
                    <dt className="flex items-center gap-1.5 text-ink-faint">
                      <Layers aria-hidden className="h-3.5 w-3.5" />
                      Readings
                    </dt>
                    <dd className="tnum font-medium text-ink">{machine.reading_count.toLocaleString()}</dd>
                  </div>
                  <div className="flex items-center justify-between">
                    <dt className="flex items-center gap-1.5 text-ink-faint">
                      <Clock aria-hidden className="h-3.5 w-3.5" />
                      Last reading
                    </dt>
                    <dd className="tnum font-medium text-ink">{formatAgo(machine.latest_reading_at)}</dd>
                  </div>
                  <div className="flex items-center justify-between">
                    <dt className="text-ink-faint">Cycle range</dt>
                    <dd className="tnum font-medium text-ink">
                      {machine.first_cycle !== null ? `${machine.first_cycle} → ${machine.last_cycle}` : "—"}
                    </dd>
                  </div>
                </dl>

                <span className="mt-3 block border-t border-edge/60 pt-2 text-[10px] text-ink-faint">
                  provenance shown per reading on detail
                </span>
              </Link>
            );
          })}
        </div>
      )}
    </>
  );
}
