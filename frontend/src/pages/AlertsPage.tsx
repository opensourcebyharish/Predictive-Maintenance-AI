import { useState } from "react";
import { BadgeCheck, Check, Filter, HeartPulse } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { acknowledgeAlert, fetchAlertSummary, fetchAlerts, fetchMachines } from "@/api/endpoints";
import { useResource } from "@/api/hooks";
import { usePollIntervalMs } from "@/api/useSettings";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { Badge } from "@/components/ui/Badge";
import { StatTile } from "@/components/ui/StatTile";
import { EmptyState, ErrorState, LoadingState, Skeleton } from "@/components/ui/States";
import { formatDateTime, shortId } from "@/lib/format";
import { ALERT_TYPE_LABELS, SEVERITY_STYLES } from "@/lib/health";
import type { AlertSeverity, AlertStatus, AlertType } from "@/api/types";

const STATUS_FILTERS: { value: "" | AlertStatus; label: string }[] = [
  { value: "", label: "All" },
  { value: "active", label: "Active" },
  { value: "acknowledged", label: "Acknowledged" },
  { value: "resolved", label: "Resolved" },
];

const SELECT_CLASS =
  "rounded-md border border-edge bg-panel-2 px-2 py-1 text-xs text-ink outline-hidden transition-colors hover:border-edge-bright focus:border-accent/50";

function severityTone(severity: AlertSeverity): "critical" | "warning" | "info" | "neutral" {
  if (severity === "critical") return "critical";
  if (severity === "high") return "warning";
  if (severity === "medium") return "info";
  return "neutral";
}

function statusTone(status: AlertStatus): "critical" | "warning" | "info" | "healthy" {
  if (status === "active") return "warning";
  if (status === "acknowledged") return "info";
  return "healthy";
}

function typeLabel(type: AlertType): string {
  return ALERT_TYPE_LABELS[type];
}

