// FrameStrip: thumbnails of the animation frames with a per-frame regenerate
// escape hatch (spec §4). Failed frames render a placeholder + regenerate
// button; the manual cleanup loop is the honest answer to imperfect frame
// consistency. Delete removes the frame on the backend (re-indexing the rest)
// so it stays gone after reload.
import { useEffect, useRef, useState } from "react";

import { adjustFrame, isAbortError, regenerateFrame } from "../api/client";
import { useProjectStore } from "../state/project";

export function FrameStrip() {
  const {
    projectId,
    frames,
    setFrame,
    action,
    activeProject,
    activeClipId,
    mutation,
    beginMutation,
    endMutation,
  } = useProjectStore();
  const [busyIndex, setBusyIndex] = useState<number | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestRef = useRef<AbortController | null>(null);

  useEffect(() => () => requestRef.current?.abort(), []);

  if (!projectId || frames.length === 0) return null;

  const failedFrames = frames.filter((frame) => frame.status === "failed");
  const okCount = frames.length - failedFrames.length;

  async function onRegenerate(index: number) {
    if (!projectId || bulkBusy) return;
    const token = beginMutation("frame", projectId);
    if (token === null) return;
    const controller = new AbortController();
    requestRef.current = controller;
    setBusyIndex(index);
    setError(null);
    try {
      const frame = await regenerateFrame(
        projectId,
        index,
        activeProject?.provider,
        { signal: controller.signal, clipId: activeClipId },
      );
      setFrame(projectId, frame, activeClipId);
    } catch (e) {
      if (!isAbortError(e)) setError(e instanceof Error ? e.message : "Regenerate failed.");
    } finally {
      requestRef.current = null;
      setBusyIndex(null);
      endMutation(token);
    }
  }

  async function onAdjust(index: number, adjustment: Parameters<typeof adjustFrame>[3]) {
    if (!projectId || !activeClipId || action === null || bulkBusy) return;
    const token = beginMutation("frame", projectId);
    if (token === null) return;
    const controller = new AbortController();
    requestRef.current = controller;
    setBusyIndex(index);
    setError(null);
    try {
      const frame = await adjustFrame(projectId, activeClipId, index, adjustment);
      setFrame(projectId, frame, activeClipId);
    } catch (e) {
      if (!isAbortError(e)) setError(e instanceof Error ? e.message : "Repair failed.");
    } finally {
      requestRef.current = null;
      setBusyIndex(null);
      endMutation(token);
    }
  }

  async function onRegenerateFailed() {
    if (!projectId || bulkBusy) return;
    const token = beginMutation("frame", projectId);
    if (token === null) return;
    const targets = failedFrames.map((frame) => frame.index);
    setBulkBusy(true);
    setError(null);
    let failures = 0;
    for (const index of targets) {
      setBusyIndex(index);
      const controller = new AbortController();
      requestRef.current = controller;
      try {
        const frame = await regenerateFrame(
          projectId,
          index,
          activeProject?.provider,
          { signal: controller.signal, clipId: activeClipId },
        );
        setFrame(projectId, frame, activeClipId);
        if (frame.status === "failed") failures += 1;
      } catch (reason) {
        if (!isAbortError(reason)) failures += 1;
      }
    }
    requestRef.current = null;
    setBusyIndex(null);
    setBulkBusy(false);
    endMutation(token);
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
          <button type="button" onClick={onRegenerateFailed} disabled={bulkBusy || mutation !== null}>
            {bulkBusy
              ? `Regenerating frame ${busyIndex === null ? "" : busyIndex + 1}…`
              : "Regenerate failed frames"}
          </button>
        </div>
      )}
      <ul>
        {frames.map((frame) => (
          <li key={frame.index} className={`frame frame-${frame.status} ${frame.enabled === false ? "frame-disabled" : ""}`}>
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
                disabled={bulkBusy || mutation !== null || busyIndex === frame.index}
                aria-label={`Regenerate frame ${frame.index + 1}`}
              >
                {busyIndex === frame.index ? "…" : "Regenerate"}
              </button>
              <button
                type="button"
                onClick={() => onAdjust(frame.index, { enabled: frame.enabled === false })}
                disabled={bulkBusy || mutation !== null || busyIndex !== null}
                aria-label={`${frame.enabled === false ? "Enable" : "Disable"} frame ${frame.index + 1}`}
              >
                {frame.enabled === false ? "Enable" : "Disable"}
              </button>
              <div className="nudge-controls" aria-label={`Nudge frame ${frame.index + 1}`}>
                <button type="button" onClick={() => onAdjust(frame.index, { nudge_x: (frame.nudge_x ?? 0) - 1 })} disabled={mutation !== null}>←</button>
                <button type="button" onClick={() => onAdjust(frame.index, { nudge_y: (frame.nudge_y ?? 0) - 1 })} disabled={mutation !== null}>↑</button>
                <button type="button" onClick={() => onAdjust(frame.index, { nudge_y: (frame.nudge_y ?? 0) + 1 })} disabled={mutation !== null}>↓</button>
                <button type="button" onClick={() => onAdjust(frame.index, { nudge_x: (frame.nudge_x ?? 0) + 1 })} disabled={mutation !== null}>→</button>
              </div>
              <button type="button" onClick={() => onAdjust(frame.index, { reset: true })} disabled={mutation !== null}>Reset</button>
            </div>
          </li>
        ))}
      </ul>
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  );
}
