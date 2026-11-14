import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import * as api from "../api/projects";
import { ApiError } from "../api/client";
import { listDatasets } from "../api/datasets";
import { listExperiments } from "../api/experiments";
import type { Dataset, Experiment, Project } from "../api/types";
import { ConfirmDialog } from "../components/ui/Modal";
import { useToast } from "../components/ui/Toast";
import { Badge, Button, Card, EmptyState, ErrorBanner, PageHeader, Spinner } from "../components/ui/primitives";
import { ProjectFormModal } from "../features/projects/ProjectFormModal";
import { formatDate, timeAgo } from "../lib/format";

export default function ProjectDetail() {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const { notify } = useToast();
  const [project, setProject] = useState<Project | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "missing" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [datasetState, setDatasetState] = useState<"loading" | "ready" | "error">("loading");
  const [datasetError, setDatasetError] = useState<string | null>(null);
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [experimentState, setExperimentState] = useState<"loading" | "ready" | "error">("loading");
  const [experimentError, setExperimentError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    setState("loading");
    try {
      setProject(await api.getProject(projectId, signal));
      setState("ready");
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      if (e instanceof ApiError && (e.status === 404 || e.status === 422)) { setState("missing"); return; }
      setError(e instanceof ApiError ? e.message : "Could not load this project.");
      setState("error");
    }
  }, [projectId]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    setDatasetState("loading");
    setDatasetError(null);
    void listDatasets(projectId)
      .then((items) => {
        if (!cancelled) {
          setDatasets(items);
          setDatasetState("ready");
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setDatasetState("error");
          setDatasetError(e instanceof ApiError ? e.message : "Could not load datasets.");
        }
      });

    setExperimentState("loading");
    setExperimentError(null);
    void listExperiments(projectId)
      .then((items) => {
        if (!cancelled) {
          setExperiments(items);
          setExperimentState("ready");
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setExperimentState("error");
          setExperimentError(e instanceof ApiError ? e.message : "Could not load experiments.");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [projectId]);

  async function confirmDelete() {
    if (!project) return;
    setBusy(true);
    setDeleteError(null);
    try {
      await api.deleteProject(project.id);
      notify("success", `Deleted “${project.name}”.`);
      navigate("/app/projects", { replace: true });
    } catch (e) {
      setDeleteError(e instanceof ApiError ? e.message : "Could not delete the project.");
      setBusy(false);
    }
  }

  if (state === "loading") return <div className="py-16 text-center"><Spinner className="h-6 w-6" label="Loading project…" /></div>;
  if (state === "error") return <ErrorBanner message={error ?? "Could not load this project."} onRetry={() => void load()} />;
  if (state === "missing" || !project) {
    return (
      <EmptyState icon="folder" title="Project not found" action={<Link to="/app/projects" className="text-sm font-medium text-accent-400 hover:text-accent-300">Back to projects</Link>}>
        It may have been deleted, or it does not belong to your account.
      </EmptyState>
    );
  }

  return (
    <>
      <p className="mb-3 text-sm"><Link to="/app/projects" className="text-ivory-300 hover:text-ivory-50">&larr; Projects</Link></p>
      <PageHeader title={project.name} subtitle={`Created ${formatDate(project.created_at)} · updated ${timeAgo(project.updated_at)}`}
        actions={<><Button variant="secondary" icon="edit" onClick={() => setEditing(true)}>Edit</Button>
          <Button variant="secondary" icon="trash" onClick={() => { setDeleteError(null); setConfirming(true); }}>Delete</Button></>} />

      <Card className="mb-6 p-5">
        <h2 className="text-sm font-semibold text-ivory-100">Description</h2>
        <p className={`mt-2 whitespace-pre-wrap text-sm ${project.description ? "text-ivory-200" : "italic text-surface-500"}`}>{project.description ?? "No description."}</p>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded border border-surface-700 bg-surface-900/60 p-5">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-ivory-100">Datasets</h2>
            {datasets.length > 0 && <Badge tone="live">{datasets.length}</Badge>}
          </div>
          {datasetState === "loading" && <div className="flex items-center gap-2 text-sm text-ivory-300"><Spinner className="h-4 w-4" /> Loading datasets…</div>}
          {datasetState === "error" && <p className="text-sm text-red-200">{datasetError}</p>}
          {datasetState === "ready" && datasets.length === 0 && (
            <div className="space-y-3">
              <p className="text-sm text-surface-400">No datasets uploaded for this project yet.</p>
              <Link to={`/app/projects/${project.id}/datasets`} className="inline-flex text-sm font-medium text-accent-400 hover:text-accent-300">Open dataset workspace →</Link>
            </div>
          )}
          {datasetState === "ready" && datasets.length > 0 && (
            <ul className="space-y-2 text-sm">
              {datasets.slice(0, 3).map((dataset) => (
                <li key={dataset.id} className="flex items-center justify-between gap-3 rounded border border-surface-700 bg-surface-950/70 px-3 py-2">
                  <Link to={`/app/projects/${project.id}/datasets/${dataset.id}`} className="min-w-0 truncate text-ivory-100 hover:text-accent-300">{dataset.name}</Link>
                  <span className="shrink-0 text-[10px] uppercase tracking-wide text-surface-400">{new Date(dataset.created_at).toLocaleDateString()}</span>
                </li>
              ))}
              <li className="pt-1">
                <Link to={`/app/projects/${project.id}/datasets`} className="inline-flex text-sm font-medium text-accent-400 hover:text-accent-300">View all datasets →</Link>
              </li>
            </ul>
          )}
        </div>

        <div className="rounded border border-surface-700 bg-surface-900/60 p-5">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-ivory-100">Experiments</h2>
            {experiments.length > 0 && <Badge tone="live">{experiments.length}</Badge>}
          </div>
          {experimentState === "loading" && <div className="flex items-center gap-2 text-sm text-ivory-300"><Spinner className="h-4 w-4" /> Loading experiments…</div>}
          {experimentState === "error" && <p className="text-sm text-red-200">{experimentError}</p>}
          {experimentState === "ready" && experiments.length === 0 && (
            <div className="space-y-3">
              <p className="text-sm text-surface-400">No runs yet for this project.</p>
              <Link to={`/app/projects/${projectId}/experiments`} className="inline-flex text-sm font-medium text-accent-400 hover:text-accent-300">Launch the experiment studio →</Link>
            </div>
          )}
          {experimentState === "ready" && experiments.length > 0 && (
            <ul className="space-y-2 text-sm">
              {experiments.slice(0, 3).map((experiment) => {
                const metrics = experiment.metrics ?? {};
                const primaryMetric =
                  (typeof metrics === "object" && metrics && "best_metrics" in metrics && typeof (metrics as Record<string, unknown>).best_metrics === "object"
                    ? ((metrics as Record<string, unknown>).best_metrics as Record<string, unknown>)
                    : metrics) as Record<string, unknown>;
                const topMetric = Object.entries(primaryMetric).find(([, value]) => typeof value === "number");

                return (
                  <li key={experiment.id} className="rounded border border-surface-700 bg-surface-950/70 px-3 py-2">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate font-medium text-ivory-100">{experiment.name}</div>
                        <div className="mt-1 text-[10px] uppercase tracking-wide text-surface-400">{experiment.task_type} • {experiment.target_column}</div>
                      </div>
                      <Badge tone={experiment.status === "completed" ? "live" : "soon"}>{experiment.status}</Badge>
                    </div>
                    <div className="mt-2 flex items-center justify-between gap-2 text-[11px] text-surface-400">
                      <span>{new Date(experiment.created_at).toLocaleDateString()}</span>
                      <span>{topMetric && typeof topMetric[1] === "number" ? `${topMetric[0]}: ${Number(topMetric[1]).toFixed(3)}` : "No metrics yet"}</span>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
          <div className="mt-4 pt-3 border-t border-surface-700">
            <Link to={`/app/projects/${projectId}/experiments`} className="inline-flex text-sm font-medium text-accent-400 hover:text-accent-300">Open experiment studio →</Link>
          </div>
        </div>
      </div>

      <ProjectFormModal open={editing} project={project} onClose={() => setEditing(false)}
        onSubmit={async (input) => { setProject(await api.updateProject(project.id, input)); notify("success", "Project updated."); }} />
      <ConfirmDialog open={confirming} title="Delete project?" confirmLabel="Delete project" busy={busy} error={deleteError}
        message={<>“{project.name}” will be permanently deleted. This cannot be undone.</>}
        onConfirm={confirmDelete} onCancel={() => setConfirming(false)} />
    </>
  );
}
