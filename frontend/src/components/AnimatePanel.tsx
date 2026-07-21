// Animate step: pick an action preset + frame count, expand the base sprite
// into an animation, then preview it (AnimationPlayer) and clean up bad frames
// (FrameStrip). Presets come from the backend so adding one needs no UI change.
import { useEffect, useState } from "react";

import {
  animate,
  listAnimationOptions,
  listPresets,
  type AnimationOptions,
  type Preset,
} from "../api/client";
import { useProjectStore } from "../state/project";
import { AnimationPlayer } from "./AnimationPlayer";
import { DirectionControls, viewModeLabel } from "./DirectionControls";
import { FrameStrip } from "./FrameStrip";
import { ProviderSelector } from "./ProviderSelector";

export function AnimatePanel() {
  const {
    projectId,
    viewMode,
    direction,
    setDirection,
    setAnimation,
    action: currentAction,
    provider,
  } = useProjectStore();
  const [presets, setPresets] = useState<Preset[]>([]);
  const [cameraOptions, setCameraOptions] = useState<AnimationOptions[]>([]);
  const [action, setAction] = useState("walk");
  const [frames, setFrames] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listPresets()
      .then(setPresets)
      .catch(() => setError("Could not load presets."));
  }, []);

  useEffect(() => {
    listAnimationOptions()
      .then(setCameraOptions)
      .catch(() => setError("Could not load camera options."));
  }, []);

  const selected = presets.find((p) => p.action === action);

  async function onAnimate() {
    if (!projectId) return;
    setBusy(true);
    setError(null);
    try {
      const result = await animate(projectId, action, {
        frames: frames === "" ? null : frames,
        direction,
        provider,
      });
      setAnimation(
        result.action,
        result.fps,
        result.frames,
        result.direction,
        result.provider,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Animation failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <h2>2. Animate</h2>

      <div className="camera-context">
        <strong>{viewModeLabel(viewMode)} base sprite</strong>
        <span>Camera mode is fixed for this project. Generate a new base sprite to change it.</span>
      </div>

      <DirectionControls
        options={cameraOptions}
        viewMode={viewMode}
        direction={direction}
        onChange={setDirection}
      />

      <ProviderSelector id="animate-image-provider" />

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

      <button
        onClick={onAnimate}
        disabled={!projectId || busy || cameraOptions.length === 0}
      >
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
