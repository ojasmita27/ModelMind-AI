import { request } from "./client";
import type { BenchmarkDataset, DatasetVersion } from "./types";

export function listBenchmarks(taskType?: string, search?: string, signal?: AbortSignal) {
  const params = new URLSearchParams();
  if (taskType) params.set("task_type", taskType);
  if (search) params.set("search", search);
  const qs = params.toString();
  return request<BenchmarkDataset[]>(`/benchmarks${qs ? `?${qs}` : ""}`, { signal });
}

export function getBenchmark(id: string, signal?: AbortSignal) {
  return request<BenchmarkDataset>(`/benchmarks/${id}`, { signal });
}

export function importBenchmark(id: string, projectId: string) {
  return request<DatasetVersion>(`/benchmarks/${id}/import?project_id=${projectId}`, { method: "POST" });
}
