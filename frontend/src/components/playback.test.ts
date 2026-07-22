// Playback timing-math tests (spec §6: "this one matters"). The frame index
// must advance correctly for a given fps/elapsed time and loop.
import { describe, expect, it } from "vitest";

import { frameAt, frameAtDurations } from "./playback";

describe("frameAt", () => {
  it("shows frame 0 at the start of the cycle", () => {
    expect(frameAt(0, 8, 6)).toBe(0);
    expect(frameAt(10, 8, 6)).toBe(0); // still within the first 125ms slot
  });

  it("advances one frame per 1/fps seconds", () => {
    // 8 fps => 125ms per frame
    expect(frameAt(125, 8, 6)).toBe(1);
    expect(frameAt(250, 8, 6)).toBe(2);
    expect(frameAt(249, 8, 6)).toBe(1); // just before the boundary
  });

  it("loops back to 0 after the last frame", () => {
    // 4 frames at 8fps => full cycle is 500ms
    expect(frameAt(500, 8, 4)).toBe(0);
    expect(frameAt(625, 8, 4)).toBe(1);
    expect(frameAt(1000, 8, 4)).toBe(0);
  });

  it("respects a different fps", () => {
    // 12 fps => ~83.33ms per frame
    expect(frameAt(83, 12, 6)).toBe(0);
    expect(frameAt(84, 12, 6)).toBe(1);
    expect(frameAt(1000, 12, 6)).toBe(0); // 12 frames elapsed % 6 == 0
  });

  it("guards degenerate inputs", () => {
    expect(frameAt(1000, 8, 0)).toBe(0);
    expect(frameAt(1000, 0, 6)).toBe(0);
    expect(frameAt(-50, 8, 6)).toBe(0);
  });
});

describe("frameAtDurations", () => {
  it("uses per-frame durations and loops deterministically", () => {
    expect(frameAtDurations(99, [100, 300], true)).toBe(0);
    expect(frameAtDurations(100, [100, 300], true)).toBe(1);
    expect(frameAtDurations(400, [100, 300], true)).toBe(0);
  });

  it("clamps once-mode playback to the final frame", () => {
    expect(frameAtDurations(10_000, [100, 100], false)).toBe(1);
  });
});
