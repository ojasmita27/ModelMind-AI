import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Badge, Card, ErrorBanner, PageHeader, Spinner } from "../components/ui/primitives";
import { useToast } from "../components/ui/Toast";
import { ApiError } from "../api/client";
import { listDeployments, type Deployment } from "../api/deployments";
import {
  getMonitoringConfig, ingestLabels, listMonitoringRuns, runMonitoring,
  type MonitoringConfig, type MonitoringRun,
} from "../api/monitoring";

const HEALTH_TONE: Record<string, "live" | "soon" | "info" | "warn"> = {
  healthy: "live", warning: "info", critical: "warn",
  insufficient_data: "soon", unknown: "soon",
};

export default function Monitoring() {
  const { projectId } = useParams<{ projectId: string }>();
  const { notify } = useToast();
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [depId, setDepId] = useState<string>("");
  const [config, setConfig] = useState<MonitoringConfig | null>(null);
  const [runs, setRuns] = useState<MonitoringRun[]>([]);
  const [latest, setLatest] = useState<MonitoringRun | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [labelText, setLabelText] = useState(""); // request_id,label per line

  const loadDeps = useCallback(async (signal?: AbortSignal) => {
    if (!projectId) return;
    try {
      const ds = await listDeployments(projectId, signal);
      setDeployments(ds.filter((d) => d.status === "active"));
      if (ds.length && !depId) setDepId(ds[0].id);
    } catch (e) {
      if (signal?.aborted) return;
      setError(e instanceof ApiError ? e.message : "Could not load deployments.");
      setStatus("error");
    }
  }, [projectId, depId]);

  const loadRuns = useCallback(async (signal?: AbortSignal) => {
    if (!projectId || !depId) return;
    try {
      const [cfg, rr] = await Promise.all([
        getMonitoringConfig(projectId, depId, ).catch(() => null),
        listMonitoringRuns(projectId, depId).catch(() => ({ runs: [] as MonitoringRun[] })),
      ]);
      if (signal?.aborted) return;
      setConfig(cfg);
      setRuns(rr.runs);
      setLatest(rr.runs[0] ?? null);
      setStatus("ready");
    } catch (e) {
      if (signal?.aborted) return;
      setError(e instanceof ApiError ? e.message : "Monitoring unavailable.");
      setStatus("error");
    }
  }, [projectId, depId]);

  useEffect(() => { const c = new AbortController(); void loadDeps(c.signal); return () => c.abort(); }, [loadDeps]);
  useEffect(() => { const c = new AbortController(); void loadRuns(c.signal); return () => c.abort(); }, [loadRuns]);

  const doRun = async () => {
    if (!projectId || !depId) return;
    setBusy(true);
    try {
      const r = await runMonitoring(projectId, depId);
      setLatest(r);
      const rr = await listMonitoringRuns(projectId, depId);
      setRuns(rr.runs);
      notify("success", `Monitoring ${r.status} — health: ${r.health_status}`);
    } catch (e) { notify("error", e instanceof ApiError ? e.message : "Monitoring run failed."); }
    finally { setBusy(false); }
  };

  const doLabels = async () => {
    if (!projectId || !depId || !labelText.trim()) return;
    const labels = labelText.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
      const [request_id, ...rest] = l.split(",");
      return { request_id: request_id.trim(), label: rest.join(",").trim() };
    }).filter((l) => l.request_id);
    if (!labels.length) { notify("error", "No valid label lines."); return; }
    setBusy(true);
    try {
      const r = await ingestLabels(projectId, depId, labels);
      notify("success", `Ingested ${r.added} label(s), skipped ${r.skipped_duplicates} duplicate(s).`);
      setLabelText("");
    } catch (e) { notify("error", e instanceof ApiError ? e.message : "Label ingestion failed."); }
    finally { setBusy(false); }
  };

  if (!projectId) return null;
  if (status === "loading" && !latest) return <div className="py-16 text-center"><Spinner label="Loading monitoring…" /></div>;
  if (status === "error") return <ErrorBanner message={error ?? "Monitoring unavailable."} onRetry={() => void loadRuns()} />;

  const feats = latest?.summary?.features ?? [];
  const perf = latest?.summary?.performance;
  const reasons = latest?.summary?.health_reasons ?? [];

  return (
    <>
      <PageHeader title="Model Monitoring" subtitle="Drift detection and health for active deployments — PSI, KS/chi-square tests, ground-truth performance when labels exist." />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select value={depId} onChange={(e) => setDepId(e.target.value)}
          className="rounded border border-surface-700 bg-surface-900 px-2 py-2 text-sm text-ivory-100">
          {deployments.length === 0 && <option value="">No active deployments</option>}
          {deployments.map((d) => <option key={d.id} value={d.id}>{d.model_name} v{d.version_number}</option>)}
        </select>
        <button onClick={() => void doRun()} disabled={busy || !depId}
          className="rounded bg-chartreuse-500 px-4 py-2 text-sm font-medium text-surface-950 disabled:opacity-50">
          {busy ? "Running…" : "Run monitoring"}
        </button>
        {latest && <Badge tone={HEALTH_TONE[latest.health_status] ?? "soon"}>health: {latest.health_status}</Badge>}
      </div>

      {deployments.length === 0 && (
        <Card className="p-6 text-sm text-surface-400">No active deployments to monitor. Deploy a production model version first.</Card>
      )}

      {depId && (
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-2">
            {latest ? (
              <>
                <Card className="p-4">
                  <h2 className="text-sm font-semibold text-ivory-100">Latest run</h2>
                  <p className="mt-1 text-xs text-surface-400">
                    {latest.sample_count} prediction samples vs {latest.reference_sample_count} reference rows · {new Date(latest.created_at).toLocaleString()}
                  </p>
                  {reasons.length > 0 && (
                    <ul className="mt-2 list-disc pl-4 text-xs text-surface-300">
                      {reasons.map((r, i) => <li key={i}>{r}</li>)}
                    </ul>
                  )}
                  {latest.summary?.methodology && <p className="mt-2 text-[11px] text-surface-500">{latest.summary.methodology}</p>}
                </Card>

                <Card className="p-4">
                  <h2 className="text-sm font-semibold text-ivory-100">Feature drift</h2>
                  {feats.length === 0 ? (
                    <p className="mt-2 text-xs text-surface-400">No feature results.</p>
                  ) : (
                    <div className="mt-2 overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead><tr className="text-left text-surface-400">
                          <th className="py-1 pr-2">Feature</th><th className="py-1 pr-2">Type</th><th className="py-1 pr-2">PSI</th>
                          <th className="py-1 pr-2">KS p / χ² p</th><th className="py-1">Missing Δ</th>
                        </tr></thead>
                        <tbody>
                          {feats.map((f) => (
                            <tr key={f.feature} className="border-t border-surface-800">
                              <td className="py-1 pr-2 text-ivory-200">{f.feature}</td>
                              <td className="py-1 pr-2">{f.type}</td>
                              <td className="py-1 pr-2">{f.psi == null ? "—" : f.psi.toFixed(3)}</td>
                              <td className="py-1 pr-2">{f.ks_pvalue != null ? f.ks_pvalue.toFixed(4) : f.chi2_pvalue != null ? f.chi2_pvalue.toFixed(4) : "—"}</td>
                              <td className="py-1">{f.missing_rate_delta ?? "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </Card>

                <Card className="p-4">
                  <h2 className="text-sm font-semibold text-ivory-100">Run history</h2>
                  {runs.length === 0 ? <p className="mt-2 text-xs text-surface-400">No runs yet.</p> : (
                    <table className="mt-2 w-full text-xs">
                      <thead><tr className="text-left text-surface-400">
                        <th className="py-1 pr-2">Time</th><th className="py-1 pr-2">Samples</th><th className="py-1 pr-2">Status</th><th className="py-1">Health</th>
                      </tr></thead>
                      <tbody>
                        {runs.map((r) => (
                          <tr key={r.id} className="border-t border-surface-800">
                            <td className="py-1 pr-2 text-surface-300">{new Date(r.created_at).toLocaleString()}</td>
                            <td className="py-1 pr-2">{r.sample_count}</td>
                            <td className="py-1 pr-2">{r.status}</td>
                            <td className="py-1"><Badge tone={HEALTH_TONE[r.health_status] ?? "soon"}>{r.health_status}</Badge></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </Card>
              </>
            ) : (
              <Card className="p-6 text-sm text-surface-400">Run monitoring to compute drift statistics.</Card>
            )}
          </div>

          <div className="space-y-4">
            {perf && (
              <Card className="p-4">
                <h2 className="text-sm font-semibold text-ivory-100">Ground-truth performance</h2>
                {perf.status === "measured" ? (
                  <div className="mt-2 space-y-1 text-xs text-ivory-200">
                    {perf.accuracy != null && <div>accuracy {perf.accuracy} · precision {perf.precision} · recall {perf.recall} · f1 {perf.f1}{perf.roc_auc != null ? ` · auc ${perf.roc_auc}` : ""}</div>}
                    {perf.mae != null && <div>MAE {perf.mae} · RMSE {perf.rmse} · R² {perf.r2}</div>}
                    <div className="text-surface-400">matched {perf.matched} labeled predictions</div>
                  </div>
                ) : (
                  <p className="mt-2 text-xs text-surface-400">{perf.status === "no_labels" ? "No ground-truth labels ingested yet." : perf.status === "insufficient_labels" ? `Only ${perf.matched} labeled predictions (need ≥5).` : perf.reason ?? perf.status}</p>
                )}
              </Card>
            )}

            <Card className="p-4">
              <h2 className="text-sm font-semibold text-ivory-100">Ingest labels</h2>
              <p className="mt-1 text-[11px] text-surface-400">One per line: request_id,label — labels match persisted prediction records.</p>
              <textarea value={labelText} onChange={(e) => setLabelText(e.target.value)} rows={5}
                placeholder={"req_abc123,yes\nreq_def456,no"}
                className="mt-2 w-full rounded border border-surface-700 bg-surface-900 px-2 py-1.5 font-mono text-xs text-ivory-100" />
              <button onClick={() => void doLabels()} disabled={busy || !labelText.trim()}
                className="mt-2 rounded bg-ivory-100 px-3 py-1.5 text-xs font-medium text-surface-950 disabled:opacity-50">
                Ingest labels
              </button>
            </Card>

            {config && (
              <Card className="p-4">
                <h2 className="text-sm font-semibold text-ivory-100">Thresholds</h2>
                <div className="mt-2 space-y-1 text-xs text-surface-300">
                  {Object.entries(config.thresholds).map(([k, v]) => <div key={k}>{k}: {v}</div>)}
                  <div className="text-surface-500">min samples: {config.min_samples} · input logging: {String(config.input_logging)}</div>
                </div>
              </Card>
            )}
          </div>
        </div>
      )}
    </>
  );
}
