import { useEffect, useState } from "react";

import { enhancePrompt } from "../api/client";
import { useProjectStore } from "../state/project";

export function PromptEnhancer() {
  const {
    prompt,
    style,
    viewMode,
    direction,
    enhancedPrompt,
    promptSource,
    setEnhancedPrompt,
    acceptEnhancedPrompt,
    useRawPrompt,
  } = useProjectStore();
  const [enabled, setEnabled] = useState(promptSource === "enhanced");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (promptSource === "enhanced" && enhancedPrompt) setEnabled(true);
  }, [enhancedPrompt, promptSource]);

  async function onPreview() {
    if (!prompt.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const result = await enhancePrompt({
        prompt: prompt.trim(),
        style,
        view_mode: viewMode,
        direction,
      });
      setEnhancedPrompt(result.enhanced_prompt);
    } catch (reason) {
      useRawPrompt();
      setError(
        reason instanceof Error ? reason.message : "Prompt enhancement failed.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="prompt-enhancer">
      <label className="enhancer-toggle">
        <input
          type="checkbox"
          aria-label="Enhance my prompt"
          checked={enabled}
          onChange={(event) => {
            setEnabled(event.target.checked);
            setError(null);
            if (!event.target.checked) useRawPrompt();
          }}
        />
        <span>
          <strong>Enhance my prompt</strong>
          <small>Optional text-model preview. Nothing is rewritten silently.</small>
        </span>
      </label>

      {enabled && (
        <>
          <button
            type="button"
            className="secondary-button"
            onClick={onPreview}
            disabled={busy || !prompt.trim()}
          >
            {busy ? "Enhancing…" : "Preview enhanced prompt"}
          </button>

          {enhancedPrompt !== null && (
            <div className="enhancer-preview">
              <label htmlFor="enhanced-prompt">Enhanced prompt preview</label>
              <textarea
                id="enhanced-prompt"
                rows={5}
                value={enhancedPrompt}
                onChange={(event) => setEnhancedPrompt(event.target.value)}
              />
              <div className="enhancer-actions">
                <button
                  type="button"
                  onClick={acceptEnhancedPrompt}
                  disabled={!enhancedPrompt.trim()}
                >
                  Use enhanced prompt
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={useRawPrompt}
                >
                  Revert to original
                </button>
              </div>
              {promptSource === "enhanced" && (
                <p className="enhancer-accepted" role="status">
                  Enhanced prompt selected for generation.
                </p>
              )}
            </div>
          )}
          {error && <p className="error" role="alert">{error}</p>}
        </>
      )}
    </div>
  );
}
