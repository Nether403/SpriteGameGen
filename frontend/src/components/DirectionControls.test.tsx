import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DirectionControls } from "./DirectionControls";

const options = [
  { view_mode: "side_scroller" as const, directions: ["left", "right"] as const },
];

afterEach(cleanup);

describe("DirectionControls", () => {
  it("keeps separately rendered direction groups independent", () => {
    render(
      <>
        <DirectionControls
          options={options.map((option) => ({ ...option, directions: [...option.directions] }))}
          viewMode="side_scroller"
          direction="left"
          onChange={vi.fn()}
        />
        <DirectionControls
          options={options.map((option) => ({ ...option, directions: [...option.directions] }))}
          viewMode="side_scroller"
          direction="right"
          onChange={vi.fn()}
        />
      </>,
    );

    const left = screen.getAllByRole("radio", { name: "Left" });
    const right = screen.getAllByRole("radio", { name: "Right" });
    expect(left[0].getAttribute("name")).not.toBe(left[1].getAttribute("name"));
    expect((left[0] as HTMLInputElement).checked).toBe(true);
    expect((right[1] as HTMLInputElement).checked).toBe(true);

    fireEvent.click(right[1]);
    expect((left[0] as HTMLInputElement).checked).toBe(true);
  });
});
