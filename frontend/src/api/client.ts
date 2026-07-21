// Typed API client. Request shaping lives here (and is unit-tested with a mocked
// fetch). Errors surface the backend's `detail` message so the UI can show it.

export type Style = "pixel" | "hires";
export type ExportFormat = "json" | "xml";
export type FrameStatus = "ok" | "failed";

export interface GenerateResult {
  project_id: string;
  sprite_url: string;
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
  style: Style;
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
): Promise<GenerateResult> {
  const form = new FormData();
  form.append("prompt", prompt);
  form.append("style", style);
  if (reference) form.append("reference", reference);
  const res = await fetch("/generate", { method: "POST", body: form });
  return unwrap<GenerateResult>(res);
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
  frames: Frame[];
}

// POST /animate — expand the base sprite into an animation. `frames` omitted
// lets the backend use the preset default count.
export async function animate(
  projectId: string,
  action: string,
  opts: { frames?: number | null; fps?: number } = {},
): Promise<AnimateResult> {
  const res = await fetch("/animate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: projectId,
      action,
      frames: opts.frames ?? null,
      fps: opts.fps ?? 8,
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

export async function listPresets(): Promise<Preset[]> {
  return unwrap<Preset[]>(await fetch("/presets"));
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
