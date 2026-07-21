import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { ProjectDetail, ProjectSummary } from "../api/client";
import { useProjectStore } from "../state/project";
import { ProjectBrowser } from "./ProjectBrowser";

const listProjects = vi.fn();
const getProject = vi.fn();
const deleteProject = vi.fn();
vi.mock("../api/client", () => ({
  listProjects: () => listProjects(),
  getProject: (id: string) => getProject(id),
  deleteProject: (id: string) => deleteProject(id),
}));

const ready: ProjectSummary = {
  id: "p1",
  prompt_preview: "a knight",
  style: "pixel",
  thumbnail_url: "/projects/p1/sprite.png?v=1",
  action: "walk",
  fps: 8,
  frame_count: 6,
  ok_count: 6,
  failed_count: 0,
  created_at: "2026-07-21T10:00:00Z",
  updated_at: "2026-07-21T10:01:00Z",
  health: "ready",
  resume_available: true,
};

const broken: ProjectSummary = {
  ...ready,
  id: "broken",
  prompt_preview: null,
  thumbnail_url: null,
  health: "corrupt",
  resume_available: false,
};

const detail: ProjectDetail = {
  id: "p1",
  schema_version: 1,
  prompt: "a knight",
  style: "pixel",
  frames: [],
  action: "walk",
  fps: 8,
  created_at: ready.created_at,
  updated_at: ready.updated_at,
  sprite_url: ready.thumbnail_url,
  health: "ready",
  resume_available: true,
};

afterEach(() => {
  cleanup();
  listProjects.mockReset();
  getProject.mockReset();
  deleteProject.mockReset();
  vi.restoreAllMocks();
  useProjectStore.getState().reset();
});

describe("ProjectBrowser", () => {
  it("loads the catalog and resumes a selected project", async () => {
    listProjects.mockResolvedValue([ready]);
    getProject.mockResolvedValue(detail);
    render(<ProjectBrowser />);

    expect(screen.getByRole("status").textContent).toContain("Loading saved projects");
    await waitFor(() => expect((screen.getByRole("button", { name: "Open project" }) as HTMLButtonElement).disabled).toBe(false));

    fireEvent.click(screen.getByRole("button", { name: "Open project" }));
    await waitFor(() => expect(useProjectStore.getState().projectId).toBe("p1"));
    expect(getProject).toHaveBeenCalledWith("p1");
  });

  it("explains unhealthy projects and deletes after confirmation", async () => {
    listProjects.mockResolvedValue([ready, broken]);
    deleteProject.mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<ProjectBrowser />);

    await waitFor(() => expect(screen.getByText("Cannot read manifest")).toBeDefined());
    expect((screen.getByRole("button", { name: "Cannot resume" }) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Delete project broken" }));
    await waitFor(() => expect(deleteProject).toHaveBeenCalledWith("broken"));
    expect(screen.queryByText("Unreadable project")).toBeNull();
  });
});
