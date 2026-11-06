import { motion } from "framer-motion";
import { Activity, AlertTriangle, Cpu, HeartPulse, ShieldAlert, Timer } from "lucide-react";
import { Link } from "react-router-dom";

import { fetchAlerts, fetchAlertSummary, fetchMachines } from "@/api/endpoints";
import { useResource } from "@/api/hooks";
import { usePollIntervalMs } from "@/api/useSettings";
import { HealthDonut } from "@/components/charts/HealthDonut";
import { Badge } from "@/components/ui/Badge";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { StatTile } from "@/components/ui/StatTile";
import { EmptyState, ErrorState, LoadingState, Skeleton } from "@/components/ui/States";
import { formatAgo, formatCount, shortId } from "@/lib/format";
import { ALERT_STATUS_STYLES, ALERT_TYPE_LABELS, SEVERITY_STYLES, healthStyle } from "@/lib/health";
import type { AlertRecord, AlertSeverity, AlertStatus } from "@/api/types";

/** Chip tone for an alert status without leaking presentation into types. */
function statusTone(status: AlertStatus): "warning" | "info" | "healthy" | "neutral" {
  if (status === "active") return "warning";
  if (status === "acknowledged") return "info";
  if (status === "resolved") return "healthy";
  return "neutral";
}

function severityTone(severity: AlertSeverity): "critical" | "warning" | "info" | "neutral" {
  if (severity === "critical") return "critical";
  if (severity === "high") return "warning";
  if (severity === "medium") return "info";
  return "neutral";
}

