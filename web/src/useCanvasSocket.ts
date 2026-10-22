// Owns the WebSocket to ws_server.py: verification, sending, and turning frames into chat state.
import { useCallback, useEffect, useReducer, useRef } from "react";
import { initialState, reducer } from "./chatState";
import type { ClientMessage, Course, ServerMessage } from "./protocol";

type Options = {
  endpoint: string;
  // Called when the socket closes; the page then asks Turnstile for a fresh token to reconnect with
  onClosed: () => void;
};

export function useCanvasSocket({ endpoint, onClosed }: Options) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const wsRef = useRef<WebSocket | null>(null);
  const onClosedRef = useRef(onClosed);
  onClosedRef.current = onClosed;

  // Re-rendering Markdown + math on every delta is wasteful; coalesce deltas to one update per frame.
  // Any other frame flushes first, so ordering is kept.
  const deltaBuffer = useRef("");
  const deltaFrame = useRef<number | null>(null);
  const flushDeltas = useCallback(() => {
    if (deltaFrame.current !== null) cancelAnimationFrame(deltaFrame.current);
    deltaFrame.current = null;
    if (deltaBuffer.current) {
      dispatch({ kind: "server", msg: { type: "delta", text: deltaBuffer.current } });
      deltaBuffer.current = "";
    }
  }, []);

  const send = useCallback((message: ClientMessage) => {
    const ws = wsRef.current;
    if (ws?.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify(message));
    return true;
  }, []);

  const connect = useCallback(
    (token: string) => {
      const current = wsRef.current;
      if (!token || (current && (current.readyState === WebSocket.OPEN || current.readyState === WebSocket.CONNECTING))) return;
      dispatch({ kind: "badge", text: "connecting…" });
      const ws = new WebSocket(endpoint);
      wsRef.current = ws;
      ws.onopen = () => {
        dispatch({ kind: "badge", text: "verifying…" });
        ws.send(JSON.stringify({ type: "verify", token } satisfies ClientMessage));
      };
      ws.onclose = () => {
        if (wsRef.current !== ws) return;
        deltaBuffer.current = "";
        flushDeltas();
        dispatch({ kind: "closed" });
        onClosedRef.current();
      };
      ws.onmessage = (event) => {
        let msg: ServerMessage;
        try {
          msg = JSON.parse(event.data);
        } catch {
          return;
        }
        if ("type" in msg && msg.type === "delta") {
          deltaBuffer.current += msg.text;
          deltaFrame.current ??= requestAnimationFrame(flushDeltas);
          return;
        }
        flushDeltas();
        dispatch({ kind: "server", msg });
        // Load the course list as soon as the connection is verified
        if ("status" in msg && msg.status === "verified") send({ type: "download" });
      };
    },
    [endpoint, flushDeltas, send],
  );

  useEffect(
    () => () => {
      const ws = wsRef.current;
      wsRef.current = null;
      ws?.close();
    },
    [],
  );

  return {
    state,
    connect,
    setBadge: useCallback((text: string) => dispatch({ kind: "badge", text }), []),
    sendChat: (text: string) => {
      if (state.pending || !state.connected || !send({ type: "chat", query: text })) return false;
      dispatch({ kind: "send", text });
      return true;
    },
    escalate: (messageId: number) => {
      if (state.pending || !state.connected || !send({ type: "escalate" })) return;
      dispatch({ kind: "escalate", messageId });
    },
    newChat: () => {
      if (state.pending || !state.connected || !send({ type: "reset" })) return;
      dispatch({ kind: "newChat" });
    },
    downloadCourses: (courses: Course[]) =>
      send({
        type: "download",
        auto_confirm: true,
        course_ids: courses.map((c) => c.id),
        course_indices: courses.map((c) => c.index),
      }),
  };
}
