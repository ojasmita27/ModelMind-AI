import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { Badge, Card, ErrorBanner, PageHeader, Spinner } from "../components/ui/primitives";
import { useToast } from "../components/ui/Toast";
import { ApiError } from "../api/client";
import {
  getDeployment, listDeployments, predictDeployment, predictionHistory, stopDeployment,
  type Deployment, type PredictionRecord, type PredictionResult,
} from "../api/deployments";
import { getWhatIfSchema, type WhatIfSchema } from "../api/whatif";

const STATUS_TONE: Record<string, "live" | "soon" | "info" | "warn"> = {
  active: "live", pending: "soon", deploying: "info", failed: "warn", stopped: "soon",
};

export default function Deployments() {
  const { projectId } = useParams<{ projectId: string }>();
  const { notify } = useToast();
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [selected, setSelected] = useState<Deployment | null>(null);
  const [schema, setSchema] = useState<WhatIfSchema | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PredictionResult | null>(null);
  const [history, setHistory] = useState<PredictionRecord[]>([]);

  const load = useCallback(async (signal?: AbortSignal) => {
    if (!projectId) return;
    setStatus("loading");
    try {
      setDeployments(await listDeployments(projectId, signal));
      setStatus("ready");
    } catch (e) {
      if (signal?.aborted) return;
      setError(e instanceof ApiError ? e.message : "Could not load deployments.");
      setStatus("error");
    }
  }, [projectId]);

  useEffect(() => { const c = new AbortController(); void load(c.signal); return () => c.abort(); }, [load]);

  const open = async (d: Deployment) => {
    if (!projectId) return;
    setSelected(d); setResult(null); setHistory([]); setSchema(null);
    try {
      const [full, hist] = await Promise.all([
        getDeployment(projectId, d.id).catch(() => d),
        predictionHistory(projectId, d.id, 20).catch(() => ({ records: [] as PredictionRecord[] })),
      ]);
      setSelected(full);
      setHistory(hist.records);
      if (full.experiment_id) {
        const s = await getWhatIfSchema(projectId, full.experiment_id).catch(() => null);
        setSchema(s);
        if (s) {
          const seed: Record<string, string> = {};
          for (const f of s.features) {
            seed[f.name] = f.type === "numeric" && f.min != null && f.max != null
              ? String(Number(((f.min + f.max) / 2).toFixed(4)))
              : (f.categories?.[0] ?? "");
          }
          setValues(seed);
        }
      }
    } catch (e) { notify("error", e instanceof ApiError ? e.message : "Load failed."); }
  };

  const payload = useMemo(() => {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(values)) {
      const spec = schema?.features.find((f) => f.name === k);
      out[k] = spec?.type === "numeric" ? (v === "" ? null : Number(v)) : v;
    }
    return out;
  }, [values, schema]);

  const runPredict = async () => {
    if (!projectId || !selected) return;
    setBusy(true);
    try {
      const r = await predictDeployment(projectId, selected.id, payload);
      setResult(r);
      const h = await predictionHistory(projectId, selected.id, 20).catch(() => null);
      if (h) setHistory(h.records);
    } catch (e) { notify("error", e instanceof ApiError ? e.message : "Prediction failed."); }
    finally { setBusy(false); }
  };

  const doStop = async () => {
    if (!projectId || !selected) return;
    setBusy(true);
    try { await stopDeployment(projectId, selected.id); notify("success", "Deployment stopped."); await load(); setSelected(null); }
    catch (e) { notify("error", e instanceof ApiError ? e.message : "Stop failed."); }
    finally { setBusy(false); }
  };

  if (!projectId) return null;
  if (status === "loading") return <div className="py-16 text-center"><Spinner label="Loading deployments…" /></div>;
  if (status === "error") return <ErrorBanner message={error ?? "Deployments unavailable."} onRetry={() => void load()} />;

  const fmt = (v: unknown) => (v == null ? "—" : typeof v === "number" ? Number(v.toFixed(4)) : String(v));

  return (
    <>
      <PageHeader title="Deployments" subtitle="Production model versions serving CPU inference. Promotion to production is not deployment — deploy explicitly here." />
      {error && <div className="mb-4"><ErrorBanner message={error} /></div>}

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-3 lg:col-span-2">
          {deployments.length === 0 && <Card className="p-6 text-sm text-surface-400">No deployments yet. Promote a validated model version to production, then deploy it from the Models page.</Card>}
          {deployments.map((d) => (
            <Card key={d.id} className={`p-4 ${selected?.id === d.id ? "border-chartreuse-500/60" : ""}`}>
              <div className="cursor-pointer" onClick={() => void open(d)}>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-ivory-100">{d.model_name ?? "model"} v{d.version_number ?? "?"}</span>
                  <Badge tone={STATUS_TONE[d.status] ?? "soon"}>{d.status}</Badge>
                </div>
                <div className="mt-1 text-xs text-surface-400">{d.algorithm} · {d.prediction_count ?? 0} predictions</div>
              </div>
            </Card>
          ))}
        </div>

        <div className="space-y-6 lg:col-span-3">
          {!selected ? (
            <Card className="p-6 text-sm text-surface-400">Select a deployment to run predictions.</Card>
          ) : (
            <>
              <Card className="p-5">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-sm font-semibold text-ivory-100">{selected.model_name} v{selected.version_number}</h2>
                    <p className="text-xs text-surface-400">{selected.algorithm} · status {selected.status}</p>
                  </div>
                  {selected.status === "active" && (
                    <button onClick={() => void doStop()} disabled={busy}
                      className="rounded border border-red-400/40 px-3 py-1.5 text-xs text-red-200">Stop</button>
                  )}
                </div>
                {selected.last_error && <div className="mt-2 text-xs text-red-300">{selected.last_error}</div>}
              </Card>

              {selected.status === "active" && schema && (
                <Card className="p-5">
                  <h2 className="text-sm font-semibold text-ivory-100">Predict</h2>
                  <div className="mt-3 grid grid-cols-2 gap-3">
                    {schema.features.map((f) => (
                      <label key={f.name} className="text-xs text-ivory-200">
                        {f.name}
                        {f.type === "numeric" ? (
                          <input type="number" step="any" value={values[f.name] ?? ""}
                            onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                            className="mt-1 w-full rounded border border-surface-700 bg-surface-900 px-2 py-1.5 text-sm" />
                        ) : (
                          <select value={values[f.name] ?? ""}
                            onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                            className="mt-1 w-full rounded border border-surface-700 bg-surface-900 px-2 py-1.5 text-sm">
                            {(f.categories ?? []).map((c) => <option key={c} value={c}>{c}</option>)}
                          </select>
                        )}
                      </label>
                    ))}
                  </div>
                  <button onClick={() => void runPredict()} disabled={busy}
                    className="mt-4 rounded bg-chartreuse-500 px-4 py-2 text-sm font-medium text-surface-950 disabled:opacity-50">
                    {busy ? "Predicting…" : "Run prediction"}
                  </button>
                </Card>
              )}

              {result && (
                <Card className="p-5">
                  <h2 className="text-sm font-semibold text-ivory-100">Result</h2>
                  <div className="mt-2 text-2xl font-bold text-chartreuse-300">{fmt(result.prediction)}</div>
                  {result.probabilities && (
                    <div className="mt-3 space-y-1">
                      {Object.entries(result.probabilities).map(([cls, p]) => (
                        <div key={cls} className="flex items-center gap-2 text-xs">
                          <span className="w-20 truncate text-ivory-200">{cls}</span>
                          <div className="h-3 flex-1 rounded bg-surface-800">
                            <div className="h-3 rounded bg-chartreuse-500/70" style={{ width: `${p * 100}%` }} />
                          </div>
                          <span className="w-12 text-right text-surface-300">{(p * 100).toFixed(1)}%</span>
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="mt-2 text-[11px] text-surface-400">
                    {result.duration_ms}ms · request {result.request_id}
                  </div>
                </Card>
              )}

              <Card className="p-5">
                <h2 className="text-sm font-semibold text-ivory-100">Prediction history</h2>
                {history.length === 0 ? (
                  <p className="mt-2 text-xs text-surface-400">No predictions recorded.</p>
                ) : (
                  <table className="mt-2 w-full text-xs">
                    <thead><tr className="text-left text-surface-400">
                      <th className="py-1 pr-2">Time</th><th className="py-1 pr-2">Request</th><th className="py-1 pr-2">Prediction</th><th className="py-1">ms</th>
                    </tr></thead>
                    <tbody>
                      {history.map((h) => (
                        <tr key={h.id} className="border-t border-surface-800">
                          <td className="py-1 pr-2 text-surface-300">{new Date(h.created_at).toLocaleString()}</td>
                          <td className="py-1 pr-2 font-mono text-surface-400">{h.request_id}</td>
                          <td className="py-1 pr-2 text-ivory-200">{h.status === "completed" ? fmt(h.output?.prediction) : `failed: ${h.error ?? ""}`}</td>
                          <td className="py-1 text-surface-300">{h.duration_ms ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Card>
            </>
          )}
        </div>
      </div>
    </>
  );
}
