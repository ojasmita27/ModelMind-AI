import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Badge, Card, ErrorBanner, PageHeader, Spinner } from "../components/ui/primitives";
import { ApiError } from "../api/client";
import { listDatasets } from "../api/datasets";
import { listExperiments } from "../api/experiments";

interface ExperimentRow {
  id: string;
  name: string;
  status: string;
  task_type: string;
  target_column: string;
  dataset_id: string | null;
  dataset_version_id: string | null;
  created_at: string;
}

export default function WhatIfLab() {
  const { projectId } = useParams<{ projectId: string }>();
  const [experiments, setExperiments] = useState<ExperimentRow[]>([]);
  const [datasetNames, setDatasetNames] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    if (!projectId) return;
    setStatus("loading");
    try {
      const [exps, dsets] = await Promise.all([
        listExperiments(projectId, signal),
        listDatasets(projectId, signal).catch(() => []),
      ]);
      if (signal?.aborted) return;
      setExperiments(exps.filter((e: any) => e.status === "completed" && e.artifact_uri));
      setDatasetNames(Object.fromEntries(dsets.map((d: any) => [d.id, d.name])));
      setStatus("ready");
    } catch (e) {
      if (signal?.aborted) return;
      setError(e instanceof ApiError ? e.message : "Could not load experiments.");
      setStatus("error");
    }
  }, [projectId]);

  useEffect(() => { const c = new AbortController(); void load(c.signal); return () => c.abort(); }, [load]);

  if (!projectId) return null;
  if (status === "loading") return <div className="py-16 text-center"><Spinner label="Loading experiments…" /></div>;
  if (status === "error") return <ErrorBanner message={error ?? "Unavailable."} onRetry={() => void load()} />;

  return (
    <>
      <PageHeader title="What-If Lab" subtitle="Select a completed experiment to explore counterfactual predictions on its trained model." />
      {experiments.length === 0 ? (
        <Card className="p-6 text-sm text-surface-400">
          No completed experiments with trained artifacts yet. Train an experiment first, then return here.
        </Card>
      ) : (
        <div className="space-y-3">
          {experiments.map((e) => (
            <Card key={e.id} className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-semibold text-ivory-100">{e.name}</div>
                  <div className="mt-0.5 text-xs text-surface-400">
                    {e.task_type} · target: {e.target_column}
                    {e.dataset_id && ` · dataset: ${datasetNames[e.dataset_id] ?? e.dataset_id.slice(0, 8)}`}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <Badge tone="live">{e.status}</Badge>
                  <Link to={`/app/projects/${projectId}/experiments/${e.id}/what-if`}
                    className="rounded bg-chartreuse-500 px-3 py-1.5 text-xs font-medium text-surface-950 hover:opacity-90">
                    Open What-If
                  </Link>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
