// FrameStrip component test (spec §6: light frontend tests). Verifies the
// regenerate/delete callbacks fire with the right frame index and that failed
// frames render a placeholder with a working regenerate button.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { FrameStrip } from "./FrameStrip";
import { useProjectStore } from "../state/project";
import type { Frame } from "../api/client";

const regenerateFrame = vi.fn();
const deleteFrame = vi.fn();
vi.mock("../api/client", () => ({
  regenerateFrame: (pid: string, index: number) => regenerateFrame(pid, index),
  deleteFrame: (pid: string, index: number) => deleteFrame(pid, index),
}));

function seed(frames: Frame[]) {
  useProjectStore.setState({
    projectId: "p1",
    action: "walk",
    fps: 8,
    frames,
    spriteUrl: null,
    style: "pixel",
    exportResult: null,
  });
}

const okFrames: Frame[] = [
  { index: 0, url: "/projects/p1/frame_0.png", status: "ok" },
  { index: 1, url: "/projects/p1/frame_1.png", status: "ok" },
  { index: 2, url: null, status: "failed" },
];

afterEach(() => {
  cleanup();
  regenerateFrame.mockReset();
  deleteFrame.mockReset();
  useProjectStore.setState({ frames: [], action: null, projectId: null });
});

describe("FrameStrip", () => {
  it("renders a thumbnail per frame and a placeholder for failed ones", () => {
    seed(okFrames);
    render(<FrameStrip />);
    expect(screen.getAllByRole("img")).toHaveLength(3); // 2 imgs + 1 placeholder
    expect(screen.getByLabelText("Frame 3 failed")).toBeDefined();
  });

  it("summarizes failures and regenerates failed frames sequentially", async () => {
    seed(okFrames);
    regenerateFrame.mockImplementation(async (_pid: string, index: number) => ({
      index,
      url: `/projects/p1/frame_${index}.png?v=refreshed`,
      status: "ok",
    }));
    render(<FrameStrip />);

    expect(screen.getByRole("status").textContent).toContain("2/3 frames succeeded");
    fireEvent.click(screen.getByRole("button", { name: "Regenerate failed frames" }));

    await waitFor(() => {
      expect(useProjectStore.getState().frames.every((frame) => frame.status === "ok")).toBe(true);
    });
    expect(regenerateFrame).toHaveBeenCalledWith("p1", 2);
  });

  it("regenerates the clicked frame with its index and updates the store", async () => {
    seed(okFrames);
    useProjectStore.setState({
      exportResult: { sheet_url: "/projects/p1/sprite_sheet.png", atlas_url: "/projects/p1/sprite.json" },
    });
    regenerateFrame.mockResolvedValue({
      index: 2,
      url: "/projects/p1/frame_2.png",
      status: "ok",
    });
    render(<FrameStrip />);

    fireEvent.click(screen.getByLabelText("Regenerate frame 3"));
    expect(regenerateFrame).toHaveBeenCalledWith("p1", 2);

    await waitFor(() => {
      expect(useProjectStore.getState().frames[2].status).toBe("ok");
      expect(useProjectStore.getState().exportResult).toBeNull();
    });
  });

  it("deletes the clicked frame via the backend and stores the result", async () => {
    seed(okFrames);
    // Backend returns the re-indexed survivors (the deleted frame is gone).
    deleteFrame.mockResolvedValue({
      project_id: "p1",
      action: "walk",
      fps: 8,
      frames: [
        { index: 0, url: "/projects/p1/frame_0.png", status: "ok" },
        { index: 1, url: null, status: "failed" },
      ],
    });
    render(<FrameStrip />);

    fireEvent.click(screen.getByLabelText("Delete frame 1"));
    expect(deleteFrame).toHaveBeenCalledWith("p1", 0);

    await waitFor(() => {
      const frames = useProjectStore.getState().frames;
      expect(frames).toHaveLength(2);
      expect(frames.map((f) => f.index)).toEqual([0, 1]);
    });
  });

  it("renders nothing without a project or frames", () => {
    useProjectStore.setState({ projectId: null, frames: [] });
    const { container } = render(<FrameStrip />);
    expect(container.firstChild).toBeNull();
  });
});
