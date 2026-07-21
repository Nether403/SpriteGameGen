import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { useProjectStore } from "../state/project";
import { AnimatePanel } from "./AnimatePanel";

const animate = vi.fn();
const listAnimationOptions = vi.fn();
const listPresets = vi.fn();
vi.mock("../api/client", () => ({
  animate: (...args: unknown[]) => animate(...args),
  listAnimationOptions: () => listAnimationOptions(),
  listPresets: () => listPresets(),
}));

afterEach(() => {
  cleanup();
  animate.mockReset();
  listAnimationOptions.mockReset();
  listPresets.mockReset();
  useProjectStore.getState().reset();
});

describe("AnimatePanel directions", () => {
  it("keeps the base camera fixed and animates in an allowed direction", async () => {
    listPresets.mockResolvedValue([
      { action: "walk", min_frames: 4, max_frames: 8, default_frames: 6, pose: "walk" },
    ]);
    listAnimationOptions.mockResolvedValue([
      {
        view_mode: "top_down_2_5d",
        directions: ["left", "right", "up", "down", "up_left", "up_right", "down_left", "down_right"],
      },
    ]);
    animate.mockResolvedValue({
      project_id: "p1",
      action: "walk",
      fps: 8,
      view_mode: "top_down_2_5d",
      direction: "up_left",
      frames: [],
    });
    useProjectStore.setState({
      projectId: "p1",
      viewMode: "top_down_2_5d",
      direction: "down_right",
    });

    render(<AnimatePanel />);

    expect(await screen.findByText("Top-down / 2.5D base sprite")).toBeDefined();
    fireEvent.click(screen.getByRole("radio", { name: "Up-left" }));
    fireEvent.click(screen.getByRole("button", { name: "Generate animation" }));

    await waitFor(() => expect(animate).toHaveBeenCalled());
    expect(animate).toHaveBeenCalledWith("p1", "walk", {
      frames: null,
      direction: "up_left",
    });
    expect(useProjectStore.getState().direction).toBe("up_left");
  });
});
