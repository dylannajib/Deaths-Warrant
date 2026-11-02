import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

// Content Security Policy for production builds. connect-src 'self' makes the browser refuse
// any request to another origin, so uploaded data provably cannot be sent anywhere.
// Dev mode skips it because Vite's hot reload needs inline scripts and a websocket.
// Cloudflare Pages serves the same policy as an HTTP header (public/_headers).
export const CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'self'",
  "worker-src 'self'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
].join("; ");

const cspMeta: Plugin = {
  name: "dw-csp-meta",
  apply: "build",
  transformIndexHtml: () => [
    { tag: "meta", attrs: { "http-equiv": "Content-Security-Policy", content: CSP }, injectTo: "head" },
  ],
};

export default defineConfig({
  plugins: [react(), cspMeta],
  worker: { format: "es" },
  server: { fs: { allow: [".."] } }, // model specs live in ../models
  test: { include: ["src/**/*.test.ts"] },
});
