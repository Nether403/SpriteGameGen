// Export step: choose atlas format, grid columns, and padding; pack + download
// the sheet and atlas.
import { useEffect, useRef, useState } from "react";

import { exportProject, isAbortError, type ExportFormat } from "../api/client";
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
  } = useProjectStore();
  const [format, setFormat] = useState<ExportFormat>("json");
  const [padding, setPadding] = useState(0);
  const [cols, setCols] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestRef = useRef<AbortController | null>(null);

  useEffect(() => () => requestRef.current?.abort(), []);

  const failedCount = frames.filter((frame) => frame.status === "failed").length;
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
      const result = await exportProject(projectId, format, {
        padding: options.padding,
        cols: options.cols,
        signal: controller.signal,
      });
      setExport(projectId, result, options);
    } catch (e) {
      if (!isAbortError(e)) setError(e instanceof Error ? e.message : "Export failed.");
    } finally {
      requestRef.current = null;
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
        <p className="hint">Regenerate or delete failed frames before exporting.</p>
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
        </ul>
      )}
    </section>
  );
}
