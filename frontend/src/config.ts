/** The ONE place for frontend configuration. */
export const APP_NAME = "ModelMind AI";
export const TAGLINE = "Train. Understand. Stress-Test. Diagnose. Improve.";

/** Base URL for API calls. Default is same-origin "/api/v1" (Vite proxies it to FastAPI in dev). */
export const API_BASE_URL: string =
  ((import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "").replace(/\/+$/, "") || "/api/v1";

/** sessionStorage (not localStorage): the session ends when the tab is closed. */
export const TOKEN_STORAGE_KEY = "modelmind.access_token";
