import { describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useFlashOnChange } from "./useFlashOnChange";

describe("useFlashOnChange", () => {
  it("returns empty when value is unchanged", () => {
    const { result, rerender } = renderHook(({ v }) => useFlashOnChange(v), {
      initialProps: { v: 100 },
    });
    expect(result.current).toBe("");
    rerender({ v: 100 });
    expect(result.current).toBe("");
  });

  it("flashes up when value increases", () => {
    const { result, rerender } = renderHook(({ v }) => useFlashOnChange(v), {
      initialProps: { v: 100 },
    });
    rerender({ v: 101 });
    expect(result.current).toBe("flash-up");
  });

  it("flashes down when value decreases", () => {
    const { result, rerender } = renderHook(({ v }) => useFlashOnChange(v), {
      initialProps: { v: 100 },
    });
    rerender({ v: 99 });
    expect(result.current).toBe("flash-down");
  });

  it("clears the flash class after ~500ms", async () => {
    const { result, rerender } = renderHook(({ v }) => useFlashOnChange(v), {
      initialProps: { v: 100 },
    });
    rerender({ v: 105 });
    expect(result.current).toBe("flash-up");
    await act(
      () =>
        new Promise<void>((resolve) => {
          setTimeout(resolve, 550);
        }),
    );
    expect(result.current).toBe("");
  });
});
