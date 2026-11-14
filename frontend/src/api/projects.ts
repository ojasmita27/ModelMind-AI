import { request } from "./client";
import type { Project, ProjectInput } from "./types";

export const listProjects = (limit: number, offset: number, signal?: AbortSignal) =>
  request<Project[]>(`/projects?limit=${limit}&offset=${offset}`, { signal });

export const getProject = (id: string, signal?: AbortSignal) => request<Project>(`/projects/${encodeURIComponent(id)}`, { signal });

export const createProject = (input: ProjectInput) => request<Project>("/projects", { method: "POST", body: input });

export const updateProject = (id: string, input: Partial<ProjectInput>) =>
  request<Project>(`/projects/${encodeURIComponent(id)}`, { method: "PATCH", body: input });

export const deleteProject = (id: string) => request<void>(`/projects/${encodeURIComponent(id)}`, { method: "DELETE" });
