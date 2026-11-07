import { useMemo, useState } from "react";
import { RefreshCw, Waves } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import {
  fetchMachineHealth,
  fetchMachineReadings,
  fetchMachines,
} from "@/api/endpoints";
import { useResource } from "@/api/hooks";
import {
  DEFAULT_POLL_INTERVAL_MS,
  POLL_INTERVAL_OPTIONS,
  getPollIntervalMs,
} from "@/api/settings";
import { MetricBar } from "@/components/charts/MetricBar";
import { TrendChart } from "@/components/charts/TrendChart";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { SimBadge } from "@/components/ui/Badge";
import { EmptyState, ErrorState, LoadingState, Skeleton } from "@/components/ui/States";
import { SensorGrid } from "@/components/panels/SensorGrid";
import { formatAgo, formatNumber, healthLabel, shortId } from "@/lib/format";
import { SERIES, healthStyle } from "@/lib/health";

const SENSOR_OPTIONS = new Array(21).fill(0).map((_, i) => `s${i + 1}`);
const DEFAULT_SENSOR = "s2";

const SELECT_CLASS =
  "rounded-md border border-edge bg-panel-2 px-2 py-1 text-xs text-ink outline-hidden transition-colors hover:border-edge-bright focus:border-accent/50";

/** Live per-machine monitoring with configurable polling. */
export function LiveMonitoringPage() {
  const [params, setParams] = useSearchParams();
  const machineId = params.get("machine") ?? "";

  const [pollOverride, setPollOverride] = useState<number | null>(null);
  const [sensor, setSensor] = useState(DEFAULT_SENSOR);

  const effectivePoll = pollOverride ?? getPollIntervalMs() ?? DEFAULT_POLL_INTERVAL_MS;

  const machines = useResource(() => fetchMachines(), undefined, { pollMs: 0 });
  const list = machines.data ?? [];
  const selected = machineId === "" ? (list[0]?.machine_id ?? "") : machineId;

  const paramsForMachine = useMemo(
    () => (selected === "" ? undefined : { machineId: selected }),
    [selected],
  );

  const health = useResource(
    () => fetchMachineHealth(selected),
    paramsForMachine,
    { pollMs: effectivePoll, enabled: selected !== "" },
  );
  const readings = useResource(
    () => fetchMachineReadings(selected, 100),
    paramsForMachine,
    { pollMs: effectivePoll, enabled: selected !== "" },
  );

  const latest = readings.data?.readings.at(-1) ?? null;
  const latestPrediction = health.data?.latest_prediction ?? null;
  const style = healthStyle(health.data?.health ?? "unknown");

  const sensorTrend = useMemo(() => {
    return (readings.data?.readings ?? []).map((reading) => ({
      x: reading.cycle,
      y: reading.sensor_values[sensor],
    }));
  }, [readings.data, sensor]);

  if (!machines.error && machines.data !== null && list.length === 0) {
    return (
      <>
        <PageHeader title="Live Monitoring" description="Real-time sensor stream, model verdicts and machine status." />
        <Panel title="Monitoring">
          <EmptyState
            title="No machines have ingested readings yet"
            hint="Run the simulator from Settings ▸ Simulator, or ingest readings directly via POST /readings."
          />
        </Panel>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Live Monitoring"
        description="Real-time sensor stream, model verdicts and machine status. Polling pauses while this tab is hidden."
        actions={
          <label className="flex items-center gap-2 text-xs text-ink-dim">
            <Waves aria-hidden className="h-3.5 w-3.5" />
            Refresh
            <select
              aria-label="Polling interval"
              value={String(pollOverride ?? GLOBAL)}
              onChange={(e) => setPollOverride(e.target.value === GLOBAL ? null : Number(e.target.value))}
              className={SELECT_CLASS}
            >
              <option value={GLOBAL}>Global ({getPollIntervalMs() === 0 ? "off" : `${getPollIntervalMs() / 1000}s`})</option>
              {POLL_INTERVAL_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
        }
      />

      {/* Machine selector strip */}
      <div className="mb-5 flex flex-wrap items-center gap-3 rounded-lg border border-edge bg-panel/60 px-3.5 py-2.5">
        <label className="flex items-center gap-2 text-xs text-ink-dim">
          Machine
          {list.length > 0 ? (
            <select
              aria-label="Select machine"
              value={selected}
              onChange={(e) => {
                const next = e.target.value;
                updateSearchParams(setParams, next);
              }}
              className="min-w-44 rounded-md border border-edge bg-panel-2 px-2 py-1.5 text-sm text-ink outline-hidden transition-colors hover:border-edge-bright focus:border-accent/50"
            >
              {list.map((machine) => (
                <option key={machine.machine_id} value={machine.machine_id}>
                  {shortId(machine.machine_id)} · {machine.dataset_id}
                </option>
              ))}
            </select>
          ) : machines.loading ? (
            <Skeleton className="h-8 w-48" />
          ) : null}
        </label>

        {machines.error ? <ErrorState compact message={machines.error.message} onRetry={machines.refetch} /> : null}

        {health.data !== null && (
          <span className={`inline-flex items-center gap-2 rounded-md border px-2 py-1 text-xs ${style.chip}`}>
            <span className={`h-2 w-2 rounded-full ${style.dot} ${health.data.active_alerts > 0 ? "animate-pulse-soft" : ""}`} aria-hidden="true" />
            {healthLabel(health.data.health)}
            {health.data.active_alerts > 0 && (
              <span className="tnum">· {health.data.active_alerts} active</span>
            )}
          </span>
        )}

        <span className="text-xs text-ink-faint">
          {health.data?.last_reading_at !== null && health.data?.last_reading_at !== undefined
            ? `last reading ${formatAgo(health.data.last_reading_at)}`
            : null}
        </span>
      </div>

      {selected === "" ? null : (
        <div className="grid gap-4 xl:grid-cols-3">
          {/* Left column: scores + status */}
          <div className="space-y-4">
            <Panel title="Model verdict" subtitle={latestPrediction ? `${latestPrediction.model} · ${latestPrediction.model_version}` : "No prediction yet"}>
              {latestPrediction ? (
                <div className="space-y-4">
                  <MetricBar
                    label="Failure probability"
                    value={latestPrediction.failure_probability}
                    color={SERIES.critical}
                    caption="P(failure within 30 cycles); thresholds 0.5 / 0.8"
                  />
                  <MetricBar
                    label="Anomaly score"
                    value={latestPrediction.anomaly_score}
                    thresholds={[]}
                    color={SERIES.info}
                    display={latestPrediction.anomaly_score === null || latestPrediction.anomaly_score === undefined ? "—" : formatNumber(latestPrediction.anomaly_score)}
                    caption={latestPrediction.anomaly_status === true ? "Detector flags this reading anomalous" : "Detected inlier"}
                  />
                  <p className="text-xs text-ink-faint">
                    Predicted {formatAgo(latestPrediction.predicted_at)} · <span className="tnum">reading #{latestPrediction.reading_id}</span>
                  </p>
                </div>
              ) : health.error || readings.error ? (
                // Fail fast: a failed machine lookup means no prediction can
                // ever arrive for this id, so skeletons would only stall UI.
                <EmptyState compact title="No prediction stored for this machine yet" />
              ) : health.loading ? (
                <LoadingState rows={2} />
              ) : (
                <EmptyState compact title="No prediction stored for this machine yet" />
              )}
            </Panel>

            <Panel
              title="Current health"
              subtitle={`Cycle ${health.data?.last_cycle ?? "—"}`}
              actions={
                <button
                  type="button"
                  onClick={() => {
                    health.refetch();
                    readings.refetch();
                  }}
                  aria-label="Refresh data now"
                  className="flex items-center gap-1.5 rounded-md border border-edge bg-panel-2 px-2.5 py-1 text-xs text-ink-dim transition-colors hover:border-accent/40 hover:text-accent"
                >
                  <RefreshCw aria-hidden className="h-3.5 w-3.5" />
                  Refresh
                </button>
              }
            >
              {readings.data === null ? (
                <LoadingState rows={2} />
              ) : latest ? (
                <div className="space-y-2 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-ink-dim">Latest stored reading</span>
                    <span className="tnum font-medium text-ink">cycle {latest.cycle}</span>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-ink-dim">Data source</span>
                    <SimBadge isSimulated={latest.is_simulated} />
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-ink-dim">Stored at</span>
                    <span className="tnum text-ink">{formatAgo(latest.stored_at)}</span>
                  </div>
                  {latestPrediction !== null && (
                    <p className={`text-xs ${latestPrediction.failure_status === true ? "text-warning" : "text-ink-faint"}`}>
                      {latestPrediction.failure_status === true
                        ? "Failure risk rule triggered (probability ≥ 0.5)"
                        : "No failure rule triggered"}
                    </p>
                  )}
                </div>
              ) : (
                <EmptyState compact title="No readings yet" />
              )}
            </Panel>
          </div>

          {/* Right column: sensor chart + grid */}
          <div className="space-y-4 xl:col-span-2">
            <Panel
              title={`Sensor trend · ${sensor}`}
              subtitle="Most recent 100 stored cycles (oldest → newest)"
              actions={
                <select
                  aria-label="Sensor channel"
                  value={sensor}
                  onChange={(e) => setSensor(e.target.value)}
                  className={SELECT_CLASS}
                >
                  {SENSOR_OPTIONS.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              }
            >
              {readings.error ? (
                <ErrorState message={readings.error.message} onRetry={readings.refetch} />
              ) : readings.data === null ? (
                <Skeleton className="h-52 w-full" />
              ) : (
                <TrendChart
                  data={sensorTrend}
                  color={SERIES.accent}
                  ariaLabel={`${sensor} trend over stored cycles`}
                  yFormatter={(v) => formatNumber(v, 2)}
                  domain={["auto", "auto"]}
                />
              )}
            </Panel>

            <Panel
              title="Latest sensor readings"
              subtitle={
                latest
                  ? `Cycle ${latest.cycle} · settings ${formatNumber(latest.setting_1, 2)} / ${formatNumber(latest.setting_2, 2)} / ${formatNumber(latest.setting_3, 2)}`
                  : undefined
              }
            >
              {readings.data === null ? (
                <LoadingState rows={2} />
              ) : latest ? (
                <SensorGrid values={latest.sensor_values} />
              ) : (
                <EmptyState compact title="No readings stored" />
              )}
            </Panel>
          </div>
        </div>
      )}
    </>
  );
}

const GLOBAL = "__global__";

function updateSearchParams(
  setParams: (next: (prev: URLSearchParams) => URLSearchParams) => void,
  machine: string,
): void {
  setParams((prev) => {
    const next = new URLSearchParams(prev);
    next.set("machine", machine);
    return next;
  });
}
