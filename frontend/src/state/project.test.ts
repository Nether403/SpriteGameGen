import { afterEach, describe, expect, it } from "vitest";

import type { ProjectDetail } from "../api/client";
import { useProjectStore } from "./project";

const detail: ProjectDetail = {
  id: "p1",
  schema_version: 1,
  prompt: "a knight",
  style: "hires",
  frames: [{ index: 0, url: "/projects/p1/sprite.png?v=1", status: "ok" }],
  action: null,
  fps: null,
  created_at: "2026-07-21T10:00:00Z",
  updated_at: "2026-07-21T10:01:00Z",
  sprite_url: "/projects/p1/sprite.png?v=2",
  health: "ready",
  resume_available: true,
};

afterEach(() => {
  useProjectStore.getState().reset();
});

describe("project store", () => {
  it("hydrates a resumable project and clears transient export state", () => {
    useProjectStore.setState({
      exportResult: { sheet_url: "old-sheet", atlas_url: "old-atlas" },
    });

    useProjectStore.getState().loadProject(detail);
    const state = useProjectStore.getState();

    expect(state.projectId).toBe("p1");
    expect(state.prompt).toBe("a knight");
    expect(state.style).toBe("hires");
    expect(state.spriteUrl).toContain("?v=2");
    expect(state.frames).toEqual(detail.frames);
    expect(state.exportResult).toBeNull();
  });

  it("clears the loaded project and prompt on reset", () => {
    useProjectStore.getState().loadProject(detail);
    useProjectStore.getState().reset();

    expect(useProjectStore.getState()).toMatchObject({
      projectId: null,
      prompt: "",
      spriteUrl: null,
      frames: [],
      action: null,
    });
  });

  it("sets the new prompt when a new project is generated", () => {
    useProjectStore.getState().loadProject(detail);
    useProjectStore.getState().setGenerated("p2", "/projects/p2/sprite.png?v=1", "a wizard");

    expect(useProjectStore.getState()).toMatchObject({
      projectId: "p2",
      prompt: "a wizard",
      frames: [],
      action: null,
    });
  });
});
