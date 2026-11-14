/** Honest feature roadmap. Every item here is NOT implemented yet and is labelled "Coming soon" in the UI. */
export interface RoadmapItem {
  slug: string;
  label: string;
  milestone: string;
  summary: string;
  willUse: string;
}

export const ROADMAP: RoadmapItem[] = [
  {
    slug: "datasets",
    label: "Datasets",
    milestone: "Milestones M2-M3",
    summary: "Upload CSV files with strict server-side validation, keep immutable dataset versions, and review automated data-quality profiling.",
    willUse: "Backend: /projects/{id}/datasets, dataset versions and profiling jobs (storage abstraction: local now, S3 later).",
  },
  {
    slug: "experiments",
    label: "Experiments",
    milestone: "Milestones M5-M8",
    summary: "Configure leakage-safe training, compare models on validation data, run one final test evaluation, and trace every result to its dataset version and configuration. Tracked in MLflow.",
    willUse: "Backend: experiment configuration, training worker, MLflow adapter. Every run stores its seed and dataset-version reference.",
  },
  {
    slug: "what-if",
    label: "What-If Lab",
    milestone: "Phase 2",
    summary: "Edit a record's feature values, compare original and modified predictions, and inspect SHAP explanations, without presenting predictions as causal claims.",
    willUse: "Reuses the saved model pipeline from the Experiments milestone.",
  },
  {
    slug: "datatwin",
    label: "DataTwin",
    milestone: "Phase 3",
    summary: "Stress-test a trained model with reproducible perturbations: missing values, noise, distribution shifts and schema changes.",
    willUse: "Reuses dataset versions and model runs; originals are never modified.",
  },
  {
    slug: "failure-intelligence",
    label: "Failure Intelligence",
    milestone: "Phase 4",
    summary: "Segment-level error analysis and evidence-based hypotheses about where and why a model underperforms.",
    willUse: "Builds on stress-test results and test evaluations; separates measured degradation from data drift.",
  },
];