/** Fleet overview: KPI tiles, health distribution, incidents, risk trend. */
export function OverviewPage() {
  const pollMs = usePollIntervalMs();

  const machines = useResource(() => fetchMachines(), undefined, { pollMs });
  const summary = useResource(() => fetchAlertSummary(), undefined, { pollMs });
  const incidents = useResource(
    () => fetchAlerts({ limit: 6 }),
    undefined,
    { pollMs: pollMs > 0 ? Math.max(pollMs, 20000) : 0 },
  );

  const data = machines.data;
  const counts = {
    total: data?.length ?? 0,
    healthy: data?.filter((m) => m.health === "healthy").length ?? 0,
    warning: data?.filter((m) => m.health === "anomalous" || m.health === "elevated_risk").length ?? 0,
    critical: data?.filter((m) => m.health === "critical_risk").length ?? 0,
  };
  const active = summary.data?.by_status["active"] ?? 0;

  return (
    <>
      <PageHeader
        title="Fleet Overview"
        description="Aggregated machine health, alert load and simulated-vs-real ingestion status across the whole plant."
        actions={
          <>
            {summary.error !== null && (
              <Badge tone="critical">
                <AlertTriangle aria-hidden className="h-3 w-3" />
                Alert summary failed
              </Badge>
            )}
            <Badge tone="info">
              <Timer aria-hidden className="h-3 w-3" />
              {pollMs > 0 ? `Polling ${pollMs / 1000}s` : "Manual refresh"}
            </Badge>
          </>
        }
      />

      {machines.error ? (
        <ErrorState message={machines.error.message} onRetry={machines.refetch} />
      ) : (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          {data === null ? (
            [...Array(5)].map((_, i) => <Skeleton key={i} className="h-24" />)
          ) : (
            <>
              <StatTile index={0} label="Machines" value={counts.total} icon={<Cpu aria-hidden className="h-4 w-4" />} hint="ingested devices" />
              <StatTile index={1} label="Healthy" value={counts.healthy} tone="healthy" icon={<HeartPulse aria-hidden className="h-4 w-4" />} />
              <StatTile index={2} label="Warning" value={counts.warning} tone="anomalous" icon={<AlertTriangle aria-hidden className="h-4 w-4" />} hint="anomaly or elevated risk" />
              <StatTile index={3} label="Critical" value={counts.critical} tone="critical_risk" icon={<ShieldAlert aria-hidden className="h-4 w-4" />} />
              <StatTile index={4} label="Active alerts" value={active} tone={active > 0 ? "warning" : "healthy"} icon={<Activity aria-hidden className="h-4 w-4" />} hint={`${formatCount(summary.data?.total ?? 0)} lifetime`} ariaLabel={`Active alerts: ${active}`} />
            </>
          )}
        </div>
      )}

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Panel title="Machine health distribution" subtitle="Share of fleet per health verdict">
          {data === null && !machines.error ? (
            <LoadingState rows={2} />
          ) : (
            <HealthDonut machines={data ?? []} />
          )}
        </Panel>

        <Panel
          title="Fleet status"
          subtitle="Live machine verdicts (newest first)"
          flush
          className="xl:col-span-2"
        >
          {data === null && !machines.error ? (
            <div className="p-4">
              <LoadingState />
            </div>
          ) : data !== null && data.length === 0 ? (
            <EmptyState
              title="No machines have ingested readings yet"
              hint={
                <>
                  Start the Phase 4 simulator (see Settings ▸ Simulator) or POST to <code className="rounded bg-white/6 px-1">/readings</code>
                  {" "}to populate the fleet.
                </>
              }
            />
          ) : (
            <div className="max-h-[320px] overflow-auto">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-panel-2 text-[11px] tracking-wide text-ink-faint uppercase">
                  <tr>
                    <th scope="col" className="px-4 py-2 font-medium">Machine</th>
                    <th scope="col" className="px-4 py-2 font-medium">Dataset</th>
                    <th scope="col" className="px-4 py-2 font-medium">Health</th>
                    <th scope="col" className="px-4 py-2 font-medium">Cycles</th>
                    <th scope="col" className="px-4 py-2 font-medium">Last reading</th>
                  </tr>
                </thead>
                <tbody>
                  {(data ?? []).map((machine) => {
                    const style = healthStyle(machine.health);
                    return (
                      <tr key={machine.machine_id} className="border-t border-edge/60 hover:bg-white/2">
                        <td className="px-4 py-2">
                          <Link to={`/devices/${encodeURIComponent(machine.machine_id)}`} className="font-medium text-ink hover:text-accent">
                            {shortId(machine.machine_id)}
                          </Link>
                        </td>
                        <td className="px-4 py-2 text-ink-dim">{machine.dataset_id}</td>
                        <td className="px-4 py-2">
                          <span className="inline-flex items-center gap-2">
                            <span className={`h-2 w-2 rounded-full ${style.dot}`} aria-hidden="true" />
                            <span className={style.text}>{style.label}</span>
                          </span>
                        </td>
                        <td className="tnum px-4 py-2 text-ink-dim">
                          {machine.first_cycle !== null ? `${machine.first_cycle}–${machine.last_cycle}` : "—"}
                        </td>
                        <td className="px-4 py-2 text-ink-dim">{formatAgo(machine.latest_reading_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>

      <div className="mt-4">
        <Panel
          title="Recent incidents"
          subtitle="Newest alerts across the fleet"
          flush
          actions={
            <Link to="/alerts" className="text-xs font-medium text-accent hover:underline">
              View all →
            </Link>
          }
        >
          {incidents.data === null && !incidents.error ? (
            <div className="p-4">
              <LoadingState rows={2} />
            </div>
          ) : (incidents.data?.length ?? 0) === 0 ? (
            <EmptyState compact title="No alerts recorded in this database yet" hint="Alerts appear when the alert engine detects anomalies or failure risk." />
          ) : (
            <motion.ul
              initial="hidden"
              animate="visible"
              variants={{ visible: { transition: { staggerChildren: 0.04 } } }}
              className="divide-y divide-edge/60"
            >
              {(incidents.data ?? []).map((alert: AlertRecord) => {
                const severity = SEVERITY_STYLES[alert.severity];
                const status = ALERT_STATUS_STYLES[alert.status];
                return (
                  <motion.li
                    key={alert.id}
                    variants={{ hidden: { opacity: 0, y: 6 }, visible: { opacity: 1, y: 0 } }}
                    className="flex flex-wrap items-center gap-2 px-4 py-2.5"
                  >
                    <span className={`h-1.5 w-1.5 rounded-full ${alert.status === "active" ? "bg-warning animate-pulse-soft" : "bg-ink-faint"}`} aria-hidden="true" />
                    <span className="text-sm font-medium text-ink">{ALERT_TYPE_LABELS[alert.alert_type]}</span>
                    <Badge tone={severityTone(alert.severity)}>
                      {severity.label}
                    </Badge>
                    <Badge tone={statusTone(alert.status)}>
                      {status.label}
                    </Badge>
                    <span className="text-xs text-ink-faint">on</span>
                    <Link to={`/devices/${encodeURIComponent(alert.machine_id)}`} className="text-xs font-medium text-ink hover:text-accent">
                      {shortId(alert.machine_id)}
                    </Link>
                    <span className="ml-auto text-xs text-ink-faint">{formatAgo(alert.created_at)}</span>
                  </motion.li>
                );
              })}
            </motion.ul>
          )}
        </Panel>
      </div>
    </>
  );
}
