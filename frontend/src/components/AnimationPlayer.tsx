// AnimationPlayer: previews the animation by looping the OK frames on a canvas
// at a controllable FPS. Timing math lives in playback.ts (unit-tested); this
// component just wires it to requestAnimationFrame and draws the current frame.
import { useEffect, useRef, useState } from "react";

import { useProjectStore } from "../state/project";
import { frameAtDurations } from "./playback";

const CANVAS_SIZE = 240;

export function AnimationPlayer() {
  const { frames, fps, projectId, action, clips, activeClipId } = useProjectStore();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [playing, setPlaying] = useState(true);
  const [previewFps, setPreviewFps] = useState(fps);
  const [background, setBackground] = useState("checker");
  const activeClip = activeClipId ? clips[activeClipId] : undefined;

  useEffect(() => setPreviewFps(fps), [projectId, action, fps]);

  // Only OK frames are playable; their urls drive the drawn images.
  const playable = frames.filter((frame) => {
    const inLoop = !activeClip || (
      frame.index >= activeClip.loop_start
      && frame.index <= (activeClip.loop_end ?? frames.length - 1)
    );
    return inLoop && frame.enabled !== false && frame.status === "ok" && frame.url;
  });
  const okUrls = playable.map((frame) => frame.url as string);
  const durations = playable.map((frame) => {
    const persisted = frame.duration_ms ?? 1000 / fps;
    return persisted * (fps / previewFps);
  });

  // Preload frame images once per url set.
  const imagesRef = useRef<HTMLImageElement[]>([]);
  useEffect(() => {
    imagesRef.current = okUrls.map((url) => {
      const img = new Image();
      img.src = url;
      return img;
    });
  }, [okUrls.join("|")]);

  useEffect(() => {
    if (!playing || okUrls.length === 0) return;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    let raf = 0;
    let start = 0;
    const draw = (now: number) => {
      if (start === 0) start = now;
      const index = frameAtDurations(
        now - start,
        durations,
        (activeClip?.loop_mode ?? "loop") === "loop",
      );
      const img = imagesRef.current[index];
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      if (img && img.complete && img.naturalWidth > 0) {
        // Contain the frame within the canvas, preserving aspect ratio.
        const scale = Math.min(
          canvas.width / img.naturalWidth,
          canvas.height / img.naturalHeight,
        );
        const w = img.naturalWidth * scale;
        const h = img.naturalHeight * scale;
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(img, (canvas.width - w) / 2, (canvas.height - h) / 2, w, h);
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [playing, previewFps, activeClip?.loop_mode, okUrls.length, okUrls.join("|"), durations.join("|")]);

  if (frames.length === 0) return null;

  return (
    <div className="animation-player">
      <h3>Preview</h3>
      {okUrls.length === 0 ? (
        <p className="hint">No playable frames yet.</p>
      ) : (
        <div className={`preview preview-${background}`}>
          <canvas
            ref={canvasRef}
            width={CANVAS_SIZE}
            height={CANVAS_SIZE}
            className="sprite"
            role="img"
            aria-label="Animation preview"
          >
            Animation preview. Use the frame thumbnails below if canvas is unavailable.
          </canvas>
        </div>
      )}
      <div className="player-controls">
        <button type="button" onClick={() => setPlaying((p) => !p)}>
          {playing ? "Pause" : "Play"}
        </button>
        <label htmlFor="fps">Preview FPS: {previewFps}</label>
        <input
          id="fps"
          type="range"
          min={1}
          max={24}
          value={previewFps}
          onChange={(e) => setPreviewFps(Number(e.target.value))}
        />
      </div>
      <label htmlFor="preview-background">Preview background</label>
      <select id="preview-background" value={background} onChange={(event) => setBackground(event.target.value)}>
        <option value="checker">Checker</option>
        <option value="light">Light</option>
        <option value="dark">Dark</option>
        <option value="green">Green screen</option>
        <option value="magenta">Magenta screen</option>
      </select>
    </div>
  );
}
