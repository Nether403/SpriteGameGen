// Export step: choose atlas format, grid columns, and padding; pack + download
// the sheet and atlas.
import { useState } from "react";

import { exportProject, type ExportFormat } from "../api/client";
import { useProjectStore } from "../state/project";

export function ExportPanel() {
  const { projectId, frames, exportResult, setExport } = useProjectStore();
  const [format, setFormat] = useState<ExportFormat>("json");
  const [padding, setPadding] = useState(0);
  const [cols, setCols] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const failedCount = frames.filter((frame) => frame.status === "failed").length;
  const disabled = !projectId || busy || failedCount > 0;

  async function onExport() {
    if (!projectId) return;
    setBusy(true);
    setError(null);
    try {
      setExport(
        await exportProject(projectId, format, {
          padding,
          cols: cols === "" ? null : cols,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <h2>3. Export</h2>
      <label htmlFor="format">Atlas format</label>
      <select
        id="format"
        value={format}
        onChange={(e) => setFormat(e.target.value as ExportFormat)}
      >
        <option value="json">JSON</option>
        <option value="xml">XML</option>
      </select>

      <label htmlFor="cols">Columns (blank = single row)</label>
      <input
        id="cols"
        type="number"
        min={1}
        value={cols}
        placeholder="auto"
        onChange={(e) => setCols(e.target.value === "" ? "" : Number(e.target.value))}
      />

      <label htmlFor="padding">Padding (px between frames)</label>
      <input
        id="padding"
        type="number"
        min={0}
        value={padding}
        onChange={(e) => setPadding(Math.max(0, Number(e.target.value) || 0))}
      />

      <button onClick={onExport} disabled={disabled}>
        {busy ? "Packing…" : "Export sprite sheet"}
      </button>

      {!projectId && <p className="hint">Generate a sprite first.</p>}
      {projectId && failedCount > 0 && (
        <p className="hint">Regenerate or delete failed frames before exporting.</p>
      )}
      {error && <p className="error">{error}</p>}

      {exportResult && (
        <ul className="downloads">
          <li>
            <a href={exportResult.sheet_url} download>
              Download sheet (PNG)
            </a>
          </li>
          <li>
            <a href={exportResult.atlas_url} download>
              Download atlas ({format.toUpperCase()})
            </a>
          </li>
        </ul>
      )}
    </section>
  );
}
