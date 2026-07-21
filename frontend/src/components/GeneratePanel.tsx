// Generate step: prompt input, optional reference upload, pixel/hires toggle.
import { useState } from "react";

import { generate, type Style } from "../api/client";
import { useProjectStore } from "../state/project";

export function GeneratePanel() {
  const { prompt, style, setPrompt, setStyle, setGenerated, spriteUrl } = useProjectStore();
  const [reference, setReference] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onGenerate() {
    if (!prompt.trim()) {
      setError("Enter a prompt first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await generate(prompt, style, reference);
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

      <label htmlFor="reference">Reference image (optional)</label>
      <input
        id="reference"
        type="file"
        accept="image/*"
        onChange={(e) => setReference(e.target.files?.[0] ?? null)}
      />

      <button onClick={onGenerate} disabled={busy}>
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
