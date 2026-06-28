import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api and /uploads to Flask so `npm run dev` works
// against the live backend on :8093. Production build is served by Flask.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8093",
      "/uploads": "http://localhost:8093",
    },
  },
  build: { outDir: "dist" },
});
