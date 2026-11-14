import { request } from "./client";

export interface TrustReceipt {
  receipt_id: string;
  experiment_id: string;
  project_id: string;
  digest: string;
  signature: { algorithm: string; value: string; key_id: string } | null;
  payload: Record<string, any>;
  verifications: { verified_at: string; ok: boolean; checks: Record<string, boolean | null>; note: string }[];
  created_at: string;
  already_existed?: boolean;
}

export interface ReceiptSummary {
  receipt_id: string;
  experiment_id: string;
  digest: string;
  created_at: string;
  signed: boolean;
  verification_count: number;
}

export interface Reproducibility {
  receipt_id: string;
  experiment_id: string;
  status: string;
  checks: { check: string; status: string; detail: string }[];
  note: string;
}

const base = (projectId: string) => `/projects/${projectId}`;

export const generateReceipt = (projectId: string, experimentId: string) =>
  request<TrustReceipt>(`${base(projectId)}/experiments/${experimentId}/trust-receipt`, { method: "POST" });

export const getReceipt = (projectId: string, experimentId: string) =>
  request<TrustReceipt>(`${base(projectId)}/experiments/${experimentId}/trust-receipt`);

export const listReceipts = (projectId: string) =>
  request<{ receipts: ReceiptSummary[] }>(`${base(projectId)}/trust-receipts`);

export const verifyReceipt = (projectId: string, receiptId: string) =>
  request<{ receipt_id: string; verification: TrustReceipt["verifications"][number]; verifications: TrustReceipt["verifications"] }>(
    `${base(projectId)}/trust-receipts/${receiptId}/verify`, { method: "POST" });

export const getReproducibility = (projectId: string, receiptId: string) =>
  request<Reproducibility>(`${base(projectId)}/trust-receipts/${receiptId}/reproducibility`);
