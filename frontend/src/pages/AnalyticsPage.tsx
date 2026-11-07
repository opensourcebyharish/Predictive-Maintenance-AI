import { useMemo, useState } from "react";
import { ScatterChart } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import {
  fetchEvaluationReport,
  fetchMachinePredictions,
  fetchMachines,
  fetchReadiness,
} from "@/api/endpoints";
import { useResource } from "@/api/hooks";
import { TrendChart } from "@/components/charts/TrendChart";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { Badge } from "@/components/ui/Badge";
import { StatTile } from "@/components/ui/StatTile";
import { EmptyState, ErrorState, LoadingState, Skeleton } from "@/components/ui/States";
import { formatPercent, shortId } from "@/lib/format";
import { SERIES } from "@/lib/health";

const DATASETS = ["FD001", "FD002", "FD003", "FD004"] as const;

const SELECT_CLASS =
  "rounded-md border border-edge bg-panel-2 px-2 py-1 text-xs text-ink outline-hidden transition-colors hover:border-edge-bright focus:border-accent/50";

/** AI Analytics: offline benchmark metrics + online prediction history. */
export function AnalyticsPage() {
  const [params, setParams] = useSearchParams();
  const datasetId = (params.get("dataset") as (typeof DATASETS)[number] | null) ?? "FD001";
  const machineId = params.get("machine") ?? "";

  const initialDataset = DATASETS.includes(datasetId as (typeof DATASETS)[number]) ? datasetId : "FD001";
  const [dataset, setDataset] = useState<(typeof DATASETS)[number]>(initialDataset);

  const report = useResource(
    () => fetchEvaluationReport(dataset),
    { dataset },
    { pollMs: 0 },
  );
  const readiness = useResource(() => fetchReadiness(), undefined, { pollMs: 0 });
  const machines = useResource(() => fetchMachines(), undefined, { pollMs: 0 });

  const machineList = machines.data ?? [];
  const selectedMachine = machineId === "" ? (machineList[0]?.machine_id ?? "") : machineId;

  const predictions = useResource(
    () => fetchMachinePredictions(selectedMachine, 200),
    selectedMachine === "" ? undefined : { machineId: selectedMachine, dataset },
    { pollMs: 0, enabled: selectedMachine !== "" },
  );

  const failureHistory = useMemo(
    () =>
      (predictions.data?.predictions ?? [])
        .slice()
        .reverse()
        .map((p) => ({ x: p.id, y: p.failure_probability })),
    [predictions.data],
  );
  const anomalyHistory = useMemo(
    () =>
      (predictions.data?.predictions ?? [])
        .slice()
        .reverse()
        .map((p) => ({ x: p.id, y: p.anomaly_score })),
    [predictions.data],
  );

  // The offline benchmark must always describe the model's default supervised
  // model (readiness reports it), never let a random_forest metric remain on
  // screen once the dataset's default model is xgboost.
  const defaultModel = readiness.data?.datasets[dataset]?.default_model ?? null;
  const selectedModelEntry = defaultModel ? report.data?.models[defaultModel] : undefined;
  const valMetrics = selectedModelEntry?.validation;
  const testMetrics = selectedModelEntry?.test;

  return (
    <>
      <PageHeader
        title="AI Analytics"
        description="Offline benchmark metrics from the Phase 2.5 evaluation reports plus live model prediction history from the monitoring database."
        actions={
          <label className="flex items-center gap-2 text-xs text-ink-dim">
            <ScatterChart aria-hidden className="h-3.5 w-3.5" />
            Dataset
            <select
              aria-label="C-MAPSS dataset"
              value={dataset}
              onChange={(e) => {
                const next = e.target.value as (typeof DATASETS)[number];
                setDataset(next);
                setParams((prev) => {
                  const nextParams = new URLSearchParams(prev);
                  nextParams.set("dataset", next);
                  return nextParams;
                });
              }}
              className={SELECT_CLASS}
            >
              {DATASETS.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
        }
      />

      {report.error ? (
        <ErrorState message={report.error.message} onRetry={report.refetch} />
      ) : (
        <div className="grid gap-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {report.data === null ? (
              [...Array(4)].map((_, i) => <Skeleton key={i} className="h-[104px]" />)
            ) : (
              <>
                <StatTile index={0} label="Validation F1" value={valMetrics ? formatPercent(valMetrics.f1) : "—"} tone="healthy" />
                <StatTile index={1} label="ROC AUC" value={valMetrics ? valMetrics.roc_auc.toFixed(3) : "—"} />
                <StatTile index={2} label="PR AUC" value={valMetrics ? valMetrics.pr_auc.toFixed(3) : "—"} />
                <StatTile index={3} label="Degraded recall" value={valMetrics ? formatPercent(valMetrics.recall) : "—"} tone="info" />
              </>
            )}
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <Panel
              title="Confusion matrix"
              subtitle={valMetrics ? `validation · ${valMetrics.n_rows.toLocaleString()} rows · horizon ${report.data?.label_config.failure_horizon} cycles` : undefined}
            >
              {report.data === null ? (
                <LoadingState rows={2} />
              ) : valMetrics ? (
                <div className="mx-auto max-w-64">
                  <table className="tnum w-full text-center text-sm" aria-label="Confusion matrix">
                    <thead className="text-[11px] text-ink-faint uppercase">
                      <tr>
                        <th scope="col" className="p-1" />
                        <th scope="col" className="p-1 font-medium">Pred healthy</th>
                        <th scope="col" className="p-1 font-medium">Pred degraded</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <th scope="row" className="p-1 text-left text-xs font-medium text-ink-dim">True healthy</th>
                        <td className="p-1">
                          <span className="tnum block rounded-md border border-healthy/20 bg-healthy/6 px-3 py-2 font-semibold text-healthy">
                            {valMetrics.confusion_matrix.tn}
                          </span>
                        </td>
                        <td className="p-1">
                          <span className="tnum block rounded-md border border-warning/20 bg-warning/6 px-3 py-2 font-semibold text-warning">
                            {valMetrics.confusion_matrix.fp}
                          </span>
                        </td>
                      </tr>
                      <tr>
                        <th scope="row" className="p-1 text-left text-xs font-medium text-ink-dim">True degraded</th>
                        <td className="p-1">
                          <span className="tnum block rounded-md border border-critical/20 bg-critical/6 px-3 py-2 font-semibold text-critical">
                            {valMetrics.confusion_matrix.fn}
                          </span>
                        </td>
                        <td className="p-1">
                          <span className="tnum block rounded-md border border-healthy/20 bg-healthy/6 px-3 py-2 font-semibold text-healthy">
                            {valMetrics.confusion_matrix.tp}
                          </span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                  <p className="mt-2 text-center text-[10px] text-ink-faint">
                    correctly issued (TP) and missed (FN) degraded predictions drive operator trust
                  </p>
                </div>
              ) : (
                <EmptyState compact title="No validation metrics in report" />
              )}
            </Panel>

            <Panel title="Benchmark split" subtitle="Phase 2.5 evaluation configuration">
              {report.data === null ? (
                <LoadingState rows={2} />
              ) : (
                <dl className="space-y-1.5 text-xs">
                  <Row label="Default supervised model" value={`${dataset} · ${defaultModel ?? "unknown"}`} />
                  <Row label="Failure horizon" value={`${report.data.label_config.failure_horizon} cycles`} />
                  <Row label="Healthy RUL min" value={`${report.data.label_config.healthy_rul_min} cycles`} />
                  <Row label="RUL cap" value={`${report.data.label_config.rul_cap} cycles`} />
                  <Row label="Train engines" value={report.data.data.train_engines.toLocaleString()} />
                  <Row label="Validation engines" value={report.data.data.validation_engines.toLocaleString()} />
                  <Row label="Test engines" value={report.data.data.official_test_engines.toLocaleString()} />
                  {testMetrics ? <Row label="Test F1" value={formatPercent(testMetrics.f1)} /> : null}
                  {testMetrics ? <Row label="Test ROC AUC" value={testMetrics.roc_auc.toFixed(3)} /> : null}
                </dl>
              )}
            </Panel>

            <Panel title="Model artefacts" subtitle={`Readiness for ${dataset}`}>
              {readiness.data === null ? (
                <LoadingState rows={2} />
              ) : (
                <ul className="space-y-2 text-xs" aria-label="Model artefact readiness">
                  {Object.entries(readiness.data.datasets).map(([id, info]) => (
                    <li
                      key={id}
                      className="flex items-center gap-2 rounded-md border border-edge/70 bg-panel-2/50 px-2.5 py-1.5 transition-colors hover:border-edge-bright"
                    >
                      <span className={`h-2 w-2 shrink-0 rounded-full ${info.ready ? "bg-healthy" : "bg-critical"} ${info.ready ? "" : "animate-pulse-soft"}`} aria-hidden="true" />
                      <span className="font-medium text-ink">{id}</span>
                      <span className="truncate text-ink-faint">{info.default_model ?? "—"}</span>
                      <Badge tone={info.ready ? "healthy" : "critical"} className="ml-auto">
                        {info.ready ? "ready" : "error"}
                      </Badge>
                    </li>
                  ))}
                  <li className="pt-1 text-[10px] text-ink-faint">
                    Models are inference-only (fitted Phase 2 artefacts). The dashboard never retrains.
                  </li>
                </ul>
              )}
            </Panel>
          </div>

          <Panel
            title="Live prediction history"
            subtitle="Trimmed to the 200 most recent stored predictions (oldest → newest)"
            actions={
              <select
                aria-label="Machine for prediction history"
                value={selectedMachine}
                onChange={(e) =>
                  setParams((prev) => {
                    const next = new URLSearchParams(prev);
                    next.set("machine", e.target.value);
                    return next;
                  })
                }
                className={SELECT_CLASS}
              >
                {machineList.map((machine) => (
                  <option key={machine.machine_id} value={machine.machine_id}>
                    {shortId(machine.machine_id)} · {machine.dataset_id}
                  </option>
                ))}
              </select>
            }
          >
            {machineList.length === 0 && !machines.loading ? (
              <EmptyState title="No machines yet" hint="Prediction history becomes available after ingestion." />
            ) : (
              <div className="grid gap-4 lg:grid-cols-2">
                <div>
                  <h3 className="mb-2 text-[11px] font-medium tracking-[0.14em] text-ink-dim uppercase">Failure probability (0–1)</h3>
                  {predictions.data === null ? (
                    <Skeleton className="h-40 w-full" />
                  ) : predictions.data.predictions.length === 0 ? (
                    <EmptyState compact title="No predictions stored for this machine" />
                  ) : (
                    <TrendChart
                      data={failureHistory}
                      color={SERIES.critical}
                      ariaLabel="Failure probability history"
                      domain={[0, 1]}
                      yFormatter={(v) => v.toFixed(2)}
                      height={200}
                    />
                  )}
                </div>
                <div>
                  <h3 className="mb-2 text-[11px] font-medium tracking-[0.14em] text-ink-dim uppercase">Anomaly score</h3>
                  {predictions.data === null ? (
                    <Skeleton className="h-40 w-full" />
                  ) : predictions.data.predictions.length === 0 ? (
                    <EmptyState compact title="No predictions stored for this machine" />
                  ) : (
                    <TrendChart
                      data={anomalyHistory}
                      color={SERIES.info}
                      ariaLabel="Anomaly score history"
                      yFormatter={(v) => v.toFixed(3)}
                      height={200}
                    />
                  )}
                </div>
                {predictions.error ? <ErrorState compact message={predictions.error.message} onRetry={predictions.refetch} /> : null}
              </div>
            )}
          </Panel>

          <p className="text-xs text-ink-faint">
            Benchmark metrics originate from the committed Phase 2.5 evaluation report
            (<code className="rounded bg-white/6 px-1 font-mono">reports/evaluation/eval_{dataset}.json</code>) served read-only via
            {" "}<code className="rounded bg-white/6 px-1 font-mono">GET /evaluation</code>. Dashboard charts never retrain models;
            inference uses frozen Phase 2 artefacts loaded by the API.
          </p>
        </div>
      )}
    </>
  );
}

function Row({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-edge/40 pb-1.5 transition-colors">
      <dt className="text-ink-faint">{label}</dt>
      <dd className="tnum font-medium text-ink">{value}</dd>
    </div>
  );
}
