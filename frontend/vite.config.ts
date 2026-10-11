import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // The dev server runs in the `web` container (compose.dev.yaml) next to `app`.
  server: {
    host: true,
    proxy: {
      "/api": "http://app:8080",
      "/healthz": "http://app:8080",
    },
  },
});
