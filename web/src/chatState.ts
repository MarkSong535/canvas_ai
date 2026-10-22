// Chat state and the reducer that applies server frames and user actions to it.
import type { Course, Renders, ServerMessage } from "./protocol";

export type ChatMessage =
  | { id: number; role: "user"; text: string }
  | { id: number; role: "ai"; text: string; renders: Renders; canEscalate: boolean }
  | { id: number; role: "error"; text: string; count: number }
  | { id: number; role: "note"; text: string };

// The reply being streamed; `text` is empty until the first delta (typing dots show meanwhile)
export type Stream = { text: string; status: string };

export type ChatState = {
  connected: boolean;
  badge: string;
  pending: boolean;
  messages: ChatMessage[];
  stream: Stream | null;
  courses: Course[];
  coursesLoaded: boolean;
  courseError: boolean;
  nextId: number;
};

export const initialState: ChatState = {
  connected: false,
  badge: "verifying…",
  pending: false,
  messages: [],
  stream: null,
  courses: [],
  coursesLoaded: false,
  courseError: false,
  nextId: 1,
};

export type Action =
  | { kind: "server"; msg: ServerMessage }
  | { kind: "badge"; text: string }
  | { kind: "closed" }
  | { kind: "send"; text: string }
  | { kind: "escalate"; messageId: number }
  | { kind: "newChat" };

export function toolLabel(name: string): string {
  if (name.startsWith("vector_store")) return "Searching course files…";
  const topic = name
    .replace(/^canvas_/, "")
    .replace(/^(get|list|search)_/, "")
    .replace(/_/g, " ");
  return topic ? `Checking ${topic}…` : "Working…";
}

// A message before it gets its id (Omit applied to each member of the union)
type NewMessage = ChatMessage extends infer M ? (M extends ChatMessage ? Omit<M, "id"> : never) : never;

function push(state: ChatState, message: NewMessage): ChatState {
  return { ...state, messages: [...state.messages, { ...message, id: state.nextId } as ChatMessage], nextId: state.nextId + 1 };
}

// Repeated identical errors collapse into one message with a counter (until a user or AI message intervenes)
function pushError(state: ChatState, text: string): ChatState {
  const last = state.messages.findLast((m) => m.role !== "note");
  if (last?.role === "error" && last.text === text) {
    const bumped = { ...last, count: last.count + 1 };
    return { ...state, messages: state.messages.map((m) => (m === last ? bumped : m)) };
  }
  return push(state, { role: "error", text, count: 1 });
}

function withStream(state: ChatState, update: (s: Stream) => Stream): ChatState {
  return state.stream ? { ...state, stream: update(state.stream) } : state;
}

function applyServer(state: ChatState, msg: ServerMessage): ChatState {
  if ("status" in msg && msg.status === "verified") {
    // The server starts a fresh conversation for every connection
    const next = { ...state, connected: true, badge: "connected" };
    return state.messages.length ? push(next, { role: "note", text: "Reconnected · earlier messages are no longer in context" }) : next;
  }
  if ("status" in msg && msg.status === "reset") return state;
  if ("type" in msg) {
    switch (msg.type) {
      case "tool":
        return withStream(state, (s) => ({ ...s, status: toolLabel(String(msg.name ?? "")) }));
      case "delta":
        return withStream(state, (s) => ({ status: "", text: s.text + msg.text }));
      case "retract":
        return withStream(state, (s) => ({ ...s, text: "" }));
      case "route":
        return msg.tier === "hard" ? withStream(state, (s) => ({ ...s, status: "Reasoning carefully…" })) : state;
    }
  }
  if ("status" in msg && msg.status === "course_list" && "courses" in msg) {
    return { ...state, coursesLoaded: true, courseError: false, courses: Array.isArray(msg.courses) ? msg.courses : [] };
  }
  if ("answer" in msg && typeof msg.answer === "string") {
    // The streamed bubble settles into the final answer, now with the server's SVG renders
    const next = { ...state, stream: null, pending: false };
    return push(next, { role: "ai", text: msg.answer, renders: msg.renders ?? {}, canEscalate: !!msg.can_escalate });
  }
  if ("error" in msg && msg.error) {
    let next: ChatState = { ...state, stream: null, pending: false };
    if (msg.status === "course_list_error") next = { ...next, coursesLoaded: false, courses: [], courseError: true };
    return pushError(next, String(msg.error));
  }
  return state;
}

// An offer to retry with deeper reasoning only stands until the user moves on
const withoutOffers = (messages: ChatMessage[]) =>
  messages.map((m) => (m.role === "ai" && m.canEscalate ? { ...m, canEscalate: false } : m));

export function reducer(state: ChatState, action: Action): ChatState {
  switch (action.kind) {
    case "server":
      return applyServer(state, action.msg);
    case "badge":
      return { ...state, badge: action.text };
    case "closed":
      // A reply cut off by the disconnect is dropped; courses reload after the next verification
      return {
        ...state,
        connected: false,
        badge: "disconnected",
        pending: false,
        stream: null,
        courses: [],
        coursesLoaded: false,
        courseError: false,
      };
    case "send": {
      const next = push({ ...state, messages: withoutOffers(state.messages) }, { role: "user", text: action.text });
      return { ...next, pending: true, stream: { text: "", status: "" } };
    }
    case "escalate":
      // The retry replaces this attempt, as it does in the agent's memory
      return {
        ...state,
        messages: state.messages.filter((m) => m.id !== action.messageId),
        pending: true,
        stream: { text: "", status: "" },
      };
    case "newChat":
      return { ...state, messages: [], stream: null };
  }
}
