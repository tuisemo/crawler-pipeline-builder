import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const legacyProxyKey = ["SEA", "DATA", "API", "PROXY", "TARGET"].join("_");
  const apiProxyTarget = env.CRAWLER_WORKFLOW_API_PROXY_TARGET || env[legacyProxyKey] || "http://127.0.0.1:8000";

  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 3101,
      strictPort: true,
      proxy: {
        "/api": {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
    },
    preview: {
      host: "127.0.0.1",
      port: 3101,
      strictPort: true,
    },
    build: {
      chunkSizeWarningLimit: 700,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes("node_modules")) {
              return undefined;
            }
            const packagePath = id.split("node_modules/")[1] || "";
            const packageName = packagePath.startsWith("@")
              ? packagePath.split("/").slice(0, 2).join("/")
              : packagePath.split("/")[0];
            if (id.includes("monaco-editor") || id.includes("@monaco-editor/react")) {
              return "monaco";
            }
            if (id.includes("@xyflow/react")) {
              return "reactflow";
            }
            if (packageName === "@ant-design/icons") {
              return "antd-icons";
            }
            if (packageName.startsWith("rc-")) {
              return `rc-${packageName.slice(3)}`;
            }
            if (packageName === "antd") {
              const antdMatch = packagePath.match(/^antd\/(?:es|lib)\/([^/]+)/);
              const componentName = antdMatch?.[1];
              if (componentName) {
                if (["form", "input", "input-number", "select", "checkbox", "radio", "switch"].includes(componentName)) {
                  return "antd-entry";
                }
                if (["table", "descriptions", "list"].includes(componentName)) {
                  return "antd-data";
                }
                if (["drawer", "collapse", "tabs", "segmented"].includes(componentName)) {
                  return "antd-panels";
                }
                if (["button", "card", "space", "tag", "tooltip", "typography", "spin", "alert", "result", "message"].includes(componentName)) {
                  return "antd-feedback";
                }
              }
              return "antd-core";
            }
            if (packageName === "@ant-design/colors" || packageName === "@ctrl/tinycolor") {
              return "antd-core";
            }
            if (id.includes("react") || id.includes("scheduler")) {
              return "react-vendor";
            }
            return "vendor";
          },
        },
      },
    },
  };
});
