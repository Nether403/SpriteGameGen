import { useId } from "react";

import type { AnimationOptions, Direction, ViewMode } from "../api/client";

const DIRECTION_LABELS: Record<Direction, string> = {
  left: "Left",
  right: "Right",
  up: "Up",
  down: "Down",
  up_left: "Up-left",
  up_right: "Up-right",
  down_left: "Down-left",
  down_right: "Down-right",
};

export function viewModeLabel(viewMode: ViewMode): string {
  return viewMode === "side_scroller" ? "Side-scroller" : "Top-down / 2.5D";
}

interface DirectionControlsProps {
  options: AnimationOptions[];
  viewMode: ViewMode;
  direction: Direction;
  onChange: (direction: Direction) => void;
}

export function DirectionControls({
  options,
  viewMode,
  direction,
  onChange,
}: DirectionControlsProps) {
  const groupName = useId();
  const allowed =
    options.find((option) => option.view_mode === viewMode)?.directions ?? [];

  return (
    <fieldset className="direction-controls">
      <legend>Facing / movement direction</legend>
      <div className="direction-grid">
        {allowed.map((value) => (
          <label key={value}>
            <input
              type="radio"
              name={`direction-${groupName}`}
              value={value}
              checked={direction === value}
              onChange={() => onChange(value)}
            />
            {DIRECTION_LABELS[value]}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
