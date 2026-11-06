import { ArrowLeft, Sparkles } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import {
  fetchMachine,
  fetchMachineReadings,
} from "@/api/endpoints";
import { useResource } from "@/api/hooks";
import { usePollIntervalMs } from "@/api/useSettings";
import { MetricBar } from "@/components/charts/MetricBar";
import { SensorGrid } from "@/components/panels/SensorGrid";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { Badge, SimBadge } from "@/components/ui/Badge";
import { StatTile } from "@/components/ui/StatTile";
import { EmptyState, ErrorState, LoadingState, Skeleton } from "@/components/ui/States";
import { formatAgo, formatDateTime, formatNumber, formatPercent, healthLabel } from "@/lib/format";
import { SERIES } from "@/lib/health";

/** One device: identity, current verdict, latest reading with provenance, history. */
export function DeviceDetailPage() {
  const { machineId = "" } = useParams();
  const pollMs = usePollIntervalMs();

  const params = useMemoParams(machineId);
  const detail = useResource(() => fetchMachine(machineId), params, { pollMs, enabled: machineId !== "" });
  const readings = useResource(() => fetchMachineReadings(machineId, 200), params, { pollMs, enabled: machineId !== "" });

  const latestReading = readings.data?.readings.at(-1) ?? null;

  const prediction = detail.data?.latest_prediction ?? null;
  const lastSimulated = recentSimulatedShare(readings.data?.readings ?? []);

  return (
    <>
      <PageHeader
        title={machineId || "Device"}
        description={`Dataset ${detail.data?.dataset_id ?? "—"} · verdict ${healthLabel(detail.data?.health ?? "unknown")}`}
        actions={
          <Link to="/devices" className="flex items-center gap-1.5 rounded border border-edge bg-panel-2 px-2.5 py-1 text-xs text-ink-dim transition hover:border-accent/40 hover:text-accent">
            <ArrowLeft aria-hidden className="h-3.5 w-3.5" />
            All devices
          </Link>
        }
      />

      {detail.error ? (
        <ErrorState message={detail.error.message} onRetry={detail.refetch} />
      ) : detail.data === null ? (
        <LoadingState rows={4} />
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile index={0} label="Readings" value={detail.data.reading_count} />
            <StatTile index={1} label="Current cycle" value={detail.data.last_cycle ?? "—"} />
            <StatTile index={2} label="Active alerts" value={detail.data.active_alerts} tone={detail.data.active_alerts > 0 ? "warning" : "healthy"} />
            <StatTile index={3} label="Health" value={healthLabel(detail.data.health)} tone={detail.data.health} />
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <Panel title="Latest prediction" subtitle={prediction ? `${prediction.model} · ${prediction.model_version}` : "no prediction yet"} className="xl:col-span-1">
              {prediction ? (
                <div className="space-y-4">
                  <MetricBar
                    label="Failure probability"
                    value={prediction.failure_probability}
                    color={SERIES.critical}
                    caption="thresholds 0.5 / 0.8 mark elevated and critical risk"
                  />
                  <MetricBar
                    label="Anomaly score"
                    value={prediction.anomaly_score}
                    thresholds={[]}
                    color={SERIES.info}
                    display={prediction.anomaly_score === null || prediction.anomaly_score === undefined ? "—" : formatNumber(prediction.anomaly_score)}
                  />
                  <p className="text-xs text-ink-faint">
                    {formatDateTime(prediction.predicted_at)} · failure rule{" "}
                    {prediction.failure_status === true ? "triggered" : "not triggered"}
                  </p>
                </div>
              ) : (
                <EmptyState compact title="No prediction stored" hint="Predictions are generated at ingestion time." />
              )}
            </Panel>

            <Panel
              title="Latest reading"
              subtitle={latestReading ? `cycle ${latestReading.cycle} · stored ${formatAgo(latestReading.stored_at)}` : "no readings yet"}
              actions={latestReading ? <SimBadge isSimulated={latestReading.is_simulated} /> : undefined}
              className="xl:col-span-2"
            >
              {latestReading ? (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-ink-dim">
                    <span className="font-medium text-ink">Source</span>
                    <Badge tone="info">{latestReading.is_simulated ? "Simulated (Phase 4 simulator)" : "Real device payload"}</Badge>
                    <span>· {lastSimulated}</span>
                  </div>
                  <SensorGrid values={latestReading.sensor_values} />
                  <p className="text-[10px] text-ink-faint">
                    Group hints (temperature / speed / pressure) are conceptual simulation groupings, not validated physical mappings.
                  </p>
                </div>
              ) : readings.data !== null ? (
                <EmptyState compact title="No readings stored for this machine" />
              ) : (
                <Skeleton className="h-32 w-full" />
              )}
            </Panel>
          </div>

          <Panel title="Reading history" subtitle="200 most recent cycles (chrono order) with provenance" flush>
            {readings.data === null ? (
              <div className="p-4">
                <LoadingState rows={3} />
              </div>
            ) : readings.data.readings.length > 0 ? (
              <div className="max-h-[360px] overflow-auto">
                <table className="w-full text-left text-sm">
                  <thead className="sticky top-0 bg-panel-2 text-[11px] tracking-wide text-ink-faint uppercase">
                    <tr>
                      <th scope="col" className="px-4 py-2 font-medium">Cycle</th>
                      <th scope="col" className="px-4 py-2 font-medium">Timestamp</th>
                      <th scope="col" className="px-4 py-2 font-medium">Source</th>
                      <th scope="col" className="px-4 py-2 font-medium">s2</th>
                      <th scope="col" className="px-4 py-2 font-medium">s8</th>
                      <th scope="col" className="px-4 py-2 font-medium">s11</th>
                    </tr>
                  </thead>
                  <tbody>
                    {readings.data.readings.slice(-60).reverse().map((reading) => (
                      <tr key={reading.id} className="border-t border-edge/60 hover:bg-white/2">
                        <td className="tnum px-4 py-1.5 font-medium text-ink">{reading.cycle}</td>
                        <td className="px-4 py-1.5 text-xs text-ink-dim">{formatDateTime(reading.timestamp)}</td>
                        <td className="px-4 py-1.5">
                          <SimBadge isSimulated={reading.is_simulated} />
                        </td>
                        <td className="tnum px-4 py-1.5 text-ink-dim">{formatNumber(reading.sensor_values.s2 ?? null, 4)}</td>
                        <td className="tnum px-4 py-1.5 text-ink-dim">{formatNumber(reading.sensor_values.s8 ?? null, 4)}</td>
                        <td className="tnum px-4 py-1.5 text-ink-dim">{formatNumber(reading.sensor_values.s11 ?? null, 4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState title="No readings stored" />
            )}
          </Panel>

          <p className="flex items-start gap-1.5 text-xs text-ink-faint">
            <Sparkles aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent/70" />
            Simulated readings are generated by the Phase 4 IoT simulator and are clearly labelled — they are not physical
            measurements. Health verdicts come from frozen Phase 2 models via the API.
          </p>
        </div>
      )}
    </>
  );
}

function useMemoParams(machineId: string): { machineId: string } | undefined {
  return machineId === "" ? undefined : { machineId };
}

/** Share of simulated readings among the most recent batch (informational). */
function recentSimulatedShare(readings: { is_simulated: boolean }[]): string {
  const recent = readings.slice(-20);
  if (recent.length === 0) return "";
  const simulated = recent.filter((r) => r.is_simulated).length;
  if (simulated === 0) return "recent readings: real";
  return `recent readings: ${simulated}/${recent.length} simulated (${formatPercent(simulated / recent.length, 0)})`;
}
