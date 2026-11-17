import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Badge, Card, ErrorBanner, PageHeader, Spinner } from "../components/ui/primitives";
import { useDataset } from "../features/datasets/useDatasets";
import {
  applyCleaning,
  cleanPreview,
  getVersionFindings,
  getVersionIntelligence,
  getVersionPreview,
} from "../api/datasets";
import type { VersionFindings } from "../api/datasets";
import type {
  CleaningOps,
  CleanPreview,
  DatasetIntelligence,
  DatasetVersion,
  PaginatedPreview,
} from "../api/types";
import { ApiError } from "../api/client";
import { Icon } from "../components/icons";

type Tab = "overview" | "columns" | "findings" | "preview" | "clean" | "versions";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "columns", label: "Columns" },
  { id: "findings", label: "Findings" },
  { id: "preview", label: "Preview" },
  { id: "clean", label: "Clean" },
  { id: "versions", label: "Versions" },
];

export default function DatasetDetail() {
  const { projectId, datasetId } = useParams<{ projectId: string; datasetId: string }>();
  if (!projectId || !datasetId) return null;

  const { data, status, error, load } = useDataset(projectId, datasetId);
  const [tab, setTab] = useState<Tab>("overview");
  const [versionId, setVersionId] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const versions = data?.versions ?? [];
  const completed = versions.filter((v) => v.job_status === "completed");
  const activeVersion: DatasetVersion | undefined = useMemo(() => {
    if (!versions.length) return undefined;
    return versions.find((v) => v.id === versionId) ?? completed[0] ?? versions[0];
  }, [versions, versionId, completed]);

  if (status === "loading")
    return <div className="py-16 text-center"><Spinner className="h-6 w-6" label="Loading dataset…" /></div>;
  if (status === "error" || !data)
    return <ErrorBanner message={error ?? "Could not load this dataset."} onRetry={() => { const c = new AbortController(); void load(c.signal); }} />;

  return (
    <>
      <p className="mb-3 text-sm">
        <Link to={`/app/projects/${projectId}/datasets`} className="text-ivory-300 hover:text-ivory-50">&larr; Datasets</Link>
      </p>
      <PageHeader title={data.name} subtitle={`Created ${new Date(data.created_at).toLocaleDateString()}`} />

      <Card className="mb-6 p-5">
        <h2 className="text-sm font-semibold text-ivory-100">Description</h2>
        <p className={`mt-2 whitespace-pre-wrap text-sm ${data.description ? "text-ivory-200" : "italic text-surface-500"}`}>
          {data.description ?? "No description"}
        </p>
      </Card>

      {versions.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="text-xs uppercase tracking-wide text-surface-400">Version</span>
          {versions.map((v) => (
            <button
              key={v.id}
              onClick={() => setVersionId(v.id)}
              className={`rounded border px-3 py-1 text-xs ${
                activeVersion?.id === v.id
                  ? "border-chartreuse-500/60 bg-chartreuse-500/10 text-chartreuse-300"
                  : "border-surface-700 bg-surface-900 text-ivory-200 hover:border-surface-500"
              }`}
            >
              v{v.version_number}
              {v.source === "cleaned" ? " ✦" : ""}
              {v.job_status !== "completed" ? ` (${v.job_status})` : ""}
            </button>
          ))}
        </div>
      )}

      <div className="mb-4 flex gap-1 border-b border-surface-700">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm ${tab === t.id ? "border-b-2 border-chartreuse-500 text-chartreuse-300" : "text-ivory-300 hover:text-ivory-50"}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {!activeVersion ? (
        <Card className="p-6 text-sm text-surface-400">No versions yet. Upload a CSV to get started.</Card>
      ) : activeVersion.job_status !== "completed" ? (
        <Card className="p-6">
          <div className="flex items-center gap-3 text-sm text-ivory-200">
            <Spinner className="h-4 w-4" />
            Version {activeVersion.version_number} is {activeVersion.job_status}
            {activeVersion.job_error ? ` — ${activeVersion.job_error}` : "…"}
          </div>
        </Card>
      ) : tab === "overview" ? (
        <OverviewTab projectId={projectId} datasetId={datasetId} versionId={activeVersion.id} />
      ) : tab === "columns" ? (
        <ColumnsTab projectId={projectId} datasetId={datasetId} versionId={activeVersion.id} />
      ) : tab === "findings" ? (
        <FindingsTab projectId={projectId} datasetId={datasetId} versionId={activeVersion.id} />
      ) : tab === "preview" ? (
        <PreviewTab projectId={projectId} datasetId={datasetId} versionId={activeVersion.id} />
      ) : tab === "clean" ? (
        <CleanTab
          projectId={projectId}
          datasetId={datasetId}
          version={activeVersion}
          columns={data.versions.find((v) => v.id === activeVersion.id)?.column_count ?? undefined}
          onApplied={() => { setVersionId(null); void load(); }}
        />
      ) : (
        <VersionsTab versions={versions} />
      )}
    </>
  );
}

