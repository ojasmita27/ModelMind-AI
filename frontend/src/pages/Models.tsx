import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Badge, Card, ErrorBanner, PageHeader, Spinner } from "../components/ui/primitives";
import { useToast } from "../components/ui/Toast";
import { ApiError } from "../api/client";
import {
  compareVersions, getModel, listModels, registerModel, rollbackVersion, transitionVersion,
  validateVersion, versionHistory,
  type ModelDetail, type ModelVersionInfo, type RegisteredModelSummary,
} from "../api/registry";
import { listExperiments } from "../api/experiments";

const STATUS_TONE: Record<string, "live" | "soon" | "info" | "warn"> = {
  production: "live", validated: "info", staging: "info", registered: "soon",
  archived: "soon", failed: "warn",
};

export default function Models() {
  const { projectId } = useParams<{ projectId: string }>();
  const { notify } = useToast();
  const [models, setModels] = useState<RegisteredModelSummary[]>([]);
  const [detail, setDetail] = useState<ModelDetail | null>(null);
  const [experiments, setExperiments] = useState<{ id: string; name: string }[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [regExpId, setRegExpId] = useState("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [compare, setCompare] = useState<{ task_type: string; versions: { version_id: string; model_name: string; version_number: number; algorithm: string; lifecycle_status: string; metrics: Record<string, number | null> }[] } | null>(null);
  const [historyFor, setHistoryFor] = useState<ModelVersionInfo | null>(null);
  const [history, setHistory] = useState<{ transitions: { from: string; to: string; note: string | null; created_at: string }[] } | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    if (!projectId) return;
    setStatus("loading");
    try {
      const [ms, exps] = await Promise.all([
        listModels(projectId, signal),
        listExperiments(projectId, signal).catch(() => []),
      ]);
      if (signal?.aborted) return;
      setModels(ms);
      setExperiments(exps.filter((e: any) => e.status === "completed" && e.artifact_uri).map((e: any) => ({ id: e.id, name: e.name })));
      setStatus("ready");
    } catch (e) {
      if (signal?.aborted) return;
      setError(e instanceof ApiError ? e.message : "Could not load the model registry.");
      setStatus("error");
    }
  }, [projectId]);

  useEffect(() => { const c = new AbortController(); void load(c.signal); return () => c.abort(); }, [load]);

  const open = async (id: string) => {
    if (!projectId) return;
    try { setDetail(await getModel(projectId, id)); } catch (e) { notify("error", e instanceof ApiError ? e.message : "Load failed."); }
  };

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    if (!projectId || !detail) return;
    setBusy(true);
    try { await fn(); notify("success", ok); await open(detail.id); void load(); }
    catch (e) { notify("error", e instanceof ApiError ? e.message : "Action failed."); }
    finally { setBusy(false); }
  };

  const toggleSelect = (vid: string) => setSelected((s) => { const n = new Set(s); n.has(vid) ? n.delete(vid) : n.add(vid); return n; });

  const runCompare = async () => {
    if (!projectId || selected.size < 2) { notify("error", "Select 2-6 versions to compare."); return; }
    try { setCompare(await compareVersions(projectId, [...selected])); }
    catch (e) { notify("error", e instanceof ApiError ? e.message : "Comparison failed."); }
  };

  const showHistory = async (v: ModelVersionInfo) => {
    if (!projectId || !detail) return;
    setHistoryFor(v);
    try { setHistory(await versionHistory(projectId, detail.id, v.id)); }
    catch { setHistory(null); }
  };

  const doRegister = async () => {
    if (!projectId || !regExpId) { notify("error", "Select a completed experiment first."); return; }
    setBusy(true);
    try {
      const v = await registerModel(projectId, regExpId);
      notify("success", `Registered ${v.algorithm} as version ${v.version_number}.`);
      setRegExpId(""); void load();
    } catch (e) { notify("error", e instanceof ApiError ? e.message : "Registration failed."); }
    finally { setBusy(false); }
  };

  if (!projectId) return null;
  if (status === "loading") return <div className="py-16 text-center"><Spinner label="Loading registry…" /></div>;
  if (status === "error") return <ErrorBanner message={error ?? "Registry unavailable."} onRetry={() => void load()} />;

  return (
    <>
      <PageHeader title="Model Registry" subtitle="Trained model versions, lifecycle states and validation — promotion here is not deployment." />

      <Card className="mb-6 p-4">
        <h2 className="text-sm font-semibold text-ivory-100">Register from experiment</h2>
        <div className="mt-2 flex gap-2">
          <select value={regExpId} onChange={(e) => setRegExpId(e.target.value)}
            className="flex-1 rounded border border-surface-700 bg-surface-900 px-2 py-2 text-sm text-ivory-100">
            <option value="">Select completed experiment…</option>
            {experiments.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
          </select>
          <button onClick={() => void doRegister()} disabled={busy || !regExpId}
            className="rounded bg-chartreuse-500 px-4 py-2 text-sm font-medium text-surface-950 disabled:opacity-50">
            {busy ? "Working…" : "Register"}
          </button>
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-3">
          {models.length === 0 && <Card className="p-6 text-sm text-surface-400">No registered models yet.</Card>}
          {models.map((m) => (
            <Card key={m.id} className={`p-4 ${detail?.id === m.id ? "border-chartreuse-500/60" : "hover:border-surface-500"}`}>
              <div className="cursor-pointer" onClick={() => void open(m.id)}>
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-ivory-100">{m.name}</span>
                <Badge tone={m.latest_version ? (STATUS_TONE[m.latest_version.lifecycle_status] ?? "soon") : "soon"}>
                  {m.latest_version?.lifecycle_status ?? "—"}
                </Badge>
              </div>
              <div className="mt-1 text-xs text-surface-400">
                {m.task_type} · {m.version_count} version{m.version_count === 1 ? "" : "s"}
                {m.latest_version && ` · latest v${m.latest_version.version_number} (${m.latest_version.algorithm})`}
              </div>
              </div>
            </Card>
          ))}
        </div>

        <div>
          {!detail ? (
            <Card className="p-6 text-sm text-surface-400">Select a model to inspect versions and lifecycle.</Card>
          ) : (
            <Card className="p-5">
              <h2 className="text-base font-semibold text-ivory-100">{detail.name}</h2>
              <p className="mt-1 text-xs text-surface-400">{detail.task_type} · {detail.versions.length} versions</p>
              <div className="mt-4 space-y-3">
                {detail.versions.map((v) => (
                  <div key={v.id} className="rounded border border-surface-700 bg-surface-900 p-3">
                    <div className="flex items-center justify-between">
                      <label className="flex items-center gap-2 text-sm text-ivory-100">
                        <input type="checkbox" className="accent-chartreuse-500" checked={selected.has(v.id)} onChange={() => toggleSelect(v.id)} />
                        v{v.version_number} — {v.algorithm}
                      </label>
                      <Badge tone={STATUS_TONE[v.lifecycle_status] ?? "soon"}>{v.lifecycle_status}</Badge>
                    </div>
                    <div className="mt-1 text-[11px] text-surface-400">
                      {(v.metrics?.validation_metrics as Record<string, number> | undefined)
                        ? Object.entries(v.metrics.validation_metrics as Record<string, number>).slice(0, 4).map(([k, val]) => `${k}: ${typeof val === "number" ? val.toFixed(3) : val}`).join(" · ")
                        : "no metrics"}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1">
                      {v.lifecycle_status === "registered" && (
                        <button disabled={busy} onClick={() => void act(() => validateVersion(projectId, detail.id, v.id), "Validation complete.")}
                          className="rounded border border-ivory-400/40 px-2 py-1 text-[11px] text-ivory-200">Validate</button>
                      )}
                      {(v.lifecycle_status === "validated" || v.lifecycle_status === "staging") && (
                        <button disabled={busy} onClick={() => void act(() => transitionVersion(projectId, detail.id, v.id, "staging"), "Moved to staging.")}
                          className="rounded border border-ivory-400/40 px-2 py-1 text-[11px] text-ivory-200">→ Staging</button>
                      )}
                      {v.lifecycle_status === "staging" && (v.validation?.ok) && (
                        <button disabled={busy} onClick={() => void act(() => transitionVersion(projectId, detail.id, v.id, "production"), "Promoted to production.")}
                          className="rounded border border-chartreuse-500/50 px-2 py-1 text-[11px] text-chartreuse-300">→ Production</button>
                      )}
                      {v.lifecycle_status === "production" && (
                        <button disabled={busy} onClick={() => void act(() => rollbackVersion(projectId, detail.id, v.id), "Rolled back.")}
                          className="rounded border border-amber-400/40 px-2 py-1 text-[11px] text-amber-200">Rollback</button>
                      )}
                      {!["archived", "failed"].includes(v.lifecycle_status) && (
                        <button disabled={busy} onClick={() => void act(() => transitionVersion(projectId, detail.id, v.id, "archived"), "Archived.")}
                          className="rounded border border-surface-600 px-2 py-1 text-[11px] text-surface-300">Archive</button>
                      )}
                    </div>
                    {v.validation && !v.validation.ok && (
                      <div className="mt-1 text-[11px] text-red-300">validation failed: {v.validation.reasons?.join("; ")}</div>
                    )}
                    <button onClick={() => void showHistory(v)} className="mt-1 text-[11px] text-ivory-300 hover:text-ivory-100">History</button>
                    {historyFor?.id === v.id && history && (
                      <div className="mt-2 border-t border-surface-700 pt-2 text-[11px] text-surface-300">
                        {history.transitions.map((t, i) => (
                          <div key={i}>{t.from || "—"} → {t.to} · {new Date(t.created_at).toLocaleString()}{t.note ? ` · ${t.note}` : ""}</div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
              {selected.size >= 2 && (
                <button onClick={() => void runCompare()} className="mt-3 rounded bg-ivory-100 px-3 py-1.5 text-xs font-medium text-surface-950">
                  Compare {selected.size} versions
                </button>
              )}
              {compare && (
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead><tr className="text-left text-surface-400">
                      <th className="py-1 pr-2">Version</th><th className="py-1 pr-2">Algorithm</th><th className="py-1 pr-2">Status</th>
                      {Object.keys(compare.versions[0]?.metrics ?? {}).map((k) => <th key={k} className="py-1 pr-2">{k}</th>)}
                    </tr></thead>
                    <tbody>
                      {compare.versions.map((cv) => (
                        <tr key={cv.version_id} className="border-t border-surface-800">
                          <td className="py-1 pr-2 text-ivory-200">{cv.model_name} v{cv.version_number}</td>
                          <td className="py-1 pr-2">{cv.algorithm}</td>
                          <td className="py-1 pr-2">{cv.lifecycle_status}</td>
                          {Object.values(cv.metrics).map((val, i) => (
                            <td key={i} className="py-1 pr-2">{val == null ? "—" : Number(val).toFixed(4)}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
