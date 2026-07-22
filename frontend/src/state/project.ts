// App state (Zustand). Holds the current project id + sprite, the animation
// frames/action/fps (Stage 2), and the export result.
import { create } from "zustand";

import type {
  Direction,
  AnimationClip,
  ExportResult,
  Frame,
  ImageProviderName,
  ProjectDetail,
  PromptSource,
  Style,
  ViewMode,
  RenderSettings,
} from "../api/client";

export interface ActiveProjectMetadata {
  prompt: string;
  enhancedPrompt: string | null;
  promptSource: PromptSource;
  style: Style;
  viewMode: ViewMode;
  direction: Direction;
  provider: ImageProviderName;
}

export interface ExportOptionsSnapshot {
  format: "json" | "xml";
  padding: number;
  cols: number | null;
}

export type ProjectMutationKind =
  | "generate"
  | "open"
  | "delete"
  | "animate"
  | "frame"
  | "workspace"
  | "export";

export interface ProjectMutation {
  token: number;
  kind: ProjectMutationKind;
  projectId: string | null;
}

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
  provider: ImageProviderName;
  activeProject: ActiveProjectMetadata | null;
  frames: Frame[];
  clips: Record<string, AnimationClip>;
  activeClipId: string | null;
  renderSettings: RenderSettings;
  action: string | null;
  fps: number;
  exportResult: ExportResult | null;
  exportOptions: ExportOptionsSnapshot | null;
  mutation: ProjectMutation | null;

  setStyle: (style: Style) => void;
  setViewMode: (viewMode: ViewMode) => void;
  setDirection: (direction: Direction) => void;
  setProvider: (provider: ImageProviderName) => void;
  setActiveDirection: (direction: Direction) => void;
  setActiveProvider: (provider: ImageProviderName) => void;
  setPrompt: (prompt: string) => void;
  setEnhancedPrompt: (prompt: string) => void;
  acceptEnhancedPrompt: () => void;
  useRawPrompt: () => void;
  setGenerated: (
    projectId: string,
    spriteUrl: string,
    prompt: string,
    provider?: ImageProviderName,
    metadata?: Omit<ActiveProjectMetadata, "prompt" | "provider">,
  ) => void;
  loadProject: (project: ProjectDetail, expectedProjectId?: string | null) => void;
  setAnimation: (
    expectedProjectId: string,
    action: string,
    fps: number,
    frames: Frame[],
    direction?: Direction,
    provider?: ImageProviderName,
    clipId?: string,
  ) => void;
  setFrame: (expectedProjectId: string, frame: Frame, expectedClipId?: string | null) => void;
  setExport: (
    expectedProjectId: string,
    result: ExportResult,
    options: ExportOptionsSnapshot,
  ) => void;
  clearExport: () => void;
  beginMutation: (kind: ProjectMutationKind, projectId: string | null) => number | null;
  endMutation: (token: number) => void;
  reset: () => void;
}

const initialAnimation = {
  frames: [] as Frame[],
  action: null as string | null,
  fps: 8,
  clips: {} as Record<string, AnimationClip>,
  activeClipId: null as string | null,
  renderSettings: {
    target_width: null,
    target_height: null,
    output_scale: 1,
    color_limit: 32,
    palette_mode: "auto" as const,
    preset_palette: null,
    custom_palette: [],
  },
};

