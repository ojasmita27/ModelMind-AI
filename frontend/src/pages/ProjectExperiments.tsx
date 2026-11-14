import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { listDatasets, getDataset, getDatasetPreview, getDatasetProfile } from "../api/datasets";
import { createExperiment, listExperiments } from "../api/experiments";
import type { ColumnProfile, Dataset, DatasetVersion, Experiment, Project } from "../api/types";
import { getProject } from "../api/projects";
import { Badge, Button, Card, ErrorBanner, PageHeader, Spinner } from "../components/ui/primitives";
import { useToast } from "../components/ui/Toast";

const MODEL_OPTIONS: Record<"classification" | "regression", string[]> = {
  classification: ["Logistic Regression", "Random Forest", "Gradient Boosting", "Naive Bayes"],
  regression: ["Linear Regression", "Random Forest", "Gradient Boosting"],
};

const metricLabelMap: Record<string, string> = {
  accuracy: "Accuracy",
  f1_macro: "F1 Macro",
  f1_weighted: "F1 Weighted",
  precision_macro: "Precision Macro",
  recall_macro: "Recall Macro",
  roc_auc: "ROC AUC",
  mse: "MSE",
  mae: "MAE",
  rmse: "RMSE",
  r2: "R²",
};

export default function ProjectExperiments() {
  const { projectId } = useParams<{ projectId: string }>();
  const { notify } = useToast();
  const [project, setProject] = useState<Project | null>(null);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [datasetVersions, setDatasetVersions] = useState<Record<string, DatasetVersion[]>>({});
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>("");
  const [selectedVersionId, setSelectedVersionId] = useState<string>("");
  const [taskType, setTaskType] = useState<"classification" | "regression">("classification");
  const [targetColumn, setTargetColumn] = useState("");
  const [availableColumns, setAvailableColumns] = useState<string[]>([]);
  const [columnProfiles, setColumnProfiles] = useState<ColumnProfile[]>([]);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [modelNames, setModelNames] = useState<string[]>([MODEL_OPTIONS.classification[0]]);
  const [trainFraction, setTrainFraction] = useState(0.7);
  const [validationFraction, setValidationFraction] = useState(0.15);
  const [testFraction, setTestFraction] = useState(0.15);
  const [randomSeed, setRandomSeed] = useState(42);
  const [tuningEnabled, setTuningEnabled] = useState(false);
  const [tuningIters, setTuningIters] = useState(5);
  const [name, setName] = useState("Baseline model");

  const selectedVersion = useMemo(
    () => (selectedVersionId ? (datasetVersions[selectedDatasetId] ?? []).find((v) => v.id === selectedVersionId) ?? null : null),
    [datasetVersions, selectedDatasetId, selectedVersionId],
  );

  const loadData = useCallback(async (signal?: AbortSignal) => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const [projectData, datasetList, experimentList] = await Promise.all([
        getProject(projectId, signal),
        listDatasets(projectId, signal),
        listExperiments(projectId, signal),
      ]);

      if (signal?.aborted) return;
      setProject(projectData);
      setDatasets(datasetList);
      setExperiments(experimentList);

      if (datasetList.length > 0) {
        const firstId = datasetList[0].id;
        setSelectedDatasetId(firstId);
        const detail = await getDataset(projectId, firstId, signal);
        if (signal?.aborted) return;
        const versions = detail.versions ?? [];
        setDatasetVersions((prev) => ({ ...prev, [firstId]: versions }));
        if (versions.length > 0) {
          setSelectedVersionId(versions[0].id);
        }
      }
    } catch (e) {
      if (signal?.aborted) return;
      setError(e instanceof ApiError ? e.message : "Could not load the experiment studio.");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    const controller = new AbortController();
    void loadData(controller.signal);
    return () => controller.abort();
  }, [loadData]);

  useEffect(() => {
    const options = MODEL_OPTIONS[taskType];
    setModelNames((current) => {
      const valid = options.filter((opt) => current.includes(opt));
      return valid.length > 0 ? valid : [options[0]];
    });
  }, [taskType]);

  useEffect(() => {
    if (!selectedDatasetId || !projectId) return;
    const controller = new AbortController();
    void getDataset(projectId, selectedDatasetId, controller.signal)
      .then((detail) => {
        if (controller.signal.aborted) return;
        setDatasetVersions((prev) => ({ ...prev, [selectedDatasetId]: detail.versions }));
        const nextVersion = detail.versions[0] ?? null;
        // Always select the newest version of THIS dataset — never keep a
        // stale version id from a previously selected dataset.
        setSelectedVersionId(nextVersion?.id ?? "");
      })
      .catch(() => {
        if (!controller.signal.aborted) setDatasetVersions((prev) => ({ ...prev, [selectedDatasetId]: [] }));
      });

    return () => controller.abort();
  }, [projectId, selectedDatasetId]);

  useEffect(() => {
    if (!projectId || !selectedDatasetId || !selectedVersion || !selectedVersion.file_path) return;
    setName(`${project?.name ?? "Model"} ${taskType} run`);
    setTargetColumn("");
    setAvailableColumns([]);
    setColumnProfiles([]);
    if (!selectedVersionId) return;

    const loadPreview = async (signal?: AbortSignal) => {
      try {
        const [preview, profile] = await Promise.all([
          getDatasetPreview(projectId, selectedDatasetId, 10, signal),
          getDatasetProfile(projectId, selectedDatasetId, signal),
        ]);
        if (signal?.aborted) return;
        setAvailableColumns(preview.columns ?? []);
        setColumnProfiles(profile.columns ?? []);
        setPreviewError(null);
      } catch (e) {
        if (signal?.aborted) return;
        setAvailableColumns([]);
        setColumnProfiles([]);
        setPreviewError(e instanceof ApiError ? e.message : "Could not load dataset preview.");
      }
    };

    const controller = new AbortController();
    void loadPreview(controller.signal);
    return () => controller.abort();
  }, [projectId, selectedDatasetId, selectedVersion, selectedVersionId, taskType, project?.name]);

  const suggestedTargetOptions = useMemo(() => {
    const candidateProfiles = columnProfiles.filter((column) => {
      if (!column.name || column.name === "id") return false;
      // Backend profiler types: "numeric" | "categorical" | "datetime" | "text".
      // Keep the legacy dtype-name checks as a fallback for older payloads.
      const type = column.type.toLowerCase();
      const isNumeric = type === "numeric"
        || type.includes("int") || type.includes("float") || type.includes("number") || type.includes("double") || type.includes("decimal");
      const isDiscrete = type === "categorical" || type === "datetime"
        || type.includes("bool") || type.includes("string") || type.includes("category") || type.includes("object");
      if (taskType === "classification") {
        const shouldSuggest = (isDiscrete && column.unique_count <= 12) || (!isNumeric && column.unique_count <= 12) || (isNumeric && column.unique_count > 1 && column.unique_count <= 12);
        return shouldSuggest && column.missing_percentage < 0.5;
      }
      return isNumeric && column.unique_count > 2 && column.missing_percentage < 0.5;
    });

    return candidateProfiles
      .sort((left, right) => {
        const leftScore = (right.unique_count - left.unique_count) + (left.missing_percentage === 0 ? 2 : 0);
        const rightScore = (left.unique_count - right.unique_count) + (right.missing_percentage === 0 ? 2 : 0);
        return leftScore - rightScore;
      })
      .slice(0, 3)
      .map((column) => column.name);
  }, [columnProfiles, taskType]);

  const datasetOptions = datasets;
  const versionOptions = selectedDatasetId ? datasetVersions[selectedDatasetId] ?? [] : [];
  const targetSelectionAmbiguous = suggestedTargetOptions.length > 1 && !targetColumn;

  // Minimal status polling: while any experiment is queued/running or any
  // dataset version is still being profiled, refresh those lists so the UI
  // reflects background job progress without a manual reload.
  const hasActiveWork =
    experiments.some((e) => e.status === "queued" || e.status === "running") ||
    versionOptions.some((v) => v.job_status === "pending" || v.job_status === "processing");

  useEffect(() => {
    if (!projectId || !hasActiveWork) return;
    const timer = setInterval(() => {
      void listExperiments(projectId)
        .then(setExperiments)
        .catch(() => undefined);
      if (selectedDatasetId) {
        void getDataset(projectId, selectedDatasetId)
          .then((detail) => {
            setDatasetVersions((prev) => ({ ...prev, [selectedDatasetId]: detail.versions }));
          })
          .catch(() => undefined);
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [projectId, hasActiveWork, selectedDatasetId]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!projectId || !selectedDatasetId || !selectedVersionId || !targetColumn) {
      notify("error", "Select a dataset version and target column before running an experiment.");
      return;
    }

    setSaving(true);
    try {
      const created = await createExperiment(projectId, {
        name: name.trim() || `${project?.name ?? "Model"} ${taskType} run`,
        dataset_id: selectedDatasetId,
        dataset_version_id: selectedVersionId,
        task_type: taskType,
        target_column: targetColumn,
        train_fraction: trainFraction,
        validation_fraction: validationFraction,
        test_fraction: testFraction,
        random_seed: randomSeed,
        model_names: modelNames,
        tuning: tuningEnabled ? { enabled: true, n_iter: tuningIters, cv: 3 } : undefined,
      });
      setExperiments((prev) => [created, ...prev]);
      notify("success", `Experiment “${created.name}” started.`);
      setName(`${project?.name ?? "Model"} ${taskType} run`);
      setTaskType("classification");
      setModelNames([MODEL_OPTIONS.classification[0]]);
      setTrainFraction(0.7);
      setValidationFraction(0.15);
      setTestFraction(0.15);
      setRandomSeed(42);
      setTuningEnabled(false);
      setTuningIters(5);
    } catch (e) {
      notify("error", e instanceof ApiError ? e.message : "Experiment could not be created.");
    } finally {
      setSaving(false);
    }
  }

  function toggleModel(model: string) {
    setModelNames((current) => {
      if (current.includes(model)) return current.filter((item) => item !== model);
      return [...current, model];
    });
  }

  if (loading) {
    return <div className="py-16 text-center"><Spinner className="h-6 w-6" label="Preparing experiment studio…" /></div>;
  }

  if (error || !project) {
    return <ErrorBanner message={error ?? "Could not load this project."} onRetry={() => void loadData()} />;
  }

  return (
    <>
      <p className="mb-3 text-sm"><Link to={`/app/projects/${projectId}`} className="text-ivory-300 hover:text-ivory-50">&larr; Project overview</Link></p>
      <PageHeader title="ML Experiment Studio" subtitle={`${project.name} • dataset lineage and training orchestration`} />

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <form onSubmit={onSubmit} className="space-y-5">
          <Card className="p-5">
            <div className="mb-4 flex items-center justify-between gap-2">
              <h2 className="text-sm font-semibold text-ivory-100">Run configuration</h2>
              <Badge tone="live">Connected</Badge>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <label className="space-y-2 text-sm text-ivory-200 md:col-span-2">
                <span>Experiment name</span>
                <input value={name} onChange={(e) => setName(e.target.value)} className="w-full rounded-lg border border-surface-600 bg-surface-900 px-3 py-2 text-ivory-50" placeholder="Baseline model" />
              </label>

              <label className="space-y-2 text-sm text-ivory-200">
                <span>Dataset</span>
                <select value={selectedDatasetId} onChange={(e) => setSelectedDatasetId(e.target.value)} className="w-full rounded-lg border border-surface-600 bg-surface-900 px-3 py-2 text-ivory-50">
                  {datasetOptions.length === 0 && <option value="">No datasets</option>}
                  {datasetOptions.map((dataset) => (
                    <option key={dataset.id} value={dataset.id}>{dataset.name}</option>
                  ))}
                </select>
              </label>

              <label className="space-y-2 text-sm text-ivory-200">
                <span>Dataset version</span>
                <select value={selectedVersionId} onChange={(e) => setSelectedVersionId(e.target.value)} className="w-full rounded-lg border border-surface-600 bg-surface-900 px-3 py-2 text-ivory-50" disabled={!versionOptions.length}>
                  {!versionOptions.length && <option value="">No versions</option>}
                  {versionOptions.map((version) => (
                    <option key={version.id} value={version.id}>Version {version.version_number}</option>
                  ))}
                </select>
              </label>

              <label className="space-y-2 text-sm text-ivory-200">
                <span>Task</span>
                <select value={taskType} onChange={(e) => setTaskType(e.target.value as "classification" | "regression")} className="w-full rounded-lg border border-surface-600 bg-surface-900 px-3 py-2 text-ivory-50">
                  <option value="classification">Classification</option>
                  <option value="regression">Regression</option>
                </select>
              </label>

              <label className="space-y-2 text-sm text-ivory-200">
                <span>Target column</span>
                <select
                  value={targetColumn}
                  onChange={(e) => setTargetColumn(e.target.value)}
                  className="w-full rounded-lg border border-surface-600 bg-surface-900 px-3 py-2 text-ivory-50"
                  disabled={!availableColumns.length}
                  aria-label="Target column"
                >
                  <option value="">{availableColumns.length ? "Choose a target column" : previewError ? "Preview unavailable" : "Waiting for dataset preview…"}</option>
                  {availableColumns.map((column) => (
                    <option key={column} value={column}>{column}</option>
                  ))}
                </select>
                {targetSelectionAmbiguous && (
                  <p className="text-xs text-amber-200">Multiple columns look suitable. Select the outcome column manually before running the experiment.</p>
                )}
                {previewError && <p className="text-xs text-red-200">{previewError}</p>}
              </label>

              <div className="md:col-span-2 space-y-3">
                <div className="text-xs uppercase tracking-wide text-surface-400">Suggested targets</div>
                <div className="flex flex-wrap gap-2">
                  {suggestedTargetOptions.length > 0 ? (
                    suggestedTargetOptions.map((column) => (
                      <button
                        key={column}
                        type="button"
                        onClick={() => setTargetColumn(column)}
                        className={`rounded-full border px-2.5 py-1 text-xs ${targetColumn === column ? "border-accent-400 bg-accent-500/15 text-accent-300" : "border-surface-600 bg-surface-900 text-ivory-300 hover:border-surface-500"}`}
                      >
                        {column}
                      </button>
                    ))
                  ) : (
                    <span className="text-xs text-surface-400">No target suggestions. Choose a column manually.</span>
                  )}
                </div>

                <div className="space-y-2 rounded border border-surface-700 bg-surface-900/50 p-3">
                  {columnProfiles.length === 0 && <p className="text-xs text-surface-400">Column metadata will appear once the dataset profile is ready.</p>}
                  {columnProfiles.map((column) => (
                    <button
                      key={column.name}
                      type="button"
                      onClick={() => setTargetColumn(column.name)}
                      className={`flex w-full items-center justify-between gap-2 rounded border px-2 py-2 text-left transition ${targetColumn === column.name ? "border-accent-400 bg-accent-500/10" : "border-surface-700 bg-surface-950/40 hover:border-surface-500"}`}
                    >
                      <div>
                        <div className="text-sm font-medium text-ivory-100">{column.name}</div>
                        <div className="text-[11px] text-surface-400">{column.type}</div>
                      </div>
                      <div className="text-right text-[11px] text-surface-400">
                        <div>{column.unique_count} unique</div>
                        <div>{column.missing_count} missing</div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              <div className="md:col-span-2">
                <div className="mb-2 text-sm text-ivory-200">Model selection</div>
                <div className="flex flex-wrap gap-2">
                  {MODEL_OPTIONS[taskType].map((model) => {
                    const active = modelNames.includes(model);
                    return (
                      <button type="button" key={model} onClick={() => toggleModel(model)} className={`rounded-full border px-3 py-1.5 text-sm transition ${active ? "border-accent-400 bg-accent-500/15 text-accent-300" : "border-surface-600 bg-surface-900 text-ivory-300 hover:border-surface-500"}`}>
                        {model}
                      </button>
                    );
                  })}
                </div>
              </div>

              <label className="space-y-2 text-sm text-ivory-200">
                <span>Train split</span>
                <input type="number" min={0.1} max={0.9} step={0.05} value={trainFraction} onChange={(e) => setTrainFraction(Number(e.target.value))} className="w-full rounded-lg border border-surface-600 bg-surface-900 px-3 py-2 text-ivory-50" />
              </label>

              <label className="space-y-2 text-sm text-ivory-200">
                <span>Validation split</span>
                <input type="number" min={0.05} max={0.4} step={0.05} value={validationFraction} onChange={(e) => setValidationFraction(Number(e.target.value))} className="w-full rounded-lg border border-surface-600 bg-surface-900 px-3 py-2 text-ivory-50" />
              </label>

              <label className="space-y-2 text-sm text-ivory-200">
                <span>Test split</span>
                <input type="number" min={0.1} max={0.5} step={0.05} value={testFraction} onChange={(e) => setTestFraction(Number(e.target.value))} className="w-full rounded-lg border border-surface-600 bg-surface-900 px-3 py-2 text-ivory-50" />
              </label>

              <label className="space-y-2 text-sm text-ivory-200">
                <span>Random seed</span>
                <input type="number" min={0} step={1} value={randomSeed} onChange={(e) => setRandomSeed(Number(e.target.value))} className="w-full rounded-lg border border-surface-600 bg-surface-900 px-3 py-2 text-ivory-50" />
              </label>

              <label className="flex items-center gap-2 pt-6 text-sm text-ivory-200">
                <input type="checkbox" checked={tuningEnabled} onChange={(e) => setTuningEnabled(e.target.checked)} className="accent-chartreuse-500" />
                Hyperparameter search (randomized)
              </label>
              {tuningEnabled && (
                <label className="space-y-2 text-sm text-ivory-200">
                  <span>Search iterations per model</span>
                  <input type="number" min={1} max={25} step={1} value={tuningIters} onChange={(e) => setTuningIters(Math.max(1, Math.min(25, Number(e.target.value) || 5)))} className="w-full rounded-lg border border-surface-600 bg-surface-900 px-3 py-2 text-ivory-50" />
                </label>
              )}
            </div>

            <div className="mt-5 flex items-center justify-between gap-3 border-t border-surface-700 pt-4">
              <div className="text-xs uppercase tracking-wide text-surface-400">Dataset version: {selectedVersion ? `#${selectedVersion.version_number}` : "Not selected"}</div>
              <Button type="submit" loading={saving} icon="flask">Run experiment</Button>
            </div>
          </Card>
        </form>

        <Card className="p-5">
          <div className="mb-4 flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-ivory-100">Run history</h2>
            <Badge tone={experiments.length > 0 ? "live" : "soon"}>{experiments.length}</Badge>
          </div>

          <div className="space-y-3">
            {experiments.length === 0 && <div className="rounded border border-dashed border-surface-600 p-4 text-sm text-surface-400">No experiment runs yet.</div>}
            {experiments.map((experiment) => {
              const bestMetrics = ((experiment.metrics ?? {}) as Record<string, unknown>).best_metrics as Record<string, unknown> | undefined;
              const validationMetrics = ((experiment.metrics ?? {}) as Record<string, unknown>).validation_metrics as Record<string, unknown> | undefined;
              const sourceMetrics = bestMetrics ?? validationMetrics ?? {};
              const metricEntries = Object.entries(sourceMetrics).filter(([, value]) => typeof value === "number");

              return (
                <div key={experiment.id} className="rounded border border-surface-700 bg-surface-900/60 p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="font-medium text-ivory-100">{experiment.name}</div>
                      <div className="mt-1 text-[10px] uppercase tracking-wide text-surface-400">{experiment.task_type} • {experiment.target_column}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge tone={experiment.status === "completed" ? "live" : "soon"}>{experiment.status}</Badge>
                      <Link to={`/app/projects/${projectId}/experiments/${experiment.id}`} className="text-xs font-medium text-accent-400 hover:text-accent-300">Details</Link>
                    </div>
                  </div>

                  <div className="mt-3 text-[11px] text-surface-400">
                    <div>Dataset version: #{(versionOptions.find((v) => v.id === experiment.dataset_version_id)?.version_number) ?? "?"}</div>
                    <div>{new Date(experiment.created_at).toLocaleString()}</div>
                  </div>

                  {experiment.error && <div className="mt-3 rounded border border-danger-500/40 bg-danger-500/10 p-2 text-xs text-red-200">{experiment.error}</div>}

                  {metricEntries.length > 0 && (
                    <div className="mt-3 space-y-1 text-xs text-ivory-200">
                      {metricEntries.slice(0, 4).map(([key, value]) => (
                        <div key={key} className="flex items-center justify-between gap-3 rounded bg-surface-950/60 px-2 py-1">
                          <span className="text-surface-400">{metricLabelMap[key] ?? key}</span>
                          <span className="font-medium text-accent-300">{Number(value).toFixed(3)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </Card>
      </div>
    </>
  );
}
