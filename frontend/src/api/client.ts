import { API_BASE_URL } from "../config";
import type { ApiErrorEnvelope } from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fieldErrors: Record<string, string>;

  constructor(status: number, code: string, message: string, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fieldErrors = fieldErrors;
  }
}

let getToken: () => string | null = () => null;
let onUnauthorized: (() => void) | null = null;

/** Wired up once by AuthProvider. Keeps the API layer free of React. */
export function configureApiClient(opts: { getToken: () => string | null; onUnauthorized: () => void }): void {
  getToken = opts.getToken;
  onUnauthorized = opts.onUnauthorized;
}

function extractFieldErrors(envelope: ApiErrorEnvelope | null): Record<string, string> {
  const out: Record<string, string> = {};
  for (const e of envelope?.error.details?.errors ?? []) {
    const field = e.loc[e.loc.length - 1];
    if (field && !(field in out)) out[field] = e.msg.replace(/^Value error, /, "");
  }
  return out;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  /** false for login/register: a 401 there means "wrong credentials", not "session expired". */
  auth?: boolean;
  signal?: AbortSignal;
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, auth = true, signal } = opts;
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = auth ? getToken() : null;
  if (token) headers.Authorization = `Bearer ${token}`;

  // Handle FormData for file uploads
  const isFormData = body instanceof FormData;
  if (!isFormData && body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : isFormData ? body : JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "network_error", "Cannot reach the ModelMind API. Check that the backend is running on port 8000.");
  }

  if (response.status === 204) return undefined as T;

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    /* non-JSON body */
  }

  if (!response.ok) {
    const envelope = (payload as ApiErrorEnvelope | null)?.error ? (payload as ApiErrorEnvelope) : null;
    if (response.status === 401 && auth) onUnauthorized?.();
    throw new ApiError(
      response.status,
      envelope?.error.code ?? "http_error",
      envelope?.error.message ?? `Request failed with status ${response.status}.`,
      extractFieldErrors(envelope),
    );
  }
  return payload as T;
}
