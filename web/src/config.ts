// Build-time settings; see .env.example. The defaults are production's.
export const WS_ENDPOINT: string = import.meta.env.VITE_WS_ENDPOINT || "wss://canvas.marksong.tech/";
export const TURNSTILE_SITEKEY: string = import.meta.env.VITE_TURNSTILE_SITEKEY || "0x4AAAAAAFTnE5faRQhVop6D";
export const TURNSTILE_ACTION = "canvas_ws"; // must match the server's TURNSTILE_ACTION

export const GITHUB_URL = "https://github.com/MarkSong535/canvas_ai";

export const SUGGESTIONS = [
  "What courses am I in?",
  "Any upcoming assignments?",
  "Show my todo list",
  "Upcoming calendar events",
];
