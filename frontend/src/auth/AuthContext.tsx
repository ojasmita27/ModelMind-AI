import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import * as authApi from "../api/auth";
import { ApiError, configureApiClient } from "../api/client";
import type { User } from "../api/types";
import { clearToken, getStoredToken, storeToken, tokenExpiryMs } from "./token";

type Status = "loading" | "authenticated" | "anonymous";

interface AuthValue {
  status: Status;
  user: User | null;
  /** One-off message for the login page (e.g. "session expired"). */
  notice: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  clearNotice: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);
export const SESSION_EXPIRED_MESSAGE = "Your session expired. Please sign in again.";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<User | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const endSession = useCallback((message: string | null) => {
    clearToken();
    setUser(null);
    setStatus("anonymous");
    setNotice(message);
  }, []);

  // Wire the API client: it reads the token from storage and reports 401s (expired/invalid token).
  useEffect(() => {
    configureApiClient({ getToken: getStoredToken, onUnauthorized: () => endSession(SESSION_EXPIRED_MESSAGE) });
  }, [endSession]);

  // Restore an existing session on page load by asking the server who we are.
  useEffect(() => {
    const controller = new AbortController();
    const token = getStoredToken();
    if (!token) {
      setStatus("anonymous");
      return;
    }
    const exp = tokenExpiryMs(token);
    if (exp !== null && exp <= Date.now()) {
      endSession(SESSION_EXPIRED_MESSAGE);
      return;
    }
    authApi.getMe(controller.signal).then(
      (me) => { setUser(me); setStatus("authenticated"); },
      (err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        // 401 is already handled by the API client. Other failures (e.g. backend down) end up here too.
        if (!(err instanceof ApiError && err.status === 401)) endSession(err instanceof ApiError ? err.message : null);
      },
    );
    return () => controller.abort();
  }, [endSession]);

  // Log out automatically when the token's own expiry time passes.
  useEffect(() => {
    if (status !== "authenticated") return;
    const token = getStoredToken();
    const exp = token ? tokenExpiryMs(token) : null;
    if (exp === null) return;
    const delay = Math.min(Math.max(exp - Date.now(), 0), 2_000_000_000);
    const timer = setTimeout(() => endSession(SESSION_EXPIRED_MESSAGE), delay);
    return () => clearTimeout(timer);
  }, [status, endSession]);

  const login = useCallback(async (email: string, password: string) => {
    const { access_token } = await authApi.login(email.trim(), password);
    storeToken(access_token);
    try {
      setUser(await authApi.getMe());
    } catch (err) {
      clearToken();
      throw err;
    }
    setNotice(null);
    setStatus("authenticated");
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    await authApi.register(email.trim(), password);
    await login(email, password);
  }, [login]);

  const logout = useCallback(() => endSession(null), [endSession]);
  const clearNotice = useCallback(() => setNotice(null), []);

  const value = useMemo<AuthValue>(
    () => ({ status, user, notice, login, register, logout, clearNotice }),
    [status, user, notice, login, register, logout, clearNotice],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
