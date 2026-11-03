import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

// Content Security Policy for production builds. connect-src 'self' makes the browser refuse
// any request to another origin, so uploaded data provably cannot be sent anywhere.
// Dev mode skips it because Vite's hot reload needs inline scripts and a websocket.
// The meta tag covers only the page. The worker, which reads the file, is a separate script
// whose policy comes from its own HTTP response headers, so the HTTP headers below are the
// authoritative policy: the build writes them to dist/_headers (Cloudflare Pages) and
// `vite preview` sends them too. They add frame-ancestors, which a meta tag cannot carry.
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

const HEADERS = [
  `Content-Security-Policy: ${CSP}; frame-ancestors 'none'`,
  "X-Content-Type-Options: nosniff",
  "Referrer-Policy: no-referrer",
  "Permissions-Policy: camera=(), microphone=(), geolocation=(), interest-cohort=()",
  "Cross-Origin-Opener-Policy: same-origin",
];

const csp: Plugin = {
  name: "dw-csp",
  apply: "build",
  transformIndexHtml: () => [
    // First in <head>, so it governs the scripts and styles that follow.
    { tag: "meta", attrs: { "http-equiv": "Content-Security-Policy", content: CSP }, injectTo: "head-prepend" },
  ],
  generateBundle() {
    this.emitFile({ type: "asset", fileName: "_headers", source: ["/*", ...HEADERS.map((h) => `  ${h}`), ""].join("\n") });
  },
};

export default defineConfig({
  plugins: [react(), csp],
  worker: { format: "es" },
  // Source maps let the browser's developer tools show the original file and line for an
  // error in the built site. The code is open source, so they reveal nothing new.
  build: { sourcemap: true },
  server: { fs: { allow: [".."] } }, // model specs live in ../models
  preview: { headers: Object.fromEntries(HEADERS.map((h) => [h.slice(0, h.indexOf(":")), h.slice(h.indexOf(":") + 1).trim()])) },
  // fsModuleCache would keep stale import.meta.glob results when a new model folder appears.
  test: { include: ["src/**/*.test.{ts,tsx}"], fsModuleCache: false },
});
