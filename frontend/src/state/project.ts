// App state (Zustand). Holds the current project id + sprite, the animation
// frames/action/fps (Stage 2), and the export result.
import { create } from "zustand";

import type { ExportResult, Frame, ProjectDetail, Style } from "../api/client";

interface ProjectState {
  projectId: string | null;
  catalogRevision: number;
  prompt: string;
  spriteUrl: string | null;
  style: Style;
  frames: Frame[];
  action: string | null;
  fps: number;
  exportResult: ExportResult | null;

  setStyle: (style: Style) => void;
  setPrompt: (prompt: string) => void;
  setGenerated: (projectId: string, spriteUrl: string, prompt: string) => void;
  loadProject: (project: ProjectDetail) => void;
  setAnimation: (action: string, fps: number, frames: Frame[]) => void;
  setFrame: (frame: Frame) => void;
  setExport: (result: ExportResult) => void;
  reset: () => void;
}

const initialAnimation = {
  frames: [] as Frame[],
  action: null as string | null,
  fps: 8,
};

export const useProjectStore = create<ProjectState>((set) => ({
  projectId: null,
  catalogRevision: 0,
  prompt: "",
  spriteUrl: null,
  style: "pixel",
  ...initialAnimation,
  exportResult: null,

  setStyle: (style) => set({ style }),
  setPrompt: (prompt) => set({ prompt }),
  setGenerated: (projectId, spriteUrl, prompt) =>
    set((state) => ({
      projectId,
      prompt,
      spriteUrl,
      ...initialAnimation,
      exportResult: null,
      catalogRevision: state.catalogRevision + 1,
    })),
  loadProject: (project) =>
    set({
      projectId: project.id,
      prompt: project.prompt,
      spriteUrl: project.sprite_url,
      style: project.style,
      frames: project.frames,
      action: project.action,
      fps: project.fps ?? 8,
      exportResult: null,
    }),
  setAnimation: (action, fps, frames) =>
    set((state) => ({
      action,
      fps,
      frames,
      exportResult: null,
      catalogRevision: state.catalogRevision + 1,
    })),
  setFrame: (frame) =>
    set((state) => ({
      frames: state.frames.map((f) => (f.index === frame.index ? frame : f)),
      exportResult: null,
      catalogRevision: state.catalogRevision + 1,
    })),
  setExport: (exportResult) => set({ exportResult }),
  reset: () =>
    set((state) => ({
      projectId: null,
      prompt: "",
      spriteUrl: null,
      ...initialAnimation,
      exportResult: null,
      catalogRevision: state.catalogRevision + 1,
    })),
}));
