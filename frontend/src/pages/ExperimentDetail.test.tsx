import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ME, mockApi, project, renderApp, signIn } from "../test/utils";

const EXP_ID = "e1";

const experiment = (status: string, extra: Record<string, unknown> = {}) => ({
  id: EXP_ID,
  project_id: "p1",
  dataset_id: "d1",
  dataset_version_id: "v1",
  name: "Churn model",
  task_type: "classification",
  target_column: "churned",
  train_fraction: 0.7,
  validation_fraction: 0.15,
  test_fraction: 0.15,
  random_seed: 42,
  model_names: ["Logistic Regression", "Random Forest"],
  status,
  error: null,
  metrics: {},
  artifact_uri: null,
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-02T00:00:00Z",
  started_at: null,
  completed_at: null,
  ...extra,
});

const completedExperiment = experiment("completed", {
  metrics: { best_model_name: "Random Forest" },
  artifact_uri: "local://experiments/e1/model.joblib",
  completed_at: "2026-10-02T00:05:00Z",
});

const classificationEvaluation = {
  experiment_id: EXP_ID,
  status: "completed",
  task_type: "classification",
  target_column: "churned",
  best_model_name: "Random Forest",
  models: [
    {
      model_name: "Logistic Regression",
      task_type: "classification",
      is_selected: false,
      status: "completed",
      error: null,
      cross_validation_metrics: { accuracy: 0.8 },
      validation_metrics: { accuracy: 0.82, f1_macro: 0.79, precision_macro: 0.8, recall_macro: 0.78, roc_auc: 0.85 },
      test_metrics: { accuracy: 0.81 },
      confusion_matrix: { labels: ["no", "yes"], matrix: [[30, 4], [5, 21]] },
      classification_report: {
        "no": { precision: 0.86, recall: 0.88, "f1-score": 0.87, support: 34 },
        "yes": { precision: 0.84, recall: 0.81, "f1-score": 0.83, support: 26 },
        accuracy: 0.85,
        "macro avg": { precision: 0.85, recall: 0.85, "f1-score": 0.85, support: 60 },
      },
    },
    {
      model_name: "Random Forest",
      task_type: "classification",
      is_selected: true,
      status: "completed",
      error: null,
      cross_validation_metrics: { accuracy: 0.85 },
      validation_metrics: { accuracy: 0.88, f1_macro: 0.86, precision_macro: 0.87, recall_macro: 0.85, roc_auc: 0.91 },
      test_metrics: { accuracy: 0.87 },
      confusion_matrix: { labels: ["no", "yes"], matrix: [[31, 3], [4, 22]] },
      classification_report: {
        "no": { precision: 0.89, recall: 0.91, "f1-score": 0.9, support: 34 },
        "yes": { precision: 0.88, recall: 0.85, "f1-score": 0.86, support: 26 },
        accuracy: 0.88,
        "macro avg": { precision: 0.88, recall: 0.88, "f1-score": 0.88, support: 60 },
      },
    },
  ],
};

const regressionEvaluation = {
  ...classificationEvaluation,
  task_type: "regression",
  target_column: "price",
  best_model_name: "Random Forest",
  models: [
    {
      ...classificationEvaluation.models[0],
      task_type: "regression",
      is_selected: false,
      validation_metrics: { mae: 12000, mse: 3.2e8, rmse: 17888, r2: 0.71 },
      test_metrics: { mae: 11500, mse: 3.0e8, rmse: 17320, r2: 0.74 },
      confusion_matrix: null,
      classification_report: null,
    },
    {
      ...classificationEvaluation.models[1],
      task_type: "regression",
      is_selected: true,
      validation_metrics: { mae: 9000, mse: 1.9e8, rmse: 13784, r2: 0.83 },
      test_metrics: { mae: 8800, mse: 1.8e8, rmse: 13416, r2: 0.85 },
      confusion_matrix: null,
      classification_report: null,
    },
  ],
};

const reproducibility = {
  experiment_id: EXP_ID,
  name: "Churn model",
  task_type: "classification",
  target_column: "churned",
  random_seed: 42,
  train_fraction: 0.7,
  validation_fraction: 0.15,
  test_fraction: 0.15,
  dataset_id: "d1",
  dataset_version_id: "v1",
  dataset_sha256: "abc123",
  model_names: ["Logistic Regression", "Random Forest"],
  model_configs: { "Random Forest": { estimator: "RandomForestClassifier", params: { n_estimators: 200 } } },
  preprocessing: { numeric: { imputer: "median" } },
  manifest: { experiment_id: EXP_ID },
  manifest_available: true,
};

const artifact = {
  experiment_id: EXP_ID,
  available: true,
  artifact_uri: "local://experiments/e1/model.joblib",
  model_file_size_bytes: 12345,
  manifest_verified: true,
  manifest_error: null,
};

