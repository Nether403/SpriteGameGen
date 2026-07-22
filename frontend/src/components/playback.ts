// Pure playback timing math, separated from the canvas component so it can be
// unit-tested directly (spec §6 flags this as the frontend logic that matters).

// Which frame is showing at `elapsedMs` for a given `fps`, looping over
// `frameCount` frames. Frame 0 shows on [0, 1/fps), frame 1 on [1/fps, 2/fps),
// and so on, wrapping back to 0 after the last frame.
export function frameAt(elapsedMs: number, fps: number, frameCount: number): number {
  if (frameCount <= 0) return 0;
  if (fps <= 0 || elapsedMs <= 0) return 0;
  const msPerFrame = 1000 / fps;
  const raw = Math.floor(elapsedMs / msPerFrame);
  // Modulo that stays correct for any non-negative raw value.
  return raw % frameCount;
}

export function frameAtDurations(
  elapsedMs: number,
  durationsMs: number[],
  loop: boolean,
): number {
  if (durationsMs.length === 0) return 0;
  const safe = durationsMs.map((duration) => Math.max(1, duration));
  const total = safe.reduce((sum, duration) => sum + duration, 0);
  const position = loop
    ? ((Math.max(0, elapsedMs) % total) + total) % total
    : Math.min(Math.max(0, elapsedMs), total - 1);
  let cursor = 0;
  for (let index = 0; index < safe.length; index += 1) {
    cursor += safe[index];
    if (position < cursor) return index;
  }
  return safe.length - 1;
}
