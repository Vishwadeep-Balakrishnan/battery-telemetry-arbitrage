import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the dashboard talks to the backend through Vite's proxy, so
// the browser only ever sees one origin (same as behind nginx in Docker).
// Point BACKEND_URL elsewhere if the backend runs on another machine, e.g.
//   BACKEND_URL=http://raspberrypi.local:8000 npm run dev
const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  build: { chunkSizeWarningLimit: 800 }, // Recharts is most of the bundle; fine for a LAN dashboard
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": backend,
      "/health": backend,
      "/ws": { target: backend.replace(/^http/, "ws"), ws: true },
    },
  },
});
