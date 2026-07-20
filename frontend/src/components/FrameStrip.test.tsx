// FrameStrip component test (spec §6: light frontend tests). Verifies the
// regenerate/delete callbacks fire with the right frame index and that failed
// frames render a placeholder with a working regenerate button.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { FrameStrip } from "./FrameStrip";
import { useProjectStore } from "../state/project";
import type { Frame } from "../api/client";

const regenerateFrame = vi.fn();
vi.mock("../api/client", () => ({
  regenerateFrame: (pid: string, index: number) => regenerateFrame(pid, index),
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
  useProjectStore.setState({ frames: [], action: null, projectId: null });
});

describe("FrameStrip", () => {
  it("renders a thumbnail per frame and a placeholder for failed ones", () => {
    seed(okFrames);
    render(<FrameStrip />);
    expect(screen.getAllByRole("img")).toHaveLength(3); // 2 imgs + 1 placeholder
    expect(screen.getByLabelText("Frame 3 failed")).toBeDefined();
  });

  it("regenerates the clicked frame with its index and updates the store", async () => {
    seed(okFrames);
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
    });
  });

  it("deletes the clicked frame and re-indexes the remainder", () => {
    seed(okFrames);
    render(<FrameStrip />);

    fireEvent.click(screen.getByLabelText("Delete frame 1"));

    const frames = useProjectStore.getState().frames;
    expect(frames).toHaveLength(2);
    // remaining frames re-indexed contiguously starting at 0
    expect(frames.map((f) => f.index)).toEqual([0, 1]);
    // the surviving urls are the ones that were not deleted
    expect(frames[0].url).toBe("/projects/p1/frame_1.png");
  });

  it("renders nothing without a project or frames", () => {
    useProjectStore.setState({ projectId: null, frames: [] });
    const { container } = render(<FrameStrip />);
    expect(container.firstChild).toBeNull();
  });
});
