import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

// In development the browser talks to Vite (http://localhost:5173) and Vite forwards /api/*
// to the FastAPI backend. Same origin => no CORS problems and no hardcoded backend URL in code.
// Use 127.0.0.1 (not "localhost"): on Windows "localhost" can resolve to IPv6 (::1) first.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const backend = env.VITE_DEV_PROXY_TARGET || "http://127.0.0.1:8000";
  return {
    plugins: [react(), tailwindcss()],
    server: { port: 5173, strictPort: true, proxy: { "/api": { target: backend, changeOrigin: true } } },
    preview: { port: 4173, proxy: { "/api": { target: backend, changeOrigin: true } } },
    test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"], css: false },
  };
});
