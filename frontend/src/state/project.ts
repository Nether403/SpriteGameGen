// App state (Zustand). Holds the current project id + sprite and export result.
// Stage 2 will extend this with frames/action/fps.
import { create } from "zustand";

import type { ExportResult, Style } from "../api/client";

interface ProjectState {
  projectId: string | null;
  spriteUrl: string | null;
  style: Style;
  exportResult: ExportResult | null;

  setStyle: (style: Style) => void;
  setGenerated: (projectId: string, spriteUrl: string) => void;
  setExport: (result: ExportResult) => void;
  reset: () => void;
}

export const useProjectStore = create<ProjectState>((set) => ({
  projectId: null,
  spriteUrl: null,
  style: "pixel",
  exportResult: null,

  setStyle: (style) => set({ style }),
  setGenerated: (projectId, spriteUrl) =>
    set({ projectId, spriteUrl, exportResult: null }),
  setExport: (exportResult) => set({ exportResult }),
  reset: () => set({ projectId: null, spriteUrl: null, exportResult: null }),
}));
