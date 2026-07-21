// App state (Zustand). Holds the current project id + sprite, the animation
// frames/action/fps (Stage 2), and the export result.
import { create } from "zustand";

import type {
  Direction,
  ExportResult,
  Frame,
  ProjectDetail,
  PromptSource,
  Style,
  ViewMode,
} from "../api/client";

interface ProjectState {
  projectId: string | null;
  catalogRevision: number;
  prompt: string;
  enhancedPrompt: string | null;
  promptSource: PromptSource;
  spriteUrl: string | null;
  style: Style;
  viewMode: ViewMode;
  direction: Direction;
  frames: Frame[];
  action: string | null;
  fps: number;
  exportResult: ExportResult | null;

  setStyle: (style: Style) => void;
  setViewMode: (viewMode: ViewMode) => void;
  setDirection: (direction: Direction) => void;
  setPrompt: (prompt: string) => void;
  setEnhancedPrompt: (prompt: string) => void;
  acceptEnhancedPrompt: () => void;
  useRawPrompt: () => void;
  setGenerated: (projectId: string, spriteUrl: string, prompt: string) => void;
  loadProject: (project: ProjectDetail) => void;
  setAnimation: (
    action: string,
    fps: number,
    frames: Frame[],
    direction?: Direction,
  ) => void;
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
  enhancedPrompt: null,
  promptSource: "raw",
  spriteUrl: null,
  style: "pixel",
  viewMode: "side_scroller",
  direction: "left",
  ...initialAnimation,
  exportResult: null,

  setStyle: (style) =>
    set({ style, enhancedPrompt: null, promptSource: "raw" }),
  setViewMode: (viewMode) =>
    set({
      viewMode,
      direction: viewMode === "side_scroller" ? "left" : "down",
      enhancedPrompt: null,
      promptSource: "raw",
    }),
  setDirection: (direction) =>
    set({ direction, enhancedPrompt: null, promptSource: "raw" }),
  setPrompt: (prompt) =>
    set({ prompt, enhancedPrompt: null, promptSource: "raw" }),
  setEnhancedPrompt: (enhancedPrompt) =>
    set({ enhancedPrompt, promptSource: "raw" }),
  acceptEnhancedPrompt: () =>
    set((state) => ({
      promptSource: state.enhancedPrompt?.trim() ? "enhanced" : "raw",
    })),
  useRawPrompt: () => set({ enhancedPrompt: null, promptSource: "raw" }),
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
      enhancedPrompt: project.enhanced_prompt,
      promptSource: project.prompt_source,
      spriteUrl: project.sprite_url,
      style: project.style,
      viewMode: project.view_mode,
      direction: project.direction,
      frames: project.frames,
      action: project.action,
      fps: project.fps ?? 8,
      exportResult: null,
    }),
  setAnimation: (action, fps, frames, direction) =>
    set((state) => ({
      action,
      fps,
      frames,
      direction: direction ?? state.direction,
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
      enhancedPrompt: null,
      promptSource: "raw",
      spriteUrl: null,
      style: "pixel",
      viewMode: "side_scroller",
      direction: "left",
      ...initialAnimation,
      exportResult: null,
      catalogRevision: state.catalogRevision + 1,
    })),
}));
