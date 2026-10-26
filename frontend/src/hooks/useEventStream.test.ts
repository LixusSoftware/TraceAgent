import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useEventStream, type StreamEvent } from "./useEventStream";

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  url: string;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  close() {
    this.closed = true;
  }

  emit(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }
}

describe("useEventStream", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("does not connect without a run", () => {
    renderHook(() => useEventStream(null, () => {}));
    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it("delivers the events the server sends, with their own type", () => {
    const received: StreamEvent[] = [];
    renderHook(() => useEventStream("run-1", (event) => received.push(event)));

    const source = FakeEventSource.instances[0];
    expect(source.url).toContain("/api/runs/run-1/events/stream");
    source.emit({ type: "connected", run_id: "run-1" });
    source.emit({ id: 7, seq: 3, type: "tool.succeeded", summary: "done", tool_name: "get_weather" });

    expect(received.map((event) => event.type)).toEqual(["connected", "tool.succeeded"]);
  });

  it("ignores malformed messages", () => {
    const received: StreamEvent[] = [];
    renderHook(() => useEventStream("run-1", (event) => received.push(event)));

    FakeEventSource.instances[0].onmessage?.({ data: "not json" });

    expect(received).toHaveLength(0);
  });

  it("uses the latest callback without reconnecting", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(({ cb }) => useEventStream("run-1", cb), { initialProps: { cb: first } });

    rerender({ cb: second });
    FakeEventSource.instances[0].emit({ type: "heartbeat" });

    expect(FakeEventSource.instances).toHaveLength(1);
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });

  it("closes the stream when the run changes or the component unmounts", () => {
    const { rerender, unmount } = renderHook(({ id }) => useEventStream(id, () => {}), { initialProps: { id: "run-1" } });

    rerender({ id: "run-2" });
    expect(FakeEventSource.instances[0].closed).toBe(true);
    expect(FakeEventSource.instances[1].url).toContain("run-2");

    unmount();
    expect(FakeEventSource.instances[1].closed).toBe(true);
  });

  it("reconnects after an error, with a growing delay", () => {
    vi.useFakeTimers();
    renderHook(() => useEventStream("run-1", () => {}));

    FakeEventSource.instances[0].onerror?.();
    expect(FakeEventSource.instances[0].closed).toBe(true);
    expect(FakeEventSource.instances).toHaveLength(1);

    vi.advanceTimersByTime(1000);
    expect(FakeEventSource.instances).toHaveLength(2);

    FakeEventSource.instances[1].onerror?.();
    vi.advanceTimersByTime(1999);
    expect(FakeEventSource.instances).toHaveLength(2);
    vi.advanceTimersByTime(1);
    expect(FakeEventSource.instances).toHaveLength(3);
  });
});
