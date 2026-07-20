// Export step: choose atlas format, pack + download sheet and atlas.
import { useState } from "react";

import { exportProject, type ExportFormat } from "../api/client";
import { useProjectStore } from "../state/project";

export function ExportPanel() {
  const { projectId, exportResult, setExport } = useProjectStore();
  const [format, setFormat] = useState<ExportFormat>("json");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const disabled = !projectId || busy;

  async function onExport() {
    if (!projectId) return;
    setBusy(true);
    setError(null);
    try {
      setExport(await exportProject(projectId, format));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <h2>2. Export</h2>
      <label htmlFor="format">Atlas format</label>
      <select
        id="format"
        value={format}
        onChange={(e) => setFormat(e.target.value as ExportFormat)}
      >
        <option value="json">JSON</option>
        <option value="xml">XML</option>
      </select>

      <button onClick={onExport} disabled={disabled}>
        {busy ? "Packing…" : "Export sprite sheet"}
      </button>

      {!projectId && <p className="hint">Generate a sprite first.</p>}
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