/** Alert management: filters, severity chips, acknowledge action, recovery trail. */
export function AlertsPage() {
  const pollMs = usePollIntervalMs();
  const [params, setParams] = useSearchParams();
  const statusFilter = (params.get("status") as AlertStatus | null) ?? "";
  const machineFilter = params.get("machine") ?? "";

  const machines = useResource(() => fetchMachines(), undefined, { pollMs: 0 });
  const summary = useResource(() => fetchAlertSummary(), undefined, { pollMs: pollMs > 0 ? Math.max(pollMs, 15000) : 0 });

  const alerts = useResource(
    () => fetchAlerts({ status: statusFilter === "" ? undefined : statusFilter, machineId: machineFilter === "" ? undefined : machineFilter, limit: 300 }),
    { status: statusFilter, machine: machineFilter },
    { pollMs },
  );

  const [acking, setAcking] = useState<number | null>(null);
  const [ackError, setAckError] = useState<string | null>(null);

  const data = alerts.data;
  const recoveries = (data ?? []).filter((a) => a.alert_type === "machine_recovered");

  function setFilter(key: "status" | "machine", value: string): void {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value === "") next.delete(key);
        else next.set(key, value);
        return next;
      },
      { replace: true },
    );
  }

  async function handleAcknowledge(alertId: number): Promise<void> {
    setAcking(alertId);
    setAckError(null);
    try {
      await acknowledgeAlert(alertId);
      alerts.refetch();
      summary.refetch();
    } catch (error) {
      setAckError(error instanceof Error ? error.message : String(error));
    } finally {
      setAcking(null);
    }
  }

  return (
    <>
      <PageHeader
        title="Alerts & Incidents"
        description="Live alert stream from the Phase 3.6 alert engine. Acknowledging requires an active alert; resolution happens automatically on machine recovery."
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {summary.data === null ? (
          [...Array(4)].map((_, i) => <Skeleton key={i} className="h-[104px]" />)
        ) : (
          <>
            <StatTile index={0} label="Active" value={summary.data.by_status["active"] ?? 0} tone="warning" />
            <StatTile index={1} label="Acknowledged" value={summary.data.by_status["acknowledged"] ?? 0} tone="info" />
            <StatTile index={2} label="Resolved" value={summary.data.by_status["resolved"] ?? 0} tone="healthy" />
            <StatTile index={3} label="Total" value={summary.data.total} />
          </>
        )}
      </div>

      <div className="mt-5 space-y-4">
        <Panel
          title="Alert stream"
          subtitle="Newest first · filtered results update the URL so views are shareable"
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <Filter aria-hidden className="h-3.5 w-3.5 text-ink-faint" />
              <select
                aria-label="Status filter"
                value={statusFilter}
                onChange={(e) => setFilter("status", e.target.value)}
                className={SELECT_CLASS}
              >
                {STATUS_FILTERS.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>
              <select
                aria-label="Machine filter"
                value={machineFilter}
                onChange={(e) => setFilter("machine", e.target.value)}
                className={`max-w-40 ${SELECT_CLASS}`}
              >
                <option value="">All machines</option>
                {(machines.data ?? []).map((m) => (
                  <option key={m.machine_id} value={m.machine_id}>
                    {shortId(m.machine_id)}
                  </option>
                ))}
              </select>
            </div>
          }
          flush
        >
          {ackError !== null && (
            <div className="px-4 pt-3">
              <ErrorState compact message={`Acknowledgement failed: ${ackError}`} onRetry={() => setAckError(null)} />
            </div>
          )}
          {alerts.error ? (
            <div className="p-4">
              <ErrorState message={alerts.error.message} onRetry={alerts.refetch} />
            </div>
          ) : data === null ? (
            <div className="p-4">
              <LoadingState rows={4} />
            </div>
          ) : data.length === 0 ? (
            <EmptyState
              title={statusFilter === "" && machineFilter === "" ? "No alerts recorded yet" : "No alerts match the selected filters"}
              hint="Alerts appear when the engine detects anomalies or failure risk during ingestion."
            />
          ) : (
            <div className="max-h-[460px] overflow-auto">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 z-10 bg-panel-2 text-[11px] tracking-wide text-ink-faint uppercase">
                  <tr className="[&>th]:border-b [&>th]:border-edge">
                    <th scope="col" className="px-4 py-2 font-medium">Alert</th>
                    <th scope="col" className="px-4 py-2 font-medium">Severity</th>
                    <th scope="col" className="px-4 py-2 font-medium">Machine</th>
                    <th scope="col" className="px-4 py-2 font-medium">Created</th>
                    <th scope="col" className="px-4 py-2 font-medium">Status</th>
                    <th scope="col" className="px-4 py-2 text-right font-medium">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map((alert) => {
                    const severity = SEVERITY_STYLES[alert.severity];
                    const active = alert.status === "active";
                    const resolved = alert.status === "resolved";
                    return (
                      <tr
                        key={alert.id}
                        className={`border-t border-edge/60 align-top transition-colors duration-150 hover:bg-panel-2/60 ${active ? "border-l-2 border-l-warning/70" : ""}`}
                      >
                        <td className="px-4 py-2.5">
                          <div className="flex items-start gap-2">
                            <span
                              className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${active ? "bg-warning animate-pulse-soft" : resolved ? "bg-healthy" : "bg-info"} ${resolved ? "opacity-60" : ""}`}
                              aria-hidden="true"
                            />
                            <div>
                              <p className="font-medium text-ink">{typeLabel(alert.alert_type)}</p>
                              <p className="max-w-md break-words text-xs text-ink-dim">{alert.message}</p>
                              {alert.acknowledged_at !== null && (
                                <p className="mt-0.5 text-[10px] text-ink-faint">
                                  ack <BadgeCheck aria-hidden className="mr-0.5 inline h-3 w-3 text-info" />
                                  {formatDateTime(alert.acknowledged_at)} by {alert.acknowledged_by ?? "—"}
                                </p>
                              )}
                              {alert.resolved_at !== null && (
                                <p className="mt-0.5 text-[10px] text-ink-faint">resolved {formatDateTime(alert.resolved_at)}</p>
                              )}
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-2.5">
                          <Badge tone={severityTone(alert.severity)}>{severity.label}</Badge>
                        </td>
                        <td className="px-4 py-2.5">
                          <Link to={`/devices/${encodeURIComponent(alert.machine_id)}`} className="tnum font-medium text-ink transition-colors hover:text-accent">
                            {shortId(alert.machine_id)}
                          </Link>
                        </td>
                        <td className="px-4 py-2.5 text-xs text-ink-dim">{formatDateTime(alert.created_at)}</td>
                        <td className="px-4 py-2.5">
                          <Badge tone={statusTone(alert.status)}>{alert.status}</Badge>
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          {alert.status === "active" ? (
                            <button
                              type="button"
                              disabled={acking !== null}
                              onClick={() => void handleAcknowledge(alert.id)}
                              className="inline-flex items-center gap-1 rounded-md border border-info/40 bg-info/10 px-2.5 py-1 text-xs font-medium text-info transition-colors hover:bg-info/20 disabled:opacity-50"
                            >
                              <Check aria-hidden className="h-3.5 w-3.5" />
                              {acking === alert.id ? "Saving…" : "Acknowledge"}
                            </button>
                          ) : (
                            <span className="text-xs text-ink-faint">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="Recovery history" subtitle="machine_recovered events emitted when a machine returned to healthy">
          {alerts.data === null ? (
            <LoadingState rows={1} />
          ) : recoveries.length === 0 ? (
            <EmptyState compact title="No recovery events yet" hint="Recovery alerts fire automatically when a machine returns to healthy state." />
          ) : (
            <ul className="space-y-2">
              {recoveries.map((alert) => (
                <li
                  key={alert.id}
                  className="flex flex-wrap items-center gap-2 rounded-md border border-healthy/20 bg-healthy/5 px-3 py-2 text-sm transition-colors hover:border-healthy/40"
                >
                  <Badge tone="healthy" aria-hidden={false}>
                    <HeartPulse aria-hidden className="h-3 w-3" />
                    Recovered
                  </Badge>
                  <Link to={`/devices/${encodeURIComponent(alert.machine_id)}`} className="tnum font-medium text-ink transition-colors hover:text-accent">
                    {shortId(alert.machine_id)}
                  </Link>
                  <span className="text-xs text-ink-faint">{formatDateTime(alert.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </>
  );
}
