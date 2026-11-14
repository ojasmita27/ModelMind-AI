import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, configureApiClient, request } from "./client";
import { mockApi } from "../test/utils";

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("sends the bearer token only when auth is on", async () => {
    const { calls } = mockApi({ "GET /api/v1/a": { body: { ok: 1 } }, "POST /api/v1/b": { body: {} } });
    configureApiClient({ getToken: () => "tok-123", onUnauthorized: () => {} });
    await request("/a");
    await request("/b", { method: "POST", body: { x: 1 }, auth: false });
    expect(calls[0].authorization).toBe("Bearer tok-123");
    expect(calls[1].authorization).toBeNull();
    expect(calls[1].body).toEqual({ x: 1 });
  });

  it("turns the backend error envelope into ApiError with field errors", async () => {
    mockApi({ "POST /api/v1/x": { status: 422, body: { error: { code: "validation_error", message: "Request validation failed.",
      details: { errors: [{ loc: ["body", "email"], msg: "value is not a valid email address" }] } } } } });
    const err = (await request("/x", { method: "POST", body: {} }).catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(422);
    expect(err.code).toBe("validation_error");
    expect(err.fieldErrors.email).toMatch(/valid email/);
  });

  it("reports 401 on authenticated calls but not on login-style calls", async () => {
    const onUnauthorized = vi.fn();
    configureApiClient({ getToken: () => "t", onUnauthorized });
    mockApi({ "GET /api/v1/secure": { status: 401, body: { error: { code: "unauthorized", message: "no" } } },
      "POST /api/v1/auth/login": { status: 401, body: { error: { code: "unauthorized", message: "bad creds" } } } });
    await request("/secure").catch(() => {});
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
    await request("/auth/login", { method: "POST", body: {}, auth: false }).catch(() => {});
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("handles 204 and unreachable servers", async () => {
    mockApi({ "DELETE /api/v1/p": { status: 204 } });
    await expect(request("/p", { method: "DELETE" })).resolves.toBeUndefined();
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    const err = (await request("/anything").catch((e: unknown) => e)) as ApiError;
    expect(err.code).toBe("network_error");
    expect(err.message).toMatch(/backend is running/);
  });
});
