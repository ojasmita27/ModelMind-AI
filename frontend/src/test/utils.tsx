import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { AppRoutes } from "../App";
import { AuthProvider } from "../auth/AuthContext";
import { ToastProvider } from "../components/ui/Toast";
import { TOKEN_STORAGE_KEY } from "../config";

export interface Call { method: string; path: string; body: unknown; authorization: string | null }
type Reply = { status?: number; body?: unknown };
type Route = Reply | ((call: Call) => Reply);

/** Replaces the network layer (fetch) for a test. Components, router and auth code run for real. */
export function mockApi(routes: Record<string, Route>) {
  const calls: Call[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const method = init?.method ?? "GET";
    const headers = new Headers(init?.headers);
    const call: Call = {
      method, path: url.pathname, authorization: headers.get("Authorization"),
      body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
    };
    calls.push(call);
    const route = routes[`${method} ${url.pathname}`];
    if (!route) return new Response(JSON.stringify({ error: { code: "not_found", message: `No mock for ${method} ${url.pathname}` } }), { status: 404 });
    const reply = typeof route === "function" ? route(call) : route;
    if (reply.status === 204) return new Response(null, { status: 204 });
    return new Response(JSON.stringify(reply.body ?? {}), { status: reply.status ?? 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return { calls, fn };
}

const b64 = (o: unknown) => btoa(JSON.stringify(o)).replace(/=+$/, "");
export function fakeJwt(expiresInSeconds: number): string {
  return `${b64({ alg: "HS256", typ: "JWT" })}.${b64({ sub: "user-1", exp: Math.floor(Date.now() / 1000) + expiresInSeconds })}.signature`;
}

export const signIn = (expiresInSeconds = 3600) => sessionStorage.setItem(TOKEN_STORAGE_KEY, fakeJwt(expiresInSeconds));

export const ME = { id: "user-1", email: "ada@example.com", created_at: "2026-01-01T00:00:00Z" };
export const project = (n: number, extra: Partial<{ name: string; description: string | null }> = {}) => ({
  id: `p${n}`, name: extra.name ?? `Project ${n}`, description: extra.description ?? null,
  created_at: "2026-10-01T00:00:00Z", updated_at: "2026-10-02T00:00:00Z",
});

export function renderApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ToastProvider><AuthProvider><AppRoutes /></AuthProvider></ToastProvider>
    </MemoryRouter>,
  );
}
