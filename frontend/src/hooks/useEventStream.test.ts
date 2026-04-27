import { describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useEventStream } from "./useEventStream";

describe("useEventStream", () => {
  it("does nothing when runId is null", () => {
    const onEvent = vi.fn();
    const { unmount } = renderHook(() => useEventStream(null, onEvent));
    expect(onEvent).not.toHaveBeenCalled();
    unmount();
  });

  it("does nothing when EventSource is undefined", () => {
    const onEvent = vi.fn();
    const { unmount } = renderHook(() => useEventStream("run-1", onEvent));
    expect(onEvent).not.toHaveBeenCalled();
    unmount();
  });
});
