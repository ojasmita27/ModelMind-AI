import { request } from "./client";

export interface WhatIfFeature {
  name: string;
  type: "numeric" | "categorical" | string;
  missing_count: number;
  min?: number | null;
  max?: number | null;
  median?: number | null;
  categories?: string[];
  categories_truncated?: boolean;
}

export interface WhatIfSchema {
  experiment_id: string;
  task_type: "classification" | "regression";
  target_column: string;
  features: WhatIfFeature[];
  classes: string[] | null;
  supports_probabilities: boolean;
}

export interface WhatIfPrediction {
  experiment_id: string;
  input: Record<string, unknown>;
  output: { prediction: unknown; probabilities?: Record<string, number> };
}

export interface CounterfactualResult {
  experiment_id: string;
  task_type: string;
  goal: Record<string, unknown>;
  immutable_features: string[];
  original: { input: Record<string, unknown>; output: { prediction: unknown; probabilities?: Record<string, number> } };
  counterfactuals: {
    features: Record<string, unknown>;
    changed_features: Record<string, { from: unknown; to: unknown }>;
    prediction: { prediction: unknown; probabilities?: Record<string, number> };
    distance: number;
    feasibility: number;
  }[];
  candidates_evaluated: number;
  note: string;
}

const base = (projectId: string, experimentId: string) =>
  `/projects/${projectId}/experiments/${experimentId}/what-if`;

export function getWhatIfSchema(projectId: string, experimentId: string, signal?: AbortSignal) {
  return request<WhatIfSchema>(`${base(projectId, experimentId)}/schema`, { signal });
}

export function whatIfPredict(projectId: string, experimentId: string, features: Record<string, unknown>) {
  return request<WhatIfPrediction>(`${base(projectId, experimentId)}/predict`, {
    method: "POST",
    body: { features },
  });
}

export function whatIfCounterfactual(
  projectId: string,
  experimentId: string,
  features: Record<string, unknown>,
  goal: Record<string, unknown>,
  opts: { n_candidates?: number; seed?: number; immutable?: string[] } = {},
) {
  return request<CounterfactualResult>(`${base(projectId, experimentId)}/counterfactual`, {
    method: "POST",
    body: {
      features,
      goal,
      n_candidates: opts.n_candidates ?? 3,
      seed: opts.seed ?? 42,
      immutable: opts.immutable ?? [],
    },
  });
}
