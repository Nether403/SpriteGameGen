// Request-shaping tests for the API client (mocked fetch). Per spec §6 the
// frontend tests are light: verify the client builds the right requests and
// surfaces backend error detail.
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  animate,
  deleteProject,
  enhancePrompt,
  exportProject,
  generate,
  getProject,
  listPresets,
  listAnimationOptions,
  listImageProviders,
  listProjects,
  regenerateFrame,
} from "./client";

function mockFetch(response: {
  ok: boolean;
  status?: number;
  statusText?: string;
  json?: () => Promise<unknown>;
}) {
  const fn = vi.fn().mockResolvedValue({
    ok: response.ok,
    status: response.status ?? (response.ok ? 200 : 400),
    statusText: response.statusText ?? "err",
    json: response.json ?? (async () => ({})),
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("generate", () => {
  it("POSTs multipart form with prompt + style", async () => {
    const fetchMock = mockFetch({
      ok: true,
      json: async () => ({ project_id: "p1", sprite_url: "/projects/p1/sprite.png" }),
    });

    const result = await generate("a knight", "pixel");

    expect(result.project_id).toBe("p1");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/generate");
    expect(init.method).toBe("POST");
    const body = init.body as FormData;
    expect(body.get("prompt")).toBe("a knight");
    expect(body.get("style")).toBe("pixel");
    expect(body.get("view_mode")).toBe("side_scroller");
    expect(body.get("direction")).toBe("left");
    expect(body.get("provider")).toBe("auto");
    expect(body.get("reference")).toBeNull();
  });

  it("serializes an explicit camera and direction once", async () => {
    const fetchMock = mockFetch({
      ok: true,
      json: async () => ({ project_id: "p1", sprite_url: "u" }),
    });

    await generate("a knight", "pixel", null, {
      viewMode: "top_down_2_5d",
      direction: "up_left",
      provider: "azure",
    });

    const body = fetchMock.mock.calls[0][1].body as FormData;
    expect(body.getAll("view_mode")).toEqual(["top_down_2_5d"]);
    expect(body.getAll("direction")).toEqual(["up_left"]);
    expect(body.getAll("provider")).toEqual(["azure"]);
  });

  it("includes an accepted enhanced prompt only when supplied", async () => {
    const fetchMock = mockFetch({
      ok: true,
      json: async () => ({ project_id: "p1", sprite_url: "u" }),
    });

    await generate("a knight", "pixel", null, {
      enhancedPrompt: "a detailed silver knight",
    });

    const body = fetchMock.mock.calls[0][1].body as FormData;
    expect(body.getAll("enhanced_prompt")).toEqual(["a detailed silver knight"]);
  });

  it("appends the reference file when provided", async () => {
    const fetchMock = mockFetch({
      ok: true,
      json: async () => ({ project_id: "p1", sprite_url: "u" }),
    });
    const file = new File(["x"], "ref.png", { type: "image/png" });

    await generate("a knight", "hires", file);

    const body = (fetchMock.mock.calls[0][1].body as FormData);
    expect(body.get("style")).toBe("hires");
    expect(body.get("reference")).toBeInstanceOf(File);
  });

  it("throws ApiError carrying the backend detail on failure", async () => {
    mockFetch({
      ok: false,
      status: 422,
      json: async () => ({ detail: "prompt must not be empty" }),
    });

    await expect(generate("", "pixel")).rejects.toMatchObject({
      name: "ApiError",
      status: 422,
      message: "prompt must not be empty",
    });
  });

  it("passes an abort signal to fetch", async () => {
    const fetchMock = mockFetch({
      ok: true,
      json: async () => ({ project_id: "p1", sprite_url: "sprite" }),
    });
    const controller = new AbortController();

    await generate("a knight", "pixel", null, { signal: controller.signal });

    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal);
  });

  it("uses a useful fallback when an error has no detail or status text", async () => {
    mockFetch({
      ok: false,
      status: 503,
      statusText: "",
      json: async () => ({}),
    });

    await expect(generate("a knight", "pixel")).rejects.toMatchObject({
      message: "Request failed (503)",
    });
  });
});

describe("enhancePrompt", () => {
  it("POSTs the raw prompt and creative context", async () => {
    const fetchMock = mockFetch({
      ok: true,
      json: async () => ({
        original_prompt: "a knight",
        enhanced_prompt: "a silver knight",
      }),
    });

    await enhancePrompt({
      prompt: "a knight",
      style: "pixel",
      view_mode: "top_down_2_5d",
      direction: "up_left",
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/prompts/enhance");
    expect(JSON.parse(init.body)).toEqual({
      prompt: "a knight",
      style: "pixel",
      view_mode: "top_down_2_5d",
      direction: "up_left",
    });
  });
});

describe("exportProject", () => {
  it("POSTs JSON body with project id, format, padding and cols", async () => {
    const fetchMock = mockFetch({
      ok: true,
      json: async () => ({ sheet_url: "s", atlas_url: "a" }),
    });

    await exportProject("p1", "xml", { padding: 2, cols: 3 });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/export");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body)).toEqual({
      project_id: "p1",
      format: "xml",
      padding: 2,
      cols: 3,
    });
  });

  it("defaults padding to 0 and cols to null", async () => {
    const fetchMock = mockFetch({
      ok: true,
      json: async () => ({ sheet_url: "s", atlas_url: "a" }),
    });

    await exportProject("p1", "json");

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      project_id: "p1",
      format: "json",
      padding: 0,
      cols: null,
    });
  });
});