let nextMutationToken = 1;

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
  provider: "auto",
  activeProject: null,
  ...initialAnimation,
  exportResult: null,
  exportOptions: null,
  mutation: null,

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
  setProvider: (provider) => set({ provider }),
  setActiveDirection: (direction) =>
    set((state) => ({
      activeProject: state.activeProject
        ? { ...state.activeProject, direction }
        : null,
    })),
  setActiveProvider: (provider) =>
    set((state) => ({
      activeProject: state.activeProject
        ? { ...state.activeProject, provider }
        : null,
    })),
  setPrompt: (prompt) =>
    set({ prompt, enhancedPrompt: null, promptSource: "raw" }),
  setEnhancedPrompt: (enhancedPrompt) =>
    set({ enhancedPrompt, promptSource: "raw" }),
  acceptEnhancedPrompt: () =>
    set((state) => ({
      promptSource: state.enhancedPrompt?.trim() ? "enhanced" : "raw",
    })),
  useRawPrompt: () => set({ enhancedPrompt: null, promptSource: "raw" }),
  setGenerated: (projectId, spriteUrl, prompt, provider, metadata) =>
    set((state) => ({
      projectId,
      prompt,
      spriteUrl,
      activeProject: {
        prompt,
        enhancedPrompt: metadata?.enhancedPrompt ?? state.enhancedPrompt,
        promptSource: metadata?.promptSource ?? state.promptSource,
        style: metadata?.style ?? state.style,
        viewMode: metadata?.viewMode ?? state.viewMode,
        direction: metadata?.direction ?? state.direction,
        provider: provider ?? state.provider,
      },
      ...initialAnimation,
      exportResult: null,
      exportOptions: null,
      catalogRevision: state.catalogRevision + 1,
    })),
  loadProject: (project, expectedProjectId) =>
    set((state) => {
      if (expectedProjectId !== undefined && state.projectId !== expectedProjectId) return state;
      const activeProject: ActiveProjectMetadata = {
        prompt: project.prompt,
        enhancedPrompt: project.enhanced_prompt,
        promptSource: project.prompt_source,
        style: project.style,
        viewMode: project.view_mode,
        direction: project.direction,
        provider: project.image_provider ?? "gemini",
      };
       const clips = project.clips ?? {};
       const activeClipId = project.active_clip_id ?? null;
       const activeClip = activeClipId ? clips[activeClipId] : undefined;
       return {
        projectId: project.id,
        prompt: project.prompt,
        enhancedPrompt: project.enhanced_prompt,
        promptSource: project.prompt_source,
        spriteUrl: project.sprite_url,
        style: project.style,
        viewMode: project.view_mode,
        direction: project.direction,
        provider: project.image_provider ?? "gemini",
        activeProject,
        clips,
        activeClipId,
        renderSettings: project.render_settings ?? initialAnimation.renderSettings,
        frames: activeClip?.frames ?? project.frames,
        action: activeClip?.action ?? project.action,
        fps: activeClip?.fps ?? project.fps ?? 8,
        exportResult: null,
        exportOptions: null,
      };
    }),
  setAnimation: (expectedProjectId, action, fps, frames, direction, provider, clipId) =>
    set((state) => {
      if (state.projectId !== expectedProjectId) return state;
      const selectedClipId = clipId ?? state.activeClipId;
      const existingClip = selectedClipId ? state.clips[selectedClipId] : undefined;
      return {
        action,
        fps,
        frames,
        activeClipId: selectedClipId,
        clips: selectedClipId
          ? {
              ...state.clips,
              [selectedClipId]: {
                id: selectedClipId,
                name: existingClip?.name ?? action,
                action,
                direction: direction ?? existingClip?.direction ?? "left",
                fps,
                loop_mode: existingClip?.loop_mode ?? "loop",
                loop_start: existingClip?.loop_start ?? 0,
                loop_end: existingClip?.loop_end ?? (frames.length ? frames.length - 1 : null),
                enabled: existingClip?.enabled ?? true,
                horizontal_flip: existingClip?.horizontal_flip ?? false,
                frames,
              },
            }
          : state.clips,
        activeProject: state.activeProject
          ? {
              ...state.activeProject,
              direction: direction ?? state.activeProject.direction,
              provider: provider ?? state.activeProject.provider,
            }
          : null,
        exportResult: null,
        exportOptions: null,
        catalogRevision: state.catalogRevision + 1,
      };
    }),
  setFrame: (expectedProjectId, frame, expectedClipId) =>
    set((state) => {
      if (state.projectId !== expectedProjectId) return state;
      if (expectedClipId !== undefined && state.activeClipId !== expectedClipId) return state;
      const frames = state.frames.map((f) => (f.index === frame.index ? frame : f));
      return {
        frames,
        clips: state.activeClipId && state.clips[state.activeClipId]
          ? {
              ...state.clips,
              [state.activeClipId]: { ...state.clips[state.activeClipId], frames },
            }
          : state.clips,
        exportResult: null,
        exportOptions: null,
        catalogRevision: state.catalogRevision + 1,
      };
    }),
  setExport: (expectedProjectId, exportResult, exportOptions) =>
    set((state) =>
      state.projectId === expectedProjectId
        ? { exportResult, exportOptions }
        : state,
    ),
  clearExport: () => set({ exportResult: null, exportOptions: null }),
  beginMutation: (kind, projectId) => {
    let acquired: number | null = null;
    set((state) => {
      if (state.mutation !== null) return state;
      acquired = nextMutationToken++;
      return { mutation: { token: acquired, kind, projectId } };
    });
    return acquired;
  },
  endMutation: (token) =>
    set((state) =>
      state.mutation?.token === token ? { mutation: null } : state,
    ),
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
      provider: "auto",
      activeProject: null,
      ...initialAnimation,
      exportResult: null,
      exportOptions: null,
      mutation: null,
      catalogRevision: state.catalogRevision + 1,
    })),
}));
