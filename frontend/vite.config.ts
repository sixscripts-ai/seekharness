import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tsconfigPaths from "vite-tsconfig-paths";
import meticulous from "@alwaysmeticulous/recorder-plugin/vite";

// Single source of truth for the Modal backend URL. Injected into the app as
// `__DEFAULT_MODAL_URL__` so api.ts does not hardcode a second copy that can
// drift out of sync with this config.
const DEFAULT_MODAL_URL = "https://sixscripts--agent-arena-backend-fastapi-app.modal.run";
const rawModalUrl = process.env.VITE_MODAL_URL;

if (rawModalUrl) {
  const cleaned = rawModalUrl
    .trim()
    .replace(/^VITE_MODAL_URL\s*=\s*/i, "")
    .replace(/^['"]|['"]$/g, "")
    .replace(/\/+$/, "");

  process.env.VITE_MODAL_URL = /^https?:\/\//i.test(cleaned)
    ? cleaned
    : DEFAULT_MODAL_URL;
}

// Record on localhost and Vercel preview builds, but never on production so
// real users' Appwrite JWTs and BYOK provider keys stay out of Meticulous.
// Vercel sets VERCEL_ENV to "production" only on production deploys.
const recorderEnabled = process.env.VERCEL_ENV === "production" ? "never" : "always";

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  define: {
    // Exposed to the client bundle; api.ts reads this as its fallback base URL.
    __DEFAULT_MODAL_URL__: JSON.stringify(DEFAULT_MODAL_URL),
  },
  build: {
    // No sourcemaps in production: 'hidden' still emits .map files that
    // anyone can fetch by guessing the URL, leaking source for a security
    // product. Local typescript maps remain available in dev.
    sourcemap: false,
  },
  plugins: [
    meticulous({
      recordingToken: "SIXsivbq1OdSAgXG3JQAnP0C06ACznSU3vm0Cg6b",
      enabled: recorderEnabled,
    }),
    react({
      babel: mode === 'development'
        ? {
            plugins: [
              'react-dev-locator',
            ],
          }
        : undefined,
    }),
    tsconfigPaths()
  ],
}))
