import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { createDataset, deleteDataset, getDataset, listDatasets } from "../../api/datasets";
import type { Dataset, DatasetWithVersions } from "../../api/types";

export function useDatasets(projectId: string) {
  const [items, setItems] = useState<Dataset[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    setStatus("loading");
    setError(null);
    try {
      const data = await listDatasets(projectId, signal);
      if (signal?.aborted) return;
      setItems(data);
      setStatus("ready");
    } catch (e) {
      if (signal?.aborted) return;
      setError(e instanceof ApiError ? e.message : "Could not load datasets.");
      setStatus("error");
    }
  }, [projectId]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const reload = useCallback(() => load(), [load]);

  const create = async (name: string, description: string | undefined, file: File) => {
    return await createDataset(projectId, name, description, file);
  };

  const remove = async (datasetId: string) => {
    await deleteDataset(projectId, datasetId);
  };

  return { items, status, error, reload, create, remove };
}

export function useDataset(projectId: string, datasetId: string) {
  const [data, setData] = useState<DatasetWithVersions | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    setStatus("loading");
    setError(null);
    try {
      const result = await getDataset(projectId, datasetId, signal);
      if (signal?.aborted) return;
      setData(result);
      setStatus("ready");
    } catch (e) {
      if (signal?.aborted) return;
      setError(e instanceof ApiError ? e.message : "Could not load dataset.");
      setStatus("error");
    }
  }, [projectId, datasetId]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  return { data, status, error, load };
}
