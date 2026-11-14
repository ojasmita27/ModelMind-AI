import { request } from "./client";
import type {
  Experiment,
  ExperimentArtifact,
  ExperimentEvaluation,
  ExperimentInput,
  ExperimentReproducibility,
} from "./types";

export function listExperiments(projectId: string, signal?: AbortSignal) {
  return request<Experiment[]>(`/projects/${projectId}/experiments`, { signal });
}

export function createExperiment(projectId: string, input: ExperimentInput) {
  return request<Experiment>(`/projects/${projectId}/experiments`, {
    method: "POST",
    body: input,
  });
}

export function getExperiment(projectId: string, experimentId: string, signal?: AbortSignal) {
  return request<Experiment>(`/projects/${projectId}/experiments/${encodeURIComponent(experimentId)}`, { signal });
}

export function getExperimentEvaluation(projectId: string, experimentId: string, signal?: AbortSignal) {
  return request<ExperimentEvaluation>(
    `/projects/${projectId}/experiments/${encodeURIComponent(experimentId)}/evaluation`,
    { signal },
  );
}

export function getExperimentReproducibility(projectId: string, experimentId: string, signal?: AbortSignal) {
  return request<ExperimentReproducibility>(
    `/projects/${projectId}/experiments/${encodeURIComponent(experimentId)}/reproducibility`,
    { signal },
  );
}

export function getExperimentArtifact(projectId: string, experimentId: string, signal?: AbortSignal) {
  return request<ExperimentArtifact>(
    `/projects/${projectId}/experiments/${encodeURIComponent(experimentId)}/artifact`,
    { signal },
  );
}
