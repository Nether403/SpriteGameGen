// App state (Zustand). Holds the current project id + sprite, the animation
// frames/action/fps (Stage 2), and the export result.
import { create } from "zustand";

import type { ExportResult, Frame, Style } from "../api/client";

interface ProjectState {
  projectId: string | null;
  spriteUrl: string | null;
  style: Style;
  frames: Frame[];
  action: string | null;
  fps: number;
  exportResult: ExportResult | null;

  setStyle: (style: Style) => void;
  setGenerated: (projectId: string, spriteUrl: string) => void;
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
  spriteUrl: null,
  style: "pixel",
  ...initialAnimation,
  exportResult: null,

  setStyle: (style) => set({ style }),
  setGenerated: (projectId, spriteUrl) =>
    set({ projectId, spriteUrl, ...initialAnimation, exportResult: null }),
  setAnimation: (action, fps, frames) => set({ action, fps, frames, exportResult: null }),
  setFrame: (frame) =>
    set((state) => ({
      frames: state.frames.map((f) => (f.index === frame.index ? frame : f)),
    })),
  setExport: (exportResult) => set({ exportResult }),
  reset: () =>
    set({ projectId: null, spriteUrl: null, ...initialAnimation, exportResult: null }),
}));
