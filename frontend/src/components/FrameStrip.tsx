// FrameStrip: thumbnails of the animation frames with a per-frame regenerate
// escape hatch (spec §4). Failed frames render a placeholder + regenerate
// button; the manual cleanup loop is the honest answer to imperfect frame
// consistency. Delete removes the frame on the backend (re-indexing the rest)
// so it stays gone after reload.
import { useState } from "react";

import { deleteFrame, regenerateFrame } from "../api/client";
import { useProjectStore } from "../state/project";

export function FrameStrip() {
  const { projectId, frames, setFrame, setAnimation, action, provider } = useProjectStore();
  const [busyIndex, setBusyIndex] = useState<number | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!projectId || frames.length === 0) return null;

  const failedFrames = frames.filter((frame) => frame.status === "failed");
  const okCount = frames.length - failedFrames.length;

  async function onRegenerate(index: number) {
    if (!projectId || bulkBusy) return;
    setBusyIndex(index);
    setError(null);
    try {
      const frame = await regenerateFrame(projectId, index, provider);
      setFrame(frame);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Regenerate failed.");
    } finally {
      setBusyIndex(null);
    }
  }

  async function onDelete(index: number) {
    if (!projectId || action === null || bulkBusy) return;
    setBusyIndex(index);
    setError(null);
    try {
      const result = await deleteFrame(projectId, index);
      setAnimation(result.action, result.fps, result.frames);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed.");
    } finally {
      setBusyIndex(null);
    }
  }

  async function onRegenerateFailed() {
    if (!projectId || bulkBusy) return;
    const targets = failedFrames.map((frame) => frame.index);
    setBulkBusy(true);
    setError(null);
    let failures = 0;
    for (const index of targets) {
      setBusyIndex(index);
      try {
        const frame = await regenerateFrame(projectId, index, provider);
        setFrame(frame);
        if (frame.status === "failed") failures += 1;
      } catch {
        failures += 1;
      }
    }
    setBusyIndex(null);
    setBulkBusy(false);
    if (failures > 0) {
      setError(`${failures} frame${failures === 1 ? "" : "s"} still failed.`);
    }
  }

  return (
    <div className="frame-strip">
      <h3>Frames</h3>
      {failedFrames.length > 0 && (
        <div className="failure-summary" role="status">
          <span>
            {okCount}/{frames.length} frames succeeded — {failedFrames.length} failed.
          </span>
          <button type="button" onClick={onRegenerateFailed} disabled={bulkBusy}>
            {bulkBusy
              ? `Regenerating frame ${busyIndex === null ? "" : busyIndex + 1}…`
              : "Regenerate failed frames"}
          </button>
        </div>
      )}
      <ul>
        {frames.map((frame) => (
          <li key={frame.index} className={`frame frame-${frame.status}`}>
            {frame.status === "ok" && frame.url ? (
              <img src={frame.url} alt={`Frame ${frame.index + 1}`} className="sprite" />
            ) : (
              <div className="frame-placeholder" role="img" aria-label={`Frame ${frame.index + 1} failed`}>
                ⚠︎
              </div>
            )}
            <span className="frame-index">#{frame.index + 1}</span>
            <div className="frame-actions">
              <button
                type="button"
                onClick={() => onRegenerate(frame.index)}
                disabled={bulkBusy || busyIndex === frame.index}
                aria-label={`Regenerate frame ${frame.index + 1}`}
              >
                {busyIndex === frame.index ? "…" : "Regenerate"}
              </button>
              <button
                type="button"
                onClick={() => onDelete(frame.index)}
                disabled={bulkBusy || busyIndex !== null}
                aria-label={`Delete frame ${frame.index + 1}`}
              >
                Delete
              </button>
            </div>
          </li>
        ))}
      </ul>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
