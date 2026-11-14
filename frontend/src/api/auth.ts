import { request } from "./client";
import type { TokenResponse, User } from "./types";

export const register = (email: string, password: string) =>
  request<User>("/auth/register", { method: "POST", body: { email, password }, auth: false });

export const login = (email: string, password: string) =>
  request<TokenResponse>("/auth/login", { method: "POST", body: { email, password }, auth: false });

export const getMe = (signal?: AbortSignal) => request<User>("/auth/me", { signal });
