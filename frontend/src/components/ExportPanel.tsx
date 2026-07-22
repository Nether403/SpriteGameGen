// Export step: choose atlas format, grid columns, and padding; pack + download
// the sheet and atlas.
import { useEffect, useRef, useState } from "react";

import { exportCharacterBundle, exportProject, isAbortError, type ExportFormat } from "../api/client";
import { useProjectStore } from "../state/project";

export function ExportPanel() {
  const {
    projectId,
    frames,
    exportResult,
    exportOptions,
    setExport,
    clearExport,
    mutation,
    beginMutation,
    endMutation,
    activeClipId,
  } = useProjectStore();
  const [format, setFormat] = useState<ExportFormat>("json");
  const [padding, setPadding] = useState(0);
  const [cols, setCols] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bundleUrl, setBundleUrl] = useState<string | null>(null);
  const [bundleScope, setBundleScope] = useState<"active" | "all_enabled">("active");
  const [godot, setGodot] = useState(false);
  const requestRef = useRef<AbortController | null>(null);

  useEffect(() => () => requestRef.current?.abort(), []);
  useEffect(() => setBundleUrl(null), [projectId]);

  const failedCount = frames.filter((frame) => frame.enabled !== false && frame.status === "failed").length;
  const disabled = !projectId || busy || mutation !== null || failedCount > 0;

  async function onExport() {
    if (!projectId) return;
    const token = beginMutation("export", projectId);
    if (token === null) return;
    const controller = new AbortController();
    requestRef.current = controller;
    const options = {
      format,
      padding,
      cols: cols === "" ? null : cols,
    };
    setBusy(true);
    setError(null);
    try {
      const exportRequest = {
        padding: options.padding,
        cols: options.cols,
        signal: controller.signal,
        ...(activeClipId ? { clipId: activeClipId } : {}),
      };
      const result = await exportProject(projectId, format, exportRequest);
      setExport(projectId, result, options);
    } catch (e) {
      if (!isAbortError(e)) setError(e instanceof Error ? e.message : "Export failed.");
    } finally {
      requestRef.current = null;
      setBusy(false);
      endMutation(token);
    }
  }

  async function onBundleExport() {
    if (!projectId) return;
    const expectedProjectId = projectId;
    const token = beginMutation("export", expectedProjectId);
    if (token === null) return;
    setBusy(true);
    setError(null);
    try {
      const result = await exportCharacterBundle(expectedProjectId, {
        scope: bundleScope,
        clipId: bundleScope === "active" ? activeClipId : null,
        engineProfile: godot ? "godot4_animatedsprite2d" : null,
      });
      if (useProjectStore.getState().projectId === expectedProjectId) {
        setBundleUrl(result.bundle_url);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Bundle export failed.");
    } finally {
      setBusy(false);
      endMutation(token);
    }
  }

  return (
    <section className="panel">
      <h2>3. Export</h2>
      <label htmlFor="format">Atlas format</label>
      <select
        id="format"
        value={format}
        onChange={(e) => {
          setFormat(e.target.value as ExportFormat);
          clearExport();
        }}
      >
        <option value="json">JSON</option>
        <option value="xml">XML</option>
      </select>

      <label htmlFor="cols">Columns (blank = automatic)</label>
      <input
        id="cols"
        type="number"
        min={1}
        value={cols}
        placeholder="auto"
        onChange={(e) => {
          setCols(e.target.value === "" ? "" : Number(e.target.value));
          clearExport();
        }}
      />

      <label htmlFor="padding">Padding (px between frames)</label>
      <input
        id="padding"
        type="number"
        min={0}
        value={padding}
        onChange={(e) => {
          setPadding(Math.max(0, Number(e.target.value) || 0));
          clearExport();
        }}
      />

      <button onClick={onExport} disabled={disabled}>
        {busy ? "Packing…" : "Export sprite sheet"}
      </button>

      {!projectId && <p className="hint">Generate a sprite first.</p>}
      {projectId && failedCount > 0 && (
        <p className="hint">Regenerate or disable failed frames before exporting.</p>
      )}
      {error && <p className="error" role="alert">{error}</p>}

      {exportResult && (
        <ul className="downloads">
          <li>
            <a href={exportResult.sheet_url} download>
              Download sheet (PNG)
            </a>
          </li>
          <li>
            <a href={exportResult.atlas_url} download>
              Download atlas ({(exportOptions?.format ?? format).toUpperCase()})
            </a>
          </li>
          {exportResult.frames_url && (
            <li>
              <a href={exportResult.frames_url} download>
                Download individual frames (ZIP)
              </a>
            </li>
          )}
        </ul>
      )}

      <hr />
      <h3>Character bundle</h3>
      <label htmlFor="bundle-scope">Bundle scope</label>
      <select id="bundle-scope" value={bundleScope} onChange={(event) => setBundleScope(event.target.value as typeof bundleScope)}>
        <option value="active">Active clip</option>
        <option value="all_enabled">All enabled clips</option>
      </select>
      <label className="inline-control">
        <input type="checkbox" checked={godot} onChange={(event) => setGodot(event.target.checked)} />
        Include Godot 4.7 AnimatedSprite2D resources
      </label>
      <button type="button" onClick={onBundleExport} disabled={disabled}>Export character bundle</button>
      {bundleUrl && <a href={bundleUrl} download>Download character bundle (ZIP)</a>}
    </section>
  );
}
