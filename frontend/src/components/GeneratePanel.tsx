// Generate step: prompt input, optional reference upload, pixel/hires toggle.
import { useEffect, useState } from "react";

import {
  generate,
  listAnimationOptions,
  type AnimationOptions,
  type Style,
  type ViewMode,
} from "../api/client";
import { useProjectStore } from "../state/project";
import { DirectionControls } from "./DirectionControls";
import { PromptEnhancer } from "./PromptEnhancer";

export function GeneratePanel() {
  const {
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
  } = useProjectStore();
  const [reference, setReference] = useState<File | null>(null);
  const [cameraOptions, setCameraOptions] = useState<AnimationOptions[]>([]);
  const [optionsError, setOptionsError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listAnimationOptions()
      .then(setCameraOptions)
      .catch(() => setOptionsError("Could not load camera options."));
  }, []);

  async function onGenerate() {
    if (!prompt.trim()) {
      setError("Enter a prompt first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await generate(prompt, style, reference, {
        viewMode,
        direction,
        enhancedPrompt: promptSource === "enhanced" ? enhancedPrompt : null,
      });
      setGenerated(result.project_id, result.sprite_url, prompt.trim());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Generation failed.");
    } finally {
      setBusy(false);
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
              name="style"
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
              name="view-mode"
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
      {optionsError && <p className="error">{optionsError}</p>}

      <PromptEnhancer />

      <label htmlFor="reference">Reference image (optional)</label>
      <input
        id="reference"
        type="file"
        accept="image/*"
        onChange={(e) => setReference(e.target.files?.[0] ?? null)}
      />

      <button onClick={onGenerate} disabled={busy || cameraOptions.length === 0}>
        {busy ? "Generating…" : "Generate sprite"}
      </button>

      {error && <p className="error">{error}</p>}

      {spriteUrl && (
        <div className="preview">
          <img src={spriteUrl} alt="Generated sprite" className="sprite" />
        </div>
      )}
    </section>
  );
}
