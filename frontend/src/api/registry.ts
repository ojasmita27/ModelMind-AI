import { request } from "./client";

export interface RegisteredModelSummary {
  id: string;
  name: string;
  description: string | null;
  task_type: string;
  created_at: string;
  version_count: number;
  latest_version: ModelVersionInfo | null;
}

export interface ModelVersionInfo {
  id: string;
  version_number: number;
  experiment_id: string;
  dataset_version_id: string | null;
  algorithm: string;
  framework: string;
  checksum_sha256: string;
  file_size_bytes: number;
  metrics: Record<string, unknown>;
  config: Record<string, unknown>;
  lifecycle_status: string;
  validation: { ok: boolean; checks: Record<string, boolean>; reasons: string[] } | null;
  created_at: string;
}

export interface ModelDetail extends Omit<RegisteredModelSummary, "version_count" | "latest_version"> {
  versions: ModelVersionInfo[];
  production_version_id: string | null;
}

const base = (projectId: string) => `/projects/${projectId}/models`;

export const listModels = (projectId: string, signal?: AbortSignal) =>
  request<RegisteredModelSummary[]>(base(projectId), { signal });

export const getModel = (projectId: string, modelId: string, signal?: AbortSignal) =>
  request<ModelDetail>(`${base(projectId)}/${modelId}`, { signal });

export const registerModel = (projectId: string, experimentId: string, name?: string) =>
  request<ModelVersionInfo & { model_id: string }>(`${base(projectId)}/register`, {
    method: "POST",
    body: { experiment_id: experimentId, name: name || null },
  });

export const validateVersion = (projectId: string, modelId: string, versionId: string) =>
  request<{ version_id: string; validation: unknown; lifecycle_status: string }>(
    `${base(projectId)}/${modelId}/versions/${versionId}/validate`, { method: "POST" });

export const transitionVersion = (projectId: string, modelId: string, versionId: string, toStatus: string, note?: string) =>
  request<{ version_id: string; from: string; to: string }>(
    `${base(projectId)}/${modelId}/versions/${versionId}/transition`,
    { method: "POST", body: { to_status: toStatus, note: note ?? null } });

export const rollbackVersion = (projectId: string, modelId: string, versionId: string) =>
  request<{ rolled_back_from: string; production_version_id: string }>(
    `${base(projectId)}/${modelId}/versions/${versionId}/rollback`, { method: "POST", body: {} });

export const versionHistory = (projectId: string, modelId: string, versionId: string) =>
  request<{ version_id: string; lifecycle_status: string; transitions: { from: string; to: string; note: string | null; created_at: string }[] }>(
    `${base(projectId)}/${modelId}/versions/${versionId}/history`);

export const compareVersions = (projectId: string, versionIds: string[]) =>
  request<{ task_type: string; versions: { version_id: string; model_name: string; version_number: number; algorithm: string; lifecycle_status: string; metrics: Record<string, number | null> }[] }>(
    `${base(projectId)}/compare?version_ids=${versionIds.join(",")}`);
