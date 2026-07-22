// Animate step: pick an action preset + frame count, expand the base sprite
// into an animation, then preview it (AnimationPlayer) and clean up bad frames
// (FrameStrip). Presets come from the backend so adding one needs no UI change.
import { useEffect, useRef, useState } from "react";

import {
  animate,
  isAbortError,
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
    activeProject,
    setActiveDirection,
    setActiveProvider,
    setAnimation,
    action: currentAction,
    mutation,
    beginMutation,
    endMutation,
  } = useProjectStore();
  const [presets, setPresets] = useState<Preset[]>([]);
  const [cameraOptions, setCameraOptions] = useState<AnimationOptions[]>([]);
  const [action, setAction] = useState("walk");
  const [frames, setFrames] = useState<number | "">("");
  const [createNew, setCreateNew] = useState(false);
  const [clipName, setClipName] = useState("");
  const [customMotion, setCustomMotion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [metadataAttempt, setMetadataAttempt] = useState(0);
  const [metadataLoading, setMetadataLoading] = useState(true);
  const requestRef = useRef<AbortController | null>(null);

  const viewMode = activeProject?.viewMode ?? "side_scroller";
  const direction = activeProject?.direction ?? "left";
  const provider = activeProject?.provider ?? "auto";

  useEffect(() => {
    const controller = new AbortController();
    setMetadataLoading(true);
    setError(null);
    Promise.all([
      listPresets({ signal: controller.signal }),
      listAnimationOptions({ signal: controller.signal }),
    ])
      .then(([nextPresets, nextOptions]) => {
        setPresets(nextPresets);
        setCameraOptions(nextOptions);
      })
      .catch((reason) => {
        if (!isAbortError(reason)) setError("Could not load animation options.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setMetadataLoading(false);
      });
    return () => controller.abort();
  }, [metadataAttempt]);

  useEffect(() => () => requestRef.current?.abort(), []);

  const selected = presets.find((p) => p.action === action);

  async function onAnimate() {
    if (!projectId) return;
    const token = beginMutation("animate", projectId);
    if (token === null) return;
    const controller = new AbortController();
    requestRef.current = controller;
    setBusy(true);
    setError(null);
    try {
      const result = await animate(projectId, action, {
        frames: frames === "" ? null : frames,
        direction,
        provider,
        signal: controller.signal,
        clipId: createNew ? crypto.randomUUID().replace(/-/g, "") : undefined,
        clipName: clipName.trim() || undefined,
        customMotion: customMotion.trim() || undefined,
      });
      setAnimation(
        projectId,
        result.action,
        result.fps,
        result.frames,
        result.direction,
        result.provider,
        result.clip_id,
      );
    } catch (e) {
      if (!isAbortError(e)) setError(e instanceof Error ? e.message : "Animation failed.");
    } finally {
      requestRef.current = null;
      setBusy(false);
      endMutation(token);
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
        onChange={setActiveDirection}
      />

      <ProviderSelector
        id="animate-image-provider"
        value={provider}
        onChange={setActiveProvider}
        disabled={mutation !== null}
      />

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

      <label className="inline-control">
        <input
          type="checkbox"
          checked={createNew}
          onChange={(event) => setCreateNew(event.target.checked)}
        />
        Preserve the current clip and create a new variant
      </label>
      <label htmlFor="clip-name">Clip name (optional)</label>
      <input
        id="clip-name"
        type="text"
        maxLength={100}
        value={clipName}
        placeholder="Walk - armored"
        onChange={(event) => setClipName(event.target.value)}
      />
      <label htmlFor="custom-motion">Custom motion (optional)</label>
      <textarea
        id="custom-motion"
        value={customMotion}
        placeholder="Describe a motion not covered by the selected action"
        onChange={(event) => setCustomMotion(event.target.value)}
      />

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
        disabled={!projectId || busy || mutation !== null || metadataLoading || cameraOptions.length === 0}
      >
        {busy ? "Animating…" : "Generate animation"}
      </button>

      {!projectId && <p className="hint">Generate a sprite first.</p>}
      {metadataLoading && <p className="hint" role="status">Loading animation options…</p>}
      {error && (
        <div className="metadata-error">
          <p className="error" role="alert">{error}</p>
          {!metadataLoading && presets.length === 0 && (
            <button type="button" className="secondary-button" onClick={() => setMetadataAttempt((value) => value + 1)}>
              Retry animation options
            </button>
          )}
        </div>
      )}

      {currentAction && (
        <>
          <AnimationPlayer />
          <FrameStrip />
        </>
      )}
    </section>
  );
}
