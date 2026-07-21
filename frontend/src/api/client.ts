// Typed API client. Request shaping lives here (and is unit-tested with a mocked
// fetch). Errors surface the backend's `detail` message so the UI can show it.

export type Style = "pixel" | "hires";
export type ViewMode = "side_scroller" | "top_down_2_5d";
export type Direction =
  | "left"
  | "right"
  | "up"
  | "down"
  | "up_left"
  | "up_right"
  | "down_left"
  | "down_right";
export type ExportFormat = "json" | "xml";
export type FrameStatus = "ok" | "failed";
export type PromptSource = "raw" | "enhanced";
export type ImageProviderName = "auto" | "azure" | "gemini" | "hyperagent";

export interface GenerateResult {
  project_id: string;
  sprite_url: string;
  prompt_source: PromptSource;
  provider: ImageProviderName;
}

export interface ExportResult {
  sheet_url: string;
  atlas_url: string;
}

export interface RequestOptions {
  signal?: AbortSignal;
}

export interface Frame {
  index: number;
  url: string | null;
  status: FrameStatus;
}

export interface Project {
  id: string;
  schema_version: number;
  prompt: string;
  enhanced_prompt: string | null;
  prompt_source: PromptSource;
  image_provider: ImageProviderName;
  style: Style;
  view_mode: ViewMode;
  direction: Direction;
  frames: Frame[];
  action: string | null;
  fps: number | null;
  created_at: string;
  updated_at: string;
}

export type ProjectHealth = "ready" | "incomplete" | "corrupt";

export interface ProjectSummary {
  id: string;
  prompt_preview: string | null;
  style: Style | null;
  view_mode: ViewMode | null;
  direction: Direction | null;
  thumbnail_url: string | null;
  action: string | null;
  fps: number | null;
  frame_count: number;
  ok_count: number;
  failed_count: number;
  created_at: string;
  updated_at: string;
  health: ProjectHealth;
  resume_available: boolean;
}

export interface ProjectDetail extends Project {
  sprite_url: string | null;
  health: ProjectHealth;
  resume_available: boolean;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

async function unwrap<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText.trim();
    try {
      const body = await res.json();
      if (body?.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new ApiError(res.status, detail || `Request failed (${res.status})`);
  }
  return (await res.json()) as T;
}

async function unwrapEmpty(res: Response): Promise<void> {
  if (!res.ok) await unwrap<never>(res);
}

// POST /generate — multipart form (prompt + style + optional reference file).
export async function generate(
  prompt: string,
  style: Style,
  reference?: File | null,
  opts: {
    viewMode?: ViewMode;
    direction?: Direction;
    enhancedPrompt?: string | null;
    provider?: ImageProviderName;
    signal?: AbortSignal;
  } = {},
): Promise<GenerateResult> {
  const form = new FormData();
  form.append("prompt", prompt);
  form.append("style", style);
  form.append("view_mode", opts.viewMode ?? "side_scroller");
  form.append("direction", opts.direction ?? "left");
  form.append("provider", opts.provider ?? "auto");
  if (opts.enhancedPrompt) form.append("enhanced_prompt", opts.enhancedPrompt);
  if (reference) form.append("reference", reference);
  const res = await fetch("/generate", { method: "POST", body: form, signal: opts.signal });
  return unwrap<GenerateResult>(res);
}

export interface EnhancePromptRequest {
  prompt: string;
  style: Style;
  view_mode: ViewMode;
  direction: Direction;
}

export interface EnhancePromptResult {
  original_prompt: string;
  enhanced_prompt: string;
}

export async function enhancePrompt(
  request: EnhancePromptRequest,
  options: RequestOptions = {},
): Promise<EnhancePromptResult> {
  const res = await fetch("/prompts/enhance", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal: options.signal,
  });
  return unwrap<EnhancePromptResult>(res);
}

// POST /export — JSON body.
export async function exportProject(
  projectId: string,
  format: ExportFormat,
  opts: { padding?: number; cols?: number | null; signal?: AbortSignal } = {},
): Promise<ExportResult> {
  const res = await fetch("/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: projectId,
      format,
      padding: opts.padding ?? 0,
      cols: opts.cols ?? null,
    }),
    signal: opts.signal,
  });
  return unwrap<ExportResult>(res);
}

export interface AnimateResult {
  project_id: string;
  action: string;
  fps: number;
  view_mode: ViewMode;
  direction: Direction;
  frames: Frame[];
  provider: ImageProviderName;
}

// POST /animate — expand the base sprite into an animation. `frames` omitted
// lets the backend use the preset default count.
export async function animate(
  projectId: string,
  action: string,
  opts: {
    frames?: number | null;
    fps?: number;
    direction?: Direction;
    provider?: ImageProviderName;
    signal?: AbortSignal;
  } = {},
): Promise<AnimateResult> {
  const res = await fetch("/animate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: projectId,
      action,
      frames: opts.frames ?? null,
      fps: opts.fps ?? 8,
      direction: opts.direction ?? "left",
      ...(opts.provider ? { provider: opts.provider } : {}),
    }),
    signal: opts.signal,
  });
  return unwrap<AnimateResult>(res);
}

// POST /animate/frame — regenerate a single frame in place (FrameStrip hatch).
export async function regenerateFrame(
  projectId: string,
  index: number,
  provider?: ImageProviderName,
  options: RequestOptions = {},
): Promise<Frame> {
  const res = await fetch("/animate/frame", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: projectId,
      index,
      ...(provider ? { provider } : {}),
    }),
    signal: options.signal,
  });
  return unwrap<Frame>(res);
}

// DELETE /animate/frame — remove a frame and re-index the rest (FrameStrip
// hatch). Returns the updated animation like /animate does.
export async function deleteFrame(
  projectId: string,
  index: number,
  options: RequestOptions = {},
): Promise<AnimateResult> {
  const res = await fetch("/animate/frame", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId, index }),
    signal: options.signal,
  });
  return unwrap<AnimateResult>(res);
}

export interface Preset {
  action: string;
  min_frames: number;
  max_frames: number;
  default_frames: number;
  pose: string;
}

export interface AnimationOptions {
  view_mode: ViewMode;
  directions: Direction[];
}

export interface ImageProviderOption {
  id: ImageProviderName;
  label: string;
  available: boolean;
  experimental: boolean;
  description: string;
  unavailable_reason: string | null;
}

export async function listPresets(options: RequestOptions = {}): Promise<Preset[]> {
  return unwrap<Preset[]>(await fetch("/presets", { signal: options.signal }));
}

export async function listAnimationOptions(options: RequestOptions = {}): Promise<AnimationOptions[]> {
  return unwrap<AnimationOptions[]>(await fetch("/animation-options", { signal: options.signal }));
}

export async function listImageProviders(options: RequestOptions = {}): Promise<ImageProviderOption[]> {
  return unwrap<ImageProviderOption[]>(await fetch("/image-providers", { signal: options.signal }));
}

export async function listProjects(options: RequestOptions = {}): Promise<ProjectSummary[]> {
  return unwrap<ProjectSummary[]>(await fetch("/projects", { signal: options.signal }));
}

export async function getProject(
  projectId: string,
  options: RequestOptions = {},
): Promise<ProjectDetail> {
  return unwrap<ProjectDetail>(
    await fetch(`/projects/${encodeURIComponent(projectId)}`, { signal: options.signal }),
  );
}

export async function deleteProject(
  projectId: string,
  options: RequestOptions = {},
): Promise<void> {
  await unwrapEmpty(
    await fetch(`/projects/${encodeURIComponent(projectId)}`, {
      method: "DELETE",
      signal: options.signal,
    }),
  );
}
