import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import basicSsl from "@vitejs/plugin-basic-ssl";

// Dev server proxies /api (HTTP + WebSocket) to the FastAPI backend.
// SONIC_LAN=1 serves over self-signed HTTPS on all interfaces so a phone on
// the same network can use its microphone (getUserMedia needs a secure context).
const lan = process.env.SONIC_LAN === "1";

export default defineConfig({
  plugins: [react(), ...(lan ? [basicSsl()] : [])],
  server: {
    port: 5173,
    host: lan ? "0.0.0.0" : "localhost",
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
