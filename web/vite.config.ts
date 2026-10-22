import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Relative asset paths, so the built dist/ can be hosted from any folder (like frontend/index.html is today)
export default defineConfig({
  plugins: [react()],
  base: "./",
  // KaTeX, marked, DOMPurify and React load together on first paint anyway (the old page pulled them from CDNs)
  build: { chunkSizeWarningLimit: 700 },
});
