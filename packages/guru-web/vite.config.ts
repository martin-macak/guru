import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Pinned dev-server port, must match Makefile + guru-server-dev.
// When a new top-level API router prefix is added to guru-server, add it
// to SERVER_PREFIXES below so `npm run dev` can reach it.
const DEV_PORT = Number.parseInt(process.env.GURU_DEV_PORT ?? "8765", 10);

const SERVER_PREFIXES = [
  "/web",
  "/graph",
  "/documents",
  "/search",
  "/status",
  "/jobs",
  "/index",
  "/cache",
  "/sync",
];

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: Object.fromEntries(
      SERVER_PREFIXES.map((p) => [
        p,
        { target: `http://127.0.0.1:${DEV_PORT}`, changeOrigin: true },
      ]),
    ),
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
  },
});
