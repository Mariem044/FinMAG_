import { defineConfig, loadEnv } from "vite";
import path from "node:path";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import tsconfigPaths from "vite-tsconfig-paths";
import { TanStackRouterVite } from "@tanstack/router-plugin/vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const devPort = Number(env.VITE_DEV_SERVER_PORT);
  const apiProxyTarget = env.VITE_API_PROXY_TARGET;

  if (!devPort) {
    throw new Error("VITE_DEV_SERVER_PORT is required in dashboard/frontend/.env");
  }
  if (!apiProxyTarget) {
    throw new Error("VITE_API_PROXY_TARGET is required in dashboard/frontend/.env");
  }

  return {
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
      port: devPort,
      strictPort: true,
      proxy: {
        "/api": {
          target: apiProxyTarget,
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
  };
});
