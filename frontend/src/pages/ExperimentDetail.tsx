import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { getDataset } from "../api/datasets";
import {
  getExperiment,
  getExperimentArtifact,
  getExperimentEvaluation,
  getExperimentReproducibility,
} from "../api/experiments";
import { getProject } from "../api/projects";
import type {
  Experiment,
  ExperimentArtifact,
  ExperimentEvaluation,
  ExperimentReproducibility,
  ModelEvaluationResult,
  Project,
} from "../api/types";
import { Badge, Card, EmptyState, ErrorBanner, PageHeader, Spinner } from "../components/ui/primitives";

const METRIC_LABELS: Record<string, string> = {
  accuracy: "Accuracy",
  precision_macro: "Precision (macro)",
  recall_macro: "Recall (macro)",
  f1_macro: "F1 (macro)",
  roc_auc: "ROC-AUC",
  mae: "MAE",
  mse: "MSE",
  rmse: "RMSE",
  r2: "R²",
};

const SPLIT_LABELS: Record<string, string> = {
  cross_validation_metrics: "Cross-validation",
  validation_metrics: "Validation",
  test_metrics: "Test",
};

const isActive = (s: string) => s === "queued" || s === "running";

function fmt(value: number | undefined): string {
  return typeof value === "number" ? value.toFixed(4) : "—";
}

function MetricGrid({ metrics, highlight }: { metrics: Record<string, number>; highlight?: boolean }) {
  const entries = Object.entries(metrics).filter(([, v]) => typeof v === "number");
  if (entries.length === 0) return <p className="text-xs text-surface-500">No metrics recorded.</p>;
  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
      {entries.map(([key, value]) => (
        <div key={key} className={`rounded border p-3 ${highlight ? "border-accent-500/40 bg-accent-500/5" : "border-surface-700 bg-surface-950/60"}`}>
          <div className="text-[11px] uppercase tracking-wide text-surface-400">{METRIC_LABELS[key] ?? key}</div>
          <div className="mt-1 font-mono text-lg tabular-nums text-ivory-50">{fmt(value)}</div>
        </div>
      ))}
    </div>
  );
}

