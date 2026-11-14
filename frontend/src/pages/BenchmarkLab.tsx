import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Card, ErrorBanner, PageHeader, Spinner } from "../components/ui/primitives";
import { useToast } from "../components/ui/Toast";
import { ApiError } from "../api/client";
import { importBenchmark, listBenchmarks } from "../api/benchmarks";
import { listProjects } from "../api/projects";
import type { BenchmarkDataset, Project } from "../api/types";

export default function BenchmarkLab() {
  const { notify } = useToast();
  const [items, setItems] = useState<BenchmarkDataset[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [taskFilter, setTaskFilter] = useState<"" | "classification" | "regression">("");
  const [selected, setSelected] = useState<BenchmarkDataset | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [importing, setImporting] = useState(false);
  const [importedVersionId, setImportedVersionId] = useState<string | null>(null);
  const [importedDatasetId, setImportedDatasetId] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    setStatus("loading");
    setError(null);
    try {
      const [benchmarks, projs] = await Promise.all([
        listBenchmarks(taskFilter || undefined, search || undefined, signal),
        listProjects(100, 0, signal).catch(() => [] as Project[]),
      ]);
      if (signal?.aborted) return;
      setItems(benchmarks);
      setProjects(projs);
      setStatus("ready");
    } catch (e) {
      if (signal?.aborted) return;
      setError(e instanceof ApiError ? e.message : "Could not load the benchmark catalog.");
      setStatus("error");
    }
  }, [taskFilter, search]);

  useEffect(() => {
    const c = new AbortController();
    const t = setTimeout(() => void load(c.signal), search ? 250 : 0);
    return () => { c.abort(); clearTimeout(t); };
  }, [load, search]);

  const counts = useMemo(() => ({
    classification: items.filter((i) => i.task_type === "classification").length,
    regression: items.filter((i) => i.task_type === "regression").length,
  }), [items]);

  const onImport = async () => {
    if (!selected || !projectId) {
      notify("error", "Select a benchmark dataset and a target project first.");
      return;
    }
    setImporting(true);
    setImportedVersionId(null);
    setImportedDatasetId(null);
    try {
      const version = await importBenchmark(selected.id, projectId);
      notify("success", `Imported “${selected.name}” as dataset version ${version.version_number}. Profiling has started.`);
      setImportedVersionId(version.id);
      setImportedDatasetId((version as any).dataset_id ?? null);
    } catch (e) {
      notify("error", e instanceof ApiError ? e.message : "Import failed.");
    } finally {
      setImporting(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Benchmark Lab"
        subtitle="Public benchmark datasets — import into a project, then train and compare models."
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search datasets…"
          className="w-64 rounded border border-surface-700 bg-surface-900 px-3 py-2 text-sm text-ivory-100 placeholder:text-surface-500"
        />
        <div className="flex gap-1">
          {([["", "All"], ["classification", "Classification"], ["regression", "Regression"]] as const).map(([v, l]) => (
            <button key={v} onClick={() => setTaskFilter(v)}
              className={`rounded border px-3 py-1.5 text-xs ${taskFilter === v ? "border-chartreuse-500/60 bg-chartreuse-500/10 text-chartreuse-300" : "border-surface-700 text-ivory-200"}`}>
              {l}
            </button>
          ))}
        </div>
        <span className="text-xs text-surface-400">{counts.classification} classification · {counts.regression} regression</span>
      </div>

      {status === "loading" && <div className="py-16 text-center"><Spinner label="Loading catalog…" /></div>}
      {status === "error" && <ErrorBanner message={error ?? "Catalog unavailable."} onRetry={() => void load()} />}

      {status === "ready" && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-3">
            {items.length === 0 && (
              <Card className="p-6 text-sm text-surface-400">No datasets match the current filters.</Card>
            )}
            {items.map((d) => (
              <Card key={d.id} className={`cursor-pointer p-4 transition ${selected?.id === d.id ? "border-chartreuse-500/60" : "hover:border-surface-500"}`}>
                <div onClick={() => { setSelected(d); setImportedVersionId(null); }} className="cursor-pointer">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-ivory-100">{d.name}</div>
                    <p className="mt-1 text-xs text-surface-300">{d.description}</p>
                  </div>
                  <Badge tone={d.task_type === "classification" ? "live" : "info"}>{d.task_type}</Badge>
                </div>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-surface-400">
                  <span>Target: <span className="text-ivory-200">{d.target_column}</span></span>
                  <span>{d.source}</span>
                  <a href={d.source_url} target="_blank" rel="noreferrer" className="text-chartreuse-300 hover:underline" onClick={(e) => e.stopPropagation()}>Source ↗</a>
                </div>
                </div>
              </Card>
            ))}
          </div>

          <Card className="h-fit p-5 lg:sticky lg:top-4">
            {!selected ? (
              <p className="text-sm text-surface-400">Select a dataset to see details and import it.</p>
            ) : (
              <div className="space-y-4">
                <div>
                  <h3 className="text-base font-semibold text-ivory-100">{selected.name}</h3>
                  <p className="mt-1 text-sm text-surface-300">{selected.description}</p>
                </div>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                  <dt className="text-surface-400">Task</dt><dd className="text-ivory-100">{selected.task_type}</dd>
                  <dt className="text-surface-400">Target column</dt><dd className="text-ivory-100">{selected.target_column}</dd>
                  <dt className="text-surface-400">Source</dt><dd className="text-ivory-100">{selected.source}</dd>
                  <dt className="text-surface-400">License</dt><dd className="text-ivory-100">{selected.license}</dd>
                </dl>
                <div>
                  <div className="mb-1 text-xs font-medium text-ivory-200">Citation</div>
                  <p className="text-xs italic text-surface-400">{selected.citation}</p>
                </div>
                <div>
                  <div className="mb-1 text-xs font-medium text-ivory-200">Import into project</div>
                  <div className="flex gap-2">
                    <select value={projectId} onChange={(e) => setProjectId(e.target.value)}
                      className="flex-1 rounded border border-surface-700 bg-surface-900 px-2 py-2 text-sm text-ivory-100">
                      <option value="">Select project…</option>
                      {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </select>
                    <button onClick={() => void onImport()} disabled={importing || !projectId}
                      className="rounded bg-chartreuse-500 px-4 py-2 text-sm font-medium text-surface-950 disabled:opacity-50">
                      {importing ? "Importing…" : "Import"}
                    </button>
                  </div>
                  {projects.length === 0 && (
                    <p className="mt-1 text-xs text-surface-400">No projects yet — <Link to="/app/projects" className="text-chartreuse-300 hover:underline">create one first</Link>.</p>
                  )}
                </div>
                {importedVersionId && projectId && (
                  <div className="rounded border border-chartreuse-500/40 bg-chartreuse-500/10 p-3 text-xs text-chartreuse-200">
                    <div className="font-medium">Imported “{selected.name}” into the selected project.</div>
                    <div className="mt-1 text-chartreuse-300/80">Profiling runs in the background — the dataset appears in the project's Datasets list.</div>
                    <div className="mt-2 flex gap-2">
                      {importedDatasetId && (
                        <Link to={`/app/projects/${projectId}/datasets/${importedDatasetId}`}
                          className="rounded bg-ivory-100 px-3 py-1.5 font-medium text-surface-950 hover:opacity-90">
                          Open Dataset
                        </Link>
                      )}
                      <Link to={`/app/projects/${projectId}/experiments`}
                        className="rounded border border-chartreuse-500/50 px-3 py-1.5 font-medium text-chartreuse-300 hover:bg-chartreuse-500/10">
                        Start Experiment
                      </Link>
                    </div>
                  </div>
                )}
              </div>
            )}
          </Card>
        </div>
      )}
    </>
  );
}