describe("animate", () => {
  it("POSTs project id + action, defaulting frames to null and fps to 8", async () => {
    const fetchMock = mockFetch({
      ok: true,
      json: async () => ({ project_id: "p1", action: "walk", fps: 8, frames: [] }),
    });

    await animate("p1", "walk");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/animate");
    expect(JSON.parse(init.body)).toEqual({
      project_id: "p1",
      action: "walk",
      frames: null,
      fps: 8,
      direction: "left",
    });
  });

  it("passes through explicit frames + fps", async () => {
    const fetchMock = mockFetch({
      ok: true,
      json: async () => ({ project_id: "p1", action: "run", fps: 12, frames: [] }),
    });

    await animate("p1", "run", {
      frames: 6,
      fps: 12,
      direction: "down_right",
      provider: "azure",
    });

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      project_id: "p1",
      action: "run",
      frames: 6,
      fps: 12,
      direction: "down_right",
      provider: "azure",
    });
  });
});

describe("animation options", () => {
  it("GETs the backend camera rules", async () => {
    const fetchMock = mockFetch({ ok: true, json: async () => [] });
    await listAnimationOptions();
    expect(fetchMock.mock.calls[0][0]).toBe("/animation-options");
  });
});

describe("image providers", () => {
  it("GETs provider availability", async () => {
    const fetchMock = mockFetch({ ok: true, json: async () => [] });
    await listImageProviders();
    expect(fetchMock.mock.calls[0][0]).toBe("/image-providers");
  });
});

describe("regenerateFrame", () => {
  it("POSTs /animate/frame with project id + index", async () => {
    const fetchMock = mockFetch({
      ok: true,
      json: async () => ({ index: 2, url: "/projects/p1/frame_2.png", status: "ok" }),
    });

    const frame = await regenerateFrame("p1", 2);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/animate/frame");
    expect(JSON.parse(init.body)).toEqual({ project_id: "p1", index: 2 });
    expect(frame.status).toBe("ok");
  });
});

describe("listPresets", () => {
  it("GETs /presets", async () => {
    const fetchMock = mockFetch({ ok: true, json: async () => [] });
    await listPresets();
    expect(fetchMock.mock.calls[0][0]).toBe("/presets");
  });
});

describe("projects", () => {
  it("lists projects via GET /projects", async () => {
    const fetchMock = mockFetch({ ok: true, json: async () => [] });
    await listProjects();
    expect(fetchMock.mock.calls[0][0]).toBe("/projects");
  });

  it("loads project detail via GET /projects/:id", async () => {
    const fetchMock = mockFetch({
      ok: true,
      json: async () => ({ id: "p1", prompt: "a knight", frames: [] }),
    });

    const project = await getProject("p1");

    expect(project.id).toBe("p1");
    expect(fetchMock.mock.calls[0][0]).toBe("/projects/p1");
  });

  it("encodes project ids used in paths", async () => {
    const fetchMock = mockFetch({
      ok: true,
      json: async () => ({ id: "folder/project one", frames: [] }),
    });

    await getProject("folder/project one");

    expect(fetchMock.mock.calls[0][0]).toBe("/projects/folder%2Fproject%20one");
  });

  it("deletes via DELETE /projects/:id", async () => {
    const fetchMock = mockFetch({ ok: true, json: async () => ({}) });
    await deleteProject("p1");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/projects/p1");
    expect(init.method).toBe("DELETE");
  });

  it("surfaces ApiError on a failed delete", async () => {
    mockFetch({ ok: false, status: 404 });
    await expect(deleteProject("nope")).rejects.toBeInstanceOf(ApiError);
  });
});
