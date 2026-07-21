import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { useProjectStore } from "../state/project";
import { GeneratePanel } from "./GeneratePanel";

const generate = vi.fn();
const enhancePrompt = vi.fn();
const listAnimationOptions = vi.fn();
vi.mock("../api/client", () => ({
  generate: (...args: unknown[]) => generate(...args),
  enhancePrompt: (...args: unknown[]) => enhancePrompt(...args),
  listAnimationOptions: () => listAnimationOptions(),
}));

const options = [
  { view_mode: "side_scroller", directions: ["left", "right"] },
  {
    view_mode: "top_down_2_5d",
    directions: [
      "left", "right", "up", "down", "up_left", "up_right", "down_left", "down_right",
    ],
  },
];

afterEach(() => {
  cleanup();
  generate.mockReset();
  enhancePrompt.mockReset();
  listAnimationOptions.mockReset();
  useProjectStore.getState().reset();
});

describe("GeneratePanel directions", () => {
  it("shows camera-aware directions and submits the selected context", async () => {
    listAnimationOptions.mockResolvedValue(options);
    generate.mockResolvedValue({ project_id: "p1", sprite_url: "sprite.png" });
    render(<GeneratePanel />);

    await screen.findByRole("radio", { name: "Left" });
    expect(screen.queryByRole("radio", { name: "Up" })).toBeNull();

    fireEvent.click(screen.getByRole("radio", { name: "Top-down / 2.5D" }));
    fireEvent.click(screen.getByRole("radio", { name: "Up-left" }));
    fireEvent.change(screen.getByLabelText("Describe your sprite"), {
      target: { value: "a knight" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate sprite" }));

    await waitFor(() => expect(generate).toHaveBeenCalled());
    expect(generate).toHaveBeenCalledWith("a knight", "pixel", null, {
      viewMode: "top_down_2_5d",
      direction: "up_left",
      enhancedPrompt: null,
    });
  });

  it("previews, edits, and explicitly accepts enhancement before generation", async () => {
    listAnimationOptions.mockResolvedValue(options);
    enhancePrompt.mockResolvedValue({
      original_prompt: "a knight",
      enhanced_prompt: "a silver-armored knight",
    });
    generate.mockResolvedValue({ project_id: "p1", sprite_url: "sprite.png" });
    render(<GeneratePanel />);

    await screen.findByRole("radio", { name: "Left" });
    fireEvent.change(screen.getByLabelText("Describe your sprite"), {
      target: { value: "a knight" },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: "Enhance my prompt" }));
    expect(enhancePrompt).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Preview enhanced prompt" }));
    const preview = await screen.findByLabelText("Enhanced prompt preview");
    fireEvent.change(preview, { target: { value: "an edited silver knight" } });
    fireEvent.click(screen.getByRole("button", { name: "Use enhanced prompt" }));
    fireEvent.click(screen.getByRole("button", { name: "Generate sprite" }));

    await waitFor(() => expect(generate).toHaveBeenCalled());
    expect(generate.mock.calls[generate.mock.calls.length - 1]?.[3]).toMatchObject({
      enhancedPrompt: "an edited silver knight",
    });

    fireEvent.click(screen.getByRole("button", { name: "Revert to original" }));
    expect(useProjectStore.getState()).toMatchObject({
      enhancedPrompt: null,
      promptSource: "raw",
      prompt: "a knight",
    });
  });

  it("keeps raw generation available when enhancement fails", async () => {
    listAnimationOptions.mockResolvedValue(options);
    enhancePrompt.mockRejectedValue(new Error("Text model unavailable"));
    generate.mockResolvedValue({ project_id: "p1", sprite_url: "sprite.png" });
    render(<GeneratePanel />);

    await screen.findByRole("radio", { name: "Left" });
    fireEvent.change(screen.getByLabelText("Describe your sprite"), {
      target: { value: "a knight" },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: "Enhance my prompt" }));
    fireEvent.click(screen.getByRole("button", { name: "Preview enhanced prompt" }));
    expect(await screen.findByText("Text model unavailable")).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Generate sprite" }));
    await waitFor(() => expect(generate).toHaveBeenCalled());
    expect(generate.mock.calls[generate.mock.calls.length - 1]?.[3]).toMatchObject({
      enhancedPrompt: null,
    });
  });
});