function ComparisonTable({ models, taskType }: { models: ModelEvaluationResult[]; taskType: string }) {
  const metricKeys = Array.from(
    new Set(models.flatMap((m) => Object.keys(m.validation_metrics))),
  ).filter((k) => typeof models.find((m) => m.validation_metrics[k] !== undefined)?.validation_metrics[k] === "number");

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[40rem] text-sm">
        <thead>
          <tr className="border-b border-surface-700 text-left text-[11px] uppercase tracking-wide text-surface-400">
            <th className="py-2 pr-4 font-medium">Model</th>
            <th className="py-2 pr-4 font-medium">Status</th>
            {metricKeys.map((k) => (
              <th key={k} className="py-2 pr-4 text-right font-medium">{METRIC_LABELS[k] ?? k} (val)</th>
            ))}
            {taskType === "regression" && (
              <th className="py-2 pr-4 text-right font-medium">R² (test)</th>
            )}
            {taskType === "classification" && (
              <th className="py-2 text-right font-medium">ROC-AUC (val)</th>
            )}
          </tr>
        </thead>
        <tbody>
          {models.map((m) => (
            <tr key={m.model_name} className={`border-b border-surface-800 ${m.is_selected ? "bg-accent-500/5" : ""}`}>
              <td className="py-2.5 pr-4">
                <span className="text-ivory-100">{m.model_name}</span>
                {m.is_selected && <span className="ml-2 text-[10px] font-semibold uppercase tracking-wide text-accent-400">selected</span>}
              </td>
              <td className="py-2.5 pr-4">
                <Badge tone={m.status === "completed" ? "live" : "soon"}>{m.status}</Badge>
              </td>
              {metricKeys.map((k) => (
                <td key={k} className="py-2.5 pr-4 text-right font-mono tabular-nums text-ivory-200">
                  {fmt(m.validation_metrics[k])}
                </td>
              ))}
              {taskType === "regression" && (
                <td className="py-2.5 pr-4 text-right font-mono tabular-nums text-ivory-200">{fmt(m.test_metrics.r2)}</td>
              )}
              {taskType === "classification" && (
                <td className="py-2.5 text-right font-mono tabular-nums text-ivory-200">{fmt(m.validation_metrics.roc_auc)}</td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ConfusionMatrix({ cm }: { cm: { labels: string[]; matrix: number[][] } }) {
  return (
    <div className="overflow-x-auto">
      <table className="text-xs">
        <thead>
          <tr>
            <th className="p-1 text-left text-surface-400">true \ pred</th>
            {cm.labels.map((l) => <th key={l} className="p-1 text-accent-300">{l}</th>)}
          </tr>
        </thead>
        <tbody>
          {cm.matrix.map((row, i) => (
            <tr key={cm.labels[i]}>
              <td className="p-1 pr-3 text-surface-400">{cm.labels[i]}</td>
              {row.map((v, j) => (
                <td key={j} className={`p-1 text-center font-mono tabular-nums ${i === j ? "text-accent-300" : "text-ivory-200"}`}>{v}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ClassificationReport({ report }: { report: ModelEvaluationResult["classification_report"] }) {
  if (!report) return null;
  const classes = Object.entries(report).filter(
    ([k, v]) => !["accuracy", "macro avg", "weighted avg"].includes(k) && typeof v === "object" && v !== null,
  );
  if (classes.length === 0) return null;
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="border-b border-surface-700 text-left text-[10px] uppercase tracking-wide text-surface-400">
          <th className="py-1.5 pr-3 font-medium">Class</th>
          <th className="py-1.5 pr-3 text-right font-medium">Precision</th>
          <th className="py-1.5 pr-3 text-right font-medium">Recall</th>
          <th className="py-1.5 pr-3 text-right font-medium">F1</th>
          <th className="py-1.5 text-right font-medium">Support</th>
        </tr>
      </thead>
      <tbody>
        {classes.map(([name, v]) => {
          const r = v as { precision: number; recall: number; "f1-score": number; support: number };
          return (
            <tr key={name} className="border-b border-surface-800">
              <td className="py-1.5 pr-3 text-ivory-200">{name}</td>
              <td className="py-1.5 pr-3 text-right font-mono tabular-nums">{fmt(r.precision)}</td>
              <td className="py-1.5 pr-3 text-right font-mono tabular-nums">{fmt(r.recall)}</td>
              <td className="py-1.5 pr-3 text-right font-mono tabular-nums">{fmt(r["f1-score"])}</td>
              <td className="py-1.5 text-right font-mono tabular-nums">{r.support}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export default function ExperimentDetail() {
  const { projectId, experimentId } = useParams<{ projectId: string; experimentId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [datasetName, setDatasetName] = useState<string | null>(null);
  const [experiment, setExperiment] = useState<Experiment | null>(null);
  const [evaluation, setEvaluation] = useState<ExperimentEvaluation | null>(null);
  const [repro, setRepro] = useState<ExperimentReproducibility | null>(null);
  const [artifact, setArtifact] = useState<ExperimentArtifact | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    if (!projectId || !experimentId) return;
    try {
      const [proj, exp, evaln, rep, art] = await Promise.all([
        getProject(projectId, signal),
        getExperiment(projectId, experimentId, signal),
        getExperimentEvaluation(projectId, experimentId, signal),
        getExperimentReproducibility(projectId, experimentId, signal),
        getExperimentArtifact(projectId, experimentId, signal),
      ]);
      setProject(proj);
      setExperiment(exp);
      setEvaluation(evaln);
      setRepro(rep);
      setArtifact(art);
      setStatus("ready");
      setError(null);
      if (exp.dataset_id) {
        getDataset(projectId, exp.dataset_id, signal)
          .then((d) => setDatasetName(d.name))
          .catch(() => undefined);
      }
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      setError(e instanceof ApiError ? e.message : "Could not load the experiment.");
      setStatus("error");
    }
  }, [projectId, experimentId]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  // Poll while the experiment is queued/running so status and results refresh.
  useEffect(() => {
    if (!experiment || !isActive(experiment.status)) return;
    const timer = setInterval(() => void load(), 3000);
    return () => clearInterval(timer);
  }, [experiment, load]);

  if (status === "loading") {
    return <div className="py-16 text-center"><Spinner className="h-6 w-6" label="Loading experiment…" /></div>;
  }
  if (status === "error" || !experiment || !evaluation) {
    return <ErrorBanner message={error ?? "Experiment not found."} onRetry={() => void load()} />;
  }

  const best = evaluation.models.find((m) => m.is_selected) ?? null;
  const completedModels = evaluation.models.filter((m) => m.status === "completed");
  const failedModels = evaluation.models.filter((m) => m.status === "failed");
  const bestValidation = best?.validation_metrics ?? {};
  const headlineMetrics = experiment.task_type === "classification"
    ? ["accuracy", "f1_macro", "precision_macro", "recall_macro", "roc_auc"]
    : ["mae", "rmse", "mse", "r2"];

  return (
    <>
      <PageHeader
        title={experiment.name}
        subtitle={
          <>
            <Link to={`/app/projects/${projectId}/experiments`} className="text-accent-400 hover:text-accent-300">Experiments</Link>
            {" / "}{project?.name ?? "Project"} / {datasetName ?? "dataset"}
          </>
        }
        actions={
          <div className="flex items-center gap-3">
            {experiment.status === "completed" && experiment.artifact_uri && (
              <Link to={`/app/projects/${projectId}/experiments/${experiment.id}/what-if`}
                className="rounded border border-chartreuse-500/50 px-3 py-1.5 text-xs font-medium text-chartreuse-300 hover:bg-chartreuse-500/10">
                What-If
              </Link>
            )}
            <Badge tone={experiment.status === "completed" ? "live" : "soon"}>{experiment.status}</Badge>
          </div>
        }
      />

      {experiment.error && (
        <div className="mb-6 rounded border border-danger-500/40 bg-danger-500/10 p-4 text-sm text-red-200">
          <span className="font-medium">Training failed: </span>{experiment.error}
        </div>
      )}

      {isActive(experiment.status) && (
        <Card className="mb-6 flex items-center gap-3 p-4">
          <Spinner className="h-4 w-4" />
          <p className="text-sm text-ivory-200">
            Experiment is <span className="font-medium text-accent-300">{experiment.status}</span>.
            Results will appear automatically when training finishes.
          </p>
        </Card>
      )}

      {/* A. Overview */}
      <Card className="mb-6 p-5">
        <h2 className="text-sm font-semibold text-ivory-100">Overview</h2>
        <dl className="mt-3 grid gap-x-8 gap-y-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div><dt className="text-xs text-surface-400">Experiment ID</dt><dd className="font-mono text-xs text-ivory-200">{experiment.id}</dd></div>
          <div><dt className="text-xs text-surface-400">Task</dt><dd className="text-ivory-100">{experiment.task_type}</dd></div>
          <div><dt className="text-xs text-surface-400">Target column</dt><dd className="text-ivory-100">{experiment.target_column}</dd></div>
          <div><dt className="text-xs text-surface-400">Created</dt><dd className="text-ivory-100">{new Date(experiment.created_at).toLocaleString()}</dd></div>
          <div><dt className="text-xs text-surface-400">Dataset</dt><dd className="text-ivory-100">{datasetName ?? (experiment.dataset_id ? experiment.dataset_id : "Deleted dataset")}</dd></div>
          <div><dt className="text-xs text-surface-400">Best model</dt><dd className="text-accent-300">{best?.model_name ?? "—"}</dd></div>
          <div><dt className="text-xs text-surface-400">Models trained</dt><dd className="text-ivory-100">{completedModels.length} of {evaluation.models.length}</dd></div>
          <div><dt className="text-xs text-surface-400">Artifact</dt><dd className="text-ivory-100">{artifact?.available ? "Stored" : "Not available"}</dd></div>
        </dl>
      </Card>

      {/* B. Performance overview (best model) */}
      {best && (
        <Card className="mb-6 p-5">
          <h2 className="text-sm font-semibold text-ivory-100">Performance — {best.model_name} <span className="text-xs font-normal text-surface-400">(validation split)</span></h2>
          <div className="mt-4">
            <MetricGrid
              metrics={Object.fromEntries(headlineMetrics.filter((k) => bestValidation[k] !== undefined).map((k) => [k, bestValidation[k]]))}
              highlight
            />
          </div>
        </Card>
      )}

      {/* C. Model comparison */}
      <Card className="mb-6 p-5">
        <h2 className="text-sm font-semibold text-ivory-100">Model comparison</h2>
        <p className="mt-1 text-xs text-surface-400">
          Validation-split metrics (model selection uses validation only; test metrics are reported separately below).
          Classification: accuracy = correct rate; precision = correctness of positive calls; recall = coverage of actual positives; F1 = harmonic mean of precision/recall; ROC-AUC = ranking quality (0.5 = random).
          Regression: MAE = mean absolute error; MSE = mean squared error; RMSE = MAE in original units; R² = variance explained (negative R² means worse than predicting the mean — a warning, not an error).
        </p>
        {evaluation.models.length === 0 ? (
          <p className="mt-4 text-sm text-surface-400">No per-model results recorded for this experiment.</p>
        ) : (
          <div className="mt-4">
            <ComparisonTable models={evaluation.models} taskType={experiment.task_type} />
          </div>
        )}
        {evaluation.models.some((m) => m.training_duration_ms != null || m.best_params) && (
          <div className="mt-4 space-y-1 text-xs text-surface-400">
            {evaluation.models.map((m) => (
              <div key={m.model_name} className="flex flex-wrap items-baseline gap-x-3">
                <span className="font-medium text-ivory-200">{m.model_name}</span>
                {m.training_duration_ms != null && <span>trained in {(m.training_duration_ms / 1000).toFixed(1)}s</span>}
                {m.best_params && <span className="font-mono">params: {JSON.stringify(m.best_params)}</span>}
              </div>
            ))}
          </div>
        )}
        {failedModels.length > 0 && (
          <div className="mt-4 space-y-2">
            {failedModels.map((m) => (
              <div key={m.model_name} className="rounded border border-danger-500/30 bg-danger-500/5 p-3 text-xs text-red-200">
                <span className="font-medium">{m.model_name} failed: </span>{m.error ?? "unknown error"}
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* D/E. Task-specific evaluation detail (selected model) */}
      {best && experiment.task_type === "classification" && best.confusion_matrix && (
        <Card className="mb-6 p-5">
          <h2 className="text-sm font-semibold text-ivory-100">Classification evaluation — {best.model_name}</h2>
          <p className="mt-1 text-xs text-surface-400">Validation split. Per-class metrics below.</p>
          <div className="mt-4 grid gap-6 lg:grid-cols-2">
            <div>
              <h3 className="text-xs font-medium uppercase tracking-wide text-surface-400">Confusion matrix</h3>
              <div className="mt-2"><ConfusionMatrix cm={best.confusion_matrix} /></div>
            </div>
            <div>
              <h3 className="text-xs font-medium uppercase tracking-wide text-surface-400">Per-class report</h3>
              <div className="mt-2"><ClassificationReport report={best.classification_report} /></div>
            </div>
          </div>
        </Card>
      )}

      {best && experiment.task_type === "regression" && (
        <Card className="mb-6 p-5">
          <h2 className="text-sm font-semibold text-ivory-100">Regression evaluation — {best.model_name}</h2>
          <div className="mt-4 space-y-4">
            {(["validation_metrics", "test_metrics", "cross_validation_metrics"] as const).map((split) => (
              <div key={split}>
                <h3 className="text-xs font-medium uppercase tracking-wide text-surface-400">{SPLIT_LABELS[split]}</h3>
                <div className="mt-2"><MetricGrid metrics={best[split]} /></div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* F. Reproducibility */}
      {repro && (
        <Card className="mb-6 p-5">
          <h2 className="text-sm font-semibold text-ivory-100">Reproducibility</h2>
          <dl className="mt-3 grid gap-x-8 gap-y-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
            <div><dt className="text-xs text-surface-400">Random seed</dt><dd className="font-mono text-ivory-100">{repro.random_seed}</dd></div>
            <div><dt className="text-xs text-surface-400">Split (train/val/test)</dt><dd className="font-mono text-ivory-100">{repro.train_fraction} / {repro.validation_fraction} / {repro.test_fraction}</dd></div>
            <div><dt className="text-xs text-surface-400">Dataset SHA-256</dt><dd className="break-all font-mono text-xs text-ivory-200">{repro.dataset_sha256 ?? "—"}</dd></div>
            <div><dt className="text-xs text-surface-400">Dataset version</dt><dd className="font-mono text-xs text-ivory-200">{repro.dataset_version_id}</dd></div>
            <div><dt className="text-xs text-surface-400">Preprocessing</dt><dd className="text-ivory-100">numeric: median+standard · categorical: mode+one-hot · fit on train only</dd></div>
            <div><dt className="text-xs text-surface-400">Manifest</dt><dd className="text-ivory-100">{repro.manifest_available ? "Verified" : "Unavailable"}</dd></div>
          </dl>
          <details className="mt-4">
            <summary className="cursor-pointer text-xs font-medium text-accent-400 hover:text-accent-300">Model configuration</summary>
            <pre className="mt-2 overflow-x-auto rounded bg-surface-950 p-3 text-[11px] text-ivory-200">{JSON.stringify(repro.model_configs, null, 2)}</pre>
          </details>
        </Card>
      )}

      {/* G. Empty evaluation state */}
      {experiment.status === "completed" && evaluation.models.length === 0 && (
        <EmptyState icon="flask" title="No evaluation results">
          This experiment completed but has no persisted per-model results. It may predate per-model result tracking.
        </EmptyState>
      )}
    </>
  );
}
