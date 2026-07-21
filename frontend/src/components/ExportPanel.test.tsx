import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { ExportPanel } from "./ExportPanel";
import { useProjectStore } from "../state/project";

const exportProject = vi.fn();
vi.mock("../api/client", () => ({
  exportProject: (pid: string, format: string, options: unknown) => exportProject(pid, format, options),
}));

function seed(status: "ok" | "failed") {
  useProjectStore.setState({
    projectId: "p1",
    spriteUrl: "/projects/p1/sprite.png?v=1",
    style: "pixel",
    action: "walk",
    fps: 8,
    frames: [
      { index: 0, url: "/projects/p1/frame_0.png?v=1", status },
      { index: 1, url: status === "ok" ? "/projects/p1/frame_1.png?v=1" : null, status },
    ],
    exportResult: null,
  });
}

afterEach(() => {
  cleanup();
  exportProject.mockReset();
  useProjectStore.setState({ projectId: null, frames: [], action: null, exportResult: null });
});

describe("ExportPanel", () => {
  it("blocks export while failed frames remain", () => {
    seed("failed");
    render(<ExportPanel />);

    expect((screen.getByRole("button", { name: "Export sprite sheet" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/Regenerate or delete failed frames/)).toBeDefined();
  });

  it("allows export when every animation frame succeeded", async () => {
    seed("ok");
    exportProject.mockResolvedValue({ sheet_url: "sheet", atlas_url: "atlas" });
    render(<ExportPanel />);

    const button = screen.getByRole("button", { name: "Export sprite sheet" });
    expect((button as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(button);
    await waitFor(() => {
      expect(exportProject).toHaveBeenCalledWith("p1", "json", { padding: 0, cols: null });
    });
  });
});