function baseRoutes(overrides: Record<string, unknown> = {}) {
  return {
    "GET /api/v1/auth/me": { body: ME },
    "GET /api/v1/projects/p1": { body: project(1, { name: "Churn project" }) },
    "GET /api/v1/projects/p1/datasets/d1": {
      body: {
        id: "d1", project_id: "p1", name: "Customers", description: null,
        created_at: "2026-01-01T00:00:00Z",
        versions: [{ id: "v1", dataset_id: "d1", version_number: 1, job_status: "completed" }],
      },
    },
    [`GET /api/v1/projects/p1/experiments/${EXP_ID}`]: { body: completedExperiment },
    [`GET /api/v1/projects/p1/experiments/${EXP_ID}/evaluation`]: { body: classificationEvaluation },
    [`GET /api/v1/projects/p1/experiments/${EXP_ID}/reproducibility`]: { body: reproducibility },
    [`GET /api/v1/projects/p1/experiments/${EXP_ID}/artifact`]: { body: artifact },
    ...overrides,
  };
}

describe("ExperimentDetail", () => {
  it("renders overview, comparison table, confusion matrix and reproducibility", async () => {
    signIn();
    mockApi(baseRoutes());
    renderApp(`/app/projects/p1/experiments/${EXP_ID}`);

    expect(await screen.findByText("Churn model")).toBeInTheDocument();
    expect(screen.getAllByText("completed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Random Forest").length).toBeGreaterThan(0);
    // comparison table: both models, selected marker
    expect(screen.getByText("Logistic Regression")).toBeInTheDocument();
    expect(screen.getByText("selected")).toBeInTheDocument();
    // confusion matrix axis + per-class report
    expect(screen.getByText("Confusion matrix")).toBeInTheDocument();
    expect(screen.getByText("Per-class report")).toBeInTheDocument();
    expect(screen.getAllByText("yes").length).toBeGreaterThan(0);
    // reproducibility
    expect(screen.getByText("Random seed")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("abc123")).toBeInTheDocument();
  });

  it("shows in-progress state while the experiment is running", async () => {
    signIn();
    mockApi(baseRoutes({
      [`GET /api/v1/projects/p1/experiments/${EXP_ID}`]: { body: experiment("running") },
      [`GET /api/v1/projects/p1/experiments/${EXP_ID}/evaluation`]: {
        body: { ...classificationEvaluation, status: "running", models: [] },
      },
    }));
    renderApp(`/app/projects/p1/experiments/${EXP_ID}`);
    expect(await screen.findByText(/Experiment is/)).toBeInTheDocument();
    expect(screen.getAllByText("running").length).toBeGreaterThan(0);
  });

  it("shows failure state with persisted error", async () => {
    signIn();
    mockApi(baseRoutes({
      [`GET /api/v1/projects/p1/experiments/${EXP_ID}`]: {
        body: experiment("failed", { error: "Target column has only one class" }),
      },
      [`GET /api/v1/projects/p1/experiments/${EXP_ID}/evaluation`]: {
        body: { ...classificationEvaluation, status: "failed", models: [] },
      },
    }));
    renderApp(`/app/projects/p1/experiments/${EXP_ID}`);
    expect(await screen.findByText(/Training failed/)).toBeInTheDocument();
    expect(screen.getByText(/Target column has only one class/)).toBeInTheDocument();
    expect(screen.getByText("No per-model results recorded for this experiment.")).toBeInTheDocument();
  });

  it("renders regression metrics honestly", async () => {
    signIn();
    mockApi(baseRoutes({
      [`GET /api/v1/projects/p1/experiments/${EXP_ID}`]: {
        body: experiment("completed", { task_type: "regression", target_column: "price" }),
      },
      [`GET /api/v1/projects/p1/experiments/${EXP_ID}/evaluation`]: { body: regressionEvaluation },
    }));
    renderApp(`/app/projects/p1/experiments/${EXP_ID}`);
    expect(await screen.findByText(/Regression evaluation/)).toBeInTheDocument();
    expect(screen.getAllByText("MAE").length).toBeGreaterThan(0);
    expect(screen.getAllByText("R²").length).toBeGreaterThan(0);
    expect(screen.queryByText("Confusion matrix")).not.toBeInTheDocument();
  });

  it("handles missing evaluation data for legacy experiments", async () => {
    signIn();
    mockApi(baseRoutes({
      [`GET /api/v1/projects/p1/experiments/${EXP_ID}/evaluation`]: {
        body: { ...classificationEvaluation, models: [] },
      },
    }));
    renderApp(`/app/projects/p1/experiments/${EXP_ID}`);
    expect(await screen.findByText("No per-model results recorded for this experiment.")).toBeInTheDocument();
    expect(screen.getByText("No evaluation results")).toBeInTheDocument();
  });

  it("shows API error state", async () => {
    signIn();
    const notFound = { status: 404, body: { error: { code: "not_found", message: "Experiment not found." } } };
    mockApi({
      "GET /api/v1/auth/me": { body: ME },
      "GET /api/v1/projects/p1": notFound,
      [`GET /api/v1/projects/p1/experiments/${EXP_ID}`]: notFound,
      [`GET /api/v1/projects/p1/experiments/${EXP_ID}/evaluation`]: notFound,
      [`GET /api/v1/projects/p1/experiments/${EXP_ID}/reproducibility`]: notFound,
      [`GET /api/v1/projects/p1/experiments/${EXP_ID}/artifact`]: notFound,
    });
    renderApp(`/app/projects/p1/experiments/${EXP_ID}`);
    expect(await screen.findByText(/Experiment not found/)).toBeInTheDocument();
  });
});
