import { request } from "./client";

export interface MonitoringConfig {
  deployment_id: string;
  thresholds: Record<string, number>;
  min_samples: number;
  input_logging: boolean;
}

export interface FeatureDrift {
  feature: string;
  type: string;
  psi?: number | null;
  ks_statistic?: number | null;
  ks_pvalue?: number | null;
  chi2_pvalue?: number | null;
  missing_rate_ref?: number;
  missing_rate_current?: number | null;
  missing_rate_delta?: number | null;
}

export interface MonitoringRun {
  id: string;
  deployment_id: string;
  status: string;
  health_status: string;
  sample_count: number;
  reference_sample_count: number;
  thresholds: Record<string, number>;
  summary: {
    features?: FeatureDrift[];
    prediction_distribution?: { available: boolean; distribution?: Record<string, number>; n?: number };
    performance?: { status: string; matched?: number; accuracy?: number; precision?: number; recall?: number; f1?: number; mae?: number; rmse?: number; r2?: number; roc_auc?: number; reason?: string };
    health_reasons?: string[];
    methodology?: string;
    reason?: string;
  };
  error: string | null;
  created_at: string;
}

const base = (projectId: string, depId: string) =>
  `/projects/${projectId}/deployments/${depId}/monitoring`;

export const getMonitoringConfig = (projectId: string, depId: string) =>
  request<MonitoringConfig>(`${base(projectId, depId)}/config`);

export const setMonitoringConfig = (projectId: string, depId: string, thresholds: Record<string, number>) =>
  request<MonitoringConfig>(`${base(projectId, depId)}/config`, { method: "PUT", body: { thresholds } });

export const runMonitoring = (projectId: string, depId: string) =>
  request<MonitoringRun>(`${base(projectId, depId)}/run`, { method: "POST", body: {} });

export const listMonitoringRuns = (projectId: string, depId: string) =>
  request<{ deployment_id: string; runs: MonitoringRun[] }>(`${base(projectId, depId)}/runs`);

export const getPerformanceHistory = (projectId: string, depId: string) =>
  request<{ deployment_id: string; series: { run_id: string; created_at: string; metrics: Record<string, number> }[] }>(
    `${base(projectId, depId)}/performance`);

export const ingestLabels = (projectId: string, depId: string, labels: { request_id: string; label: unknown }[]) =>
  request<{ added: number; skipped_duplicates: number }>(`${base(projectId, depId)}/labels`, {
    method: "POST", body: { labels },
  });
