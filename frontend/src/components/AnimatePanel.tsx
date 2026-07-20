// Animate step: pick an action preset + frame count, expand the base sprite
// into an animation, then preview it (AnimationPlayer) and clean up bad frames
// (FrameStrip). Presets come from the backend so adding one needs no UI change.
import { useEffect, useState } from "react";

import { animate, listPresets, type Preset } from "../api/client";
import { useProjectStore } from "../state/project";
import { AnimationPlayer } from "./AnimationPlayer";
import { FrameStrip } from "./FrameStrip";

export function AnimatePanel() {
  const { projectId, setAnimation, action: currentAction } = useProjectStore();
  const [presets, setPresets] = useState<Preset[]>([]);
  const [action, setAction] = useState("walk");
  const [frames, setFrames] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listPresets()
      .then(setPresets)
      .catch(() => setError("Could not load presets."));
  }, []);

  const selected = presets.find((p) => p.action === action);

  async function onAnimate() {
    if (!projectId) return;
    setBusy(true);
    setError(null);
    try {
      const result = await animate(projectId, action, {
        frames: frames === "" ? null : frames,
      });
      setAnimation(result.action, result.fps, result.frames);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Animation failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <h2>2. Animate</h2>

      <label htmlFor="action">Action</label>
      <select
        id="action"
        value={action}
        onChange={(e) => {
          setAction(e.target.value);
          setFrames("");
        }}
      >
        {presets.map((p) => (
          <option key={p.action} value={p.action}>
            {p.action}
          </option>
        ))}
      </select>

      {selected && (
        <>
          <label htmlFor="frames">
            Frames ({selected.min_frames}–{selected.max_frames}, default{" "}
            {selected.default_frames})
          </label>
          <input
            id="frames"
            type="number"
            min={selected.min_frames}
            max={selected.max_frames}
            value={frames}
            placeholder={String(selected.default_frames)}
            onChange={(e) =>
              setFrames(e.target.value === "" ? "" : Number(e.target.value))
            }
          />
        </>
      )}

      <button onClick={onAnimate} disabled={!projectId || busy}>
        {busy ? "Animating…" : "Generate animation"}
      </button>

      {!projectId && <p className="hint">Generate a sprite first.</p>}
      {error && <p className="error">{error}</p>}

      {currentAction && (
        <>
          <AnimationPlayer />
          <FrameStrip />
        </>
      )}
    </section>
  );
}
