import { useEffect, useRef, useCallback } from "react";

export type StreamEvent =
  | { type: "connected"; run_id: string }
  | { type: "heartbeat" }
  | {
      type: "event";
      id: number;
      seq: number;
      event_type: string;
      actor: string;
      summary: string;
      status: string | null;
      step_id: string | null;
      tool_name: string | null;
      timestamp: string;
    };

const RECONNECT_DELAYS = [1000, 2000, 5000, 10000, 15000];

export function useEventStream(
  runId: string | null,
  onEvent: (event: StreamEvent) => void
) {
  const esRef = useRef<EventSource | null>(null);
  const reconnectAttemptRef = useRef(0);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onEventRef = useRef(onEvent);

  onEventRef.current = onEvent;

  const connect = useCallback(() => {
    if (!runId || typeof EventSource === "undefined") return;

    const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
    const url = `${baseUrl}/api/runs/${runId}/events/stream`;

    const es = new EventSource(url);
    esRef.current = es;

    es.onopen = () => {
      reconnectAttemptRef.current = 0;
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
      const delay = RECONNECT_DELAYS[Math.min(reconnectAttemptRef.current, RECONNECT_DELAYS.length - 1)];
      reconnectAttemptRef.current += 1;
      timeoutRef.current = setTimeout(connect, delay);
    };
  }, [runId]);

  useEffect(() => {
    if (!runId) {
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      reconnectAttemptRef.current = 0;
      return;
    }

    connect();

    return () => {
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };
  }, [runId, connect]);
}
