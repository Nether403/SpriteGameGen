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
      expect(exportProject).toHaveBeenCalledWith("p1", "json", {
        padding: 0,
        cols: null,
        signal: expect.any(AbortSignal),
      });
    });
  });

  it("labels a completed export with the options that produced it", async () => {
    seed("ok");
    let finishExport!: (result: { sheet_url: string; atlas_url: string }) => void;
    exportProject.mockReturnValue(
      new Promise((resolve) => {
        finishExport = resolve;
      }),
    );
    render(<ExportPanel />);

    fireEvent.click(screen.getByRole("button", { name: "Export sprite sheet" }));
    fireEvent.change(screen.getByLabelText("Atlas format"), {
      target: { value: "xml" },
    });
    finishExport({ sheet_url: "sheet", atlas_url: "atlas" });

    expect(await screen.findByRole("link", { name: "Download atlas (JSON)" })).toBeDefined();
  });

  it("clears download links when export options change", async () => {
    seed("ok");
    exportProject.mockResolvedValue({ sheet_url: "sheet", atlas_url: "atlas" });
    render(<ExportPanel />);

    fireEvent.click(screen.getByRole("button", { name: "Export sprite sheet" }));
    expect(await screen.findByRole("link", { name: "Download atlas (JSON)" })).toBeDefined();

    fireEvent.change(screen.getByLabelText("Padding (px between frames)"), {
      target: { value: "2" },
    });
    expect(screen.queryByRole("link", { name: /Download atlas/ })).toBeNull();
  });
});
