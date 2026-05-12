import { defineConfig } from "vite";
import path from "node:path";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import tsconfigPaths from "vite-tsconfig-paths";
import { TanStackRouterVite } from "@tanstack/router-plugin/vite";

export default defineConfig({
  resolve: {
    alias: {
      "@tanstack/react-table": path.resolve(
        "node_modules/@tanstack/react-table/build/lib/index.esm.js",
      ),
      "@tanstack/table-core": path.resolve(
        "node_modules/@tanstack/table-core/build/lib/index.esm.js",
      ),
    },
  },
  plugins: [
    TanStackRouterVite({ autoCodeSplitting: true }),
    react(),
    tailwindcss(),
    tsconfigPaths(),
  ],
  server: {
    port: 8080,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
    watch: {
      usePolling: true,
    },
  },
  optimizeDeps: {
    include: [
      "react",
      "react-dom",
      "react/jsx-runtime",
      "@tanstack/react-router",
      "lucide-react",
      "recharts",
      "zustand",
    ],
    force: false,
  },
  build: {
    target: "esnext",
  },
});
