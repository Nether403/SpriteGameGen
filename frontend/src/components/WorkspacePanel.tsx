import { useEffect, useState } from "react";

import {
  deleteClip,
  getProject,
  selectClip,
  setRenderSettings,
  updateClip,
  type RenderSettings,
} from "../api/client";
import { useProjectStore } from "../state/project";

export function WorkspacePanel() {
  const {
    projectId,
    clips,
    activeClipId,
    renderSettings,
    loadProject,
    mutation,
    beginMutation,
    endMutation,
  } = useProjectStore();
  const [settings, setSettings] = useState<RenderSettings>(renderSettings);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setSettings(renderSettings), [projectId, renderSettings]);

  if (!projectId) return null;

  async function refresh() {
    if (!projectId) return;
    loadProject(await getProject(projectId), projectId);
  }

  async function mutate(operation: () => Promise<unknown>) {
    if (!projectId) return;
    const token = beginMutation("workspace", projectId);
    if (token === null) return;
    setBusy(true);
    setError(null);
    try {
      await operation();
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Workspace update failed.");
    } finally {
      setBusy(false);
      endMutation(token);
    }
  }

  return (
    <section className="panel workspace-panel">
      <div>
        <p className="eyebrow">Character workspace</p>
        <h2>Clips &amp; local repair</h2>
      </div>

      {Object.keys(clips).length === 0 ? (
        <p className="hint">Generate an animation to create the first clip.</p>
      ) : (
        <ul className="clip-list" aria-label="Animation clips">
          {Object.values(clips).map((clip) => (
            <li key={clip.id} className={clip.id === activeClipId ? "clip-active" : ""}>
              <button
                type="button"
                className="clip-select"
                disabled={busy || mutation !== null || clip.id === activeClipId}
                onClick={() => mutate(() => selectClip(projectId, clip.id))}
              >
                <strong>{clip.name}</strong>
                <span>{clip.action} · {clip.frames.length} frames · {clip.fps} FPS</span>
              </button>
              <div className="clip-actions">
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy || mutation !== null}
                  onClick={() => {
                    const name = window.prompt("Clip name", clip.name)?.trim();
                    if (name) void mutate(() => updateClip(projectId, clip.id, { name }));
                  }}
                >Rename</button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy || mutation !== null}
                  onClick={() => mutate(() => updateClip(projectId, clip.id, { enabled: !clip.enabled }))}
                >{clip.enabled ? "Disable" : "Enable"}</button>
                <button
                  type="button"
                  className="danger-button"
                  disabled={busy || mutation !== null}
                  onClick={() => mutate(() => deleteClip(projectId, clip.id))}
                >Delete</button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <fieldset className="quality-grid" disabled={busy || mutation !== null}>
        <legend>Pixel quality</legend>
        <label htmlFor="target-width">Logical width</label>
        <input id="target-width" type="number" min={1} max={1024} value={settings.target_width ?? ""}
          onChange={(event) => setSettings({ ...settings, target_width: event.target.value ? Number(event.target.value) : null, target_height: event.target.value ? settings.target_height ?? Number(event.target.value) : null })} />
        <label htmlFor="target-height">Logical height</label>
        <input id="target-height" type="number" min={1} max={1024} value={settings.target_height ?? ""}
          onChange={(event) => setSettings({ ...settings, target_height: event.target.value ? Number(event.target.value) : null, target_width: event.target.value ? settings.target_width ?? Number(event.target.value) : null })} />
        <label htmlFor="output-scale">Output scale</label>
        <input id="output-scale" type="number" min={1} max={16} value={settings.output_scale}
          onChange={(event) => setSettings({ ...settings, output_scale: Number(event.target.value) })} />
        <label htmlFor="color-limit">Color limit</label>
        <input id="color-limit" type="number" min={1} max={256} value={settings.color_limit}
          onChange={(event) => setSettings({ ...settings, color_limit: Number(event.target.value) })} />
        <label htmlFor="palette-mode">Palette</label>
        <select id="palette-mode" value={settings.palette_mode}
          onChange={(event) => setSettings({ ...settings, palette_mode: event.target.value as RenderSettings["palette_mode"] })}>
          <option value="auto">Per-frame auto</option>
          <option value="shared_auto">Shared auto</option>
          <option value="preset">PICO-8 preset</option>
          <option value="custom">Custom</option>
        </select>
        {settings.palette_mode === "custom" && (
          <>
            <label htmlFor="custom-palette">Hex colors</label>
            <input id="custom-palette" type="text" value={settings.custom_palette.join(", ")}
              onChange={(event) => setSettings({ ...settings, custom_palette: event.target.value.split(",").map((value) => value.trim()).filter(Boolean) })} />
          </>
        )}
      </fieldset>
      <button type="button" disabled={busy || mutation !== null} onClick={() => mutate(() => setRenderSettings(projectId, {
        ...settings,
        preset_palette: settings.palette_mode === "preset" ? "pico8" : null,
      }))}>{busy ? "Applying…" : "Apply without provider calls"}</button>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}
