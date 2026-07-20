// Request-shaping tests for the API client (mocked fetch). Per spec §6 the
// frontend tests are light: verify the client builds the right requests and
// surfaces backend error detail.
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  animate,
  deleteProject,
  exportProject,
  generate,
  listPresets,
  listProjects,
  regenerateFrame,
} from "./client";

function mockFetch(response: {
  ok: boolean;
  status?: number;
  json?: () => Promise<unknown>;
}) {
  const fn = vi.fn().mockResolvedValue({
    ok: response.ok,
    status: response.status ?? (response.ok ? 200 : 400),
    statusText: "err",
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
    expect(body.get("reference")).toBeNull();
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
    });
  });

  it("passes through explicit frames + fps", async () => {
    const fetchMock = mockFetch({
      ok: true,
      json: async () => ({ project_id: "p1", action: "run", fps: 12, frames: [] }),
    });

    await animate("p1", "run", { frames: 6, fps: 12 });

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      project_id: "p1",
      action: "run",
      frames: 6,
      fps: 12,
    });
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
