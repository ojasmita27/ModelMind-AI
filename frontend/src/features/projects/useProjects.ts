import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../../api/projects";
import { ApiError } from "../../api/client";
import type { Project, ProjectInput } from "../../api/types";

type Status = "loading" | "ready" | "error";
const messageOf = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong. Please try again.");

/** Loads the signed-in user's projects (server-side owner-scoped) and exposes CRUD actions. */
export function useProjects(pageSize = 50) {
  const [items, setItems] = useState<Project[]>([]);
  const [status, setStatus] = useState<Status>("loading");
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  const load = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const page = await api.listProjects(pageSize, 0);
      if (!alive.current) return;
      setItems(page);
      setHasMore(page.length === pageSize);
      setStatus("ready");
    } catch (e) {
      if (!alive.current) return;
      setError(messageOf(e));
      setStatus("error");
    }
  }, [pageSize]);

  useEffect(() => { void load(); }, [load]);

  const loadMore = useCallback(async () => {
    setLoadingMore(true);
    try {
      const page = await api.listProjects(pageSize, items.length);
      if (!alive.current) return;
      setItems((cur) => [...cur, ...page.filter((p) => !cur.some((c) => c.id === p.id))]);
      setHasMore(page.length === pageSize);
    } catch (e) {
      if (alive.current) setError(messageOf(e));
    } finally {
      if (alive.current) setLoadingMore(false);
    }
  }, [pageSize, items.length]);

  const create = useCallback(async (input: ProjectInput) => {
    const created = await api.createProject(input);
    setItems((cur) => [created, ...cur]);
    return created;
  }, []);

  const update = useCallback(async (id: string, input: Partial<ProjectInput>) => {
    const updated = await api.updateProject(id, input);
    setItems((cur) => cur.map((p) => (p.id === id ? updated : p)));
    return updated;
  }, []);

  const remove = useCallback(async (id: string) => {
    await api.deleteProject(id);
    setItems((cur) => cur.filter((p) => p.id !== id));
  }, []);

  return { items, status, error, hasMore, loadingMore, reload: load, loadMore, create, update, remove };
}
