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

export interface GenerateResult {
  project_id: string;
  sprite_url: string;
  prompt_source: PromptSource;
}

export interface ExportResult {
  sheet_url: string;
  atlas_url: string;
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

async function unwrap<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
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
  } = {},
): Promise<GenerateResult> {
  const form = new FormData();
  form.append("prompt", prompt);
  form.append("style", style);
  form.append("view_mode", opts.viewMode ?? "side_scroller");
  form.append("direction", opts.direction ?? "left");
  if (opts.enhancedPrompt) form.append("enhanced_prompt", opts.enhancedPrompt);
  if (reference) form.append("reference", reference);
  const res = await fetch("/generate", { method: "POST", body: form });
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
): Promise<EnhancePromptResult> {
  const res = await fetch("/prompts/enhance", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  return unwrap<EnhancePromptResult>(res);
}

// POST /export — JSON body.
export async function exportProject(
  projectId: string,
  format: ExportFormat,
  opts: { padding?: number; cols?: number | null } = {},
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
}

// POST /animate — expand the base sprite into an animation. `frames` omitted
// lets the backend use the preset default count.
export async function animate(
  projectId: string,
  action: string,
  opts: { frames?: number | null; fps?: number; direction?: Direction } = {},
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
    }),
  });
  return unwrap<AnimateResult>(res);
}

// POST /animate/frame — regenerate a single frame in place (FrameStrip hatch).
export async function regenerateFrame(
  projectId: string,
  index: number,
): Promise<Frame> {
  const res = await fetch("/animate/frame", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId, index }),
  });
  return unwrap<Frame>(res);
}

// DELETE /animate/frame — remove a frame and re-index the rest (FrameStrip
// hatch). Returns the updated animation like /animate does.
export async function deleteFrame(
  projectId: string,
  index: number,
): Promise<AnimateResult> {
  const res = await fetch("/animate/frame", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId, index }),
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

export async function listPresets(): Promise<Preset[]> {
  return unwrap<Preset[]>(await fetch("/presets"));
}

export async function listAnimationOptions(): Promise<AnimationOptions[]> {
  return unwrap<AnimationOptions[]>(await fetch("/animation-options"));
}

export async function listProjects(): Promise<ProjectSummary[]> {
  return unwrap<ProjectSummary[]>(await fetch("/projects"));
}

export async function getProject(projectId: string): Promise<ProjectDetail> {
  return unwrap<ProjectDetail>(await fetch(`/projects/${projectId}`));
}

export async function deleteProject(projectId: string): Promise<void> {
  const res = await fetch(`/projects/${projectId}`, { method: "DELETE" });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
}
