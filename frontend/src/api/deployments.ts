import { request } from "./client";

export interface Deployment {
  id: string;
  project_id: string;
  model_id: string;
  version_id: string;
  experiment_id?: string;
  model_name?: string;
  version_number?: number;
  algorithm?: string;
  status: string;
  config: Record<string, unknown>;
  last_error: string | null;
  checksum_sha256?: string;
  prediction_count?: number;
  created_at: string;
  updated_at: string;
}

export interface PredictionResult {
  request_id: string;
  deployment_id: string;
  model_id: string;
  model_version_id: string;
  prediction: unknown;
  probabilities?: Record<string, number>;
  duration_ms: number;
  timestamp: string;
}

export interface PredictionRecord {
  id: string;
  request_id: string;
  status: string;
  input: Record<string, unknown> | null;
  output: { prediction?: unknown; probabilities?: Record<string, number> } | null;
  duration_ms: number | null;
  error: string | null;
  created_at: string;
}

const base = (projectId: string) => `/projects/${projectId}`;

export const deployVersion = (projectId: string, modelId: string, versionId: string) =>
  request<Deployment>(`${base(projectId)}/models/${modelId}/versions/${versionId}/deploy`, {
    method: "POST", body: {},
  });

export const listDeployments = (projectId: string, signal?: AbortSignal) =>
  request<Deployment[]>(`${base(projectId)}/deployments`, { signal });

export const getDeployment = (projectId: string, deploymentId: string, signal?: AbortSignal) =>
  request<Deployment>(`${base(projectId)}/deployments/${deploymentId}`, { signal });

export const stopDeployment = (projectId: string, deploymentId: string) =>
  request<Deployment>(`${base(projectId)}/deployments/${deploymentId}/stop`, { method: "POST" });

export const predictDeployment = (projectId: string, deploymentId: string, features: Record<string, unknown>) =>
  request<PredictionResult>(`${base(projectId)}/deployments/${deploymentId}/predict`, {
    method: "POST", body: { features },
  });

export const predictionHistory = (projectId: string, deploymentId: string, limit = 50, offset = 0) =>
  request<{ deployment_id: string; total: number; records: PredictionRecord[] }>(
    `${base(projectId)}/deployments/${deploymentId}/predictions?limit=${limit}&offset=${offset}`);
