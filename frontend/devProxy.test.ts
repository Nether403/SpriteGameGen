// @vitest-environment node
import type { UserConfig } from "vite";
import { describe, expect, it } from "vitest";

import config from "./vite.config";


describe("development API proxy", () => {
  it("covers every backend route root used by the frontend client", () => {
    const proxy = (config as UserConfig).server?.proxy;

    expect(proxy).toMatchObject({
      "/generate": "http://localhost:8000",
      "/prompts": "http://localhost:8000",
      "/animate": "http://localhost:8000",
      "/animation-options": "http://localhost:8000",
      "/image-providers": "http://localhost:8000",
      "/presets": "http://localhost:8000",
      "/export": "http://localhost:8000",
      "/projects": "http://localhost:8000",
      "/health": "http://localhost:8000",
    });
  });
});
