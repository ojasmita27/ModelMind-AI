import { request } from "./client";

export interface CopilotAnswer {
  project_id: string;
  question: string;
  answer: string;
  statements?: string[];
  evidence?: { type: string; id: string; label: string }[];
  limitations?: string[];
  mode: string;
  provider_note?: string;
}

export interface ResearchReport {
  project_id: string;
  generated_at: string;
  sections: { title: string; status: string; content: string }[];
}

const base = (projectId: string) => `/projects/${projectId}/copilot`;

export const askCopilot = (projectId: string, question: string) =>
  request<CopilotAnswer>(`${base(projectId)}/ask`, { method: "POST", body: { question } });

export const getResearchReport = (projectId: string) =>
  request<ResearchReport>(`${base(projectId)}/report`, { method: "POST", body: {} });

export const getCopilotContext = (projectId: string, signal?: AbortSignal) =>
  request<Record<string, unknown>>(`${base(projectId)}/context`, { signal });
