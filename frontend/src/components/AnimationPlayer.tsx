// AnimationPlayer: previews the animation by looping the OK frames on a canvas
// at a controllable FPS. Timing math lives in playback.ts (unit-tested); this
// component just wires it to requestAnimationFrame and draws the current frame.
import { useEffect, useRef, useState } from "react";

import { useProjectStore } from "../state/project";
import { frameAt } from "./playback";

const CANVAS_SIZE = 240;

export function AnimationPlayer() {
  const { frames, fps, setAnimation, action } = useProjectStore();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [playing, setPlaying] = useState(true);

  // Only OK frames are playable; their urls drive the drawn images.
  const okUrls = frames
    .filter((f) => f.status === "ok" && f.url)
    .map((f) => f.url as string);

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
      const index = frameAt(now - start, fps, okUrls.length);
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
  }, [playing, fps, okUrls.length, okUrls.join("|")]);

  if (frames.length === 0) return null;

  function onFps(next: number) {
    if (action !== null) setAnimation(action, next, frames);
  }

  return (
    <div className="animation-player">
      <h3>Preview</h3>
      {okUrls.length === 0 ? (
        <p className="hint">No playable frames yet.</p>
      ) : (
        <div className="preview">
          <canvas
            ref={canvasRef}
            width={CANVAS_SIZE}
            height={CANVAS_SIZE}
            className="sprite"
            aria-label="Animation preview"
          />
        </div>
      )}
      <div className="player-controls">
        <button type="button" onClick={() => setPlaying((p) => !p)}>
          {playing ? "Pause" : "Play"}
        </button>
        <label htmlFor="fps">FPS: {fps}</label>
        <input
          id="fps"
          type="range"
          min={1}
          max={24}
          value={fps}
          onChange={(e) => onFps(Number(e.target.value))}
        />
      </div>
    </div>
  );
}
