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
  prompt: string;
  style: Style;
  frames: Frame[];
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

export async function listProjects(): Promise<Project[]> {
  return unwrap<Project[]>(await fetch("/projects"));
}

export async function deleteProject(projectId: string): Promise<void> {
  const res = await fetch(`/projects/${projectId}`, { method: "DELETE" });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
}
