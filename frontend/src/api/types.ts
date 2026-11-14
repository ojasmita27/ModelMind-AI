export interface User {
  id: string;
  email: string;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface Project {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectInput {
  name: string;
  description: string | null;
}

export interface ColumnProfile {
  name: string;
  type: string;
  missing_count: number;
  missing_percentage: number;
  unique_count: number;
  sample_values: string[];
}

export interface DatasetVersion {
  id: string;
  dataset_id: string;
  version_number: number;
  sha256_checksum: string;
  file_path: string;
  file_size_bytes: number;
  row_count: number | null;
  column_count: number | null;
  job_status: "pending" | "processing" | "completed" | "failed";
  job_error: string | null;
  job_started_at: string | null;
  job_completed_at: string | null;
  source: string;
  derived_from_version_id: string | null;
  transformation_log: string[] | null;
  created_at: string;
}

export interface DatasetIntelligenceColumn {
  name: string;
  type: "numeric" | "categorical" | "datetime" | "text" | string;
  missing_count: number;
  missing_percentage: number;
  unique_count: number;
  unique_percentage: number;
  is_constant: boolean;
  is_near_constant: boolean;
  is_high_cardinality: boolean;
  is_identifier: boolean;
  sample_values: string[];
  stats?: Record<string, number | string | null>;
  top_values?: Record<string, number>;
}

export interface DatasetIntelligence {
  row_count: number;
  column_count: number;
  columns: DatasetIntelligenceColumn[];
  duplicate_row_count: number;
  duplicate_row_percentage: number;
  correlation: { columns: string[]; matrix: number[][] } | null;
  target: {
    column: string;
    type: string;
    missing_count: number;
    class_count: number;
    distribution: Record<string, number>;
    imbalance_ratio?: number;
    dominant_class_pct?: number;
  } | null;
  quality_score: number;
  quality_criteria: Record<string, number>;
  warnings: string[];
}

export interface CleaningOps {
  drop_columns?: string[];
  rename_columns?: Record<string, string>;
  missing?: { strategy?: string; constant_value?: string | number };
  drop_duplicates?: boolean;
  outliers?: { enabled?: boolean; columns?: string[]; strategy?: string; k?: number };
  datetime_extract?: { column: string; parts: string[] }[];
  encode?: { column: string; method: string }[];
  scale?: { method?: string; columns?: string[] };
}

export interface CleanPreview {
  columns: string[];
  rows: Record<string, unknown>[];
  shape_before: { rows: number; columns: number };
  shape_after: { rows: number; columns: number };
  rows_removed: number;
  columns_removed: number;
  missing_before: { missing_cells: number; missing_pct: number; columns_with_missing: number };
  missing_after: { missing_cells: number; missing_pct: number; columns_with_missing: number };
  transformation_log: string[];
}

export interface PaginatedPreview {
  columns: string[];
  rows: Record<string, unknown>[];
  total_rows: number;
  offset: number;
  limit: number;
  has_more: boolean;
}

export interface BenchmarkDataset {
  id: string;
  name: string;
  description: string;
  task_type: "classification" | "regression";
  target_column: string;
  source: string;
  source_url: string;
  license: string;
  citation: string;
}

export interface Dataset {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  created_at: string;
}

export interface DatasetInput {
  name: string;
  description?: string | null;
}

export interface DatasetWithVersions extends Dataset {
  versions: DatasetVersion[];
}

export interface ExperimentMetricSummary {
  accuracy?: number;
  f1_macro?: number;
  f1_weighted?: number;
  precision_macro?: number;
  recall_macro?: number;
  roc_auc?: number;
  mse?: number;
  mae?: number;
  rmse?: number;
  r2?: number;
  [key: string]: number | undefined;
}

export interface Experiment {
  id: string;
  project_id: string;
  dataset_id: string | null;
  dataset_version_id: string | null;
  name: string;
  task_type: "classification" | "regression";
  target_column: string;
  train_fraction: number;
  validation_fraction: number;
  test_fraction: number;
  random_seed: number;
  model_names: string[];
  preprocessing_config?: Record<string, unknown> | null;
  tuning_config?: Record<string, unknown> | null;
  status: "queued" | "running" | "completed" | "failed";
  error: string | null;
  metrics: Record<string, unknown>;
  artifact_uri: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface ExperimentInput {
  name: string;
  dataset_id: string;
  dataset_version_id: string;
  task_type: "classification" | "regression";
  target_column: string;
  train_fraction: number;
  validation_fraction: number;
  test_fraction: number;
  random_seed: number;
  model_names: string[];
  preprocessing?: Record<string, unknown>;
  tuning?: { enabled?: boolean; n_iter?: number; cv?: number };
}

export interface ApiErrorEnvelope {
  error: { code: string; message: string; details?: { errors?: { loc: string[]; msg: string }[] } };
}

export interface ModelEvaluationResult {
  model_name: string;
  task_type: string;
  is_selected: boolean;
  status: "completed" | "failed";
  error: string | null;
  cross_validation_metrics: Record<string, number>;
  validation_metrics: Record<string, number>;
  test_metrics: Record<string, number>;
  confusion_matrix: { labels: string[]; matrix: number[][] } | null;
  classification_report: Record<string, { precision: number; recall: number; "f1-score": number; support: number } | number> | null;
  best_params: Record<string, unknown> | null;
  training_duration_ms: number | null;
}

export interface ExperimentEvaluation {
  experiment_id: string;
  status: string;
  task_type: string;
  target_column: string;
  best_model_name: string | null;
  models: ModelEvaluationResult[];
}

export interface ExperimentReproducibility {
  experiment_id: string;
  name: string;
  task_type: string;
  target_column: string;
  random_seed: number;
  train_fraction: number;
  validation_fraction: number;
  test_fraction: number;
  dataset_id: string;
  dataset_version_id: string;
  dataset_sha256: string | null;
  model_names: string[];
  model_configs: Record<string, { estimator: string; params: Record<string, unknown> }>;
  preprocessing: Record<string, unknown>;
  manifest: Record<string, unknown> | null;
  manifest_available: boolean;
}

export interface ExperimentArtifact {
  experiment_id: string;
  available: boolean;
  artifact_uri: string | null;
  model_file_size_bytes: number | null;
  manifest_verified: boolean;
  manifest_error: string | null;
}
