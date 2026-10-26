import { useEffect, useRef } from "react";

// The server sends each recorded event with its own type ("tool.succeeded", "run.completed"...)
// next to the two control messages below.
export type StreamEvent =
  | { type: "connected"; run_id: string }
  | { type: "heartbeat" }
  | {
      type: string;
      id: number;
      seq: number;
      actor: string;
      summary: string;
      status: string | null;
      step_id: string | null;
      tool_name: string | null;
      timestamp: string | null;
    };

const RECONNECT_DELAYS = [1000, 2000, 5000, 10000, 15000];

export function useEventStream(
  runId: string | null,
  onEvent: (event: StreamEvent) => void
) {
  const onEventRef = useRef(onEvent);

  // Keep the latest callback without reconnecting every time it changes.
  useEffect(() => {
    onEventRef.current = onEvent;
  });

  useEffect(() => {
    if (!runId || typeof EventSource === "undefined") return;

    const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
    const url = `${baseUrl}/api/runs/${runId}/events/stream`;
    let source: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let attempts = 0;

    function connect() {
      const es = new EventSource(url);
      source = es;

      es.onopen = () => {
        attempts = 0;
      };

      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data) as StreamEvent;
          onEventRef.current(data);
        } catch {
          // Ignore malformed events
        }
      };

      es.onerror = () => {
        es.close();
        const delay = RECONNECT_DELAYS[Math.min(attempts, RECONNECT_DELAYS.length - 1)];
        attempts += 1;
        timer = setTimeout(connect, delay);
      };
    }

    connect();

    return () => {
      source?.close();
      if (timer) clearTimeout(timer);
    };
  }, [runId]);
}
