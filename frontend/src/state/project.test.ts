import { afterEach, describe, expect, it } from "vitest";

import type { ProjectDetail } from "../api/client";
import { useProjectStore } from "./project";

const detail: ProjectDetail = {
  id: "p1",
  schema_version: 1,
  prompt: "a knight",
  enhanced_prompt: "a silver-armored knight",
  prompt_source: "enhanced",
  image_provider: "azure",
  style: "hires",
  view_mode: "top_down_2_5d",
  direction: "up_left",
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
    expect(state.enhancedPrompt).toBe("a silver-armored knight");
    expect(state.promptSource).toBe("enhanced");
    expect(state.style).toBe("hires");
    expect(state.viewMode).toBe("top_down_2_5d");
    expect(state.direction).toBe("up_left");
    expect(state.provider).toBe("azure");
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
      enhancedPrompt: null,
      promptSource: "raw",
      spriteUrl: null,
      frames: [],
      action: null,
      viewMode: "side_scroller",
      direction: "left",
      provider: "auto",
    });
  });

  it("invalidates an enhanced preview when its raw prompt changes", () => {
    useProjectStore.getState().loadProject(detail);
    useProjectStore.getState().setPrompt("a wizard");

    expect(useProjectStore.getState().enhancedPrompt).toBeNull();
    expect(useProjectStore.getState().promptSource).toBe("raw");
  });

  it("selects a valid default when the camera mode changes", () => {
    useProjectStore.getState().setViewMode("top_down_2_5d");
    expect(useProjectStore.getState().direction).toBe("down");

    useProjectStore.getState().setDirection("up_right");
    useProjectStore.getState().setViewMode("side_scroller");
    expect(useProjectStore.getState().direction).toBe("left");
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
