/// <reference types="vitest/config" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Dev server proxies API calls to the FastAPI backend on :8000 so the frontend
// can use same-origin relative paths (/generate, /projects/...).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/generate": "http://localhost:8000",
      "/prompts": "http://localhost:8000",
      "/animate": "http://localhost:8000",
      "/animation-options": "http://localhost:8000",
      "/image-providers": "http://localhost:8000",
      "/presets": "http://localhost:8000",
      "/export": "http://localhost:8000",
      "/projects": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
  },
});