/* ---------------- Overview ---------------- */

function OverviewTab({ projectId, datasetId, versionId }: { projectId: string; datasetId: string; versionId: string }) {
  const [intel, setIntel] = useState<DatasetIntelligence | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [target, setTarget] = useState("");

  const loadIntel = useCallback(async (t?: string) => {
    setStatus("loading");
    setError(null);
    try {
      setIntel(await getVersionIntelligence(projectId, datasetId, versionId, t || undefined));
      setStatus("ready");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not compute dataset intelligence.");
      setStatus("error");
    }
  }, [projectId, datasetId, versionId]);

  useEffect(() => {
    const c = new AbortController();
    void (async () => {
      setStatus("loading");
      try {
        const data = await getVersionIntelligence(projectId, datasetId, versionId, undefined, c.signal);
        if (c.signal.aborted) return;
        setIntel(data);
        setStatus("ready");
      } catch (e) {
        if (c.signal.aborted) return;
        setError(e instanceof ApiError ? e.message : "Could not compute dataset intelligence.");
        setStatus("error");
      }
    })();
    return () => c.abort();
  }, [projectId, datasetId, versionId]);

  if (status === "loading") return <div className="py-10 text-center"><Spinner label="Analyzing dataset…" /></div>;
  if (status === "error" || !intel)
    return <ErrorBanner message={error ?? "Intelligence unavailable."} onRetry={() => void loadIntel(target || undefined)} />;

  const scoreColor = intel.quality_score >= 80 ? "text-chartreuse-300" : intel.quality_score >= 50 ? "text-amber-300" : "text-red-300";
  const maxDist = intel.target ? Math.max(...Object.values(intel.target.distribution)) : 1;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        <Card className="p-5">
          <div className="text-xs uppercase tracking-wide text-surface-400">Data quality score</div>
          <div className={`mt-1 text-4xl font-bold ${scoreColor}`}>{intel.quality_score}</div>
          <div className="mt-3 h-2 rounded bg-surface-800">
            <div className={`h-2 rounded ${intel.quality_score >= 80 ? "bg-chartreuse-500" : intel.quality_score >= 50 ? "bg-amber-500" : "bg-red-500"}`} style={{ width: `${intel.quality_score}%` }} />
          </div>
          <p className="mt-2 text-xs text-surface-400">Transparent criteria below — recomputed from the raw CSV on every load.</p>
        </Card>
        <Card className="p-5">
          <div className="text-xs uppercase tracking-wide text-surface-400">Dimensions</div>
          <div className="mt-1 text-2xl font-semibold text-ivory-100">{intel.row_count.toLocaleString()} × {intel.column_count}</div>
          <div className="mt-2 text-sm text-surface-300">
            {intel.duplicate_row_count} duplicate rows ({intel.duplicate_row_percentage}%)
          </div>
        </Card>
        <Card className="p-5">
          <div className="text-xs uppercase tracking-wide text-surface-400">Score criteria (penalties)</div>
          <ul className="mt-2 space-y-1 text-xs text-surface-300">
            {Object.entries(intel.quality_criteria).map(([k, v]) => (
              <li key={k} className="flex justify-between"><span className="capitalize">{k.replace(/_/g, " ")}</span><span>{v}</span></li>
            ))}
          </ul>
        </Card>
      </div>

      {intel.warnings.length > 0 && (
        <Card className="border-amber-500/30 p-4">
          <h3 className="mb-2 text-sm font-semibold text-amber-200">Data quality warnings</h3>
          <ul className="list-inside list-disc space-y-1 text-sm text-ivory-200">
            {intel.warnings.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </Card>
      )}

      {intel.target && (
        <Card className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-ivory-100">Target analysis — {intel.target.column}</h3>
            <select
              value={target}
              onChange={(e) => { setTarget(e.target.value); void loadIntel(e.target.value); }}
              className="rounded border border-surface-700 bg-surface-900 px-2 py-1 text-xs text-ivory-100"
            >
              <option value="">no target</option>
              {intel.columns.map((c) => <option key={c.name} value={c.name}>{c.name} ({c.type})</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            {Object.entries(intel.target.distribution).map(([label, count]) => (
              <div key={label} className="flex items-center gap-2 text-xs">
                <span className="w-24 truncate text-ivory-200">{label}</span>
                <div className="h-4 flex-1 rounded bg-surface-800">
                  <div className="h-4 rounded bg-chartreuse-500/70" style={{ width: `${(count / maxDist) * 100}%` }} />
                </div>
                <span className="w-14 text-right text-surface-300">{count}</span>
              </div>
            ))}
          </div>
          {intel.target.imbalance_ratio !== undefined && (
            <p className="mt-3 text-xs text-surface-400">
              Imbalance ratio {intel.target.imbalance_ratio}:1 — dominant class {intel.target.dominant_class_pct}%.
            </p>
          )}
        </Card>
      )}

      {intel.correlation && intel.correlation.columns.length >= 2 && (
        <Card className="p-5">
          <h3 className="mb-3 text-sm font-semibold text-ivory-100">Numeric correlation</h3>
          <div className="overflow-x-auto">
            <table className="text-xs">
              <thead>
                <tr>
                  <th className="p-1" />
                  {intel.correlation.columns.map((c) => <th key={c} className="max-w-24 truncate px-1 py-1 text-surface-300">{c}</th>)}
                </tr>
              </thead>
              <tbody>
                {intel.correlation.matrix.map((row, i) => (
                  <tr key={i}>
                    <td className="max-w-24 truncate p-1 pr-2 text-ivory-200">{intel.correlation!.columns[i]}</td>
                    {row.map((v, j) => {
                      const intensity = Math.abs(v);
                      const bg = v >= 0 ? `rgba(163,230,53,${0.08 + intensity * 0.5})` : `rgba(248,113,113,${0.08 + intensity * 0.5})`;
                      return <td key={j} className="px-1 py-1 text-center" style={{ background: bg }}>{v.toFixed(2)}</td>;
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <button onClick={() => void loadIntel(target || undefined)} className="text-xs text-chartreuse-300 hover:underline">
        Refresh intelligence
      </button>
      <span className="ml-2 hidden text-xs text-surface-500">(recomputes from the stored CSV)</span>
    </div>
  );
}

/* ---------------- Findings ---------------- */

const SEV_TONE: Record<string, "live" | "warn" | "info"> = { critical: "warn", warning: "warn", info: "info" };

function FindingsTab({ projectId, datasetId, versionId }: { projectId: string; datasetId: string; versionId: string }) {
  const [data, setData] = useState<VersionFindings | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const c = new AbortController();
    setStatus("loading");
    getVersionFindings(projectId, datasetId, versionId, undefined, c.signal)
      .then((d) => { if (!c.signal.aborted) { setData(d); setStatus("ready"); setError(null); } })
      .catch((e) => { if (!c.signal.aborted) { setStatus("error"); setError(e instanceof ApiError ? e.message : "Could not load findings."); } });
    return () => c.abort();
  }, [projectId, datasetId, versionId, retry]);

  if (status === "loading") return <div className="py-10 text-center"><Spinner label="Computing findings…" /></div>;
  if (status === "error") return <ErrorBanner message={error ?? "Could not load findings."} onRetry={() => setRetry((r) => r + 1)} />;
  if (!data) return null;

  const s = data.severity_summary;
  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <span className="text-ivory-200">{data.row_count.toLocaleString()} rows analyzed</span>
          <Badge tone="warn">{s.warning ?? 0} warnings</Badge>
          <Badge tone="live">{s.info ?? 0} info</Badge>
          {(s.critical ?? 0) > 0 && <Badge tone="warn">{s.critical} critical</Badge>}
          <span className="ml-auto text-xs text-surface-500">{data.note}</span>
        </div>
      </Card>
      {data.findings.length === 0 ? (
        <Card className="p-6 text-sm text-ivory-300">No findings — dataset looks clean on the checked heuristics.</Card>
      ) : (
        data.findings.map((f) => (
          <Card key={f.id} className="p-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={SEV_TONE[f.severity] ?? "info"}>{f.severity}</Badge>
              <span className="font-medium text-ivory-100">{f.category.replace(/_/g, " ")}</span>
              <span className="text-xs text-surface-500">{f.method}</span>
            </div>
            <p className="mt-2 text-sm text-ivory-300">{f.evidence}</p>
            <p className="mt-1 text-sm text-surface-400">{f.explanation}</p>
            <p className="mt-1 text-xs text-chartreuse-300">→ {f.recommendation}</p>
            <div className="mt-2 flex flex-wrap gap-1">
              {f.columns.map((c) => <Badge key={c} tone="info">{c}</Badge>)}
              {f.affected_pct != null && <span className="text-xs text-surface-500">{f.affected_pct}% of rows affected</span>}
              <span className="text-xs text-surface-500">confidence: {f.confidence}</span>
            </div>
          </Card>
        ))
      )}
    </div>
  );
}

/* ---------------- Columns ---------------- */

function ColumnsTab({ projectId, datasetId, versionId }: { projectId: string; datasetId: string; versionId: string }) {
  const [intel, setIntel] = useState<DatasetIntelligence | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    const c = new AbortController();
    getVersionIntelligence(projectId, datasetId, versionId, undefined, c.signal)
      .then((d) => { if (!c.signal.aborted) { setIntel(d); setStatus("ready"); } })
      .catch(() => { if (!c.signal.aborted) setStatus("error"); });
    return () => c.abort();
  }, [projectId, datasetId, versionId]);

  if (status === "loading") return <div className="py-10 text-center"><Spinner label="Loading column profiles…" /></div>;
  if (status === "error" || !intel) return <ErrorBanner message="Could not load column profiles." />;

  return (
    <Card className="overflow-x-auto p-4">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase text-surface-400">
            <th className="p-2">Column</th><th className="p-2">Type</th><th className="p-2">Missing</th>
            <th className="p-2">Unique</th><th className="p-2">Stats / top values</th><th className="p-2">Flags</th>
          </tr>
        </thead>
        <tbody>
          {intel.columns.map((c) => (
            <tr key={c.name} className="border-t border-surface-800">
              <td className="p-2 font-medium text-ivory-100">{c.name}</td>
              <td className="p-2"><Badge tone={c.type === "numeric" ? "live" : c.type === "datetime" ? "info" : "soon"}>{c.type}</Badge></td>
              <td className="p-2 text-ivory-200">{c.missing_count} ({c.missing_percentage}%)</td>
              <td className="p-2 text-ivory-200">{c.unique_count}</td>
              <td className="max-w-xs truncate p-2 text-xs text-surface-300">
                {c.stats
                  ? `mean ${c.stats.mean} · sd ${c.stats.std} · [${c.stats.min}, ${c.stats.max}]${c.stats.outlier_count ? ` · ${c.stats.outlier_count} outliers` : ""}`
                  : c.top_values
                    ? Object.entries(c.top_values).slice(0, 3).map(([k, v]) => `${k}: ${v}`).join(", ")
                    : c.sample_values.slice(0, 3).join(", ")}
              </td>
              <td className="p-2">
                <div className="flex flex-wrap gap-1">
                  {c.is_identifier && <Badge tone="warn">id?</Badge>}
                  {c.is_constant && <Badge tone="warn">constant</Badge>}
                  {c.is_near_constant && !c.is_constant && <Badge tone="warn">near-const</Badge>}
                  {c.is_high_cardinality && <Badge tone="warn">high-card</Badge>}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

/* ---------------- Preview ---------------- */

function PreviewTab({ projectId, datasetId, versionId }: { projectId: string; datasetId: string; versionId: string }) {
  const [data, setData] = useState<PaginatedPreview | null>(null);
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const limit = 25;

  useEffect(() => {
    const c = new AbortController();
    setStatus("loading");
    getVersionPreview(projectId, datasetId, versionId, offset, limit, c.signal)
      .then((d) => { if (!c.signal.aborted) { setData(d); setStatus("ready"); } })
      .catch(() => { if (!c.signal.aborted) setStatus("error"); });
    return () => c.abort();
  }, [projectId, datasetId, versionId, offset]);

  if (status === "loading") return <div className="py-10 text-center"><Spinner label="Loading preview…" /></div>;
  if (status === "error" || !data) return <ErrorBanner message="Could not load preview." />;

  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between text-xs text-surface-400">
        <span>{data.total_rows.toLocaleString()} rows — showing {offset + 1}–{Math.min(offset + limit, data.total_rows)}</span>
        <div className="flex gap-2">
          <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))} className="rounded border border-surface-700 px-2 py-1 disabled:opacity-40">Prev</button>
          <button disabled={!data.has_more} onClick={() => setOffset(offset + limit)} className="rounded border border-surface-700 px-2 py-1 disabled:opacity-40">Next</button>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-surface-400">
              {data.columns.map((c) => <th key={c} className="max-w-40 truncate p-1">{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, i) => (
              <tr key={i} className="border-t border-surface-800">
                {data.columns.map((c) => <td key={c} className="max-w-40 truncate p-1 text-ivory-200">{String(row[c] ?? "")}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

/* ---------------- Clean ---------------- */

function CleanTab({ projectId, datasetId, version, onApplied }: { projectId: string; datasetId: string; version: DatasetVersion; columns?: number; onApplied: () => void }) {
  const [columnNames, setColumnNames] = useState<string[]>([]);
  const [ops, setOps] = useState<CleaningOps>({
    drop_columns: [],
    rename_columns: {},
    missing: { strategy: "none" },
    drop_duplicates: false,
    outliers: { enabled: false, strategy: "drop_rows", k: 1.5 },
    scale: { method: "none" },
  });
  const [preview, setPreview] = useState<CleanPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getVersionPreview(projectId, datasetId, version.id, 0, 1)
      .then((p) => setColumnNames(p.columns))
      .catch(() => setColumnNames([]));
  }, [projectId, datasetId, version.id]);

  const set = <K extends keyof CleaningOps>(key: K, value: CleaningOps[K]) =>
    setOps((o) => ({ ...o, [key]: value }));

  const runPreview = async () => {
    setBusy(true); setError(null); setMessage(null);
    try {
      setPreview(await cleanPreview(projectId, datasetId, version.id, ops));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Preview failed.");
    } finally {
      setBusy(false);
    }
  };

  const apply = async () => {
    setBusy(true); setError(null); setMessage(null);
    try {
      const created = await applyCleaning(projectId, datasetId, version.id, ops);
      setMessage(`Created version ${created.version_number} (${created.source}).`);
      setPreview(null);
      onApplied();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Cleaning failed.");
    } finally {
      setBusy(false);
    }
  };

  const missingStrategies = [
    ["none", "No missing-value handling"],
    ["drop_rows", "Drop rows with any missing value"],
    ["numeric_mean", "Numeric: mean imputation"],
    ["numeric_median", "Numeric: median imputation"],
    ["numeric_constant", "Numeric: constant"],
    ["categorical_mode", "Categorical: mode imputation"],
    ["categorical_constant", "Categorical: constant"],
  ];

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="space-y-4 p-5">
        <h3 className="text-sm font-semibold text-ivory-100">Cleaning operations</h3>
        <p className="text-xs text-surface-400">Source version v{version.version_number} is never modified — results are saved as a new version.</p>

        <div>
          <div className="mb-1 text-xs font-medium text-ivory-200">Drop columns</div>
          <div className="flex max-h-28 flex-wrap gap-1 overflow-y-auto">
            {columnNames.map((c) => {
              const dropped = ops.drop_columns?.includes(c);
              return (
                <button key={c} type="button"
                  onClick={() => set("drop_columns", dropped ? ops.drop_columns?.filter((x) => x !== c) : [...(ops.drop_columns ?? []), c])}
                  className={`rounded border px-2 py-0.5 text-xs ${dropped ? "border-red-500/60 bg-red-500/10 text-red-200" : "border-surface-700 text-ivory-200"}`}>
                  {c}
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <div className="mb-1 text-xs font-medium text-ivory-200">Missing values</div>
          <select value={ops.missing?.strategy ?? "none"}
            onChange={(e) => set("missing", { strategy: e.target.value })}
            className="w-full rounded border border-surface-700 bg-surface-900 px-2 py-1.5 text-sm text-ivory-100">
            {missingStrategies.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>

        <label className="flex items-center gap-2 text-sm text-ivory-200">
          <input type="checkbox" checked={!!ops.drop_duplicates}
            onChange={(e) => set("drop_duplicates", e.target.checked)} className="accent-chartreuse-500" />
          Remove duplicate rows
        </label>

        <div className="rounded border border-surface-700 p-3">
          <label className="flex items-center gap-2 text-sm text-ivory-200">
            <input type="checkbox" checked={!!ops.outliers?.enabled}
              onChange={(e) => set("outliers", { ...(ops.outliers ?? {}), enabled: e.target.checked })} className="accent-chartreuse-500" />
            Outlier handling (IQR, all numeric columns)
          </label>
          {ops.outliers?.enabled && (
            <div className="mt-2 flex gap-3 text-xs text-ivory-200">
              <select value={ops.outliers.strategy ?? "drop_rows"}
                onChange={(e) => set("outliers", { ...(ops.outliers ?? {}), strategy: e.target.value })}
                className="rounded border border-surface-700 bg-surface-900 px-2 py-1">
                <option value="drop_rows">Drop outlier rows</option>
                <option value="clip">Clip to bounds</option>
              </select>
              <label className="flex items-center gap-1">k=
                <input type="number" step="0.5" value={ops.outliers.k ?? 1.5}
                  onChange={(e) => set("outliers", { ...(ops.outliers ?? {}), k: parseFloat(e.target.value) || 1.5 })}
                  className="w-16 rounded border border-surface-700 bg-surface-900 px-1 py-1" />
              </label>
            </div>
          )}
        </div>

        <div>
          <div className="mb-1 text-xs font-medium text-ivory-200">Numeric scaling</div>
          <select value={ops.scale?.method ?? "none"}
            onChange={(e) => set("scale", { method: e.target.value })}
            className="w-full rounded border border-surface-700 bg-surface-900 px-2 py-1.5 text-sm text-ivory-100">
            <option value="none">No scaling</option>
            <option value="standard">Standardization (z-score)</option>
            <option value="minmax">Min-max normalization</option>
          </select>
        </div>

        <div>
          <div className="mb-1 text-xs font-medium text-ivory-200">Categorical encoding</div>
          <div className="flex gap-2">
            <select value={ops.encode?.[0]?.column ?? ""}
              onChange={(e) => {
                const col = e.target.value;
                set("encode", col ? [{ column: col, method: ops.encode?.[0]?.method ?? "one_hot" }] : []);
              }}
              className="flex-1 rounded border border-surface-700 bg-surface-900 px-2 py-1.5 text-sm text-ivory-100">
              <option value="">None</option>
              {columnNames.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            {ops.encode?.length ? (
              <select value={ops.encode[0].method}
                onChange={(e) => set("encode", [{ column: ops.encode![0].column, method: e.target.value }])}
                className="rounded border border-surface-700 bg-surface-900 px-2 py-1.5 text-sm text-ivory-100">
                <option value="one_hot">One-hot</option>
                <option value="ordinal">Ordinal</option>
              </select>
            ) : null}
          </div>
        </div>

        <div>
          <div className="mb-1 text-xs font-medium text-ivory-200">Datetime extraction</div>
          <select value={ops.datetime_extract?.[0]?.column ?? ""}
            onChange={(e) => {
              const col = e.target.value;
              set("datetime_extract", col ? [{ column: col, parts: ["year", "month", "day"] }] : []);
            }}
            className="w-full rounded border border-surface-700 bg-surface-900 px-2 py-1.5 text-sm text-ivory-100">
            <option value="">None</option>
            {columnNames.map((c) => <option key={c} value={c}>{c} (year/month/day)</option>)}
          </select>
        </div>

        {error && <ErrorBanner message={error} />}
        {message && <p className="text-sm text-chartreuse-300">{message}</p>}

        <div className="flex gap-2">
          <button onClick={() => void runPreview()} disabled={busy}
            className="rounded bg-ivory-100 px-4 py-2 text-sm font-medium text-surface-950 disabled:opacity-50">
            {busy ? "Working…" : "Preview changes"}
          </button>
          <button onClick={() => void apply()} disabled={busy || !preview}
            className="rounded bg-chartreuse-500 px-4 py-2 text-sm font-medium text-surface-950 disabled:opacity-50">
            Save as new version
          </button>
        </div>
        {!preview && <p className="text-xs text-surface-500">Preview first — saving is only enabled after a successful preview.</p>}
      </Card>

      <Card className="p-5">
        <h3 className="mb-3 text-sm font-semibold text-ivory-100">Preview</h3>
        {!preview ? (
          <p className="text-sm text-surface-400">Configure operations and click “Preview changes”.</p>
        ) : (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2 text-xs text-surface-300 sm:grid-cols-4">
              <div className="rounded border border-surface-700 p-2">
                <div className="text-surface-400">Rows</div>
                <div>{preview.shape_before.rows.toLocaleString()} → {preview.shape_after.rows.toLocaleString()}
                  {preview.rows_removed > 0 && <span className="text-red-300"> (−{preview.rows_removed})</span>}</div>
              </div>
              <div className="rounded border border-surface-700 p-2">
                <div className="text-surface-400">Columns</div>
                <div>{preview.shape_before.columns} → {preview.shape_after.columns}
                  {preview.columns_removed > 0 && <span className="text-red-300"> (−{preview.columns_removed})</span>}</div>
              </div>
              <div className="rounded border border-surface-700 p-2">
                <div className="text-surface-400">Missing cells</div>
                <div>{preview.missing_before.missing_cells.toLocaleString()} → {preview.missing_after.missing_cells.toLocaleString()}</div>
              </div>
              <div className="rounded border border-surface-700 p-2">
                <div className="text-surface-400">Missing %</div>
                <div>{preview.missing_before.missing_pct}% → {preview.missing_after.missing_pct}%</div>
              </div>
            </div>
            {preview.transformation_log.length > 0 && (
              <ul className="list-inside list-disc space-y-0.5 text-xs text-chartreuse-200">
                {preview.transformation_log.map((l, i) => <li key={i}>{l}</li>)}
              </ul>
            )}
            <div className="max-h-96 overflow-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-surface-400">
                    {preview.columns.map((c) => <th key={c} className="max-w-32 truncate p-1">{c}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.slice(0, 10).map((row, i) => (
                    <tr key={i} className="border-t border-surface-800">
                      {preview.columns.map((c) => <td key={c} className="max-w-32 truncate p-1 text-ivory-200">{String(row[c] ?? "")}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

/* ---------------- Versions ---------------- */

function VersionsTab({ versions }: { versions: DatasetVersion[] }) {
  if (!versions.length) return <Card className="p-6 text-sm text-surface-400">No versions yet.</Card>;
  return (
    <Card className="p-5">
      <ul className="space-y-3">
        {versions.map((v) => (
          <li key={v.id} className="rounded border border-surface-700 bg-surface-900 p-4">
            <div className="flex items-center justify-between gap-4">
              <div>
                <span className="text-sm font-medium text-ivory-100">
                  Version {v.version_number} {v.source === "cleaned" && <Badge tone="info">cleaned</Badge>}
                </span>
                <div className="mt-1 flex items-center gap-2">
                  <Badge tone={v.job_status === "completed" ? "live" : "soon"}>{v.job_status}</Badge>
                  <span className="text-xs text-surface-400">{new Date(v.created_at).toLocaleString()}</span>
                </div>
                {v.derived_from_version_id && (
                  <div className="mt-1 text-xs text-surface-400">Derived from version {versions.find((x) => x.id === v.derived_from_version_id)?.version_number ?? "?"}</div>
                )}
              </div>
              <div className="text-right text-xs text-surface-400">
                <div>{v.row_count ?? "?"} rows × {v.column_count ?? "?"} cols</div>
                <div>{(v.file_size_bytes / 1024 / 1024).toFixed(2)} MB</div>
                <div className="font-mono">{v.sha256_checksum.slice(0, 12)}…</div>
              </div>
            </div>
            {v.transformation_log && v.transformation_log.length > 0 && (
              <details className="mt-2">
                <summary className="cursor-pointer text-xs text-chartreuse-300">Transformation history ({v.transformation_log.length})</summary>
                <ul className="mt-1 list-inside list-disc space-y-0.5 text-xs text-surface-300">
                  {v.transformation_log.map((l, i) => <li key={i}>{l}</li>)}
                </ul>
              </details>
            )}
            {v.job_error && (
              <div className="mt-2 rounded border border-danger-500/40 bg-danger-500/10 p-2 text-xs text-red-200">
                <Icon name="alert" className="mr-1 inline h-3 w-3" />{v.job_error}
              </div>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}
