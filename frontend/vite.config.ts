import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

function getNodeModulePackageName(id: string): string | null {
  const normalized = id.replace(/\\/g, "/");
  const match = normalized.match(/node_modules\/(?:\.pnpm\/[^/]+\/node_modules\/)?((?:@[^/]+\/[^/]+)|[^/]+)/);
  return match?.[1] ?? null;
}

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
            const normalized = id.replace(/\\/g, "/");
            const packageName = getNodeModulePackageName(id);
            const packagePathMatch = normalized.match(/node_modules\/(?:\.pnpm\/[^/]+\/node_modules\/)?(.+)/);
            const packagePath = packagePathMatch?.[1] || "";
            if (normalized.includes("monaco-editor") || normalized.includes("@monaco-editor/react")) {
              return "monaco";
            }
            if (normalized.includes("@xyflow/react")) {
              return "reactflow";
            }
            if (!packageName) {
              return "vendor";
            }
            if (packageName === "@ant-design/icons") {
              return "antd-icons";
            }
            if (
              packageName === "@ant-design/cssinjs" ||
              packageName === "@ant-design/cssinjs-utils" ||
              packageName === "@babel/runtime" ||
              packageName === "@rc-component/util" ||
              packageName === "stylis" ||
              packageName === "csstype" ||
              packageName === "clsx"
            ) {
              return "antd-runtime";
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
            if (packageName === "react" || packageName === "react-dom" || packageName === "scheduler") {
              return "react-core";
            }
            if (packageName.startsWith("@rc-component/")) {
              return `rc-${packageName.split("/")[1]}`;
            }
            return "vendor";
          },
        },
      },
    },
  };
});
