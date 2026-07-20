// FrameStrip: thumbnails of the animation frames with a per-frame regenerate
// escape hatch (spec §4). Failed frames render a placeholder + regenerate
// button; the manual cleanup loop is the honest answer to imperfect frame
// consistency. Delete removes a frame from the working set locally.
import { useState } from "react";

import { regenerateFrame } from "../api/client";
import { useProjectStore } from "../state/project";

export function FrameStrip() {
  const { projectId, frames, setFrame, setAnimation, action, fps } = useProjectStore();
  const [busyIndex, setBusyIndex] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!projectId || frames.length === 0) return null;

  async function onRegenerate(index: number) {
    if (!projectId) return;
    setBusyIndex(index);
    setError(null);
    try {
      const frame = await regenerateFrame(projectId, index);
      setFrame(frame);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Regenerate failed.");
    } finally {
      setBusyIndex(null);
    }
  }

  function onDelete(index: number) {
    if (action === null) return;
    // Drop the frame and re-index the remainder so the strip stays contiguous.
    const remaining = frames
      .filter((f) => f.index !== index)
      .map((f, i) => ({ ...f, index: i }));
    setAnimation(action, fps, remaining);
  }

  return (
    <div className="frame-strip">
      <h3>Frames</h3>
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
                disabled={busyIndex === frame.index}
                aria-label={`Regenerate frame ${frame.index + 1}`}
              >
                {busyIndex === frame.index ? "…" : "Regenerate"}
              </button>
              <button
                type="button"
                onClick={() => onDelete(frame.index)}
                disabled={busyIndex !== null}
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
