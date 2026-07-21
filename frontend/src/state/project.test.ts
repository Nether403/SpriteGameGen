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

  it("ignores an animation response for a project that is no longer active", () => {
    useProjectStore.getState().loadProject(detail);
    useProjectStore.getState().loadProject({
      ...detail,
      id: "p2",
      prompt: "a wizard",
      sprite_url: "/projects/p2/sprite.png",
      frames: [],
      action: null,
    });

    useProjectStore.getState().setAnimation(
      "p1",
      "run",
      12,
      [{ index: 0, url: "/projects/p1/frame_0.png", status: "ok" }],
      "right",
      "gemini",
    );

    expect(useProjectStore.getState()).toMatchObject({
      projectId: "p2",
      action: null,
      frames: [],
    });
  });

  it("keeps generation draft edits separate from the open project context", () => {
    useProjectStore.getState().loadProject(detail);

    useProjectStore.getState().setViewMode("side_scroller");
    useProjectStore.getState().setDirection("right");
    useProjectStore.getState().setStyle("pixel");
    useProjectStore.getState().setProvider("hyperagent");

    expect(useProjectStore.getState().activeProject).toMatchObject({
      prompt: "a knight",
      style: "hires",
      viewMode: "top_down_2_5d",
      direction: "up_left",
      provider: "azure",
    });
    expect(useProjectStore.getState()).toMatchObject({
      style: "pixel",
      viewMode: "side_scroller",
      direction: "right",
      provider: "hyperagent",
    });
  });

  it("allows only one shared project mutation at a time", () => {
    const openToken = useProjectStore.getState().beginMutation("open", "p1");

    expect(openToken).not.toBeNull();
    expect(useProjectStore.getState().beginMutation("export", "p2")).toBeNull();
    expect(useProjectStore.getState().mutation).toMatchObject({
      kind: "open",
      projectId: "p1",
    });

    useProjectStore.getState().endMutation(openToken as number);
    expect(useProjectStore.getState().beginMutation("export", "p2")).not.toBeNull();
  });

  it("ignores stale frame and export commits", () => {
    useProjectStore.getState().loadProject(detail);
    useProjectStore.getState().loadProject({ ...detail, id: "p2", frames: [] });

    useProjectStore.getState().setFrame("p1", {
      index: 0,
      url: "/projects/p1/frame.png",
      status: "ok",
    });
    useProjectStore.getState().setExport(
      "p1",
      { sheet_url: "old-sheet", atlas_url: "old-atlas" },
      { format: "json", padding: 0, cols: null },
    );

    expect(useProjectStore.getState()).toMatchObject({
      projectId: "p2",
      frames: [],
      exportResult: null,
    });
  });
});
