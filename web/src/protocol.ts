// Messages exchanged with ws_server.py over the WebSocket (one JSON object per message).

export type Course = { id: number | string; name?: string; index?: number };

// Snippet key ("I:"/"D:" + tex for inline/display math, "C:" + code for ```chemfig blocks) -> server-rendered SVG
export type Renders = Record<string, string>;

export type ClientMessage =
  | { type: "verify"; token: string }
  | { type: "chat"; query: string }
  | { type: "escalate" }
  | { type: "reset" }
  | { type: "download"; auto_confirm?: boolean; course_ids?: Course["id"][]; course_indices?: Course["index"][] };

// Frames streamed while an answer is being produced
export type StreamFrame =
  | { type: "tool"; name: string }
  | { type: "delta"; text: string }
  | { type: "retract" }
  | { type: "route"; tier: "simple" | "standard" | "hard" };

// Everything the server can send; replies are told apart by their fields, not always by `type`
export type ServerMessage =
  | StreamFrame
  | { type?: "answer"; answer: string; renders?: Renders; can_escalate?: boolean; tier?: string }
  | { status: "verified" | "reset" }
  | { status: "course_list"; courses: Course[] }
  | { status?: string; error: string };
