import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useProjectStore } from "../state/project";
import { AnimationPlayer } from "./AnimationPlayer";

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  useProjectStore.setState({
    projectId: "p1",
    action: "walk",
    fps: 8,
    catalogRevision: 4,
    frames: [{ index: 0, url: "/frame.png", status: "ok" }],
    exportResult: { sheet_url: "sheet", atlas_url: "atlas" },
    exportOptions: { format: "json", padding: 0, cols: null },
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  useProjectStore.getState().reset();
});

describe("AnimationPlayer", () => {
  it("keeps preview FPS local without invalidating project data", () => {
    render(<AnimationPlayer />);

    fireEvent.change(screen.getByLabelText("Preview FPS: 8"), {
      target: { value: "12" },
    });

    expect(screen.getByLabelText("Preview FPS: 12")).toBeDefined();
    expect(useProjectStore.getState()).toMatchObject({
      fps: 8,
      catalogRevision: 4,
      exportResult: { sheet_url: "sheet", atlas_url: "atlas" },
    });
  });
});
