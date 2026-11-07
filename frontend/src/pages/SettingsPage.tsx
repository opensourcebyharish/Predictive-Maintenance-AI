import { useCallback, useState } from "react";
import { Plug, Save, Terminal, Timer } from "lucide-react";

import { fetchHealth, fetchReadiness } from "@/api/endpoints";
import { useResource } from "@/api/hooks";
import { classifyBackendStatus } from "@/lib/backendStatus";
import { useApiBaseUrl, usePollInterval } from "@/api/useSettings";
import { DEFAULT_API_BASE_URL, POLL_INTERVAL_OPTIONS } from "@/api/settings";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { Badge } from "@/components/ui/Badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";

const INPUT_CLASS =
  "w-full rounded-md border border-edge bg-panel-2 px-2.5 py-1.5 text-sm text-ink outline-hidden transition-colors placeholder:text-ink-faint hover:border-edge-bright focus:border-accent/50";

/** Connection, polling, alert thresholds, simulator instructions. */
export function SettingsPage() {
  const [baseUrl, setBaseUrl] = useApiBaseUrl();
  const [pollMs, setPollMs] = usePollInterval();
  const [draftUrl, setDraftUrl] = useState(baseUrl);

  const connectivity = useResource(() => fetchHealth(), undefined, { pollMs: 15000 });
  const readiness = useResource(() => fetchReadiness(), undefined, { pollMs: 15000 });
  const status = classifyBackendStatus({ health: connectivity, readiness, online: null });
  const statusError = connectivity.error ?? readiness.error;

  const applyUrl = useCallback(() => {
    setBaseUrl(draftUrl);
    connectivity.refetch();
    readiness.refetch();
  }, [draftUrl, connectivity, readiness, setBaseUrl]);

  return (
    <>
      <PageHeader
        title="Settings"
        description="Backend connection, polling cadence and operating documentation for this dashboard."
      />

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Backend connection" subtitle="Base URL of the FastAPI ingestion + monitoring API">
          <div className="space-y-3">
            <label className="block text-xs text-ink-dim">
              API base URL
              <div className="mt-1 flex gap-2">
                <input
                  type="url"
                  value={draftUrl}
                  onChange={(e) => setDraftUrl(e.target.value)}
                  placeholder={DEFAULT_API_BASE_URL}
                  aria-label="API base URL"
                  className={INPUT_CLASS}
                />
                <button
                  type="button"
                  onClick={applyUrl}
                  className="flex shrink-0 items-center gap-1.5 rounded-md border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/20"
                >
                  <Save aria-hidden className="h-3.5 w-3.5" />
                  Apply
                </button>
              </div>
            </label>

            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="text-ink-faint">Status</span>
              {status === "connecting" ? (
                <LoadingState rows={1} />
              ) : status === "network-failure" || status === "http-failure" ? (
                <>
                  <Badge tone="critical">{status === "network-failure" ? "network failure" : "http failure"}</Badge>
                  <ErrorState compact message={statusError?.message ?? "Cannot reach backend"} />
                </>
              ) : (
                <>
                  <Badge tone={status === "healthy" ? "healthy" : "warning"}>connected</Badge>
                  <span className="text-ink-dim">
                    {connectivity.data?.app ?? "api"} v{connectivity.data?.version ?? "—"}
                    {status === "healthy"
                      ? " · models loaded · services ready"
                      : " · services not ready"}
                  </span>
                </>
              )}
            </div>
            <p className="text-[11px] text-ink-faint">
              Default: <code className="rounded bg-white/6 px-1 font-mono">{DEFAULT_API_BASE_URL}</code>. Set
              {" "}<code className="rounded bg-white/6 px-1 font-mono">VITE_API_BASE_URL</code> at build time or change here (persisted in
              this browser). CORS on the backend defaults to <code className="rounded bg-white/6 px-1 font-mono">*</code>.
            </p>
          </div>
        </Panel>

        <Panel title="Polling configuration" subtitle="Applies to Overview, Live Monitoring and Alerts pages">
          <div className="space-y-3">
            <label className="flex items-center gap-3 text-xs text-ink-dim">
              <Timer aria-hidden className="h-4 w-4 shrink-0 text-ink-faint" />
              Refresh interval
              <select
                aria-label="Global polling interval"
                value={pollMs}
                onChange={(e) => setPollMs(Number(e.target.value))}
                className="rounded-md border border-edge bg-panel-2 px-2 py-1 text-xs text-ink outline-hidden transition-colors hover:border-edge-bright focus:border-accent/50"
              >
                {POLL_INTERVAL_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>
            <ul className="space-y-1 text-[11px] text-ink-faint">
              <li>· Polling pauses automatically while this browser tab is hidden.</li>
              <li>· Live Monitoring page intensity can override the global value instance-by-instance.</li>
              <li>· Offline backends surface a retry button instead of leaving stale data silent.</li>
            </ul>
          </div>
        </Panel>

        <Panel title="Alert thresholds" subtitle="Configured on the backend (Phase 3.6 alert engine)">
          <dl className="space-y-2 text-xs">
            <ThresholdRow label="Elevated failure risk" value="failure_probability ≥ 0.5" hint="env: API_ALERT_ELEVATED_FAILURE" />
            <ThresholdRow label="Critical failure risk" value="failure_probability ≥ 0.8" hint="env: API_ALERT_CRITICAL_FAILURE" />
            <ThresholdRow label="Anomaly detection" value="enabled" hint="env: API_ALERT_ANOMALY_ENABLED" />
            <ThresholdRow label="Deduplication" value="1 active alert per (machine, type)" hint="recoveries auto-close alerts" />
          </dl>
        </Panel>

        <Panel title="Simulator (Phase 4)" subtitle="Generate labelled simulated readings to exercise the dashboard">
          <EmptyState
            compact
            title=""
            hint={
              <div className="space-y-3 text-left">
                <p className="text-xs text-ink-dim">
                  Start the backend, then run the CLI from the project root:
                </p>
                <div className="space-y-1 rounded-md border border-edge bg-base/80 p-3 font-mono text-[11px] leading-5 text-ink">
                  <p><Terminal aria-hidden className="mr-1 inline h-3 w-3 text-accent" />.venv\Scripts\python.exe -m uvicorn predictive_maintenance.api.main:app --app-dir src</p>
                  <p>python scripts\run_simulator.py start --machines 4 --scenario developing_degradation</p>
                  <p>python scripts\run_simulator.py scenario abnormal_vibration</p>
                  <p>python scripts\run_simulator.py status</p>
                  <p>python scripts\run_simulator.py stop</p>
                </div>
                <p className="text-[11px] text-ink-faint">
                  All simulator readings carry <Badge tone="info">is_simulated=true</Badge> and are marked{" "}
                  <Plug aria-hidden className="mr-0.5 inline h-3 w-3 text-accent" />
                  <strong className="text-ink-dim">Sim</strong> wherever they appear in this dashboard.
                </p>
              </div>
            }
          />
        </Panel>
      </div>
    </>
  );
}

function ThresholdRow({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-edge/40 pb-2">
      <dt>
        <span className="block font-medium text-ink">{label}</span>
        <span className="text-[10px] text-ink-faint">{hint}</span>
      </dt>
      <dd className="tnum text-right text-ink-dim">{value}</dd>
    </div>
  );
}
