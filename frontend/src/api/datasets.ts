import { request } from "./client";
import type {
  CleaningOps,
  CleanPreview,
  ColumnProfile,
  Dataset,
  DatasetIntelligence,
  DatasetVersion,
  DatasetWithVersions,
  PaginatedPreview,
} from "./types";

export function listDatasets(projectId: string, signal?: AbortSignal) {
  return request<Dataset[]>(`/projects/${projectId}/datasets`, { signal });
}

export function getDataset(projectId: string, datasetId: string, signal?: AbortSignal) {
  return request<DatasetWithVersions>(`/projects/${projectId}/datasets/${datasetId}`, { signal });
}

export function getDatasetPreview(projectId: string, datasetId: string, limit = 10, signal?: AbortSignal) {
  return request<{ columns: string[]; rows: Record<string, unknown>[] }>(
    `/projects/${projectId}/datasets/${datasetId}/preview?limit=${limit}`,
    { signal },
  );
}

export function getDatasetProfile(projectId: string, datasetId: string, signal?: AbortSignal) {
  return request<{ row_count: number; column_count: number; columns: ColumnProfile[]; duplicate_row_count: number; duplicate_row_percentage: number; constant_columns: string[]; warnings: string[] }>(
    `/projects/${projectId}/datasets/${datasetId}/profile`,
    { signal },
  );
}

export function createDataset(
  projectId: string,
  name: string,
  description: string | undefined,
  file: File,
) {
  const formData = new FormData();
  formData.append("name", name);
  if (description) formData.append("description", description);
  formData.append("file", file);

  return request<DatasetVersion>(`/projects/${projectId}/datasets`, {
    method: "POST",
    body: formData,
  });
}

export function deleteDataset(projectId: string, datasetId: string) {
  return request<void>(`/projects/${projectId}/datasets/${datasetId}`, {
    method: "DELETE",
  });
}

export function listDatasetVersions(projectId: string, datasetId: string) {
  return request<DatasetVersion[]>(`/projects/${projectId}/datasets/${datasetId}/versions`);
}

export function getDatasetVersion(projectId: string, datasetId: string, versionId: string) {
  return request<DatasetVersion>(
    `/projects/${projectId}/datasets/${datasetId}/versions/${versionId}`,
  );
}

function versionBase(projectId: string, datasetId: string, versionId: string) {
  return `/projects/${projectId}/datasets/${datasetId}/versions/${versionId}`;
}

export function getVersionIntelligence(
  projectId: string,
  datasetId: string,
  versionId: string,
  targetColumn?: string,
  signal?: AbortSignal,
) {
  const qs = targetColumn ? `?target_column=${encodeURIComponent(targetColumn)}` : "";
  return request<DatasetIntelligence>(`${versionBase(projectId, datasetId, versionId)}/intelligence${qs}`, { signal });
}

export interface DatasetFinding {
  id: string;
  category: string;
  method: string;
  columns: string[];
  affected_rows: number | null;
  affected_pct: number | null;
  severity: "critical" | "warning" | "info";
  evidence: string;
  confidence: string;
  explanation: string;
  recommendation: string;
}

export interface VersionFindings {
  dataset_version_id: string;
  row_count: number;
  findings: DatasetFinding[];
  severity_summary: Record<string, number>;
  note: string;
}

export function getVersionFindings(
  projectId: string,
  datasetId: string,
  versionId: string,
  targetColumn?: string,
  signal?: AbortSignal,
) {
  const qs = targetColumn ? `?target_column=${encodeURIComponent(targetColumn)}` : "";
  return request<VersionFindings>(`${versionBase(projectId, datasetId, versionId)}/findings${qs}`, { signal });
}

export function getVersionPreview(
  projectId: string,
  datasetId: string,
  versionId: string,
  offset = 0,
  limit = 25,
  signal?: AbortSignal,
) {
  return request<PaginatedPreview>(
    `${versionBase(projectId, datasetId, versionId)}/preview?offset=${offset}&limit=${limit}`,
    { signal },
  );
}

export function cleanPreview(
  projectId: string,
  datasetId: string,
  versionId: string,
  ops: CleaningOps,
) {
  return request<CleanPreview>(`${versionBase(projectId, datasetId, versionId)}/clean-preview`, {
    method: "POST",
    body: ops,
  });
}

export function applyCleaning(
  projectId: string,
  datasetId: string,
  versionId: string,
  ops: CleaningOps,
) {
  return request<DatasetVersion>(`${versionBase(projectId, datasetId, versionId)}/clean`, {
    method: "POST",
    body: ops,
  });
}
