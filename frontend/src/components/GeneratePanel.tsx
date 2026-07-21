// Generate step: prompt input, optional reference upload, pixel/hires toggle.
import { useEffect, useId, useRef, useState } from "react";

import {
  generate,
  isAbortError,
  listAnimationOptions,
  type AnimationOptions,
  type Style,
  type ViewMode,
} from "../api/client";
import { useProjectStore } from "../state/project";
import { DirectionControls } from "./DirectionControls";
import { PromptEnhancer } from "./PromptEnhancer";
import { ProviderSelector } from "./ProviderSelector";

export function GeneratePanel() {
  const {
    projectId,
    prompt,
    style,
    viewMode,
    direction,
    enhancedPrompt,
    promptSource,
    setPrompt,
    setStyle,
    setViewMode,
    setDirection,
    setGenerated,
    spriteUrl,
    provider,
    mutation,
    beginMutation,
    endMutation,
  } = useProjectStore();
  const [reference, setReference] = useState<File | null>(null);
  const [cameraOptions, setCameraOptions] = useState<AnimationOptions[]>([]);
  const [optionsError, setOptionsError] = useState<string | null>(null);
  const [optionsAttempt, setOptionsAttempt] = useState(0);
  const [optionsLoading, setOptionsLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestRef = useRef<AbortController | null>(null);
  const styleGroupName = `style-${useId()}`;
  const viewModeGroupName = `view-mode-${useId()}`;

  useEffect(() => {
    const controller = new AbortController();
    setOptionsLoading(true);
    setOptionsError(null);
    listAnimationOptions({ signal: controller.signal })
      .then(setCameraOptions)
      .catch((reason) => {
        if (!isAbortError(reason)) setOptionsError("Could not load camera options.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setOptionsLoading(false);
      });
    return () => controller.abort();
  }, [optionsAttempt]);

  useEffect(() => () => requestRef.current?.abort(), []);

  async function onGenerate() {
    if (!prompt.trim()) {
      setError("Enter a prompt first.");
      return;
    }
    const token = beginMutation("generate", projectId ?? null);
    if (token === null) return;
    const controller = new AbortController();
    requestRef.current = controller;
    const metadata = { enhancedPrompt, promptSource, style, viewMode, direction };
    setBusy(true);
    setError(null);
    try {
      const result = await generate(prompt, style, reference, {
        viewMode,
        direction,
        enhancedPrompt: promptSource === "enhanced" ? enhancedPrompt : null,
        provider,
        signal: controller.signal,
      });
      setGenerated(result.project_id, result.sprite_url, prompt.trim(), result.provider, metadata);
    } catch (e) {
      if (!isAbortError(e)) setError(e instanceof Error ? e.message : "Generation failed.");
    } finally {
      requestRef.current = null;
      setBusy(false);
      endMutation(token);
    }
  }

  return (
    <section className="panel">
      <h2>1. Generate</h2>
      <label htmlFor="prompt">Describe your sprite</label>
      <textarea
        id="prompt"
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="a knight with a sword"
        rows={3}
      />

      <fieldset className="style-toggle">
        <legend>Art style</legend>
        {(["pixel", "hires"] as Style[]).map((s) => (
          <label key={s}>
            <input
              type="radio"
              name={styleGroupName}
              value={s}
              checked={style === s}
              onChange={() => setStyle(s)}
            />
            {s === "pixel" ? "Pixel art" : "Hi-res"}
          </label>
        ))}
      </fieldset>

      <fieldset className="style-toggle camera-toggle">
        <legend>Game camera</legend>
        {cameraOptions.map((option) => (
          <label key={option.view_mode}>
            <input
              type="radio"
              name={viewModeGroupName}
              value={option.view_mode}
              checked={viewMode === option.view_mode}
              onChange={() => setViewMode(option.view_mode as ViewMode)}
            />
            {option.view_mode === "side_scroller"
              ? "Side-scroller"
              : "Top-down / 2.5D"}
          </label>
        ))}
      </fieldset>

      <DirectionControls
        options={cameraOptions}
        viewMode={viewMode}
        direction={direction}
        onChange={setDirection}
      />
      {optionsLoading && <p className="hint" role="status">Loading camera options…</p>}
      {optionsError && (
        <div className="metadata-error">
          <p className="error" role="alert">{optionsError}</p>
          <button type="button" className="secondary-button" onClick={() => setOptionsAttempt((value) => value + 1)}>
            Retry camera options
          </button>
        </div>
      )}

      <PromptEnhancer />

      <ProviderSelector id="generate-image-provider" disabled={mutation !== null} />

      <label htmlFor="reference">Reference image (optional)</label>
      <input
        id="reference"
        type="file"
        accept="image/*"
        onChange={(e) => setReference(e.target.files?.[0] ?? null)}
      />

      <button onClick={onGenerate} disabled={busy || mutation !== null || cameraOptions.length === 0}>
        {busy ? "Generating…" : "Generate sprite"}
      </button>

      {error && <p className="error" role="alert">{error}</p>}

      {spriteUrl && (
        <div className="preview">
          <img src={spriteUrl} alt="Generated sprite" className="sprite" />
        </div>
      )}
    </section>
  );
}
