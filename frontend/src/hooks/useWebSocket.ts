/**
 * useWebSocket — persistent WebSocket connection to SentinelTwin backend.
 * Auto-reconnects with exponential backoff. Dispatches all frames to Zustand store.
 */

import { useEffect, useRef, useCallback } from "react";
import { useSentinelStore } from "../stores/sentinel.store";

const WS_URL = "ws://localhost:8000/ws/telemetry";
const MAX_RETRY_DELAY_MS = 30_000;

export type WSConnectionStatus = "CONNECTING" | "CONNECTED" | "DISCONNECTED" | "RECONNECTING";

export function useWebSocket() {
  const wsRef    = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout>>();
  const retryCount = useRef(0);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    useSentinelStore.getState().setWSStatus("CONNECTING");
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      retryCount.current = 0;
      useSentinelStore.getState().setWSStatus("CONNECTED");
    };

    ws.onmessage = (evt: MessageEvent) => {
      try {
        const frame = JSON.parse(evt.data as string);
        useSentinelStore.getState().handleWSFrame(frame);
      } catch {
        // malformed frame — ignore
      }
    };

    ws.onclose = () => {
      useSentinelStore.getState().setWSStatus("RECONNECTING");
      const delay = Math.min(1000 * Math.pow(2, retryCount.current), MAX_RETRY_DELAY_MS);
      retryCount.current += 1;
      retryRef.current = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(retryRef.current);
      wsRef.current?.close();
      useSentinelStore.getState().setWSStatus("DISCONNECTED");
    };
  }, [connect]);
}
